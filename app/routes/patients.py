"""
Patients API Endpoints
Professional refactored version with strict isolation and modern dependencies.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.logging import logger
from app.core.dependencies import CurrentUser, HospitalCtx, DbSession, Pagination
from app.core.exceptions import PatientNotFoundException
from app.core.cache import cache_service, CacheKeys
from app.models.patient import Patient
from app.models.audit_log import AuditAction
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate
from app.services.audit_service import AuditService

router = APIRouter()


@router.get("/", response_model=List[PatientResponse])
async def list_patients(
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser,
    page: Pagination
):
    """
    List all patients for the current hospital.
    
    ISOLATION: Strict hospital filtering enforced by HospitalCtx.
    AUDIT: Records the bulk access event.
    CACHING: Patient lists are cached for 5 minutes.
    """
    logger.debug(f"User {user.email} listing patients for hospital {hospital_ctx.hospital_id}")
    
    cache_key = f"{CacheKeys.hospital_patients(str(hospital_ctx.hospital_id))}:page:{page.skip}:{page.limit}"
    
    cached_data = await cache_service.get(cache_key)
    if cached_data:
        return cached_data
    
    query = hospital_ctx.apply_isolation(
        select(Patient).offset(page.skip).limit(page.limit),
        Patient
    )
    
    result = await db.execute(query)
    patients = result.scalars().all()
    
    await AuditService.log_action(
        db=db,
        hospital_id=hospital_ctx.hospital_id,
        user_id=user.id,
        user_email=user.email,
        action=AuditAction.READ,
        resource_type="patient_list",
        description=f"Listed {len(patients)} patients"
    )
    
    patients_data = [PatientResponse.model_validate(patient).model_dump() for patient in patients]
    await cache_service.set(cache_key, patients_data, ttl_seconds=300)
    
    return patients


@router.post("/", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    patient_in: PatientCreate,
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser
):
    """
    Register a new patient.
    
    ISOLATION: Automatic hospital assignment from authenticated context.
    """
    logger.info(f"User {user.email} creating patient: {patient_in.first_name} {patient_in.last_name}")
    
    patient = Patient(
        **patient_in.model_dump(),
        hospital_id=hospital_ctx.hospital_id
    )
    
    db.add(patient)
    await db.flush()
    await db.refresh(patient)
    
    return patient


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: UUID,
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser
):
    """
    Fetch a single patient record.
    
    ISOLATION: Ownership verification against current hospital context.
    EXCEPTION: Custom PatientNotFoundException for consistent error reporting.
    """
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id)
    )
    patient = result.scalar_one_or_none()
    
    if not patient:
        raise PatientNotFoundException(str(patient_id))
    
    # Verify strict ownership
    hospital_ctx.verify_ownership(patient)
    
    return patient


@router.patch("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: UUID,
    patient_in: PatientUpdate,
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser
):
    """
    Update patient clinical information.
    
    ISOLATION: Ownership check mandatory before modification.
    """
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id)
    )
    patient = result.scalar_one_or_none()
    
    if not patient:
        raise PatientNotFoundException(str(patient_id))
    
    hospital_ctx.verify_ownership(patient)
    
    update_data = patient_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(patient, field, value)
    
    await db.flush()
    await db.refresh(patient)
    
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: UUID,
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser
):
    """
    Remove patient record from the system.
    
    ISOLATION: Ownership check mandatory before deletion.
    """
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id)
    )
    patient = result.scalar_one_or_none()
    
    if not patient:
        raise PatientNotFoundException(str(patient_id))
    
    hospital_ctx.verify_ownership(patient)
    
    await db.delete(patient)
    await db.flush()
    
    await cache_service.invalidate_patient_cache(str(patient_id))
    
    return None