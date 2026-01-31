"""Authentication dependencies for FastAPI route protection."""
import os
import time
import asyncio
from datetime import datetime, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models import User
from backend.app.auth.security import verify_access_token

# HTTP Bearer token scheme
security = HTTPBearer()

# Short-lived cache to reduce DB lookups for auth
AUTH_USER_CACHE_TTL_SECONDS = int(os.getenv("AUTH_USER_CACHE_TTL_SECONDS", "30"))
_user_cache: dict[str, tuple[float, User]] = {}
_user_cache_lock = asyncio.Lock()


def _exp_to_epoch(exp_val: Optional[object]) -> Optional[float]:
    if exp_val is None:
        return None
    if isinstance(exp_val, (int, float)):
        return float(exp_val)
    if isinstance(exp_val, datetime):
        if exp_val.tzinfo is None:
            exp_val = exp_val.replace(tzinfo=timezone.utc)
        return exp_val.timestamp()
    return None


async def _get_cached_user(token: str) -> Optional[User]:
    if AUTH_USER_CACHE_TTL_SECONDS <= 0:
        return None
    now = time.time()
    async with _user_cache_lock:
        entry = _user_cache.get(token)
        if not entry:
            return None
        expires_at, user = entry
        if expires_at <= now:
            _user_cache.pop(token, None)
            return None
        return user


async def _set_cached_user(token: str, user: User, token_exp_epoch: Optional[float]) -> None:
    if AUTH_USER_CACHE_TTL_SECONDS <= 0:
        return
    now = time.time()
    cache_exp = now + AUTH_USER_CACHE_TTL_SECONDS
    if token_exp_epoch is not None:
        cache_exp = min(cache_exp, token_exp_epoch - 1)
        if cache_exp <= now:
            return
    async with _user_cache_lock:
        _user_cache[token] = (cache_exp, user)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from the JWT access token.
    
    Args:
        credentials: The HTTP Authorization credentials
        db: Database session
        
    Returns:
        The authenticated User object
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials

    cached_user = await _get_cached_user(token)
    if cached_user is not None:
        return cached_user

    payload = verify_access_token(token)
    
    if payload is None:
        raise credentials_exception
    
    user_id_str: str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception
    
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise credentials_exception
    
    # Query user from database
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception

    token_exp_epoch = _exp_to_epoch(payload.get("exp"))
    await _set_cached_user(token, user, token_exp_epoch)
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get the current authenticated and active user.
    
    Args:
        current_user: The current user from get_current_user
        
    Returns:
        The authenticated and active User object
        
    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Require the current user to be an admin.
    
    Args:
        current_user: The current active user
        
    Returns:
        The admin User object
        
    Raises:
        HTTPException: If user is not an admin
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user
