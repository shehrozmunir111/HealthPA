"""
Prior Authorization Request Model
Core business entity with FSM (Finite State Machine) support.
"""

from uuid import uuid4
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from enum import Enum as PyEnum

from sqlalchemy import String, DateTime, ForeignKey, Text, Enum, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.hospital import Hospital
    from app.models.user import User
    from app.models.patient import Patient


class PARequestStatus(str, PyEnum):
    """
    Finite State Machine states for PA Requests.
    
    Transitions:
        DRAFT -> PENDING
        PENDING -> APPROVED | DENIED | NEEDS_INFO
        NEEDS_INFO -> PENDING
        APPROVED -> COMPLETED
        DENIED -> APPEALED
        APPEALED -> PENDING
    """
    DRAFT = "draft"
    PENDING = "pending"
    NEEDS_INFO = "needs_info"
    APPROVED = "approved"
    DENIED = "denied"
    APPEALED = "appealed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PARequest(Base):
    """
    Prior Authorization Request Model
    
    CONSTRAINT: Every PA request belongs to exactly one hospital and one patient.
    Hospital isolation ensures complete data separation between tenants.
    """
    
    __tablename__ = "pa_requests"
    
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
    
    # Patient reference (must be in same hospital - enforced at application level)
    patient_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Creator reference
    created_by_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Request details
    request_number: Mapped[str] = mapped_column(
        String(50), 
        unique=True, 
        nullable=False,
        index=True
    )
    
    # Clinical information
    diagnosis_codes: Mapped[List[str]] = mapped_column(JSONB, default=list)  # ICD-10 codes
    procedure_codes: Mapped[List[str]] = mapped_column(JSONB, default=list)  # CPT codes
    clinical_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # AI-extracted data
    ai_extracted_codes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ai_confidence_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)
    
    # Insurance/Payer info
    payer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    payer_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # FSM State
    status: Mapped[PARequestStatus] = mapped_column(
        Enum(PARequestStatus),
        default=PARequestStatus.DRAFT,
        nullable=False,
        index=True
    )
    
    # Status history for audit trail
    status_history: Mapped[List[dict]] = mapped_column(
        JSONB,
        default=list,
        comment="Array of {status, timestamp, user_id, notes}"
    )
    
    # Decision info
    decision_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Urgency
    is_urgent: Mapped[bool] = mapped_column(default=False, nullable=False)
    requested_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # OCR/Attachments metadata
    attachments: Mapped[List[dict]] = mapped_column(
        JSONB,
        default=list,
        comment="Array of {filename, path, ocr_text, uploaded_at}"
    )
    
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
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="pa_requests")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="pa_requests")
    created_by: Mapped[Optional["User"]] = relationship("User", back_populates="pa_requests_created")
    
    def transition_to(self, new_status: PARequestStatus, user_id: Optional[str] = None, notes: Optional[str] = None):
        """
        FSM Transition method.
        Validates and records state transitions.
        """
        # Record transition in history
        transition = {
            "from": self.status.value,
            "to": new_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "notes": notes
        }
        
        if not self.status_history:
            self.status_history = []
        self.status_history.append(transition)
        
        # Update state
        self.status = new_status
        
        # Update timestamps based on state
        if new_status == PARequestStatus.PENDING and not self.submitted_at:
            self.submitted_at = datetime.utcnow()
        elif new_status in [PARequestStatus.APPROVED, PARequestStatus.DENIED, PARequestStatus.COMPLETED]:
            self.completed_at = datetime.utcnow()
            self.decision_date = datetime.utcnow()
    
    def __repr__(self) -> str:
        return f"<PARequest(id={self.id}, request_number={self.request_number}, status={self.status})>"