from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.core.dependencies import DbSession
from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.security import HospitalContext, get_current_active_user, get_hospital_context
from app.models.appointment import Appointment, AppointmentStatus
from app.models.patient import Patient
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentResponse, AppointmentUpdate

router = APIRouter()

CurrentUser = Annotated[User, Depends(get_current_active_user)]
HospCtx = Annotated[HospitalContext, Depends(get_hospital_context)]


@router.get("/", response_model=List[AppointmentResponse])
async def list_appointments(
    db: DbSession,
    ctx: HospCtx,
    status_filter: Optional[AppointmentStatus] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List all appointments for the caller's hospital (paginated)."""
    stmt = ctx.apply_isolation(select(Appointment), Appointment).order_by(
        Appointment.scheduled_at.asc()
    )
    if status_filter:
        stmt = stmt.where(Appointment.status == status_filter)
    stmt = stmt.offset(skip).limit(limit)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    appt_in: AppointmentCreate,
    db: DbSession,
    ctx: HospCtx,
    current_user: CurrentUser,
):
    """Create an appointment. The patient must belong to the same hospital."""
    # Verify patient belongs to this hospital
    patient_result = await db.execute(
        select(Patient).where(
            Patient.id == appt_in.patient_id,
            Patient.hospital_id == ctx.hospital_id,
        )
    )
    if not patient_result.scalar_one_or_none():
        raise NotFoundException(f"Patient '{appt_in.patient_id}' not found.")

    appt = Appointment(
        hospital_id=ctx.hospital_id,
        patient_id=appt_in.patient_id,
        created_by_id=current_user.id,
        provider_name=appt_in.provider_name,
        appointment_type=appt_in.appointment_type,
        scheduled_at=appt_in.scheduled_at,
        notes=appt_in.notes,
    )
    db.add(appt)
    await db.flush()
    await db.refresh(appt)
    return appt


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: UUID,
    db: DbSession,
    ctx: HospCtx,
):
    """Retrieve a single appointment (must belong to caller's hospital)."""
    result = await db.execute(
        select(Appointment).where(Appointment.id == appointment_id)
    )
    appt: Appointment | None = result.scalar_one_or_none()
    if not appt:
        raise NotFoundException(f"Appointment '{appointment_id}' not found.")
    ctx.verify_ownership(appt)
    return appt


@router.patch("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: UUID,
    appt_in: AppointmentUpdate,
    db: DbSession,
    ctx: HospCtx,
):
    """Update an appointment's fields (partial update)."""
    result = await db.execute(
        select(Appointment).where(Appointment.id == appointment_id)
    )
    appt: Appointment | None = result.scalar_one_or_none()
    if not appt:
        raise NotFoundException(f"Appointment '{appointment_id}' not found.")
    ctx.verify_ownership(appt)

    for field, value in appt_in.model_dump(exclude_unset=True).items():
        setattr(appt, field, value)

    await db.flush()
    await db.refresh(appt)
    return appt


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: UUID,
    db: DbSession,
    ctx: HospCtx,
):
    """Cancel / delete an appointment."""
    result = await db.execute(
        select(Appointment).where(Appointment.id == appointment_id)
    )
    appt: Appointment | None = result.scalar_one_or_none()
    if not appt:
        raise NotFoundException(f"Appointment '{appointment_id}' not found.")
    ctx.verify_ownership(appt)
    await db.delete(appt)
    await db.flush()
