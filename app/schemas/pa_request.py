"""
PA Request Pydantic Schemas
"""

from datetime import date, datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.models.pa_request import PARequestStatus
from app.core.sanitization import InputSanitizer


class PARequestBase(BaseModel):
    """Base PA Request schema with input sanitization."""
    request_number: str = Field(..., min_length=1, max_length=50)
    diagnosis_codes: List[str] = Field(default_factory=list)
    procedure_codes: List[str] = Field(default_factory=list)
    clinical_notes: Optional[str] = None
    payer_name: str = Field(..., min_length=1, max_length=200)
    payer_id: Optional[str] = Field(None, max_length=100)
    is_urgent: bool = False
    requested_date: date = Field(default_factory=date.today)
    
    @field_validator('request_number', 'payer_name', 'payer_id')
    @classmethod
    def sanitize_strings(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize string inputs."""
        if v is None:
            return v
        return InputSanitizer.sanitize_string(v)
    
    @field_validator('clinical_notes')
    @classmethod
    def sanitize_clinical_notes(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize clinical notes specifically for medical content."""
        if v is None:
            return v
        return InputSanitizer.sanitize_clinical_notes(v)


class PARequestCreate(PARequestBase):
    """Schema for creating a PA request."""
    patient_id: UUID


class PARequestUpdate(BaseModel):
    """Schema for updating a PA request."""
    diagnosis_codes: Optional[List[str]] = None
    procedure_codes: Optional[List[str]] = None
    clinical_notes: Optional[str] = None
    payer_name: Optional[str] = Field(None, min_length=1, max_length=200)
    is_urgent: Optional[bool] = None


class PARequestStatusUpdate(BaseModel):
    """Schema for updating PA request status."""
    status: PARequestStatus
    notes: Optional[str] = None


class PARequestResponse(PARequestBase):
    """Schema for PA request response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    hospital_id: UUID
    patient_id: UUID
    patient_name: Optional[str] = None
    created_by_id: Optional[UUID] = None
    status: PARequestStatus
    status_history: List[dict] = Field(default_factory=list)
    ai_extracted_codes: Optional[dict] = None
    ai_confidence_score: Optional[float] = None
    decision_notes: Optional[str] = None
    decision_date: Optional[datetime] = None
    decision_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    attachments: List[dict] = Field(default_factory=list)