"""
Prior Authorization Request Model
Core business entity with FSM (Finite State Machine) support.
"""

from uuid import uuid4
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, List, Optional
from enum import Enum as PyEnum

from sqlalchemy import String, Date, DateTime, ForeignKey, Text, Enum, Numeric, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")

if TYPE_CHECKING:
    from app.models.hospital import Hospital
    from app.models.user import User
    from app.models.patient import Patient


class PARequestStatus(str, PyEnum):
    """
    Finite State Machine states for PA Requests.
    
    Valid Transitions:
        DRAFT -> PENDING, CANCELLED
        PENDING -> APPROVED, DENIED, NEEDS_INFO, CANCELLED
        NEEDS_INFO -> PENDING, CANCELLED
        APPROVED -> COMPLETED, CANCELLED
        DENIED -> APPEALED, CANCELLED
        APPEALED -> PENDING, DENIED, CANCELLED
        COMPLETED -> (terminal state)
        CANCELLED -> (terminal state)
    """
    DRAFT = "draft"
    PENDING = "pending"
    NEEDS_INFO = "needs_info"
    APPROVED = "approved"
    DENIED = "denied"
    APPEALED = "appealed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class FSMTransitionError(Exception):
    """Raised when an invalid FSM transition is attempted."""
    pass


class FSMValidator:
    """
    Validates PA Request state transitions according to business rules.
    """
    
    TRANSITIONS: dict[PARequestStatus, set[PARequestStatus]] = {
        PARequestStatus.DRAFT: {
            PARequestStatus.PENDING,
            PARequestStatus.CANCELLED,
        },
        PARequestStatus.PENDING: {
            PARequestStatus.APPROVED,
            PARequestStatus.DENIED,
            PARequestStatus.NEEDS_INFO,
            PARequestStatus.CANCELLED,
        },
        PARequestStatus.NEEDS_INFO: {
            PARequestStatus.PENDING,
            PARequestStatus.CANCELLED,
        },
        PARequestStatus.APPROVED: {
            PARequestStatus.COMPLETED,
            PARequestStatus.CANCELLED,
        },
        PARequestStatus.DENIED: {
            PARequestStatus.APPEALED,
            PARequestStatus.CANCELLED,
        },
        PARequestStatus.APPEALED: {
            PARequestStatus.PENDING,
            PARequestStatus.DENIED,
            PARequestStatus.CANCELLED,
        },
        PARequestStatus.COMPLETED: set(),
        PARequestStatus.CANCELLED: set(),
    }
    
    @classmethod
    def can_transition(cls, from_status: PARequestStatus, to_status: PARequestStatus) -> bool:
        """Check if transition is valid."""
        if from_status == to_status:
            return False
        allowed = cls.TRANSITIONS.get(from_status, set())
        return to_status in allowed
    
    @classmethod
    def get_allowed_transitions(cls, from_status: PARequestStatus) -> set[PARequestStatus]:
        """Get all allowed transitions from current status."""
        return cls.TRANSITIONS.get(from_status, set())
    
    @classmethod
    def validate(cls, from_status: PARequestStatus, to_status: PARequestStatus) -> None:
        """Validate transition and raise FSMTransitionError if invalid."""
        if not cls.can_transition(from_status, to_status):
            allowed = cls.get_allowed_transitions(from_status)
            allowed_str = ", ".join(s.value for s in allowed) if allowed else "none (terminal state)"
            raise FSMTransitionError(
                f"Invalid transition from '{from_status.value}' to '{to_status.value}'. "
                f"Allowed transitions: {allowed_str}"
            )


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
    diagnosis_codes: Mapped[List[str]] = mapped_column(JSONType, default=list)  # ICD-10 codes
    procedure_codes: Mapped[List[str]] = mapped_column(JSONType, default=list)  # CPT codes
    clinical_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # AI-extracted data
    ai_extracted_codes: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
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
        JSONType,
        default=list,
        comment="Array of {status, timestamp, user_id, notes}"
    )
    
    # Decision info
    decision_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Urgency
    is_urgent: Mapped[bool] = mapped_column(default=False, nullable=False)
    requested_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # OCR/Attachments metadata
    attachments: Mapped[List[dict]] = mapped_column(
        JSONType,
        default=list,
        comment="Array of {filename, path, ocr_text, uploaded_at}"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
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
        FSM Transition method with validation.
        Validates state transitions and records history.
        
        Raises:
            FSMTransitionError: If transition is not allowed.
        """
        # Validate transition using FSMValidator
        FSMValidator.validate(self.status, new_status)
        
        # Record transition in history
        transition = {
            "from": self.status.value,
            "to": new_status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "notes": notes
        }
        
        if not self.status_history:
            self.status_history = []
        self.status_history.append(transition)
        
        # Update state
        self.status = new_status
        
        # Update timestamps based on state
        now = datetime.now(timezone.utc)
        if new_status == PARequestStatus.PENDING and not self.submitted_at:
            self.submitted_at = now
        elif new_status in [PARequestStatus.APPROVED, PARequestStatus.DENIED, PARequestStatus.COMPLETED]:
            self.completed_at = now
            self.decision_date = now
            self.decision_notes = notes
    
    def __repr__(self) -> str:
        return f"<PARequest(id={self.id}, request_number={self.request_number}, status={self.status})>"
