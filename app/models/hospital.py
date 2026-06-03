"""
Hospital Model
Top-level tenant entity. All other data belongs to a hospital.
"""

from uuid import uuid4
from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.patient import Patient
    from app.models.pa_request import PARequest
    from app.models.appointment import Appointment
    from app.models.audit_log import AuditLog


class Hospital(Base):
    """
    Hospital/Tenant Model
    
    This is the root of our multi-tenancy hierarchy.
    Every piece of data belongs to exactly one hospital.
    """
    
    __tablename__ = "hospitals"
    
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(500), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
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
    
    # Relationships
    users: Mapped[List["User"]] = relationship("User", back_populates="hospital")
    patients: Mapped[List["Patient"]] = relationship("Patient", back_populates="hospital")
    pa_requests: Mapped[List["PARequest"]] = relationship("PARequest", back_populates="hospital")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="hospital")
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="hospital")
    
    def __repr__(self) -> str:
        return f"<Hospital(id={self.id}, name={self.name}, code={self.code})>"