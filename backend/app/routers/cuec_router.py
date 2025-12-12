"""
Router for CUEC (Complementary User Entity Control) operations.
"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, Body, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.future import select
from sqlalchemy.exc import MultipleResultsFound

from ..models import CUEC, Scan
from ..database import get_db
from ..services.scan_service import mark_executive_summary_stale

router = APIRouter()


@router.patch("/report/{scan_id}/cuecs/{cuec_id}/annotation")
async def patch_cuec_annotation(scan_id: int, cuec_id: str, data: Dict[str, Any] = Body(...), db=Depends(get_db)):
    """Update CUEC annotation by TSC ID (legacy endpoint)."""
    cuec = (await db.execute(select(CUEC).where(CUEC.scan_id == scan_id, CUEC.cuec_tsc_id == cuec_id))).scalar_one_or_none()
    if not cuec:
        raise HTTPException(status_code=404, detail="CUEC not found")
    cuec.annotation = data.get("annotation", "")
    db.add(cuec)
    await db.commit()
    return {"status": "ok"}


@router.patch("/report/{scan_id}/cuecs/{cuec_id}")
async def patch_cuec(scan_id: int, cuec_id: int, data: Dict[str, Any] = Body(...), db=Depends(get_db)):
    """Update CUEC by database ID."""
    logging.debug(f"/report/{scan_id}/cuecs/{cuec_id} payload: {data}")
    try:
        cuec = (await db.execute(select(CUEC).where(CUEC.scan_id == scan_id, CUEC.id == cuec_id))).scalar_one_or_none()
        if not cuec:
            return JSONResponse({"error": "CUEC not found"}, status_code=404)
        justification_note = None
        if "cuec_confidence" in data:
            old = getattr(cuec, "cuec_confidence", None)
            new_val = None
            try:
                val = data["cuec_confidence"]
                if isinstance(val, str):
                    s = val.strip()
                    if s.endswith('%'):
                        n = float(s[:-1])
                        new_val = n / 100.0
                    else:
                        n = float(s)
                        new_val = (n / 100.0) if n > 1 else n
                elif isinstance(val, (int, float)):
                    f = float(val)
                    new_val = (f / 100.0) if f > 1 else f
            except Exception:
                new_val = None
            if new_val is not None:
                cuec.cuec_confidence = new_val
            justification_note = f"UI edit: cuec_confidence {old} -> {cuec.cuec_confidence}"
        if "cuec_confidence_justification" in data:
            # Always append, never overwrite
            prev = getattr(cuec, "cuec_confidence_justification", "") or ""
            sep = "\n" if prev else ""
            cuec.cuec_confidence_justification = f"{prev}{sep}{data['cuec_confidence_justification']}"
        if "annotation" in data:
            cuec.annotation = data["annotation"]
        if "analyst_notes" in data:
            cuec.analyst_notes = data["analyst_notes"]
        if "control_strength" in data:
            cuec.control_strength = data["control_strength"]
        # New: allow editing CUEC text fields
        if "cuec_description" in data:
            cuec.cuec_description = data["cuec_description"]
        if "cuec_gpt_reasoning" in data:
            cuec.cuec_gpt_reasoning = data["cuec_gpt_reasoning"]
        if "cuec_justification" in data:
            cuec.cuec_justification = data["cuec_justification"]
        # Append auto audit note
        if justification_note:
            prev = getattr(cuec, "cuec_confidence_justification", "") or ""
            sep = "\n" if prev else ""
            cuec.cuec_confidence_justification = f"{prev}{sep}{justification_note}"
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        db.add(cuec)
        await db.commit()
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/cuecs/{cuec_id} DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.patch("/report/{scan_id}/cuecs/tsc/{cuec_tsc_id}")
async def patch_cuec_by_tsc(scan_id: int, cuec_tsc_id: str, data: Dict[str, Any] = Body(...), db=Depends(get_db)):
    """Legacy-compatible route to update a CUEC by its TSC ID.
    If multiple rows share the TSC ID within a scan, returns 409 to avoid ambiguity.
    Prefer the numeric ID route: /report/{scan_id}/cuecs/{id}
    """
    logging.debug(f"/report/{scan_id}/cuecs/tsc/{cuec_tsc_id} payload: {data}")
    try:
        try:
            cuec = (await db.execute(
                select(CUEC).where(CUEC.scan_id == scan_id, CUEC.cuec_tsc_id == cuec_tsc_id)
            )).scalar_one_or_none()
        except MultipleResultsFound:
            return JSONResponse({
                "error": "Multiple CUECs matched cuec_tsc_id. Use ID endpoint /report/{scan_id}/cuecs/{id}"
            }, status_code=409)
        if not cuec:
            return JSONResponse({"error": "CUEC not found"}, status_code=404)
        justification_note = None
        if "cuec_confidence" in data:
            old = getattr(cuec, "cuec_confidence", None)
            new_val = None
            try:
                val = data["cuec_confidence"]
                if isinstance(val, str):
                    s = val.strip()
                    if s.endswith('%'):
                        n = float(s[:-1])
                        new_val = n / 100.0
                    else:
                        n = float(s)
                        new_val = (n / 100.0) if n > 1 else n
                elif isinstance(val, (int, float)):
                    f = float(val)
                    new_val = (f / 100.0) if f > 1 else f
            except Exception:
                new_val = None
            if new_val is not None:
                cuec.cuec_confidence = new_val
            justification_note = f"UI edit: cuec_confidence {old} -> {cuec.cuec_confidence}"
        if "cuec_confidence_justification" in data:
            prev = getattr(cuec, "cuec_confidence_justification", "") or ""
            sep = "\n" if prev else ""
            cuec.cuec_confidence_justification = f"{prev}{sep}{data['cuec_confidence_justification']}"
        if "annotation" in data:
            cuec.annotation = data["annotation"]
        if "control_strength" in data:
            cuec.control_strength = data["control_strength"]
        if "cuec_description" in data:
            cuec.cuec_description = data["cuec_description"]
        if "cuec_gpt_reasoning" in data:
            cuec.cuec_gpt_reasoning = data["cuec_gpt_reasoning"]
        if "cuec_justification" in data:
            cuec.cuec_justification = data["cuec_justification"]
        if justification_note:
            prev = getattr(cuec, "cuec_confidence_justification", "") or ""
            sep = "\n" if prev else ""
            cuec.cuec_confidence_justification = f"{prev}{sep}{justification_note}"
        await mark_executive_summary_stale(scan_id, db)
        db.add(cuec)
        await db.commit()
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/cuecs/tsc/{cuec_tsc_id} DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/report/{scan_id}/cuecs/{cuec_id}/recompute_frameworks")
async def recompute_cuec_frameworks(scan_id: int, cuec_id: int, db=Depends(get_db)):
    """Recompute framework mappings for a CUEC using dynamic multi-framework system.
    
    Phase 2: Now supports unlimited frameworks beyond TSC/COSO based on report type.
    
    Updates and persists:
    - framework_mappings: Universal JSON with all framework mappings
    - primary_framework, primary_criterion_id, primary_confidence
    - Legacy columns: cuec_tsc_mappings, cuec_coso_mappings (backward compatibility)
    """
    try:
        from ..services.framework_mapping_service import recompute_cuec_framework_mappings
        
        result = await recompute_cuec_framework_mappings(scan_id, cuec_id, db)
        
        if result.get("success"):
            return result
        else:
            return JSONResponse(result, status_code=500)
            
    except Exception as e:
        logging.error(f"Error recomputing CUEC frameworks for {cuec_id}: {e}")
        return JSONResponse({"error": str(e), "success": False}, status_code=500)
