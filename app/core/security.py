from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db)
) -> User:
    """Validate JWT token and return current user (401 if invalid)."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        hospital_id: str = payload.get("hospital_id")
        
        if user_id is None or hospital_id is None:
            raise credentials_exception
            
    except (JWTError, ValueError):
        raise credentials_exception
    
    # Fetch user from database
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    
    if user is None or not user.is_active:
        raise credentials_exception

    if str(user.hospital_id) != hospital_id:
        raise credentials_exception
        
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """Ensure user is active."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


class HospitalContext:
    """Encapsulates hospital_id and applies hospital isolation filters to queries."""
    
    def __init__(self, hospital_id: UUID):
        self.hospital_id = hospital_id
    
    def apply_isolation(self, query, model_class):
        """Apply hospital_id filter to a SQLAlchemy query."""
        return query.where(model_class.hospital_id == self.hospital_id)
    
    def verify_ownership(self, obj) -> bool:
        """Verify an object belongs to this hospital (raises HTTPException if not)."""
        if obj.hospital_id != self.hospital_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Object does not belong to your hospital"
            )
        return True


async def get_hospital_context(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> HospitalContext:
    """Dependency providing the current user's HospitalContext (core isolation mechanism)."""
    return HospitalContext(hospital_id=current_user.hospital_id)
