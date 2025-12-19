"""
Audit utilities for tracking changes to database records.
"""
import datetime
from typing import Optional
from ..models import Control, CUEC, SubserviceOrg


def mark_system_update(record, reason: str):
    """
    Mark a record as updated by the system/tool rather than a user.
    
    Args:
        record: Control, CUEC, or SubserviceOrg model instance
        reason: Description of what system process made the update
    """
    record.updated_at = datetime.datetime.utcnow()
    record.updated_by_user_id = None  # None indicates system update
    
    # Append to edit_log
    existing_log = getattr(record, "edit_log", "") or ""
    separator = "\n" if existing_log and not existing_log.endswith("\n") else ""
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %I:%M %p")
    record.edit_log = f"{existing_log}{separator}[SYSTEM] {reason} ({timestamp})"


def mark_user_update(record, user_id: int, reason: Optional[str] = None):
    """
    Mark a record as updated by a specific user.
    
    Args:
        record: Control, CUEC, or SubserviceOrg model instance
        user_id: ID of the user making the update
        reason: Optional description of the update
    """
    record.updated_at = datetime.datetime.utcnow()
    record.updated_by_user_id = user_id
    
    if reason:
        existing_log = getattr(record, "edit_log", "") or ""
        separator = "\n" if existing_log and not existing_log.endswith("\n") else ""
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %I:%M %p")
        record.edit_log = f"{existing_log}{separator}{reason} ({timestamp})"
