"""
Appointment Model
Patient appointments scoped per hospital (multi-tenant).
"""

from uuid import uuid4
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from enum import Enum as PyEnum

from sqlalchemy import String, DateTime, Boolean, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.hospital import Hospital
    from app.models.patient import Patient
    from app.models.user import User


class AppointmentStatus(str, PyEnum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Appointment(Base):
    """
    Appointment Model with mandatory hospital_id for tenant isolation.
    reminder_sent prevents duplicate 24-hour reminder emails.
    """

    __tablename__ = "appointments"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    hospital_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    patient_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    created_by_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    provider_name: Mapped[str] = mapped_column(String(200), nullable=False)
    appointment_type: Mapped[str] = mapped_column(String(100), nullable=False)

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )

    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus),
        default=AppointmentStatus.SCHEDULED,
        nullable=False,
        index=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Prevents duplicate reminder emails from the Beat task
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

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
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="appointments")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="appointments")
    created_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by_id],
        back_populates="appointments_created"
    )

    def __repr__(self) -> str:
        return f"<Appointment(id={self.id}, patient_id={self.patient_id}, scheduled_at={self.scheduled_at})>"
