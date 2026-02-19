"""
Redis Service
Handles Redis connection pooling and job management operations.
Now delegates to job_state.py (Redis Hash) instead of JSON blobs.
"""

import json
import logging
import redis
from typing import Optional, Dict, Any

from ..job_state import (
    get_job_compat, job_hmset, job_delete, job_exists,
    flatten_job_dict,
)

logger = logging.getLogger(__name__)

# Redis connection pool singleton for better performance
_redis_pool = None


def get_redis_client(redis_url: str):
    """Get Redis client with connection pooling for improved performance."""
    global _redis_pool
    if _redis_pool is None:
        try:
            _redis_pool = redis.ConnectionPool.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=0.5,  # fast-fail DNS/connect
                socket_timeout=0.75,          # read/write timeout
                health_check_interval=5,
                retry_on_timeout=True,
                max_connections=20
            )
        except Exception:
            # Fallback pool without special options
            _redis_pool = redis.ConnectionPool.from_url(
                redis_url, 
                decode_responses=True, 
                max_connections=20
            )
    
    return redis.Redis(connection_pool=_redis_pool)


def get_job(job_id: str, redis_client=None) -> Optional[Dict[str, Any]]:
    """
    Get job data from Redis Hash, returning a backward-compatible nested dict.
    
    Args:
        job_id: The job ID
        redis_client: Optional Redis client (will create one if not provided)
        
    Returns:
        Job dictionary or None if not found
    """
    if redis_client is None:
        from ..config import REDIS_URL
        redis_client = get_redis_client(REDIS_URL)
        
    try:
        return get_job_compat(job_id, redis_client)
    except Exception as e:
        logger.warning(f"[get_job] Redis access failed: {e}")
        return None


def set_job(
    job_id: str, 
    job_dict: Dict[str, Any], 
    redis_client=None,
    expiry_seconds: int = 60*60*24  # 24 hours default
) -> None:
    """
    Save job data to Redis Hash with expiry.
    Flattens any nested dicts (identified_entities, counters, phase_completion)
    before writing.
    
    Args:
        job_id: The job ID
        job_dict: Job data dictionary (may contain nested dicts)
        redis_client: Optional Redis client (will create one if not provided)
        expiry_seconds: Time until expiry (default: 24 hours)
    """
    if redis_client is None:
        from ..config import REDIS_URL
        redis_client = get_redis_client(REDIS_URL)
    
    flat = flatten_job_dict(job_dict)
    job_hmset(job_id, flat, redis_client)


def del_job(job_id: str, redis_client=None) -> None:
    """
    Delete job data from Redis.
    
    Args:
        job_id: The job ID
        redis_client: Optional Redis client (will create one if not provided)
    """
    if redis_client is None:
        from ..config import REDIS_URL
        redis_client = get_redis_client(REDIS_URL)
        
    job_delete(job_id, redis_client)
