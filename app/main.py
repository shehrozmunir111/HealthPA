"""
HealthPA - AI-Powered Prior Authorization System
Main FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as api_v1_router
from app.core.logging import setup_logging
from app.core.config import settings
from app.core.database import engine, Base
from app.core.middleware import ProcessTimeAndRequestIDMiddleware
from app.core.exceptions import HealthPAException

# Setup logging
setup_logging()
logger = logging.getLogger("healthpa.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Creates tables on startup (dev only - use Alembic in production).
    """
    # Startup
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}...")
    
    if settings.DEBUG:
        logger.warning("Running in DEBUG mode. Creating tables automatically.")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AI-Powered Prior Authorization System for Healthcare",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# --- Global Exception Handlers ---

@app.exception_handler(HealthPAException)
async def health_pa_exception_handler(request: Request, exc: HealthPAException):
    """
    Standardize clinical domain error responses.
    """
    logger.error(f"DOMAIN_ERROR: {exc.detail} | REQ_ID: {getattr(request.state, 'id', 'N/A')}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "message": exc.detail,
            "request_id": getattr(request.state, "id", None)
        },
    )

# --- Middleware ---

# Performance & Tracing Middleware
app.add_middleware(ProcessTimeAndRequestIDMiddleware)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API Routers ---

# Version 1 Router
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["Infrastructure"])
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy", 
        "version": settings.VERSION,
        "project": settings.PROJECT_NAME
    }


# Add custom exception handlers if needed
# from app.core.exceptions import HealthPAException
# @app.exception_handler(HealthPAException)
# async def custom_exception_handler(request, exc):
#     return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})