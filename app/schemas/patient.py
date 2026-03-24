"""
Patient Pydantic Schemas
"""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from pydantic.functional_validators import BeforeValidator

from app.core.sanitization import InputSanitizer


class PatientBase(BaseModel):
    """Base patient schema with input sanitization."""
    mrn: str = Field(..., min_length=1, max_length=50, description="Medical Record Number")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: date
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    insurance_provider: Optional[str] = Field(None, max_length=200)
    insurance_policy_number: Optional[str] = Field(None, max_length=100)
    insurance_group_number: Optional[str] = Field(None, max_length=100)
    
    @field_validator('mrn', 'first_name', 'last_name', 'address', 'insurance_provider', 'insurance_policy_number', 'insurance_group_number')
    @classmethod
    def sanitize_strings(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize string inputs to prevent XSS/injection."""
        if v is None:
            return v
        return InputSanitizer.sanitize_string(v)
    
    @field_validator('phone')
    @classmethod
    def validate_phone_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone number format."""
        if v is None:
            return v
        v = InputSanitizer.sanitize_string(v)
        if v and not InputSanitizer.validate_phone(v):
            raise ValueError('Invalid phone number format')
        return v


class PatientCreate(PatientBase):
    """Schema for creating a patient."""
    pass


class PatientUpdate(BaseModel):
    """Schema for updating a patient."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    insurance_provider: Optional[str] = Field(None, max_length=200)
    insurance_policy_number: Optional[str] = Field(None, max_length=100)
    insurance_group_number: Optional[str] = Field(None, max_length=100)


class PatientResponse(PatientBase):
    """Schema for patient response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    hospital_id: UUID
    created_at: datetime
    updated_at: datetime