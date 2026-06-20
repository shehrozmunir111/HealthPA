from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class HealthPAException(HTTPException):
    """Base exception for all domain-specific errors."""
    def __init__(
        self, 
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: Any = None,
        headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class NotFoundException(HealthPAException):
    """Resource not found (404)."""
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ForbiddenException(HealthPAException):
    """Permission denied (403)."""
    def __init__(self, detail: str = "Permission denied"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class UnauthorizedException(HealthPAException):
    """Authentication required (401)."""
    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )


class BadRequestException(HealthPAException):
    """Invalid request (400)."""
    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class ConflictException(HealthPAException):
    """Resource conflict (409) - e.g. duplicate email."""
    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class InternalServerException(HealthPAException):
    """Generic internal server error (500)."""
    def __init__(self, detail: str = "Internal server error"):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


# Healthcare Specific Exceptions
class PatientNotFoundException(NotFoundException):
    def __init__(self, identifier: str):
        super().__init__(detail=f"Patient with ID/MRN '{identifier}' not found.")


class HospitalAccessDeniedException(ForbiddenException):
    def __init__(self):
        super().__init__(detail="You do not have access to this hospital's data.")


class InvalidPARequestStatusException(BadRequestException):
    def __init__(self, current: str, target: str):
        super().__init__(detail=f"Cannot transition PA Request from '{current}' to '{target}'.")
