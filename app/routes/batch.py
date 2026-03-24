"""
Batch Processing Endpoints for HealthPA
Supports bulk upload of PA requests via CSV
"""

import csv
import io
import logging
from typing import List, Optional
from uuid import uuid4
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.logging import logger
from app.core.dependencies import CurrentUser, HospitalCtx, DbSession
from app.core.exceptions import BadRequestException
from app.models.patient import Patient
from app.models.pa_request import PARequest, PARequestStatus
from app.services.webhook_service import webhook_service

router = APIRouter()
logger = logging.getLogger("healthpa.batch")


class BatchResult(BaseModel):
    """Result of a batch operation."""
    total: int
    success: int
    failed: int
    errors: List[dict] = Field(default_factory=list)


class BatchPAResultItem(BaseModel):
    """Item in batch result."""
    row: int
    success: bool
    request_number: Optional[str] = None
    error: Optional[str] = None


@router.post("/pa-requests/csv", status_code=207)
async def batch_import_pa_requests(
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser,
    file: UploadFile = File(...)
):
    """
    Bulk import PA requests from CSV file.
    
    CSV Format (required columns):
        - patient_mrn: Patient Medical Record Number
        - request_number: Unique request number
        - diagnosis_codes: JSON array string (e.g., '["J44.0", "R05.9"]')
        - procedure_codes: JSON array string
        - clinical_notes: Clinical notes text
        - payer_name: Insurance payer name
        - payer_id: Insurance policy number
        - is_urgent: 'true' or 'false'
    
    Returns multi-status response (207) with detailed results.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    content = await file.read()
    
    try:
        decoded_content = content.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")
    
    reader = csv.DictReader(io.StringIO(decoded_content))
    
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty or has no headers")
    
    required_cols = ['patient_mrn', 'request_number', 'payer_name']
    missing = [col for col in required_cols if col not in reader.fieldnames]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing)}"
        )
    
    results: List[BatchPAResultItem] = []
    success_count = 0
    failed_count = 0
    
    for row_num, row in enumerate(reader, start=2):
        try:
            result = await _process_csv_row(row, row_num, hospital_ctx, user, db)
            results.append(result)
            if result.success:
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            results.append(BatchPAResultItem(
                row=row_num,
                success=False,
                error=str(e)
            ))
            failed_count += 1
    
    return {
        "summary": {
            "total": len(results),
            "success": success_count,
            "failed": failed_count
        },
        "details": [r.model_dump() for r in results]
    }


async def _process_csv_row(
    row: dict,
    row_num: int,
    hospital_ctx: HospitalCtx,
    user: CurrentUser,
    db: DbSession
) -> BatchPAResultItem:
    """Process a single CSV row."""
    from sqlalchemy import select
    
    patient_mrn = row.get('patient_mrn', '').strip()
    request_number = row.get('request_number', '').strip()
    payer_name = row.get('payer_name', '').strip()
    
    if not all([patient_mrn, request_number, payer_name]):
        return BatchPAResultItem(
            row=row_num,
            success=False,
            error="Missing required fields (patient_mrn, request_number, payer_name)"
        )
    
    patient_result = await db.execute(
        select(Patient).where(
            Patient.hospital_id == hospital_ctx.hospital_id,
            Patient.mrn == patient_mrn
        )
    )
    patient = patient_result.scalar_one_or_none()
    
    if not patient:
        return BatchPAResultItem(
            row=row_num,
            success=False,
            error=f"Patient with MRN '{patient_mrn}' not found"
        )
    
    diagnosis_codes = _parse_json_field(row.get('diagnosis_codes', '[]'))
    procedure_codes = _parse_json_field(row.get('procedure_codes', '[]'))
    
    pa_request = PARequest(
        id=uuid4(),
        hospital_id=hospital_ctx.hospital_id,
        patient_id=patient.id,
        created_by_id=user.id,
        request_number=request_number,
        diagnosis_codes=diagnosis_codes,
        procedure_codes=procedure_codes,
        clinical_notes=row.get('clinical_notes', '').strip() or None,
        payer_name=payer_name,
        payer_id=row.get('payer_id', '').strip() or None,
        is_urgent=row.get('is_urgent', '').lower() == 'true',
        requested_date=datetime.utcnow(),
        status=PARequestStatus.DRAFT,
        status_history=[{
            "status": "draft",
            "timestamp": datetime.utcnow().isoformat(),
            "user": user.email
        }]
    )
    
    db.add(pa_request)
    await db.flush()
    
    webhook_service.notify_pa_created(
        pa_request_id=pa_request.id,
        hospital_id=hospital_ctx.hospital_id,
        request_number=pa_request.request_number,
        patient_id=pa_request.patient_id
    )
    
    return BatchPAResultItem(
        row=row_num,
        success=True,
        request_number=request_number
    )


def _parse_json_field(value: str) -> List[dict]:
    """Parse JSON field from CSV (handles simple JSON arrays)."""
    import json
    
    if not value or value.strip() in ('', '[]', '{}'):
        return []
    
    value = value.strip()
    
    if value.startswith('[') or value.startswith('{'):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except json.JSONDecodeError:
            pass
    
    return []


@router.post("/patients/csv", status_code=207)
async def batch_import_patients(
    db: DbSession,
    hospital_ctx: HospitalCtx,
    user: CurrentUser,
    file: UploadFile = File(...)
):
    """
    Bulk import patients from CSV file.
    
    CSV Format (required columns):
        - mrn: Medical Record Number
        - first_name: Patient first name
        - last_name: Patient last name
        - date_of_birth: Date in YYYY-MM-DD format
        - phone: Phone number (optional)
        - email: Email address (optional)
        - address: Address (optional)
        - insurance_provider: Insurance provider (optional)
        - insurance_policy_number: Policy number (optional)
    
    Returns multi-status response (207) with detailed results.
    """
    from datetime import date
    from app.core.sanitization import InputSanitizer
    from app.models.patient import Patient
    
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    content = await file.read()
    
    try:
        decoded_content = content.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")
    
    reader = csv.DictReader(io.StringIO(decoded_content))
    
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty or has no headers")
    
    results: List[BatchPAResultItem] = []
    success_count = 0
    failed_count = 0
    
    for row_num, row in enumerate(reader, start=2):
        try:
            mrn = row.get('mrn', '').strip()
            first_name = row.get('first_name', '').strip()
            last_name = row.get('last_name', '').strip()
            dob_str = row.get('date_of_birth', '').strip()
            
            if not all([mrn, first_name, last_name, dob_str]):
                raise ValueError("Missing required fields")
            
            try:
                date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError(f"Invalid date format: {dob_str}. Use YYYY-MM-DD")
            
            patient = Patient(
                id=uuid4(),
                hospital_id=hospital_ctx.hospital_id,
                mrn=InputSanitizer.sanitize_string(mrn),
                first_name=InputSanitizer.sanitize_string(first_name),
                last_name=InputSanitizer.sanitize_string(last_name),
                date_of_birth=date_of_birth,
                phone=InputSanitizer.sanitize_string(row.get('phone', '').strip()) or None,
                email=row.get('email', '').strip() or None,
                address=InputSanitizer.sanitize_string(row.get('address', '').strip()) or None,
                insurance_provider=InputSanitizer.sanitize_string(row.get('insurance_provider', '').strip()) or None,
                insurance_policy_number=InputSanitizer.sanitize_string(row.get('insurance_policy_number', '').strip()) or None,
                insurance_group_number=InputSanitizer.sanitize_string(row.get('insurance_group_number', '').strip()) or None,
            )
            
            db.add(patient)
            await db.flush()
            
            results.append(BatchPAResultItem(
                row=row_num,
                success=True,
                request_number=mrn
            ))
            success_count += 1
            
        except Exception as e:
            results.append(BatchPAResultItem(
                row=row_num,
                success=False,
                error=str(e)
            ))
            failed_count += 1
    
    return {
        "summary": {
            "total": len(results),
            "success": success_count,
            "failed": failed_count
        },
        "details": [r.model_dump() for r in results]
    }
