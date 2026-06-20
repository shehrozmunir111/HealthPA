"""
Authentication Endpoints — with email verification, password reset, and fraud detection.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import DbSession
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
    UnauthorizedException,
)
from app.core.logging import logger, security_logger
from app.core.password import get_password_hash, verify_password
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VERIFICATION_TTL_HOURS = 24
_RESET_TTL_HOURS = 1
_LOCKOUT_MINUTES = 30


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Schemas (auth-specific, kept inline to avoid over-engineering)
# ---------------------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login", description="OAuth2 password flow login.")
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
):
    """
    Authenticate user.
    Tracks failed attempts; locks account after FAILED_LOGIN_MAX_ATTEMPTS
    consecutive failures and fires a fraud-alert email to admin.
    """
    ip = _client_ip(request)
    security_logger.debug("Login attempt for %s from %s", form_data.username, ip)

    result = await db.execute(select(User).where(User.email == form_data.username))
    user: User | None = result.scalar_one_or_none()

    # --- account lockout check (before password verification) ---
    if user and user.locked_until:
        if user.locked_until > datetime.now(timezone.utc):
            raise BadRequestException(
                f"Account is temporarily locked. Try again after "
                f"{user.locked_until.strftime('%Y-%m-%d %H:%M UTC')}."
            )
        # Lock expired — reset counter
        user.failed_login_attempts = 0
        user.locked_until = None

    # --- credential verification ---
    if not user or not verify_password(form_data.password, user.hashed_password):
        security_logger.warning("Failed login for %s from %s", form_data.username, ip)

        if user:
            user.failed_login_attempts += 1

            if user.failed_login_attempts >= settings.FAILED_LOGIN_MAX_ATTEMPTS:
                locked_until = datetime.now(timezone.utc) + timedelta(minutes=_LOCKOUT_MINUTES)
                user.locked_until = locked_until
                await db.commit()

                # Fire fraud alert (non-blocking)
                try:
                    from app.tasks.email import send_fraud_alert
                    send_fraud_alert.delay(
                        user_email=user.email,
                        failed_attempts=user.failed_login_attempts,
                        ip_address=ip,
                        locked_until_iso=locked_until.isoformat(),
                    )
                except Exception:
                    logger.warning("Failed to queue fraud alert (Celery/Redis unavailable)")
                security_logger.warning(
                    "Account LOCKED for %s after %d failed attempts",
                    user.email, user.failed_login_attempts,
                )
                raise BadRequestException(
                    f"Too many failed attempts. Account locked for {_LOCKOUT_MINUTES} minutes."
                )

            await db.commit()

        raise UnauthorizedException("Incorrect email or password")

    # --- status checks ---
    if not user.is_active:
        raise BadRequestException("User account is inactive.")

    # --- success: reset failure counter, issue token ---
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "hospital_id": str(user.hospital_id),
            "role": user.role.value,
        },
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    security_logger.info("Successful login for %s", form_data.username)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "hospital_id": str(user.hospital_id),
    }


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: DbSession):
    """
    Register a new staff member.
    Sends a verification email via Celery (non-blocking).
    """
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise ConflictException(f"Email '{user_in.email}' is already registered.")

    verification_token = secrets.token_urlsafe(32)
    token_expires = datetime.now(timezone.utc) + timedelta(hours=_VERIFICATION_TTL_HOURS)

    user = User(
        email=user_in.email,
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        role=user_in.role,
        is_active=user_in.is_active,
        hospital_id=user_in.hospital_id,
        is_verified=False,
        verification_token=verification_token,
        verification_token_expires=token_expires,
    )
    user.set_password(user_in.password)

    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Send verification email (non-blocking, optional — Redis/Celery may not be running)
    try:
        from app.tasks.email import send_verification_email
        send_verification_email.delay(
            to_email=user.email,
            full_name=user.full_name,
            token=verification_token,
        )
    except Exception:
        logger.warning("Failed to queue verification email (Celery/Redis unavailable)")

    security_logger.info("New user registered: %s (hospital %s)", user.email, user.hospital_id)
    return user


@router.get("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(token: str, db: DbSession):
    """
    Verify a user's email address using the token from the verification email.
    The token is one-time-use and expires after 24 hours.
    """
    result = await db.execute(
        select(User).where(User.verification_token == token)
    )
    user: User | None = result.scalar_one_or_none()

    if not user:
        raise BadRequestException("Invalid or expired verification token.")

    if user.verification_token_expires and user.verification_token_expires < datetime.now(timezone.utc):
        raise BadRequestException("Verification token has expired. Please request a new one.")

    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    await db.commit()

    security_logger.info("Email verified for user %s", user.email)
    return {"message": "Email verified successfully. You can now log in."}


@router.post("/resend-verification", status_code=status.HTTP_200_OK)
async def resend_verification(body: ForgotPasswordRequest, db: DbSession):
    """
    Re-send a verification email. Always returns 200 to prevent email enumeration.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user: User | None = result.scalar_one_or_none()

    if user and not user.is_verified:
        token = secrets.token_urlsafe(32)
        user.verification_token = token
        user.verification_token_expires = datetime.now(timezone.utc) + timedelta(hours=_VERIFICATION_TTL_HOURS)
        await db.commit()

        try:
            from app.tasks.email import send_verification_email
            send_verification_email.delay(
                to_email=user.email,
                full_name=user.full_name,
                token=token,
            )
        except Exception:
            logger.warning("Failed to queue verification email (Celery/Redis unavailable)")

    return {"message": "If that email exists and is unverified, a new link has been sent."}


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(body: ForgotPasswordRequest, db: DbSession):
    """
    Initiate password reset. Always returns 200 to prevent email enumeration.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user: User | None = result.scalar_one_or_none()

    if user and user.is_active:
        reset_token = secrets.token_urlsafe(32)
        user.reset_token = reset_token
        user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=_RESET_TTL_HOURS)
        await db.commit()

        try:
            from app.tasks.email import send_password_reset_email
            send_password_reset_email.delay(
                to_email=user.email,
                full_name=user.full_name,
                token=reset_token,
            )
        except Exception:
            logger.warning("Failed to queue password reset email (Celery/Redis unavailable)")

    security_logger.info("Password reset requested for %s", body.email)
    return {"message": "If that email is registered, a password reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(body: ResetPasswordRequest, db: DbSession):
    """
    Complete password reset using the token from the reset email.
    """
    result = await db.execute(
        select(User).where(User.reset_token == body.token)
    )
    user: User | None = result.scalar_one_or_none()

    if not user:
        raise BadRequestException("Invalid or expired reset token.")

    if user.reset_token_expires and user.reset_token_expires < datetime.now(timezone.utc):
        raise BadRequestException("Reset token has expired. Please request a new one.")

    if len(body.new_password) < 8:
        raise BadRequestException("Password must be at least 8 characters.")

    user.set_password(body.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    # Clear any lockout on successful password reset
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.commit()

    security_logger.info("Password reset completed for user %s", user.email)
    return {"message": "Password has been reset successfully. You can now log in."}
