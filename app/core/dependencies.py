"""
Core Dependencies
Global dependencies for the FastAPI application.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    get_current_active_user,
    get_hospital_context,
    HospitalContext,
)
from app.models.user import User

# --- Database Dependencies ---

# DB Session dependency
DbSession = Annotated[AsyncSession, Depends(get_db)]


# --- Authentication Dependencies ---

# Currently logged in active user
CurrentUser = Annotated[User, Depends(get_current_active_user)]


# --- Multi-tenancy / Isolation Dependencies ---

# Hospital context with isolation filters applied
HospitalCtx = Annotated[HospitalContext, Depends(get_hospital_context)]


# --- Role-Based Access Control (RBAC) ---

class RoleChecker:
    """
    Dependency that enforces specific user roles for an endpoint.
    
    Usage:
        @router.post("/", dependencies=[Depends(RoleChecker([UserRole.ADMIN]))])
    """
    def __init__(self, allowed_roles: list):
        self.allowed_roles = allowed_roles

    def __call__(self, user: CurrentUser):
        if user.role not in self.allowed_roles:
            from app.core.exceptions import ForbiddenException
            raise ForbiddenException(
                f"Role {user.role} is not authorized. Required: {self.allowed_roles}"
            )
        return user


# Optional: Add common paging parameters dependency
class PaginationParams:
    def __init__(self, skip: int = 0, limit: int = 100):
        self.skip = skip
        self.limit = limit

Pagination = Annotated[PaginationParams, Depends()]
