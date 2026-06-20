"""
Hospital Management Endpoints
Professional refactored version.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.core.logging import logger
from app.core.dependencies import CurrentUser, DbSession, Pagination, RoleChecker
from app.core.exceptions import NotFoundException, ConflictException
from app.models.hospital import Hospital
from app.models.user import UserRole
from app.schemas.hospital import (
    HospitalCreate,
    HospitalPublic,
    HospitalResponse,
    HospitalUpdate,
)

router = APIRouter()
admin_required = Depends(RoleChecker([UserRole.ADMIN]))


@router.get("/public", response_model=List[HospitalPublic])
async def list_hospitals_public(db: DbSession, page: Pagination):
    """
    Minimal, UNAUTHENTICATED hospital list for the registration page
    (a new user must pick their hospital before they have a token).
    Declared before '/{hospital_id}' so the static path wins.
    """
    result = await db.execute(
        select(Hospital).where(Hospital.is_active.is_(True)).offset(page.skip).limit(page.limit)
    )
    return result.scalars().all()


@router.get("/", response_model=List[HospitalResponse], dependencies=[admin_required])
async def list_hospitals(
    db: DbSession,
    user: CurrentUser,
    page: Pagination,
):
    """
    Retrieve all registered hospitals. Admin-only (full records).
    """
    result = await db.execute(select(Hospital).offset(page.skip).limit(page.limit))
    return result.scalars().all()


@router.post("/", response_model=HospitalResponse, status_code=status.HTTP_201_CREATED, dependencies=[admin_required])
async def create_hospital(
    hospital_in: HospitalCreate,
    db: DbSession,
    user: CurrentUser
):
    """
    Onboard a new healthcare facility.
    
    PROTECTION: Restricted to administrative staff or superusers in production.
    CHECK: Ensures facility codes are unique across the ecosystem.
    """
    logger.info(f"User {user.email} onboarding new hospital: {hospital_in.name} ({hospital_in.code})")
    
    # Uniqueness check for facility code
    result = await db.execute(select(Hospital).where(Hospital.code == hospital_in.code))
    if result.scalar_one_or_none():
        raise ConflictException(f"Hospital facility code '{hospital_in.code}' already exists.")
    
    hospital = Hospital(**hospital_in.model_dump())
    db.add(hospital)
    await db.flush()
    await db.refresh(hospital)
    
    return hospital


@router.get("/{hospital_id}", response_model=HospitalResponse, dependencies=[admin_required])
async def get_hospital(
    hospital_id: UUID,
    db: DbSession,
    user: CurrentUser
):
    """
    Fetch facility details by unique identifier.
    """
    result = await db.execute(select(Hospital).where(Hospital.id == hospital_id))
    hospital = result.scalar_one_or_none()
    
    if not hospital:
        raise NotFoundException(f"Hospital with ID '{hospital_id}' not found.")
    
    return hospital


@router.patch("/{hospital_id}", response_model=HospitalResponse, dependencies=[admin_required])
async def update_hospital(
    hospital_id: UUID,
    hospital_in: HospitalUpdate,
    db: DbSession,
    user: CurrentUser
):
    """
    Update healthcare facility metadata.
    """
    result = await db.execute(select(Hospital).where(Hospital.id == hospital_id))
    hospital = result.scalar_one_or_none()
    
    if not hospital:
        raise NotFoundException(f"Hospital with ID '{hospital_id}' not found.")
    
    update_data = hospital_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(hospital, field, value)
    
    await db.flush()
    await db.refresh(hospital)
    
    return hospital
