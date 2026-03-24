"""
Prior Authorization (PA) Request Endpoints
Professional refactored version.
"""

from fastapi import APIRouter, status, Query, UploadFile, File
from sqlalchemy import select

from app.core._logging import logger
from app.core.dependencies import CurrentUser, HospitalCtx, DbSession, Pagination
from app.core.exceptions import NotFoundException, BadRequestException
from app.models.pa_request import PARequest, PARequestStatus
from app.models.patient import Patient
from app.services.ocr_service import save_upload_file, process_ocr
from app.schemas.pa_request import (
    PARequestCreate, 
    PARequestResponse, 
    PARequestUpdate,
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
    """
    Onboard a clinical document and trigger background OCR processing.
    
    ISOLATION: Strict hospital ownership verification.
    WORKFLOW: 
    1. Synchronously saves the file to local storage.
    2. Updates metadata record.
    3. Queues background OCR task for clinical extraction.
    """
    logger.info(f"User {user.email} uploading document '{file.filename}' for PA {pa_request_id}")
    
    # 1. Fetch and verify ownership
    result = await db.execute(select(PARequest).where(PARequest.id == pa_request_id))
    pa_request = result.scalar_one_or_none()
    
    if not pa_request:
        raise NotFoundException(f"PA Request {pa_request_id} not found.")
    
    hospital_ctx.verify_ownership(pa_request)
    
    # 2. Save file to professional storage location
    file_path = save_upload_file(file)
    
    # 3. Update PA Request metadata
    attachment = {
        "id": str(uuid4()),
        "filename": file.filename,
        "path": file_path,
        "status": "processing",
        "uploaded_at": datetime.utcnow().isoformat(),
        "ocr_result": None
    }
    
    # SQLAlchemy note: Must create new list to trigger JSONB update detection or use mutable extension
    attachments = list(pa_request.attachments or [])
    attachments.append(attachment)
    pa_request.attachments = attachments
    
    await db.flush()
    await db.refresh(pa_request)
    
    # 4. Queue background OCR task (The "Non-blocking" Professional way)
    process_ocr.delay(file_path, file.filename)
    
    return {
        "message": "Clinical document accepted and queued for processing.",
        "attachment_id": attachment["id"],
        "status": "processing"
    }

# --- Existing Endpoints ---


@router.get("/", response_model=List[PARequestResponse])
async def list_pa_requests(
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser,
    page: Pagination,
    status_filter: Optional[PARequestStatus] = Query(None, alias="status")
):
    """
    Retrieve clinical PA requests filtered by facility isolation.
    """
    logger.debug(f"User {user.email} listing PA requests (filter: {status_filter})")
    
    query = hospital_ctx.apply_isolation(select(PARequest), PARequest)
    
    if status_filter:
        query = query.where(PARequest.status == status_filter)
    
    query = query.offset(page.skip).limit(page.limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=PARequestResponse, status_code=status.HTTP_201_CREATED)
async def create_pa_request(
    pa_request_in: PARequestCreate,
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser
):
    """
    Initialize a new Prior Authorization submission.
    
    VALIDATION: Ensures the associated patient belongs to the same clinical facility.
    """
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
    
    return pa_request


@router.get("/{pa_request_id}", response_model=PARequestResponse)
async def get_pa_request(
    pa_request_id: UUID,
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser
):
    """
    Retrieve request details by clinical identifier.
    """
    result = await db.execute(
        select(PARequest).where(PARequest.id == pa_request_id)
    )
    pa_request = result.scalar_one_or_none()
    
    if not pa_request:
        raise NotFoundException(f"PA Request ID {pa_request_id} not found.")
    
    hospital_ctx.verify_ownership(pa_request)
    
    return pa_request


@router.patch("/{pa_request_id}/status", response_model=PARequestResponse)
async def update_pa_status(
    pa_request_id: UUID,
    status_update: PARequestStatusUpdate,
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser
):
    """
    Advance clinical workflow status via FSM transition.
    """
    logger.info(f"User {user.email} transitioning PA {pa_request_id} to {status_update.status}")
    
    result = await db.execute(
        select(PARequest).where(PARequest.id == pa_request_id)
    )
    pa_request = result.scalar_one_or_none()
    
    if not pa_request:
        raise NotFoundException(f"PA Request ID {pa_request_id} not found.")
    
    hospital_ctx.verify_ownership(pa_request)
    
    try:
        # Perform FSM transition
        pa_request.transition_to(
            new_status=status_update.status,
            user_id=str(user.id),
            notes=status_update.notes
        )
    except ValueError as e:
        raise BadRequestException(str(e))
    
    await db.flush()
    await db.refresh(pa_request)
    
    return pa_request