"""
Custom Middlewares for HealthPA application.
"""

import time
import uuid
from collections import defaultdict
from typing import Dict, List
from datetime import datetime, timedelta
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import logger


class RateLimitConfig:
    """Rate limiting configuration."""
    DEFAULT_RATE = 100
    DEFAULT_WINDOW = 60
    AUTH_RATE = 10
    AUTH_WINDOW = 60
    
    @classmethod
    def get_limits(cls, path: str) -> tuple[int, int]:
        """Get rate limits for a given path."""
        if "/auth/login" in path or "/auth/register" in path:
            return cls.AUTH_RATE, cls.AUTH_WINDOW
        return cls.DEFAULT_RATE, cls.DEFAULT_WINDOW


class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window algorithm.
    Thread-safe implementation.
    """
    
    def __init__(self):
        self._requests: Dict[str, List[datetime]] = defaultdict(list)
        self._lock = Lock()
    
    def _clean_old_requests(self, key: str, window_seconds: int) -> None:
        """Remove requests outside the current window."""
        cutoff = datetime.now() - timedelta(seconds=window_seconds)
        self._requests[key] = [
            ts for ts in self._requests[key] 
            if ts > cutoff
        ]
    
    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check if request is allowed under rate limit."""
        with self._lock:
            self._clean_old_requests(key, window_seconds)
            
            if len(self._requests[key]) >= max_requests:
                return False
            
            self._requests[key].append(datetime.now())
            return True
    
    def get_remaining(self, key: str, max_requests: int, window_seconds: int) -> int:
        """Get remaining requests in current window."""
        with self._lock:
            self._clean_old_requests(key, window_seconds)
            return max(0, max_requests - len(self._requests[key]))
    
    def get_reset_time(self, key: str, window_seconds: int) -> datetime:
        """Get time when rate limit resets."""
        with self._lock:
            if not self._requests[key]:
                return datetime.now()
            oldest = min(self._requests[key])
            return oldest + timedelta(seconds=window_seconds)


rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware to prevent abuse.
    Uses IP-based limiting for unauthenticated requests.
    Uses user-based limiting for authenticated requests.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if "/health" in str(request.url):
            return await call_next(request)
        
        # Get client identifier (IP or user ID if authenticated)
        client_id = self._get_client_id(request)
        
        # Get rate limits for this path
        max_requests, window_seconds = RateLimitConfig.get_limits(str(request.url.path))
        
        # Check rate limit
        if not rate_limiter.is_allowed(client_id, max_requests, window_seconds):
            reset_time = rate_limiter.get_reset_time(client_id, window_seconds)
            retry_after = int((reset_time - datetime.now()).total_seconds())
            
            logger.warning(f"Rate limit exceeded for {client_id} on {request.url.path}")
            
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please try again later.",
                    "retry_after_seconds": max(1, retry_after),
                    "limit": max_requests,
                    "window_seconds": window_seconds
                },
                headers={
                    "Retry-After": str(max(1, retry_after)),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(reset_time.timestamp()))
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        remaining = rate_limiter.get_remaining(client_id, max_requests, window_seconds)
        reset_time = rate_limiter.get_reset_time(client_id, window_seconds)
        
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(reset_time.timestamp()))
        
        return response
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request."""
        # Check if user is authenticated (user_id in state)
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"
        
        # Fall back to IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        
        return f"ip:{request.client.host if request.client else 'unknown'}"


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
