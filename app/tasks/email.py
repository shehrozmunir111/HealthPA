import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError
from celery import shared_task
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logger = logging.getLogger("healthpa.email")

# Sync DB engine — used only inside Celery tasks (no asyncio event loop)
_sync_engine = None
_SyncSession = None


def _get_sync_session():
    global _sync_engine, _SyncSession
    if _SyncSession is None:
        _sync_engine = create_engine(
            settings.sync_database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _SyncSession = sessionmaker(_sync_engine, autocommit=False, autoflush=False)
    return _SyncSession()


# HTML email templates

def _base_template(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f4f6f9; margin: 0; padding: 0; }}
    .wrapper {{ max-width: 600px; margin: 40px auto; background: #ffffff;
               border-radius: 8px; overflow: hidden;
               box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
    .header  {{ background: #1a56db; padding: 28px 32px; color: #fff; }}
    .header h1 {{ margin: 0; font-size: 22px; font-weight: 600; }}
    .body    {{ padding: 32px; color: #374151; line-height: 1.6; }}
    .body p  {{ margin: 0 0 16px; }}
    .btn     {{ display: inline-block; padding: 12px 28px; background: #1a56db;
               color: #fff !important; text-decoration: none; border-radius: 6px;
               font-weight: 600; font-size: 15px; margin: 8px 0 24px; }}
    .footer  {{ background: #f9fafb; border-top: 1px solid #e5e7eb;
               padding: 20px 32px; font-size: 12px; color: #9ca3af; }}
    .alert   {{ background: #fef2f2; border-left: 4px solid #ef4444;
               padding: 12px 16px; border-radius: 4px; margin-bottom: 20px; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header"><h1>HealthPA</h1></div>
    <div class="body">{body}</div>
    <div class="footer">
      &copy; {datetime.utcnow().year} HealthPA. This is an automated message — please do not reply.
    </div>
  </div>
</body>
</html>"""


def _verification_html(full_name: str, verify_url: str) -> str:
    body = f"""
<p>Hi {full_name},</p>
<p>Welcome to HealthPA! Please verify your email address to activate your account.</p>
<p><a class="btn" href="{verify_url}">Verify Email Address</a></p>
<p>This link expires in <strong>24 hours</strong>. If you did not create an account, you can safely ignore this email.</p>
"""
    return _base_template("Verify your HealthPA email", body)


def _password_reset_html(full_name: str, reset_url: str) -> str:
    body = f"""
<p>Hi {full_name},</p>
<p>We received a request to reset your HealthPA password.</p>
<p><a class="btn" href="{reset_url}">Reset Password</a></p>
<p>This link expires in <strong>1 hour</strong>. If you did not request a password reset, please ignore this email — your password will remain unchanged.</p>
"""
    return _base_template("Reset your HealthPA password", body)


def _appointment_reminder_html(
    patient_name: str,
    provider_name: str,
    appointment_type: str,
    scheduled_at: datetime,
) -> str:
    formatted_dt = scheduled_at.strftime("%A, %B %d %Y at %I:%M %p UTC")
    body = f"""
<p>Dear {patient_name},</p>
<p>This is a friendly reminder of your upcoming appointment:</p>
<table style="border-collapse:collapse;width:100%;margin-bottom:20px">
  <tr><td style="padding:8px;border:1px solid #e5e7eb;font-weight:600">Type</td>
      <td style="padding:8px;border:1px solid #e5e7eb">{appointment_type}</td></tr>
  <tr><td style="padding:8px;border:1px solid #e5e7eb;font-weight:600">Provider</td>
      <td style="padding:8px;border:1px solid #e5e7eb">{provider_name}</td></tr>
  <tr><td style="padding:8px;border:1px solid #e5e7eb;font-weight:600">Date &amp; Time</td>
      <td style="padding:8px;border:1px solid #e5e7eb">{formatted_dt}</td></tr>
</table>
<p>If you need to reschedule or cancel, please contact us as soon as possible.</p>
"""
    return _base_template("Appointment Reminder — HealthPA", body)


def _fraud_alert_html(
    user_email: str,
    failed_attempts: int,
    ip_address: str,
    locked_until: datetime,
) -> str:
    locked_str = locked_until.strftime("%Y-%m-%d %H:%M UTC")
    body = f"""
<div class="alert">
  <strong>Security Alert:</strong> An account has been locked due to repeated failed login attempts.
</div>
<p><strong>Account:</strong> {user_email}</p>
<p><strong>Failed attempts:</strong> {failed_attempts}</p>
<p><strong>Source IP:</strong> {ip_address}</p>
<p><strong>Account locked until:</strong> {locked_str}</p>
<p>Please review this activity in the HealthPA admin panel and take appropriate action if the login attempts appear malicious.</p>
"""
    return _base_template("HealthPA Security Alert — Account Locked", body)


# Core send task

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="app.tasks.email.send_email",
)
def send_email(self, to_email: str, subject: str, html_body: str) -> dict:
    """Send an HTML email via AWS SES, retrying up to 3 times on transient errors."""
    if not settings.AWS_ACCESS_KEY_ID or not settings.SES_SENDER_EMAIL:
        logger.warning("SES not configured — email to %s skipped", to_email)
        return {"status": "skipped", "reason": "SES not configured"}

    client = boto3.client(
        "ses",
        region_name=settings.AWS_SES_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
    try:
        response = client.send_email(
            Source=settings.SES_SENDER_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html_body, "Charset": "UTF-8"}},
            },
        )
        logger.info("Email sent to %s | MessageId=%s", to_email, response["MessageId"])
        return {"status": "sent", "message_id": response["MessageId"]}
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        logger.error("SES error (%s) sending to %s: %s", error_code, to_email, exc)
        raise self.retry(exc=exc)


# High-level helpers (thin wrappers that build HTML and call send_email)

@shared_task(name="app.tasks.email.send_verification_email")
def send_verification_email(to_email: str, full_name: str, token: str) -> None:
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    html = _verification_html(full_name, verify_url)
    send_email.delay(to_email, "Verify your HealthPA email address", html)


@shared_task(name="app.tasks.email.send_password_reset_email")
def send_password_reset_email(to_email: str, full_name: str, token: str) -> None:
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    html = _password_reset_html(full_name, reset_url)
    send_email.delay(to_email, "Reset your HealthPA password", html)


@shared_task(name="app.tasks.email.send_appointment_reminder")
def send_appointment_reminder(
    to_email: str,
    patient_name: str,
    provider_name: str,
    appointment_type: str,
    scheduled_at_iso: str,
) -> None:
    scheduled_at = datetime.fromisoformat(scheduled_at_iso)
    html = _appointment_reminder_html(patient_name, provider_name, appointment_type, scheduled_at)
    send_email.delay(to_email, "Appointment Reminder — HealthPA", html)


@shared_task(name="app.tasks.email.send_fraud_alert")
def send_fraud_alert(
    user_email: str,
    failed_attempts: int,
    ip_address: str,
    locked_until_iso: str,
) -> None:
    if not settings.ADMIN_EMAIL:
        logger.warning("ADMIN_EMAIL not set — fraud alert skipped for %s", user_email)
        return
    locked_until = datetime.fromisoformat(locked_until_iso)
    html = _fraud_alert_html(user_email, failed_attempts, ip_address, locked_until)
    send_email.delay(
        settings.ADMIN_EMAIL,
        f"Security Alert: Account locked — {user_email}",
        html,
    )


# Celery Beat task — runs every hour, sends 24-hour appointment reminders

@shared_task(name="app.tasks.email.send_appointment_reminders")
def send_appointment_reminders() -> dict:
    """Hourly Beat task: send reminders for appointments ~24h out and mark reminder_sent to avoid duplicates."""
    from app.models.appointment import Appointment, AppointmentStatus
    from app.models.patient import Patient

    now = datetime.now(timezone.utc)
    window_start = now + timedelta(hours=23, minutes=55)
    window_end = now + timedelta(hours=24, minutes=5)

    sent_count = 0
    skipped_count = 0

    with _get_sync_session() as session:
        stmt = (
            select(Appointment)
            .where(
                Appointment.scheduled_at >= window_start,
                Appointment.scheduled_at <= window_end,
                Appointment.reminder_sent.is_(False),
                Appointment.status == AppointmentStatus.SCHEDULED,
            )
        )
        appointments = session.execute(stmt).scalars().all()

        for appt in appointments:
            patient = session.get(Patient, appt.patient_id)
            if patient and patient.email:
                send_appointment_reminder.delay(
                    to_email=patient.email,
                    patient_name=patient.full_name,
                    provider_name=appt.provider_name,
                    appointment_type=appt.appointment_type,
                    scheduled_at_iso=appt.scheduled_at.isoformat(),
                )
                appt.reminder_sent = True
                sent_count += 1
            else:
                skipped_count += 1

        session.commit()

    logger.info(
        "Appointment reminders: sent=%d skipped=%d (window %s – %s)",
        sent_count, skipped_count, window_start.isoformat(), window_end.isoformat(),
    )
    return {"sent": sent_count, "skipped": skipped_count}
