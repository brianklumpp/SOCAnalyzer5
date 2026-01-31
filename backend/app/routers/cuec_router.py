"""
Router for CUEC (Complementary User Entity Control) operations.
"""
import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, Body, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.future import select
from sqlalchemy.exc import MultipleResultsFound

from ..models import CUEC, Scan
from ..models import User
from ..database import get_db
from ..services.scan_service import mark_executive_summary_stale
from ..auth.dependencies import get_current_active_user

router = APIRouter()

from ..extractors.cuec_extractor import map_cuecs_to_objectives


def _norm_pct_like(val):
    """Normalize percentage-like values to 0-1 float."""
    if val is None:
        return None
    try:
        if isinstance(val, str):
            s = val.strip()
            if s.endswith('%'):
                return float(s[:-1]) / 100.0
            n = float(s)
            return n / 100.0 if n > 1 else n
        elif isinstance(val, (int, float)):
            f = float(val)
            return f / 100.0 if f > 1 else f
    except Exception:
        return None
    return None


@router.post("/report/{scan_id}/cuecs")
async def create_cuec(scan_id: int, data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Create a new CUEC row for a scan."""
    try:
        logging.info(f"[CREATE_CUEC] Request data for scan {scan_id}: {data}")
        logging.info(f"[CREATE_CUEC] User: {current_user.username}")
        
        desc = str(data.get("cuec_description", "")).strip()
        if not desc:
            logging.error(f"[CREATE_CUEC] Missing required field: cuec_description")
            raise HTTPException(status_code=400, detail="cuec_description is required")
        conf = _norm_pct_like(data.get("cuec_confidence"))
        
        # Default confidence to 0.9 (90%) for manual entries
        if conf is None:
            conf = 0.9
        
        # Generate initial confidence justification and edit log
        timestamp = datetime.now().isoformat()
        initial_justification = data.get("cuec_confidence_justification") or f"Manually added with {int(conf * 100)}% confidence"
        initial_edit_log = f"CUEC manually created [{timestamp}]"
        
        cuec = CUEC(
            scan_id=scan_id,
            cuec_description=desc,
            cuec_confidence=conf,
            control_strength=(data.get("control_strength") or None),
            cuec_confidence_justification=initial_justification,
            cuec_gpt_reasoning=data.get("cuec_gpt_reasoning"),
            cuec_justification=data.get("cuec_justification"),
            annotation=data.get("annotation"),
            analyst_notes=data.get("analyst_notes"),
            edit_log=initial_edit_log,
        )
        db.add(cuec)
        await mark_executive_summary_stale(scan_id, db)
        await db.commit()
        await db.refresh(cuec)
        return {
            "id": cuec.id,
            "cuec_description": cuec.cuec_description,
            "cuec_confidence": cuec.cuec_confidence,
            "control_strength": cuec.control_strength,
            "cuec_confidence_justification": cuec.cuec_confidence_justification,
            "cuec_gpt_reasoning": cuec.cuec_gpt_reasoning,
            "cuec_justification": cuec.cuec_justification,
            "annotation": cuec.annotation,
            "analyst_notes": cuec.analyst_notes,
            "edit_log": cuec.edit_log,
            "framework_mappings": cuec.framework_mappings,
            "primary_framework": cuec.primary_framework,
            "primary_criterion_id": cuec.primary_criterion_id,
            "primary_confidence": cuec.primary_confidence,
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"[CREATE_CUEC] Error creating CUEC: {str(e)}")
        import traceback
        logging.error(f"[CREATE_CUEC] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/report/{scan_id}/cuecs/{cuec_id}/annotation")
async def patch_cuec_annotation(scan_id: int, cuec_id: str, data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Update CUEC annotation by TSC ID (legacy endpoint)."""
    cuec = (await db.execute(select(CUEC).where(CUEC.scan_id == scan_id, CUEC.cuec_tsc_id == cuec_id))).scalar_one_or_none()
    if not cuec:
        raise HTTPException(status_code=404, detail="CUEC not found")
    cuec.annotation = data.get("annotation", "")
    db.add(cuec)
    await db.commit()
    return {"status": "ok"}


@router.patch("/report/{scan_id}/cuecs/{cuec_id}")
async def patch_cuec(scan_id: int, cuec_id: int, data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
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
        # Note: edit_log is auto-generated only, skip if sent from frontend
        if "annotation" in data:
            cuec.annotation = data["annotation"]
        if "analyst_notes" in data:
            cuec.analyst_notes = data["analyst_notes"]
            prev_log = getattr(cuec, "edit_log", "") or ""
            sep = ",\n" if prev_log else ""
            cuec.edit_log = f"{prev_log}{sep}Analyst notes updated by {current_user.username} [{datetime.now().isoformat()}]"
        if "control_strength" in data:
            cuec.control_strength = data["control_strength"]
        # New: allow editing CUEC text fields
        if "cuec_description" in data:
            cuec.cuec_description = data["cuec_description"]
        if "cuec_gpt_reasoning" in data:
            cuec.cuec_gpt_reasoning = data["cuec_gpt_reasoning"]
        if "cuec_justification" in data:
            cuec.cuec_justification = data["cuec_justification"]
        # Append confidence change to edit log
        if justification_note:
            prev_log = getattr(cuec, "edit_log", "") or ""
            sep = ",\n" if prev_log else ""
            now = datetime.now().strftime("%Y-%m-%d %I:%M %p")
            cuec.edit_log = f"{prev_log}{sep}{justification_note} by {current_user.username} ({now})"
        
        # Update audit fields
        cuec.updated_at = datetime.now()
        cuec.updated_by_user_id = current_user.id
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        db.add(cuec)
        await db.commit()
        await db.refresh(cuec)
        
        # Get username for updated_by
        updated_by_username = None
        if cuec.updated_by_user_id:
            from ..models import User
            user_result = await db.execute(select(User).where(User.id == cuec.updated_by_user_id))
            user = user_result.scalar_one_or_none()
            if user:
                updated_by_username = user.username
        
        return {
            "id": cuec.id,
            "cuec_description": cuec.cuec_description,
            "cuec_confidence": cuec.cuec_confidence,
            "cuec_confidence_justification": cuec.cuec_confidence_justification,
            "edit_log": cuec.edit_log,
            "analyst_notes": cuec.analyst_notes,
            "annotation": cuec.annotation,
            "control_strength": cuec.control_strength,
            "cuec_gpt_reasoning": cuec.cuec_gpt_reasoning,
            "cuec_justification": cuec.cuec_justification,
            "updated_at": cuec.updated_at.isoformat() if cuec.updated_at else None,
            "updated_by": updated_by_username or "System" if cuec.updated_at and not cuec.updated_by_user_id else updated_by_username
        }
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/cuecs/{cuec_id} DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/report/{scan_id}/cuecs/objectives/map")
async def map_cuec_objectives_endpoint(
    scan_id: int,
    force: bool = False,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Map objectives to CUECs for this scan."""
    try:
        from ..database import sync_engine
        from sqlalchemy.orm import sessionmaker

        SessionLocal = sessionmaker(bind=sync_engine)
        sync_db = SessionLocal()
        try:
            mappings_created = map_cuecs_to_objectives(scan_id, sync_db, force=force)
            return {
                "status": "success",
                "mappings_created": mappings_created
            }
        finally:
            sync_db.close()
    except Exception as e:
        logging.error(f"Failed to map CUECs to objectives for scan {scan_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.patch("/report/{scan_id}/cuecs/tsc/{cuec_tsc_id}")
async def patch_cuec_by_tsc(scan_id: int, cuec_tsc_id: str, data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
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
        # Note: edit_log is auto-generated only, skip if sent from frontend
        if "annotation" in data:
            cuec.annotation = data["annotation"]
        if "analyst_notes" in data:
            cuec.analyst_notes = data["analyst_notes"]
            prev_log = getattr(cuec, "edit_log", "") or ""
            sep = ",\n" if prev_log else ""
            cuec.edit_log = f"{prev_log}{sep}Analyst notes updated by {current_user.username} [{datetime.now().isoformat()}]"
        if "control_strength" in data:
            cuec.control_strength = data["control_strength"]
        if "cuec_description" in data:
            cuec.cuec_description = data["cuec_description"]
        if "cuec_gpt_reasoning" in data:
            cuec.cuec_gpt_reasoning = data["cuec_gpt_reasoning"]
        if "cuec_justification" in data:
            cuec.cuec_justification = data["cuec_justification"]
        if justification_note:
            prev_log = getattr(cuec, "edit_log", "") or ""
            sep = ",\n" if prev_log else ""
            cuec.edit_log = f"{prev_log}{sep}{justification_note} [{datetime.now().isoformat()}]"
        await mark_executive_summary_stale(scan_id, db)
        db.add(cuec)
        await db.commit()
        await db.refresh(cuec)
        return {
            "id": cuec.id,
            "cuec_description": cuec.cuec_description,
            "cuec_confidence": cuec.cuec_confidence,
            "cuec_confidence_justification": cuec.cuec_confidence_justification,
            "edit_log": cuec.edit_log,
            "analyst_notes": cuec.analyst_notes,
            "annotation": cuec.annotation,
            "control_strength": cuec.control_strength,
            "cuec_gpt_reasoning": cuec.cuec_gpt_reasoning,
            "cuec_justification": cuec.cuec_justification
        }
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/cuecs/tsc/{cuec_tsc_id} DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/report/{scan_id}/cuecs/recompute_all_high_confidence")
async def recompute_all_high_confidence_cuecs(scan_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Recompute framework mappings for all high confidence CUECs (confidence > 70%)."""
    try:
        # Get all high confidence CUECs for this scan
        result = await db.execute(
            select(CUEC).where(
                CUEC.scan_id == scan_id,
                CUEC.cuec_confidence > 0.7
            )
        )
        high_conf_cuecs = result.scalars().all()
        
        if not high_conf_cuecs:
            return {
                "success": True,
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "message": "No high confidence CUECs found (confidence > 70%)"
            }
        
        from ..services.framework_mapping_service import recompute_cuec_framework_mappings
        
        results = []
        success_count = 0
        failed_count = 0
        
        for cuec in high_conf_cuecs:
            try:
                result = await recompute_cuec_framework_mappings(scan_id, cuec.id, db)
                results.append(result)
                if result.get("success"):
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logging.error(f"Error recomputing frameworks for CUEC {cuec.id}: {e}")
                results.append({"success": False, "cuec_id": cuec.id, "error": str(e)})
                failed_count += 1
        
        return {
            "success": True,
            "total": len(high_conf_cuecs),
            "success_count": success_count,
            "failed_count": failed_count,
            "message": f"Recomputed {success_count} of {len(high_conf_cuecs)} high confidence CUECs",
            "results": results
        }
        
    except Exception as e:
        logging.error(f"Error in bulk recompute for high confidence CUECs: {e}")
        return JSONResponse({"error": str(e), "success": False}, status_code=500)


@router.post("/report/{scan_id}/cuecs/{cuec_id}/recompute_frameworks")
async def recompute_cuec_frameworks(scan_id: int, cuec_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
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
