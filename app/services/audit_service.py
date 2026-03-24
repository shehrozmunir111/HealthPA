"""
Professional Audit Logging Service
HIPAA-compliant trail for tracking user actions.
"""

from typing import Optional, Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_log import AuditLog, AuditAction


class AuditService:
    """Service for managing audit trails."""
    
    @staticmethod
    async def log_action(
        db: AsyncSession,
        hospital_id: UUID,
        user_id: Optional[UUID],
        user_email: Optional[str],
        action: AuditAction,
        resource_type: str,
        resource_id: Optional[UUID] = None,
        description: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        tags: Optional[list[str]] = None
    ) -> AuditLog:
        """
        Record a significant action in the audit trail.
        """
        audit_entry = AuditLog(
            hospital_id=hospital_id,
            user_id=user_id,
            user_email=user_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            details=details,
            tags=tags
        )
        
        db.add(audit_entry)
        await db.flush()
        return audit_entry

    @staticmethod
    async def log_clinical_access(
        db: AsyncSession,
        hospital_id: UUID,
        user_id: UUID,
        user_email: str,
        resource_type: str,
        resource_id: UUID,
        description: str
    ):
        """Standardized helper for logging clinical data access (READ)."""
        return await AuditService.log_action(
            db=db,
            hospital_id=hospital_id,
            user_id=user_id,
            user_email=user_email,
            action=AuditAction.READ,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description
        )
