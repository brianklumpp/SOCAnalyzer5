"""
Redis Service
Handles Redis connection pooling and job management operations.
"""

import json
import logging
import redis
from typing import Optional, Dict, Any

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
    Get job data from Redis.
    
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
        job_json = redis_client.get(f"job:{job_id}")
    except Exception as e:
        logger.warning(f"[get_job] Redis access failed: {e}")
        return None
        
    if job_json:
        try:
            return json.loads(job_json)
        except Exception:
            return None
    return None


def set_job(
    job_id: str, 
    job_dict: Dict[str, Any], 
    redis_client=None,
    expiry_seconds: int = 60*60*24  # 24 hours default
) -> None:
    """
    Save job data to Redis with expiry.
    
    Args:
        job_id: The job ID
        job_dict: Job data dictionary
        redis_client: Optional Redis client (will create one if not provided)
        expiry_seconds: Time until expiry (default: 24 hours)
    """
    if redis_client is None:
        from ..config import REDIS_URL
        redis_client = get_redis_client(REDIS_URL)
        
    redis_client.set(
        f"job:{job_id}", 
        json.dumps(job_dict), 
        ex=expiry_seconds
    )


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
        
    redis_client.delete(f"job:{job_id}")
