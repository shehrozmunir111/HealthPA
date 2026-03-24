"""
PA Request Pydantic Schemas
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from app.models.pa_request import PARequestStatus


class PARequestBase(BaseModel):
    """Base PA Request schema."""
    request_number: str = Field(..., min_length=1, max_length=50)
    diagnosis_codes: List[str] = Field(default_factory=list)
    procedure_codes: List[str] = Field(default_factory=list)
    clinical_notes: Optional[str] = None
    payer_name: str = Field(..., min_length=1, max_length=200)
    payer_id: Optional[str] = Field(None, max_length=100)
    is_urgent: bool = False


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