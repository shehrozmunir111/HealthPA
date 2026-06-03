"""
HealthPA API Router

Versioning Strategy:
    - All endpoints under /api/
    - New features added to existing version
    - Breaking changes will require new version prefix
"""

from fastapi import APIRouter

from app.routes import auth, hospitals, patients, pa_requests, batch, analytics, appointments

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
router.include_router(hospitals.router, prefix="/hospitals", tags=["Hospitals"])
router.include_router(patients.router, prefix="/patients", tags=["Patients"])
router.include_router(pa_requests.router, prefix="/pa-requests", tags=["PA-Workflow"])
router.include_router(batch.router, prefix="/batch", tags=["Batch-Operations"])
router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
router.include_router(appointments.router, prefix="/appointments", tags=["Appointments"])
