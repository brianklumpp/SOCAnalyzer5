"""
Redis helper functions for job management with connection pooling.
Now delegates to job_state.py (Redis Hash) instead of JSON blobs.
"""
import json as _json
import logging
import redis
from typing import Optional, Dict, Any

from ..config import REDIS_URL
from ..job_state import (
    get_job_compat, job_hmset, job_delete, job_exists,
    flatten_job_dict,
)


# Redis connection pool singleton for better performance
_redis_pool = None


def _get_redis():
    """Get Redis client with connection pooling for improved performance."""
    global _redis_pool
    if _redis_pool is None:
        try:
            _redis_pool = redis.ConnectionPool.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.5,  # fast-fail DNS/connect
                socket_timeout=0.75,          # read/write timeout
                health_check_interval=5,
                retry_on_timeout=True,
                max_connections=20
            )
        except Exception:
            # Fallback pool without special options
            _redis_pool = redis.ConnectionPool.from_url(REDIS_URL, decode_responses=True, max_connections=20)
    
    return redis.Redis(connection_pool=_redis_pool)


def get_job(job_id: str, redis_client=None) -> Optional[Dict[str, Any]]:
    """
    Get job status from Redis Hash, returning a backward-compatible nested dict.
    
    Args:
        job_id: Job identifier
        redis_client: Optional Redis client (will create if None)
        
    Returns:
        Job dictionary or None if not found
    """
    if redis_client is None:
        redis_client = _get_redis()
    try:
        return get_job_compat(job_id, redis_client)
    except Exception as e:
        logging.warning(f"[get_job] Redis access failed: {e}")
        return None


def set_job(job_id: str, job_dict: Dict[str, Any], redis_client=None) -> None:
    """
    Store job status in Redis Hash with 24-hour expiry.
    Flattens any nested dicts (identified_entities, counters, phase_completion)
    before writing.
    
    Args:
        job_id: Job identifier
        job_dict: Job data to store (may contain nested dicts)
        redis_client: Optional Redis client (will create if None)
    """
    if redis_client is None:
        redis_client = _get_redis()
    flat = flatten_job_dict(job_dict)
    job_hmset(job_id, flat, redis_client)


def del_job(job_id: str, redis_client=None) -> None:
    """
    Delete job from Redis.
    
    Args:
        job_id: Job identifier
        redis_client: Optional Redis client (will create if None)
    """
    if redis_client is None:
        redis_client = _get_redis()
    job_delete(job_id, redis_client)

