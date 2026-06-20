from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.models.appointment import AppointmentStatus


class AppointmentCreate(BaseModel):
    patient_id: UUID
    provider_name: str
    appointment_type: str
    scheduled_at: datetime
    notes: Optional[str] = None

    @field_validator("provider_name", "appointment_type")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be blank")
        return v.strip()


class AppointmentUpdate(BaseModel):
    provider_name: Optional[str] = None
    appointment_type: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    status: Optional[AppointmentStatus] = None
    notes: Optional[str] = None


class AppointmentResponse(BaseModel):
    id: UUID
    hospital_id: UUID
    patient_id: UUID
    created_by_id: Optional[UUID]
    provider_name: str
    appointment_type: str
    scheduled_at: datetime
    status: AppointmentStatus
    notes: Optional[str]
    reminder_sent: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
