import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.dependencies import CurrentUser, HospitalCtx, DbSession
from app.models.pa_request import PARequest, PARequestStatus
from app.models.patient import Patient

router = APIRouter()
logger = logging.getLogger("healthpa.analytics")


@router.get("/pa-summary")
async def get_pa_summary(
    hospital_ctx: HospitalCtx,
    db: DbSession,
    user: CurrentUser,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze")
):
    """Get PA request summary statistics (status counts and approval metrics) for the hospital."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    base_query = select(PARequest).where(
        PARequest.hospital_id == hospital_ctx.hospital_id,
        PARequest.created_at >= start_date
    )
    
    result = await db.execute(base_query)
    pa_requests = result.scalars().all()
    
    status_counts = {}
    for status in PARequestStatus:
        status_counts[status.value] = sum(1 for pa in pa_requests if pa.status == status)
    
    total_count = len(pa_requests)
    approved_count = status_counts.get('approved', 0)
    approval_rate = (approved_count / total_count * 100) if total_count > 0 else 0
    
    return {
        "period_days": days,
        "start_date": start_date.isoformat(),
        "end_date": datetime.utcnow().isoformat(),
        "total_requests": total_count,
        "status_breakdown": status_counts,
        "approval_rate": round(approval_rate, 2),
        "urgent_requests": sum(1 for pa in pa_requests if pa.is_urgent)
    }


@router.get("/processing-time")
async def get_processing_time_stats(
    hospital_ctx: HospitalCtx,
    db: DbSession,
    user: CurrentUser,
    days: int = Query(30, ge=1, le=365)
):
    """Get average processing time (creation to final decision) statistics."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    query = select(PARequest).where(
        PARequest.hospital_id == hospital_ctx.hospital_id,
        PARequest.created_at >= start_date,
        PARequest.completed_at.isnot(None)
    )
    
    result = await db.execute(query)
    completed_requests = result.scalars().all()
    
    if not completed_requests:
        return {
            "period_days": days,
            "sample_size": 0,
            "avg_processing_hours": None,
            "min_processing_hours": None,
            "max_processing_hours": None
        }
    
    processing_times = []
    for pa in completed_requests:
        if pa.completed_at and pa.created_at:
            delta = pa.completed_at - pa.created_at
            processing_times.append(delta.total_seconds() / 3600)
    
    return {
        "period_days": days,
        "sample_size": len(processing_times),
        "avg_processing_hours": round(sum(processing_times) / len(processing_times), 2) if processing_times else None,
        "min_processing_hours": round(min(processing_times), 2) if processing_times else None,
        "max_processing_hours": round(max(processing_times), 2) if processing_times else None
    }


@router.get("/payer-breakdown")
async def get_payer_breakdown(
    hospital_ctx: HospitalCtx,
    db: DbSession,
    user: CurrentUser,
    days: int = Query(30, ge=1, le=365)
):
    """Get approval rates broken down by insurance payer."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    query = select(PARequest).where(
        PARequest.hospital_id == hospital_ctx.hospital_id,
        PARequest.created_at >= start_date
    )
    
    result = await db.execute(query)
    pa_requests = result.scalars().all()
    
    payer_stats = {}
    for pa in pa_requests:
        payer = pa.payer_name or "Unknown"
        if payer not in payer_stats:
            payer_stats[payer] = {"total": 0, "approved": 0, "denied": 0}
        
        payer_stats[payer]["total"] += 1
        if pa.status == PARequestStatus.APPROVED:
            payer_stats[payer]["approved"] += 1
        elif pa.status == PARequestStatus.DENIED:
            payer_stats[payer]["denied"] += 1
    
    payer_breakdown = []
    for payer, stats in payer_stats.items():
        rate = (stats["approved"] / stats["total"] * 100) if stats["total"] > 0 else 0
        payer_breakdown.append({
            "payer": payer,
            "total_requests": stats["total"],
            "approved": stats["approved"],
            "denied": stats["denied"],
            "approval_rate": round(rate, 2)
        })
    
    payer_breakdown.sort(key=lambda row: row["total_requests"], reverse=True)
    
    return {
        "period_days": days,
        "payers": payer_breakdown
    }


@router.get("/trends")
async def get_trends(
    hospital_ctx: HospitalCtx,
    db: DbSession,
    user: CurrentUser,
    days: int = Query(30, ge=7, le=365)
):
    """Get daily trends (counts and approval rates) for PA requests."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    query = select(PARequest).where(
        PARequest.hospital_id == hospital_ctx.hospital_id,
        PARequest.created_at >= start_date
    )
    
    result = await db.execute(query)
    pa_requests = result.scalars().all()
    
    daily_stats = {}
    for pa in pa_requests:
        date_key = pa.created_at.strftime("%Y-%m-%d")
        if date_key not in daily_stats:
            daily_stats[date_key] = {"total": 0, "approved": 0, "pending": 0}
        
        daily_stats[date_key]["total"] += 1
        if pa.status == PARequestStatus.APPROVED:
            daily_stats[date_key]["approved"] += 1
        elif pa.status == PARequestStatus.PENDING:
            daily_stats[date_key]["pending"] += 1
    
    trends = []
    current_date = start_date
    while current_date <= datetime.utcnow():
        date_key = current_date.strftime("%Y-%m-%d")
        stats = daily_stats.get(date_key, {"total": 0, "approved": 0, "pending": 0})
        trends.append({
            "date": date_key,
            "total": stats["total"],
            "approved": stats["approved"],
            "pending": stats["pending"]
        })
        current_date += timedelta(days=1)
    
    return {
        "period_days": days,
        "trends": trends
    }


@router.get("/patient-stats")
async def get_patient_stats(
    hospital_ctx: HospitalCtx,
    db: DbSession,
    user: CurrentUser
):
    """Get patient statistics for the hospital."""
    query = select(func.count(Patient.id)).where(
        Patient.hospital_id == hospital_ctx.hospital_id
    )
    
    result = await db.execute(query)
    total_patients = result.scalar() or 0
    
    pa_query = select(
        Patient.id,
        func.count(PARequest.id).label("pa_count")
    ).outerjoin(
        PARequest, Patient.id == PARequest.patient_id
    ).where(
        Patient.hospital_id == hospital_ctx.hospital_id
    ).group_by(Patient.id)
    
    pa_result = await db.execute(pa_query)
    pa_counts = pa_result.all()
    
    patients_with_pa = sum(1 for row in pa_counts if row.pa_count > 0)
    avg_pa_per_patient = sum(row.pa_count for row in pa_counts) / len(pa_counts) if pa_counts else 0
    
    return {
        "total_patients": total_patients,
        "patients_with_pa_requests": patients_with_pa,
        "avg_pa_requests_per_patient": round(avg_pa_per_patient, 2)
    }
