"""
Router for subservice organization operations.
"""
import logging
import traceback
from typing import Dict, Any

from fastapi import APIRouter, Depends, Body, HTTPException
from sqlalchemy.future import select

from ..models import SubserviceOrg
from ..models import User
from ..database import get_db
from ..services.scan_service import mark_executive_summary_stale
from ..auth.dependencies import get_current_active_user

router = APIRouter()

# Allowed fields for PATCH operations
ALLOWED_SUBORG_FIELDS = {
    "confidence",
    "confidence_justification",
    "annotation",
    "analyst_notes",
    "third_party_description",
    "third_party_page_ref",
    "name",
    "edit_log",
}


def _suborg_apply_changes(suborg: SubserviceOrg, data: Dict[str, Any], current_user):
    """Apply changes to subservice org fields."""
    from datetime import datetime
    import logging
    
    logging.info(f"[SUBORG] _apply_changes called with data keys: {list(data.keys())}")
    
    for k in ALLOWED_SUBORG_FIELDS:
        if k in data:
            # Skip edit_log - it's only modified automatically below
            if k == "edit_log":
                continue
            
            # Track old value for logging
            old_value = getattr(suborg, k, None)
            
            # Normalize confidence to float if passed as string percentage or whole number
            if k == "confidence":
                v = data[k]
                if isinstance(v, str):
                    s = v.strip()
                    try:
                        if s.endswith('%'):
                            suborg.confidence = float(s[:-1]) / 100.0
                        else:
                            n = float(s)
                            suborg.confidence = n / 100.0 if n > 1 else n
                    except Exception:
                        # Ignore invalid parses
                        pass
                elif isinstance(v, (int, float)):
                    suborg.confidence = (float(v) / 100.0) if float(v) > 1 else float(v)
            else:
                # Set the field value for all other fields
                setattr(suborg, k, data[k])
            
            # Log the change to edit_log if value changed
            new_value = getattr(suborg, k, None)
            if old_value != new_value:
                prev_log = getattr(suborg, "edit_log", "") or ""
                sep = ",\n" if prev_log else ""
                timestamp = datetime.now().isoformat()
                
                # Format the log message with username
                if k == "analyst_notes":
                    log_msg = f"Analyst notes updated by {current_user.username} [{timestamp}]"
                elif k == "confidence":
                    log_msg = f"UI edit: confidence {old_value} -> {new_value} by {current_user.username} [{timestamp}]"
                else:
                    log_msg = f"UI edit: {k} updated [{timestamp}]"
                
                suborg.edit_log = f"{prev_log}{sep}{log_msg}"
                logging.info(f"[SUBORG] Logged change for {k}: old={old_value}, new={new_value}, edit_log={suborg.edit_log}")


@router.patch("/report/{scan_id}/suborgs/id/{suborg_id}")
async def patch_suborg_by_id(scan_id: int, suborg_id: int, payload: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Update subservice org by database ID."""
    try:
        from datetime import datetime
        logging.info(f"PATCH suborg by id: scan_id={scan_id}, suborg_id={suborg_id}, payload={payload}")
        row = (await db.execute(select(SubserviceOrg).where(SubserviceOrg.id == suborg_id, SubserviceOrg.scan_id == scan_id))).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Subservice org not found")
        # If renaming, trim whitespace but allow duplicates (extractors may produce duplicates intentionally)
        if isinstance(payload, dict) and "name" in payload and payload["name"] is not None:
            payload["name"] = str(payload["name"]).strip()
        _suborg_apply_changes(row, payload or {}, current_user)
        
        # Update audit fields
        row.updated_at = datetime.utcnow()
        row.updated_by_user_id = current_user.id
        
        await mark_executive_summary_stale(scan_id, db)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        
        # Get username for updated_by
        updated_by_username = None
        if row.updated_by_user_id:
            user_result = await db.execute(select(User).where(User.id == row.updated_by_user_id))
            user = user_result.scalar_one_or_none()
            if user:
                updated_by_username = user.username
        
        return {
            "id": row.id,
            "name": row.name,
            "confidence": row.confidence,
            "confidence_justification": row.confidence_justification,
            "edit_log": row.edit_log,
            "analyst_notes": row.analyst_notes,
            "annotation": row.annotation,
            "third_party_description": row.third_party_description,
            "third_party_page_ref": row.third_party_page_ref,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": updated_by_username or "System" if row.updated_at and not row.updated_by_user_id else updated_by_username
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"PATCH suborg by id failed: {e}\n{traceback.format_exc()}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update subservice org")


@router.patch("/report/{scan_id}/suborgs/{suborg_name}")
async def patch_suborg_by_name(scan_id: int, suborg_name: str, payload: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Update subservice org by name (legacy endpoint, prefer ID-based endpoint)."""
    try:
        from datetime import datetime
        logging.info(f"PATCH suborg by name: scan_id={scan_id}, name={suborg_name}, payload={payload}")
        q = (await db.execute(select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id, SubserviceOrg.name == suborg_name))).scalars().all()
        if not q:
            raise HTTPException(status_code=404, detail="Subservice org not found")
        if len(q) > 1:
            # Ambiguous legacy route
            raise HTTPException(status_code=409, detail="Multiple subservice orgs share this name; use ID endpoint")
        row = q[0]
        # If renaming, trim whitespace; duplicates are allowed. Keep legacy-name-route 409 only for ambiguity on selection.
        if isinstance(payload, dict) and "name" in payload and payload["name"] is not None:
            payload["name"] = str(payload["name"]).strip()
        _suborg_apply_changes(row, payload or {}, current_user)
        
        # Add username to edit_log if changes were made
        if row.edit_log and not row.edit_log.endswith(f"by {current_user.username}"):
            # Replace the last timestamp with username + timestamp
            import re
            row.edit_log = re.sub(r'\[([^\]]+)\]$', f'by {current_user.username} (\\1)', row.edit_log)
        
        # Update audit fields
        row.updated_at = datetime.utcnow()
        row.updated_by_user_id = current_user.id
        
        await mark_executive_summary_stale(scan_id, db)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        
        # Get username for updated_by
        updated_by_username = None
        if row.updated_by_user_id:
            user_result = await db.execute(select(User).where(User.id == row.updated_by_user_id))
            user = user_result.scalar_one_or_none()
            if user:
                updated_by_username = user.username
        
        return {
            "id": row.id,
            "name": row.name,
            "confidence": row.confidence,
            "confidence_justification": row.confidence_justification,
            "edit_log": row.edit_log,
            "analyst_notes": row.analyst_notes,
            "annotation": row.annotation,
            "third_party_description": row.third_party_description,
            "third_party_page_ref": row.third_party_page_ref,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": updated_by_username or "System" if row.updated_at and not row.updated_by_user_id else updated_by_username
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"PATCH suborg by name failed: {e}\n{traceback.format_exc()}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update subservice org")
