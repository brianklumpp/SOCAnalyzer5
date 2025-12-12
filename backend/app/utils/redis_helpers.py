"""
Redis helper functions for job management with connection pooling.
"""
import json as _json
import logging
import redis.asyncio as redis
from typing import Optional, Dict, Any

from ..config import REDIS_URL


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


async def get_job(job_id: str, redis_client=None) -> Optional[Dict[str, Any]]:
    """
    Get job status from Redis.
    
    Args:
        job_id: Job identifier
        redis_client: Optional Redis client (will create if None)
        
    Returns:
        Job dictionary or None if not found
    """
    if redis_client is None:
        redis_client = _get_redis()
        try:
            job_json = await redis_client.get(f"job:{job_id}")
        except Exception as e:
            logging.warning(f"[get_job] Redis access failed: {e}")
            return None
        if job_json:
            try:
                return _json.loads(job_json)
            except Exception:
                return None
        return None
    else:
        # Use provided client (no try/except needed, caller handles)
        job_json = await redis_client.get(f"job:{job_id}")
        if job_json:
            try:
                return _json.loads(job_json)
            except Exception:
                return None
        return None


async def set_job(job_id: str, job_dict: Dict[str, Any], redis_client=None) -> None:
    """
    Store job status in Redis with 24-hour expiry.
    
    Args:
        job_id: Job identifier
        job_dict: Job data to store
        redis_client: Optional Redis client (will create if None)
    """
    if redis_client is None:
        redis_client = _get_redis()
    await redis_client.set(f"job:{job_id}", _json.dumps(job_dict), ex=60*60*24)  # 24h expiry


async def del_job(job_id: str, redis_client=None) -> None:
    """
    Delete job from Redis.
    
    Args:
        job_id: Job identifier
        redis_client: Optional Redis client (will create if None)
    """
    if redis_client is None:
        redis_client = _get_redis()
    await redis_client.delete(f"job:{job_id}")
