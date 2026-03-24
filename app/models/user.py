"""
User Model
Staff members belonging to a hospital. hospital_id enforces isolation.
"""

from uuid import uuid4
from datetime import datetime
from typing import TYPE_CHECKING, List
from enum import Enum as PyEnum

from sqlalchemy import String, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.security import get_password_hash

if TYPE_CHECKING:
    from app.models.hospital import Hospital
    from app.models.pa_request import PARequest


class UserRole(str, PyEnum):
    """User roles for RBAC."""
    ADMIN = "admin"
    DOCTOR = "doctor"
    NURSE = "nurse"
    STAFF = "staff"
    REVIEWER = "reviewer"


class User(Base):
    """
    User Model with mandatory hospital_id
    
    CONSTRAINT: Every user MUST belong to a hospital.
    This ensures Hospital A can NEVER access Hospital B's users.
    """
    
    __tablename__ = "users"
    
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4
    )
    
    # MANDATORY: Foreign key to hospital (isolation boundary)
    hospital_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True  # Index for fast filtering
    )
    
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Role-based access control
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), 
        default=UserRole.STAFF,
        nullable=False
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    last_login: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="users")
    pa_requests_created: Mapped[List["PARequest"]] = relationship(
        "PARequest", 
        foreign_keys="PARequest.created_by_id",
        back_populates="created_by"
    )
    
    def set_password(self, password: str) -> None:
        """Hash and set password."""
        self.hashed_password = get_password_hash(password)
    
    @property
    def full_name(self) -> str:
        """Return full name."""
        return f"{self.first_name} {self.last_name}"
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, hospital_id={self.hospital_id})>"