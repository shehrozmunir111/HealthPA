"""
Custom Middlewares for HealthPA application.
"""

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import logger


class ProcessTimeAndRequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds a unique Request ID to each request and
    logs the processing time for performance monitoring.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Generate Request ID
        request_id = str(uuid.uuid4())
        request.state.id = request_id
        
        # Start timing
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate process time
        process_time = time.time() - start_time
        
        # Add headers to response for tracing
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.4f}s"
        
        # Log performance (for non-healthcheck routes)
        if not "/health" in str(request.url):
            logger.info(
                f"REQUEST: {request.method} {request.url.path} "
                f"RESP_STATUS: {response.status_code} "
                f"TIME: {process_time:.4f}s "
                f"REQ_ID: {request_id}"
            )
            
        return response
