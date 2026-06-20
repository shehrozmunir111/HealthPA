from uuid import uuid4
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List
from enum import Enum as PyEnum

from sqlalchemy import String, DateTime, ForeignKey, Text, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.hospital import Hospital

JSONType = JSON().with_variant(JSONB(), "postgresql")
ArrayType = ARRAY(String).with_variant(JSON, "sqlite")


class AuditAction(str, PyEnum):
    """Types of auditable actions."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    EXPORT = "export"
    PRINT = "print"
    STATUS_CHANGE = "status_change"
    # AI grounded-coding layer
    AI_CODES_PROPOSED = "ai_codes_proposed"
    CODES_REVIEWED = "codes_reviewed"


class AuditLog(Base):
    """HIPAA audit log recording significant actions, with JSONB metadata."""
    
    __tablename__ = "audit_logs"
    
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
    
    # Who performed the action
    user_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    user_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # What was done
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction),
        nullable=False,
        index=True
    )
    
    # What resource was affected
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "patient", "pa_request", etc.
    resource_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    # Detailed context (flexible JSONB)
    details: Mapped[Optional[dict]] = mapped_column(
        JSONType,
        nullable=True,
        comment="Flexible metadata: changed_fields, ip_address, user_agent, etc."
    )
    
    # For searching/filtering
    tags: Mapped[Optional[List[str]]] = mapped_column(
        ArrayType,
        nullable=True,
        comment="Tags for categorizing audit events"
    )
    
    # Description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True
    )
    
    # Relationships
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="audit_logs")
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, resource={self.resource_type})>"