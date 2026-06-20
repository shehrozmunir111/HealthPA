from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, status, Query, UploadFile, File
from sqlalchemy import select

from app.core.logging import logger
from app.core.dependencies import CurrentUser, HospitalCtx, DbSession, Pagination
from app.core.exceptions import NotFoundException, BadRequestException, InternalServerException
from app.models.pa_request import PARequest, PARequestStatus, FSMTransitionError, FSMValidator
from app.models.patient import Patient
from app.services.webhook_service import webhook_service
from sqlalchemy.orm import joinedload
from app.schemas.pa_request import (
    PARequestCreate, 
    PARequestResponse, 
    PARequestStatusUpdate
)

router = APIRouter()


@router.post("/{pa_request_id}/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_clinical_document(
    pa_request_id: UUID,
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser,
    file: UploadFile = File(...)
):
    """Save a clinical document (hospital-owned) and queue a background OCR task."""
    logger.info(f"User {user.email} uploading document '{file.filename}' for PA {pa_request_id}")
    
    # 1. Fetch and verify ownership
    result = await db.execute(select(PARequest).where(PARequest.id == pa_request_id))
    pa_request = result.scalar_one_or_none()
    
    if not pa_request:
        raise NotFoundException(f"PA Request {pa_request_id} not found.")
    
    hospital_ctx.verify_ownership(pa_request)

    try:
        from app.services.ocr_service import save_upload_file, process_ocr
    except ImportError as exc:
        raise InternalServerException(
            "OCR dependencies are not installed. Upload processing is unavailable."
        ) from exc
    
    # 2. Save file to professional storage location
    file_path = save_upload_file(file)
    
    # 3. Update PA Request metadata
    attachment = {
        "id": str(uuid4()),
        "filename": file.filename,
        "path": file_path,
        "status": "processing",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "ocr_result": None
    }
    
    # New list needed to trigger JSONB update detection.
    attachments = list(pa_request.attachments or [])
    attachments.append(attachment)
    pa_request.attachments = attachments
    
    await db.flush()
    await db.refresh(pa_request)
    
    # 4. Queue background OCR task (non-blocking)
    process_ocr.delay(file_path, file.filename)
    
    return {
        "message": "Clinical document accepted and queued for processing.",
        "attachment_id": attachment["id"],
        "status": "processing"
    }

# --- Existing Endpoints ---


@router.get("/")
async def list_pa_requests(
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser,
    page: Pagination,
    status_filter: Optional[PARequestStatus] = Query(None, alias="status")
):
    """Retrieve clinical PA requests filtered by facility isolation."""
    logger.debug(f"User {user.email} listing PA requests (filter: {status_filter})")
    
    query = (
        select(PARequest, Patient)
        .join(Patient, PARequest.patient_id == Patient.id)
    )
    query = hospital_ctx.apply_isolation(query, PARequest)
    
    if status_filter:
        query = query.where(PARequest.status == status_filter)
    
    query = query.offset(page.skip).limit(page.limit)
    result = await db.execute(query)
    
    out = []
    for pa, patient in result.all():
        data = PARequestResponse.model_validate(pa)
        out.append({**data.model_dump(), "patient_name": patient.full_name})
    return out


@router.post("/", response_model=PARequestResponse, status_code=status.HTTP_201_CREATED)
async def create_pa_request(
    pa_request_in: PARequestCreate,
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser
):
    """Initialize a new Prior Authorization submission (patient must belong to the same facility)."""
    logger.info(f"User {user.email} initiating PA for patient ID: {pa_request_in.patient_id}")
    
    # Cross-tenant integrity check
    patient_result = await db.execute(select(Patient).where(Patient.id == pa_request_in.patient_id))
    patient = patient_result.scalar_one_or_none()
    
    if not patient:
        raise NotFoundException(f"Patient ID {pa_request_in.patient_id} not found.")
    
    hospital_ctx.verify_ownership(patient)
    
    pa_request = PARequest(
        **pa_request_in.model_dump(),
        hospital_id=hospital_ctx.hospital_id,
        created_by_id=user.id
    )
    
    db.add(pa_request)
    await db.flush()
    await db.refresh(pa_request)
    
    webhook_service.notify_pa_created(
        pa_request_id=pa_request.id,
        hospital_id=hospital_ctx.hospital_id,
        request_number=pa_request.request_number,
        patient_id=pa_request.patient_id
    )
    
    return pa_request


@router.get("/{pa_request_id}")
async def get_pa_request(
    pa_request_id: UUID,
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser
):
    """Retrieve request details by clinical identifier."""
    result = await db.execute(
        select(PARequest, Patient)
        .join(Patient, PARequest.patient_id == Patient.id)
        .where(PARequest.id == pa_request_id)
    )
    row = result.one_or_none()
    
    if not row:
        raise NotFoundException(f"PA Request ID {pa_request_id} not found.")
    
    pa_request, patient = row
    hospital_ctx.verify_ownership(pa_request)
    
    data = PARequestResponse.model_validate(pa_request)
    return {**data.model_dump(), "patient_name": patient.full_name}


@router.patch("/{pa_request_id}/status", response_model=PARequestResponse)
async def update_pa_status(
    pa_request_id: UUID,
    status_update: PARequestStatusUpdate,
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser
):
    """Advance clinical workflow status via a validated FSM transition."""
    logger.info(f"User {user.email} transitioning PA {pa_request_id} to {status_update.status}")
    
    result = await db.execute(
        select(PARequest).where(PARequest.id == pa_request_id)
    )
    pa_request = result.scalar_one_or_none()
    
    if not pa_request:
        raise NotFoundException(f"PA Request ID {pa_request_id} not found.")
    
    hospital_ctx.verify_ownership(pa_request)
    
    try:
        pa_request.transition_to(
            new_status=status_update.status,
            user_id=str(user.id),
            notes=status_update.notes
        )
    except FSMTransitionError as e:
        allowed = FSMValidator.get_allowed_transitions(pa_request.status)
        allowed_str = [status.value for status in allowed] if allowed else []
        raise BadRequestException(
            f"{str(e)} Allowed transitions from current status: {allowed_str}"
        )
    except ValueError as e:
        raise BadRequestException(str(e))
    
    await db.flush()
    await db.refresh(pa_request)
    
    webhook_service.notify_status_changed(
        pa_request_id=pa_request.id,
        hospital_id=hospital_ctx.hospital_id,
        status=pa_request.status,
        request_number=pa_request.request_number,
        patient_id=pa_request.patient_id,
        decision_notes=status_update.notes
    )
    
    return pa_request
