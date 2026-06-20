"""
Hospital Pydantic Schemas
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class HospitalBase(BaseModel):
    """Base hospital schema."""
    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=50)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)


class HospitalCreate(HospitalBase):
    """Schema for creating a hospital."""
    pass


class HospitalUpdate(BaseModel):
    """Schema for updating a hospital."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None


class HospitalResponse(HospitalBase):
    """Schema for hospital response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class HospitalPublic(BaseModel):
    """Minimal hospital info exposed unauthenticated for the registration page."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str