import json
import logging
from typing import Optional, Any, Callable, TypeVar
from functools import wraps
from datetime import timedelta

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger("healthpa.cache")

T = TypeVar('T')


class CacheService:
    """Redis-based caching service with get/set and decorator caching."""
    
    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._enabled = False
    
    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            self._redis = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            await self._redis.ping()
            self._enabled = True
            logger.info("Redis cache connected successfully")
        except Exception as e:
            logger.warning(f"Redis connection failed, caching disabled: {e}")
            self._enabled = False
    
    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._enabled = False
    
    def is_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self._enabled and self._redis is not None
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self.is_enabled():
            return None
        
        try:
            value = await self._redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Cache get error for key {key}: {e}")
            return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 300
    ) -> bool:
        """Set value in cache with TTL."""
        if not self.is_enabled():
            return False
        
        try:
            serialized = json.dumps(value, default=str)
            await self._redis.setex(key, ttl_seconds, serialized)
            return True
        except Exception as e:
            logger.warning(f"Cache set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if not self.is_enabled():
            return False
        
        try:
            await self._redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete error for key {key}: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        if not self.is_enabled():
            return 0
        
        try:
            keys = await self._redis.keys(pattern)
            if keys:
                return await self._redis.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Cache delete pattern error for {pattern}: {e}")
            return 0
    
    async def invalidate_hospital_cache(self, hospital_id: str) -> None:
        """Invalidate all cache entries for a hospital."""
        await self.delete_pattern(f"hospital:{hospital_id}:*")
    
    async def invalidate_patient_cache(self, patient_id: str) -> None:
        """Invalidate all cache entries for a patient."""
        await self.delete_pattern(f"patient:{patient_id}:*")


cache_service = CacheService()


def cached(
    key_prefix: str,
    ttl_seconds: int = 300,
    hospital_dependent: bool = False
):
    """Decorator for caching function results."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            if not cache_service.is_enabled():
                return await func(*args, **kwargs)
            
            hospital_id = kwargs.get('hospital_id')
            if hospital_dependent and hospital_id:
                cache_key = f"{key_prefix}:hospital:{hospital_id}"
            else:
                cache_key = key_prefix
            
            cached_value = await cache_service.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_value
            
            result = await func(*args, **kwargs)
            
            if result is not None:
                await cache_service.set(cache_key, _serialize_result(result), ttl_seconds)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def _serialize_result(result: Any) -> Any:
    """Serialize result for caching."""
    if hasattr(result, 'model_dump'):
        return result.model_dump()
    elif hasattr(result, '__dict__'):
        return result.__dict__
    return result


class CacheKeys:
    """Cache key generators."""
    
    @staticmethod
    def hospital(hospital_id: str) -> str:
        return f"hospital:{hospital_id}"
    
    @staticmethod
    def hospital_patients(hospital_id: str) -> str:
        return f"hospital:{hospital_id}:patients"
    
    @staticmethod
    def patient(patient_id: str) -> str:
        return f"patient:{patient_id}"
    
    @staticmethod
    def pa_requests(hospital_id: str, status: Optional[str] = None) -> str:
        if status:
            return f"hospital:{hospital_id}:pa_requests:status:{status}"
        return f"hospital:{hospital_id}:pa_requests"
