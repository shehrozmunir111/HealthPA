"""
API v1 Router
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, hospitals, patients, pa_requests

router = APIRouter()

# Authentication & Identity
router.include_router(auth.router, prefix="/auth", tags=["Auth"])

# Clinical & Healthcare Data
router.include_router(hospitals.router, prefix="/hospitals", tags=["Clinical-Provider"])
router.include_router(patients.router, prefix="/patients", tags=["Clinical-Patient"])

# Prior Authorization Operations
router.include_router(pa_requests.router, prefix="/pa-requests", tags=["PA-Workflow"])