from uuid import uuid4
from datetime import datetime, date
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, DateTime, Date, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")

if TYPE_CHECKING:
    from app.models.hospital import Hospital
    from app.models.pa_request import PARequest
    from app.models.appointment import Appointment


class Patient(Base):
    """Patient model isolated to a single hospital (no cross-hospital access)."""
    
    __tablename__ = "patients"
    
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    
    # MANDATORY: Hospital isolation
    hospital_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Patient demographics (HIPAA protected)
    mrn: Mapped[str] = mapped_column(String(50), nullable=False)  # Medical Record Number
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Insurance info
    insurance_provider: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    insurance_policy_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    insurance_group_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Additional metadata (flexible JSON storage)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    
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
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="patients")
    pa_requests: Mapped[List["PARequest"]] = relationship("PARequest", back_populates="patient")
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="patient")
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self) -> int:
        """Calculate age from DOB."""
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
    
    def __repr__(self) -> str:
        return f"<Patient(id={self.id}, mrn={self.mrn}, hospital_id={self.hospital_id})>"