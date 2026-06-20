from uuid import uuid4
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from enum import Enum as PyEnum

from sqlalchemy import String, DateTime, Boolean, ForeignKey, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.password import get_password_hash

if TYPE_CHECKING:
    from app.models.hospital import Hospital
    from app.models.pa_request import PARequest
    from app.models.appointment import Appointment


class UserRole(str, PyEnum):
    """User roles for RBAC."""
    ADMIN = "admin"
    DOCTOR = "doctor"
    NURSE = "nurse"
    STAFF = "staff"
    REVIEWER = "reviewer"


class User(Base):
    """User with mandatory hospital_id enforcing per-tenant isolation."""
    
    __tablename__ = "users"
    
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4
    )
    
    # Foreign key to hospital (isolation boundary)
    hospital_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True
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

    # Email verification
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    verification_token_expires: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Password reset
    reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    reset_token_expires: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Fraud / account lockout
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="users")
    pa_requests_created: Mapped[List["PARequest"]] = relationship(
        "PARequest",
        foreign_keys="PARequest.created_by_id",
        back_populates="created_by"
    )
    appointments_created: Mapped[List["Appointment"]] = relationship(
        "Appointment",
        foreign_keys="Appointment.created_by_id",
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