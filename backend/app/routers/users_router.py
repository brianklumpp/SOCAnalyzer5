"""
Router for user management operations (admin-only).
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.future import select
from pydantic import BaseModel, EmailStr

from ..models import User, RefreshToken
from ..database import get_db
from ..auth.dependencies import require_admin
from ..auth.security import get_password_hash

router = APIRouter(prefix="/users", tags=["users"])


class UserUpdate(BaseModel):
    """Schema for updating user fields."""
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class UserResponse(BaseModel):
    """Schema for user data in responses."""
    id: int
    username: str
    email: str
    full_name: Optional[str]
    is_admin: bool
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None),
    db=Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    List all users with pagination and optional search.
    
    Admin-only endpoint.
    """
    try:
        # Build query
        query = select(User)
        
        # Add search filter if provided
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                (User.username.ilike(search_pattern)) |
                (User.email.ilike(search_pattern)) |
                (User.full_name.ilike(search_pattern))
            )
        
        # Add ordering and pagination
        query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)
        
        # Execute query
        result = await db.execute(query)
        users = result.scalars().all()
        
        return users
        
    except Exception as e:
        logging.error(f"Error listing users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db=Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get a specific user by ID.
    
    Admin-only endpoint.
    """
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    update_data: UserUpdate,
    db=Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Update user fields.
    
    Admin-only endpoint. Cannot modify own admin status.
    """
    try:
        # Get user
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Prevent admin from removing own admin status
        if user.id == current_user.id and update_data.is_admin is False:
            raise HTTPException(
                status_code=400, 
                detail="Cannot remove your own admin status"
            )
        
        # Update fields
        if update_data.full_name is not None:
            user.full_name = update_data.full_name
        
        if update_data.email is not None:
            # Check if email is already taken by another user
            result = await db.execute(
                select(User).where(User.email == update_data.email, User.id != user_id)
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Email already in use")
            user.email = update_data.email
        
        if update_data.is_active is not None:
            # Prevent admin from deactivating themselves
            if user.id == current_user.id and update_data.is_active is False:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot deactivate your own account"
                )
            user.is_active = update_data.is_active
        
        if update_data.is_admin is not None:
            user.is_admin = update_data.is_admin
        
        await db.commit()
        await db.refresh(user)
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating user {user_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db=Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Delete a user.
    
    Admin-only endpoint. Cannot delete own account.
    """
    try:
        # Prevent admin from deleting themselves
        if user_id == current_user.id:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete your own account"
            )
        
        # Get user
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Delete associated refresh tokens
        await db.execute(
            select(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        
        # Delete user (CASCADE will handle refresh_tokens via FK)
        await db.delete(user)
        await db.commit()
        
        return {"message": f"User '{user.username}' deleted successfully", "user_id": user_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting user {user_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    db=Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Reset user password to a temporary value.
    
    Admin-only endpoint. Returns temporary password for admin to share with user.
    """
    import secrets
    import string
    
    try:
        # Get user
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Generate temporary password (12 characters, alphanumeric)
        alphabet = string.ascii_letters + string.digits
        temp_password = ''.join(secrets.choice(alphabet) for _ in range(12))
        
        # Update user password
        user.hashed_password = get_password_hash(temp_password)
        
        # Revoke all refresh tokens to force re-login
        await db.execute(
            select(RefreshToken)
            .where(RefreshToken.user_id == user_id)
        )
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        tokens = result.scalars().all()
        for token in tokens:
            token.revoked = True
        
        await db.commit()
        
        return {
            "message": f"Password reset for user '{user.username}'",
            "temporary_password": temp_password,
            "username": user.username,
            "note": "User should change this password after first login"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error resetting password for user {user_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to reset password: {str(e)}")
