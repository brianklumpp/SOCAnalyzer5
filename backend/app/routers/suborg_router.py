"""
Router for subservice organization operations.
"""
import logging
import traceback
from typing import Dict, Any

from fastapi import APIRouter, Depends, Body, HTTPException
from sqlalchemy.future import select

from ..models import SubserviceOrg
from ..database import get_db
from ..services.scan_service import mark_executive_summary_stale

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
}


def _suborg_apply_changes(suborg: SubserviceOrg, data: Dict[str, Any]):
    """Apply changes to subservice org fields."""
    for k in ALLOWED_SUBORG_FIELDS:
        if k in data:
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
                continue
            setattr(suborg, k, data[k])


@router.patch("/report/{scan_id}/suborgs/id/{suborg_id}")
async def patch_suborg_by_id(scan_id: int, suborg_id: int, payload: Dict[str, Any] = Body(...), db=Depends(get_db)):
    """Update subservice org by database ID."""
    try:
        logging.info(f"PATCH suborg by id: scan_id={scan_id}, suborg_id={suborg_id}, payload={payload}")
        row = (await db.execute(select(SubserviceOrg).where(SubserviceOrg.id == suborg_id, SubserviceOrg.scan_id == scan_id))).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Subservice org not found")
        # If renaming, trim whitespace but allow duplicates (extractors may produce duplicates intentionally)
        if isinstance(payload, dict) and "name" in payload and payload["name"] is not None:
            payload["name"] = str(payload["name"]).strip()
        _suborg_apply_changes(row, payload or {})
        await mark_executive_summary_stale(scan_id, db)
        await db.commit()
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"PATCH suborg by id failed: {e}\n{traceback.format_exc()}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update subservice org")


@router.patch("/report/{scan_id}/suborgs/{suborg_name}")
async def patch_suborg_by_name(scan_id: int, suborg_name: str, payload: Dict[str, Any] = Body(...), db=Depends(get_db)):
    """Update subservice org by name (legacy endpoint, prefer ID-based endpoint)."""
    try:
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
        _suborg_apply_changes(row, payload or {})
        await mark_executive_summary_stale(scan_id, db)
        await db.commit()
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"PATCH suborg by name failed: {e}\n{traceback.format_exc()}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update subservice org")
