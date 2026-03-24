"""
Authentication Endpoints
Professional refactored version.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.core.logging import security_logger
from app.core.config import settings
from app.core.dependencies import DbSession
from app.core.exceptions import UnauthorizedException, ConflictException, BadRequestException
from app.core.security import create_access_token
from app.core.password import verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse

router = APIRouter()


@router.post("/login", description="Perform OAuth2 password flow login.")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession
):
    """
    Standardize OAuth2 login.
    RETURNS: Bearer JWT token valid for specified duration.
    """
    security_logger.debug(f"Attempting login for user: {form_data.username}")
    
    # 1. Identity Verification
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        security_logger.warning(f"Failed login attempt for user: {form_data.username}")
        raise UnauthorizedException("Incorrect email or password")
    
    # 2. Status Validation
    if not user.is_active:
        security_logger.warning(f"Login attempt for inactive user: {form_data.username}")
        raise BadRequestException("User account is inactive.")
    
    # 3. Token Issuance
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "hospital_id": str(user.hospital_id),
            "role": user.role.value
        },
        expires_delta=access_token_expires
    )
    
    security_logger.info(f"Successful login for user: {form_data.username}")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "hospital_id": str(user.hospital_id)
    }


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    db: DbSession
):
    """
    Onboard new staff members.
    Requires existing Hospital ID for tenant association.
    """
    # Duplicate check
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise ConflictException(f"Email '{user_in.email}' is already registered.")
    
    # New user instantiation
    user = User(
        email=user_in.email,
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        role=user_in.role,
        is_active=user_in.is_active,
        hospital_id=user_in.hospital_id
    )
    user.set_password(user_in.password)
    
    db.add(user)
    await db.flush()
    await db.refresh(user)
    
    security_logger.info(f"New user registered: {user_in.email} for hospital ID: {user_in.hospital_id}")
    
    return user