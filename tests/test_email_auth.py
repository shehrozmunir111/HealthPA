"""
Tests for AWS SES email features:
  - Email verification on signup
  - Password reset flow
  - Fraud / lockout detection
  - Appointment CRUD + reminder flag
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password import get_password_hash
from app.models.appointment import Appointment, AppointmentStatus
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def verified_user(db_session: AsyncSession, test_hospital: Hospital) -> User:
    """A fully verified, active user."""
    user = User(
        id=uuid4(),
        email="verified@test.com",
        hashed_password=get_password_hash("securepass123"),
        first_name="Vera",
        last_name="Verified",
        role=UserRole.STAFF,
        is_active=True,
        is_verified=True,
        hospital_id=test_hospital.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def unverified_user(db_session: AsyncSession, test_hospital: Hospital) -> User:
    """A user who has not yet verified their email."""
    token = secrets.token_urlsafe(32)
    user = User(
        id=uuid4(),
        email="unverified@test.com",
        hashed_password=get_password_hash("securepass123"),
        first_name="Una",
        last_name="Unverified",
        role=UserRole.STAFF,
        is_active=True,
        is_verified=False,
        verification_token=token,
        verification_token_expires=datetime.now(timezone.utc) + timedelta(hours=24),
        hospital_id=test_hospital.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def user_with_reset_token(db_session: AsyncSession, test_hospital: Hospital) -> User:
    """A user with a valid password reset token."""
    token = secrets.token_urlsafe(32)
    user = User(
        id=uuid4(),
        email="reset@test.com",
        hashed_password=get_password_hash("oldpassword123"),
        first_name="Res",
        last_name="Etter",
        role=UserRole.STAFF,
        is_active=True,
        is_verified=True,
        reset_token=token,
        reset_token_expires=datetime.now(timezone.utc) + timedelta(hours=1),
        hospital_id=test_hospital.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_appointment(
    db_session: AsyncSession,
    test_hospital: Hospital,
    test_patient: Patient,
    test_user: User,
) -> Appointment:
    appt = Appointment(
        id=uuid4(),
        hospital_id=test_hospital.id,
        patient_id=test_patient.id,
        created_by_id=test_user.id,
        provider_name="Dr. Smith",
        appointment_type="General Checkup",
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
        status=AppointmentStatus.SCHEDULED,
    )
    db_session.add(appt)
    await db_session.commit()
    await db_session.refresh(appt)
    return appt


# ---------------------------------------------------------------------------
# Registration + email verification
# ---------------------------------------------------------------------------

class TestRegisterSendsVerificationEmail:
    @patch("app.tasks.email.send_verification_email.delay")
    async def test_register_queues_verification_email(
        self, mock_delay: MagicMock, client: AsyncClient, test_hospital: Hospital
    ):
        payload = {
            "email": "newdoc@test.com",
            "password": "strongpass123",
            "first_name": "New",
            "last_name": "Doctor",
            "role": "doctor",
            "hospital_id": str(test_hospital.id),
        }
        resp = await client.post("/api/auth/register", json=payload)

        assert resp.status_code == 201
        mock_delay.assert_called_once()
        call_kwargs = mock_delay.call_args
        assert call_kwargs.kwargs["to_email"] == "newdoc@test.com"
        assert "token" in call_kwargs.kwargs

    @patch("app.tasks.email.send_verification_email.delay")
    async def test_register_duplicate_email_returns_409(
        self, _mock: MagicMock, client: AsyncClient, verified_user: User
    ):
        payload = {
            "email": verified_user.email,
            "password": "pass123456",
            "first_name": "Dup",
            "last_name": "User",
            "role": "staff",
            "hospital_id": str(verified_user.hospital_id),
        }
        resp = await client.post("/api/auth/register", json=payload)
        assert resp.status_code == 409


class TestEmailVerification:
    async def test_verify_valid_token(
        self, client: AsyncClient, unverified_user: User, db_session: AsyncSession
    ):
        token = unverified_user.verification_token
        resp = await client.get(f"/api/auth/verify-email?token={token}")

        assert resp.status_code == 200
        assert "verified" in resp.json()["message"].lower()

        await db_session.refresh(unverified_user)
        assert unverified_user.is_verified is True
        assert unverified_user.verification_token is None

    async def test_verify_invalid_token_returns_400(self, client: AsyncClient):
        resp = await client.get("/api/auth/verify-email?token=totally-invalid-token")
        assert resp.status_code == 400

    async def test_verify_expired_token_returns_400(
        self, client: AsyncClient, db_session: AsyncSession, test_hospital: Hospital
    ):
        expired_token = secrets.token_urlsafe(32)
        user = User(
            id=uuid4(),
            email="expired@test.com",
            hashed_password=get_password_hash("pass"),
            first_name="Ex",
            last_name="Pired",
            role=UserRole.STAFF,
            is_active=True,
            is_verified=False,
            verification_token=expired_token,
            verification_token_expires=datetime.now(timezone.utc) - timedelta(hours=1),
            hospital_id=test_hospital.id,
        )
        db_session.add(user)
        await db_session.commit()

        resp = await client.get(f"/api/auth/verify-email?token={expired_token}")
        assert resp.status_code == 400

    @patch("app.tasks.email.send_verification_email.delay")
    async def test_resend_verification(
        self, mock_delay: MagicMock, client: AsyncClient, unverified_user: User
    ):
        resp = await client.post(
            "/api/auth/resend-verification",
            json={"email": unverified_user.email},
        )
        assert resp.status_code == 200
        mock_delay.assert_called_once()

    @patch("app.tasks.email.send_verification_email.delay")
    async def test_resend_verification_unknown_email_returns_200(
        self, mock_delay: MagicMock, client: AsyncClient
    ):
        # Anti-enumeration: always 200 regardless of whether email exists
        resp = await client.post(
            "/api/auth/resend-verification",
            json={"email": "nobody@example.com"},
        )
        assert resp.status_code == 200
        mock_delay.assert_not_called()


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

class TestPasswordReset:
    @patch("app.tasks.email.send_password_reset_email.delay")
    async def test_forgot_password_queues_email(
        self, mock_delay: MagicMock, client: AsyncClient, verified_user: User
    ):
        resp = await client.post(
            "/api/auth/forgot-password",
            json={"email": verified_user.email},
        )
        assert resp.status_code == 200
        mock_delay.assert_called_once()
        assert mock_delay.call_args.kwargs["to_email"] == verified_user.email

    @patch("app.tasks.email.send_password_reset_email.delay")
    async def test_forgot_password_unknown_email_returns_200(
        self, mock_delay: MagicMock, client: AsyncClient
    ):
        resp = await client.post(
            "/api/auth/forgot-password",
            json={"email": "ghost@example.com"},
        )
        assert resp.status_code == 200
        mock_delay.assert_not_called()

    async def test_reset_password_valid_token(
        self,
        client: AsyncClient,
        user_with_reset_token: User,
        db_session: AsyncSession,
    ):
        token = user_with_reset_token.reset_token
        resp = await client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": "brandnewpass456"},
        )
        assert resp.status_code == 200

        await db_session.refresh(user_with_reset_token)
        assert user_with_reset_token.reset_token is None

    async def test_reset_password_invalid_token_returns_400(self, client: AsyncClient):
        resp = await client.post(
            "/api/auth/reset-password",
            json={"token": "bogus-token", "new_password": "newpass123"},
        )
        assert resp.status_code == 400

    async def test_reset_password_too_short_returns_400(
        self, client: AsyncClient, user_with_reset_token: User
    ):
        resp = await client.post(
            "/api/auth/reset-password",
            json={"token": user_with_reset_token.reset_token, "new_password": "short"},
        )
        assert resp.status_code == 400

    async def test_reset_password_expired_token_returns_400(
        self, client: AsyncClient, db_session: AsyncSession, test_hospital: Hospital
    ):
        token = secrets.token_urlsafe(32)
        user = User(
            id=uuid4(),
            email="oldreset@test.com",
            hashed_password=get_password_hash("pass"),
            first_name="Old",
            last_name="Reset",
            role=UserRole.STAFF,
            is_active=True,
            is_verified=True,
            reset_token=token,
            reset_token_expires=datetime.now(timezone.utc) - timedelta(minutes=1),
            hospital_id=test_hospital.id,
        )
        db_session.add(user)
        await db_session.commit()

        resp = await client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": "newpassword123"},
        )
        assert resp.status_code == 400

    async def test_can_login_after_reset(
        self,
        client: AsyncClient,
        user_with_reset_token: User,
    ):
        await client.post(
            "/api/auth/reset-password",
            json={
                "token": user_with_reset_token.reset_token,
                "new_password": "freshnewpass99",
            },
        )
        login_resp = await client.post(
            "/api/auth/login",
            data={
                "username": user_with_reset_token.email,
                "password": "freshnewpass99",
            },
        )
        assert login_resp.status_code == 200
        assert "access_token" in login_resp.json()


# ---------------------------------------------------------------------------
# Fraud / account lockout
# ---------------------------------------------------------------------------

class TestFraudDetection:
    @patch("app.tasks.email.send_fraud_alert.delay")
    async def test_account_locked_after_max_attempts(
        self,
        mock_fraud: MagicMock,
        client: AsyncClient,
        verified_user: User,
        db_session: AsyncSession,
    ):
        from app.core.config import settings

        for _ in range(settings.FAILED_LOGIN_MAX_ATTEMPTS):
            resp = await client.post(
                "/api/auth/login",
                data={"username": verified_user.email, "password": "wrongpass"},
            )

        # Last attempt should trigger lockout
        assert resp.status_code in (400, 401)
        mock_fraud.assert_called_once()

        fraud_call = mock_fraud.call_args.kwargs
        assert fraud_call["user_email"] == verified_user.email
        assert fraud_call["failed_attempts"] >= settings.FAILED_LOGIN_MAX_ATTEMPTS

    @patch("app.tasks.email.send_fraud_alert.delay")
    async def test_locked_account_cannot_login(
        self,
        _mock: MagicMock,
        client: AsyncClient,
        db_session: AsyncSession,
        test_hospital: Hospital,
    ):
        user = User(
            id=uuid4(),
            email="locked@test.com",
            hashed_password=get_password_hash("correctpass"),
            first_name="Lock",
            last_name="Down",
            role=UserRole.STAFF,
            is_active=True,
            is_verified=True,
            failed_login_attempts=5,
            locked_until=datetime.now(timezone.utc) + timedelta(minutes=30),
            hospital_id=test_hospital.id,
        )
        db_session.add(user)
        await db_session.commit()

        resp = await client.post(
            "/api/auth/login",
            data={"username": "locked@test.com", "password": "correctpass"},
        )
        assert resp.status_code == 400
        assert "locked" in resp.json()["message"].lower()

    async def test_failed_attempts_reset_on_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_hospital: Hospital,
    ):
        user = User(
            id=uuid4(),
            email="recovering@test.com",
            hashed_password=get_password_hash("rightpass"),
            first_name="Re",
            last_name="Cover",
            role=UserRole.STAFF,
            is_active=True,
            is_verified=True,
            failed_login_attempts=2,
            hospital_id=test_hospital.id,
        )
        db_session.add(user)
        await db_session.commit()

        resp = await client.post(
            "/api/auth/login",
            data={"username": "recovering@test.com", "password": "rightpass"},
        )
        assert resp.status_code == 200

        await db_session.refresh(user)
        assert user.failed_login_attempts == 0
        assert user.locked_until is None


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------

class TestAppointments:
    async def test_create_appointment(
        self,
        auth_client: AsyncClient,
        test_patient: Patient,
    ):
        payload = {
            "patient_id": str(test_patient.id),
            "provider_name": "Dr. Jones",
            "appointment_type": "Follow-up",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        }
        resp = await auth_client.post("/api/appointments/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider_name"] == "Dr. Jones"
        assert data["reminder_sent"] is False
        assert data["status"] == "scheduled"

    async def test_list_appointments(
        self,
        auth_client: AsyncClient,
        test_appointment: Appointment,
    ):
        resp = await auth_client.get("/api/appointments/")
        assert resp.status_code == 200
        ids = [a["id"] for a in resp.json()]
        assert str(test_appointment.id) in ids

    async def test_get_appointment(
        self,
        auth_client: AsyncClient,
        test_appointment: Appointment,
    ):
        resp = await auth_client.get(f"/api/appointments/{test_appointment.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(test_appointment.id)

    async def test_update_appointment(
        self,
        auth_client: AsyncClient,
        test_appointment: Appointment,
    ):
        resp = await auth_client.patch(
            f"/api/appointments/{test_appointment.id}",
            json={"status": "confirmed", "notes": "Patient confirmed via phone"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"
        assert resp.json()["notes"] == "Patient confirmed via phone"

    async def test_delete_appointment(
        self,
        auth_client: AsyncClient,
        test_appointment: Appointment,
    ):
        resp = await auth_client.delete(f"/api/appointments/{test_appointment.id}")
        assert resp.status_code == 204

        get_resp = await auth_client.get(f"/api/appointments/{test_appointment.id}")
        assert get_resp.status_code == 404

    async def test_cross_hospital_isolation(
        self,
        client: AsyncClient,
        test_appointment: Appointment,
        user_2_token: str,
    ):
        """Hospital B user cannot access Hospital A's appointments."""
        client.headers["Authorization"] = f"Bearer {user_2_token}"
        resp = await client.get(f"/api/appointments/{test_appointment.id}")
        assert resp.status_code == 403

    async def test_create_appointment_wrong_hospital_patient_returns_404(
        self,
        auth_client: AsyncClient,
        test_patient_2: Patient,
    ):
        """Patients from a different hospital cannot be booked by this hospital's users."""
        payload = {
            "patient_id": str(test_patient_2.id),
            "provider_name": "Dr. X",
            "appointment_type": "Consult",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        }
        resp = await auth_client.post("/api/appointments/", json=payload)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Email task unit tests (no SES/DB needed)
# ---------------------------------------------------------------------------

class TestEmailTaskUnit:
    def test_verification_html_contains_link(self):
        from app.tasks.email import _verification_html
        html = _verification_html("John Doe", "https://example.com/verify?token=abc123")
        assert "https://example.com/verify?token=abc123" in html
        assert "John Doe" in html

    def test_password_reset_html_contains_link(self):
        from app.tasks.email import _password_reset_html
        html = _password_reset_html("Jane Smith", "https://example.com/reset?token=xyz")
        assert "https://example.com/reset?token=xyz" in html
        assert "Jane Smith" in html

    def test_appointment_reminder_html_contains_provider(self):
        from app.tasks.email import _appointment_reminder_html
        dt = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
        html = _appointment_reminder_html("Bob Patient", "Dr. House", "MRI Scan", dt)
        assert "Dr. House" in html
        assert "MRI Scan" in html
        assert "Bob Patient" in html

    def test_fraud_alert_html_contains_email(self):
        from app.tasks.email import _fraud_alert_html
        locked = datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc)
        html = _fraud_alert_html("bad@test.com", 5, "1.2.3.4", locked)
        assert "bad@test.com" in html
        assert "1.2.3.4" in html

    @patch("app.tasks.email.boto3.client")
    def test_send_email_calls_ses(self, mock_boto_client: MagicMock):
        from app.tasks.email import send_email

        mock_ses = MagicMock()
        mock_ses.send_email.return_value = {"MessageId": "test-msg-id"}
        mock_boto_client.return_value = mock_ses

        with patch("app.tasks.email.settings") as mock_settings:
            mock_settings.AWS_ACCESS_KEY_ID = "FAKE_KEY"
            mock_settings.AWS_SECRET_ACCESS_KEY = "FAKE_SECRET"
            mock_settings.AWS_SES_REGION = "us-east-1"
            mock_settings.SES_SENDER_EMAIL = "noreply@example.com"

            result = send_email.run("to@example.com", "Test Subject", "<p>Hello</p>")

        assert result["status"] == "sent"
        assert result["message_id"] == "test-msg-id"
        mock_ses.send_email.assert_called_once()

    @patch("app.tasks.email.boto3.client")
    def test_send_email_skipped_when_not_configured(self, mock_boto_client: MagicMock):
        from app.tasks.email import send_email

        with patch("app.tasks.email.settings") as mock_settings:
            mock_settings.AWS_ACCESS_KEY_ID = ""
            mock_settings.SES_SENDER_EMAIL = ""

            result = send_email.run("to@example.com", "Subject", "<p>body</p>")

        assert result["status"] == "skipped"
        mock_boto_client.assert_not_called()
