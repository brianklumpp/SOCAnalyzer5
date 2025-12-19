"""
Router for control operations including CRUD, merge, split, and link operations.
"""
import logging
import datetime
import traceback
from typing import Dict, Any, Tuple

from fastapi import APIRouter, Depends, Body, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import and_
from sqlalchemy.future import select
from sqlalchemy.exc import MultipleResultsFound

from ..models import Control, Scan
from ..models import User
from ..database import get_db
from ..services import merge_service
from ..services.scan_service import mark_executive_summary_stale
from ..auth.dependencies import get_current_active_user
from .. import config as cfg

router = APIRouter()


def _parse_page_refs(value):
    """Parse page references from various formats to list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        if ',' in value:
            return [p.strip() for p in value.split(',')]
        return [value.strip()]
    if isinstance(value, int):
        return [str(value)]
    return []


@router.patch("/report/{scan_id}/controls/annotation/{control_id}")
async def patch_control_annotation(scan_id: int, control_id: str, data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Update control annotation by control_id (legacy endpoint, may match multiple)."""
    try:
        ctrl = (await db.execute(select(Control).where(Control.scan_id == scan_id, Control.control_id == control_id))).scalar_one_or_none()
    except MultipleResultsFound:
        return JSONResponse({
            "error": "Multiple controls matched control_id. Use ID endpoint /report/{scan_id}/controls/id/{control_db_id}"
        }, status_code=409)
    if not ctrl:
        raise HTTPException(status_code=404, detail="Control not found")
    ctrl.annotation = data.get("annotation", "")
    db.add(ctrl)
    await db.commit()
    return {"status": "ok"}


@router.patch("/report/{scan_id}/controls/{control_id}")
async def patch_control(scan_id: int, control_id: str, data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Update control by control_id (legacy endpoint, prefer ID-based endpoint)."""
    logging.info(f"[CONTROL PATCH] scan_id={scan_id}, control_id={control_id}, payload keys: {list(data.keys())}")
    logging.debug(f"/report/{scan_id}/controls/{control_id} payload: {data}")
    try:
        try:
            ctrl = (await db.execute(select(Control).where(Control.scan_id == scan_id, Control.control_id == control_id))).scalar_one_or_none()
        except MultipleResultsFound:
            return JSONResponse({
                "error": "Multiple controls matched control_id. Use ID endpoint /report/{scan_id}/controls/id/{control_db_id}"
            }, status_code=409)
        if not ctrl:
            return JSONResponse({"error": "Control not found"}, status_code=404)
        
        # Update allowed fields
        justification_note = None
        if "control_confidence" in data:
            old = getattr(ctrl, "control_confidence", None)
            new_val = None
            try:
                val = data["control_confidence"]
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
                ctrl.control_confidence = new_val
            justification_note = f"UI edit: control_confidence {old} -> {ctrl.control_confidence}"
        
        if "analyst_notes" in data:
            ctrl.analyst_notes = data["analyst_notes"]
            now = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
            existing = ctrl.edit_log or ""
            separator = "\n" if existing and not existing.endswith("\n") else ""
            ctrl.edit_log = f"{existing}{separator}Analyst notes updated by {current_user.username} ({now})"
        elif "confidence_calc" in data:
            ctrl.confidence_calc = data["confidence_calc"]
        # Note: edit_log is auto-generated only, skip if sent from frontend
        
        if "annotation" in data:
            ctrl.annotation = data["annotation"]
        if "control_id" in data:
            ctrl.control_id = data["control_id"]
        if "control_desc" in data:
            ctrl.control_desc = data["control_desc"]
        if "control_test" in data:
            ctrl.control_test = data["control_test"]
        if "control_test_results" in data:
            ctrl.control_test_results = data["control_test_results"]
        if "control_page_refs" in data or "control_page_ref" in data:
            ctrl.control_page_refs = _parse_page_refs(data.get("control_page_refs") or data.get("control_page_ref"))
        if "has_deviation" in data:
            ctrl.has_deviation = data["has_deviation"]
        if "deviation_desc" in data:
            ctrl.deviation_desc = data["deviation_desc"]
        
        # Auto-populate deviation_desc from control_test_results if has_deviation=true but deviation_desc is blank
        if ctrl.has_deviation and not (ctrl.deviation_desc or "").strip():
            test_results = ctrl.control_test_results or ""
            if test_results:
                # Extract deviation text after "Deviation noted."
                import re
                match = re.search(r'Deviation noted\.\s*(.+?)(?:\n\n|$)', test_results, re.IGNORECASE | re.DOTALL)
                if match:
                    ctrl.deviation_desc = match.group(1).strip()
                # Fallback: use first 300 chars of test_results if it contains "deviation"
                elif 'deviation' in test_results.lower() or 'exception' in test_results.lower():
                    ctrl.deviation_desc = test_results[:300].strip()
        
        # Append audit note to edit_log
        if justification_note:
            prev = getattr(ctrl, "edit_log", "") or ""
            sep = ",\n" if prev else ""
            now = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
            ctrl.edit_log = f"{prev}{sep}{justification_note} by {current_user.username} ({now})"
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        db.add(ctrl)
        await db.commit()
        await db.refresh(ctrl)
        
        return {
            "id": ctrl.id,
            "control_id": ctrl.control_id,
            "control_desc": ctrl.control_desc,
            "control_test": ctrl.control_test,
            "control_test_results": ctrl.control_test_results,
            "control_confidence": ctrl.control_confidence,
            "confidence_calc": ctrl.confidence_calc,
            "edit_log": ctrl.edit_log,
            "analyst_notes": ctrl.analyst_notes,
            "annotation": ctrl.annotation,
            "framework_mappings": ctrl.framework_mappings,
            "primary_framework": ctrl.primary_framework,
            "primary_criterion_id": ctrl.primary_criterion_id,
            "primary_confidence": ctrl.primary_confidence,
            "control_page_refs": ctrl.control_page_refs,
            "has_deviation": ctrl.has_deviation,
            "deviation_desc": ctrl.deviation_desc
        }
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/controls/{control_id} DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.patch("/report/{scan_id}/controls/id/{control_db_id}")
async def patch_control_by_db_id(scan_id: int, control_db_id: int, data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Update a control by its numeric database ID to avoid duplicate control_id ambiguity."""
    logging.info(f"[CONTROL PATCH BY ID] scan_id={scan_id}, control_db_id={control_db_id}, payload keys: {list(data.keys())}")
    logging.debug(f"[PATCH CONTROL] scan_id={scan_id}, control_id={control_db_id}, payload keys: {list(data.keys())}")
    try:
        ctrl = (await db.execute(select(Control).where(Control.scan_id == scan_id, Control.id == control_db_id))).scalar_one_or_none()
        if not ctrl:
            return JSONResponse({"error": "Control not found"}, status_code=404)
        
        justification_note = None
        if "control_confidence" in data:
            old = getattr(ctrl, "control_confidence", None)
            new_val = None
            try:
                val = data["control_confidence"]
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
                ctrl.control_confidence = new_val
            justification_note = f"UI edit: control_confidence {old} -> {ctrl.control_confidence}"
        
        if "analyst_notes" in data:
            ctrl.analyst_notes = data["analyst_notes"]
            now = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
            existing = ctrl.edit_log or ""
            separator = "\n" if existing and not existing.endswith("\n") else ""
            ctrl.edit_log = f"{existing}{separator}Analyst notes updated by {current_user.username} ({now})"
        elif "confidence_calc" in data:
            ctrl.confidence_calc = data["confidence_calc"]
        # Note: edit_log is auto-generated only, skip if sent from frontend
        
        if "annotation" in data:
            ctrl.annotation = data["annotation"]
        if "control_id" in data:
            ctrl.control_id = data["control_id"]
        if "control_desc" in data:
            ctrl.control_desc = data["control_desc"]
        if "control_test" in data:
            ctrl.control_test = data["control_test"]
        if "control_test_results" in data:
            ctrl.control_test_results = data["control_test_results"]
        if "control_page_refs" in data or "control_page_ref" in data:
            ctrl.control_page_refs = _parse_page_refs(data.get("control_page_refs") or data.get("control_page_ref"))
        if "has_deviation" in data:
            ctrl.has_deviation = data["has_deviation"]
        if "deviation_desc" in data:
            ctrl.deviation_desc = data["deviation_desc"]
        
        # Auto-populate deviation_desc from control_test_results if has_deviation=true but deviation_desc is blank
        if ctrl.has_deviation and not (ctrl.deviation_desc or "").strip():
            test_results = ctrl.control_test_results or ""
            if test_results:
                # Extract deviation text after "Deviation noted."
                import re
                match = re.search(r'Deviation noted\.\s*(.+?)(?:\n\n|$)', test_results, re.IGNORECASE | re.DOTALL)
                if match:
                    ctrl.deviation_desc = match.group(1).strip()
                # Fallback: use first 300 chars of test_results if it contains "deviation"
                elif 'deviation' in test_results.lower() or 'exception' in test_results.lower():
                    ctrl.deviation_desc = test_results[:300].strip()
        
        if justification_note:
            prev = getattr(ctrl, "edit_log", "") or ""
            sep = ",\n" if prev else ""
            now = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
            ctrl.edit_log = f"{prev}{sep}{justification_note} by {current_user.username} ({now})"
        
        # Update audit fields
        ctrl.updated_at = datetime.datetime.utcnow()
        ctrl.updated_by_user_id = current_user.id
        
        await mark_executive_summary_stale(scan_id, db)
        db.add(ctrl)
        await db.commit()
        await db.refresh(ctrl)
        
        # Get username for updated_by
        updated_by_username = None
        if ctrl.updated_by_user_id:
            user_result = await db.execute(select(User).where(User.id == ctrl.updated_by_user_id))
            user = user_result.scalar_one_or_none()
            if user:
                updated_by_username = user.username
        
        return {
            "id": ctrl.id,
            "control_id": ctrl.control_id,
            "control_desc": ctrl.control_desc,
            "control_test": ctrl.control_test,
            "control_test_results": ctrl.control_test_results,
            "control_confidence": ctrl.control_confidence,
            "confidence_calc": ctrl.confidence_calc,
            "edit_log": ctrl.edit_log,
            "analyst_notes": ctrl.analyst_notes,
            "annotation": ctrl.annotation,
            "framework_mappings": ctrl.framework_mappings,
            "primary_framework": ctrl.primary_framework,
            "primary_criterion_id": ctrl.primary_criterion_id,
            "primary_confidence": ctrl.primary_confidence,
            "control_page_refs": ctrl.control_page_refs,
            "has_deviation": ctrl.has_deviation,
            "deviation_desc": ctrl.deviation_desc,
            "updated_at": ctrl.updated_at.isoformat() if ctrl.updated_at else None,
            "updated_by": updated_by_username or "System" if ctrl.updated_at and not ctrl.updated_by_user_id else updated_by_username
        }
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/controls/{control_db_id} DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/report/{scan_id}/cleanup")
async def trigger_cleanup(scan_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Manually trigger automated cleanup for a scan."""
    try:
        cleanup_stats = await merge_service.automated_cleanup(scan_id, db)
        if cleanup_stats:
            return {"status": "success", "stats": cleanup_stats}
        else:
            return {"status": "error", "message": "Cleanup failed"}
    except Exception as e:
        logging.error(f"Error triggering cleanup: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/report/{scan_id}/controls/suggest-merges")
async def suggest_control_merges(scan_id: int, db=Depends(get_db)):
    """
    Analyze controls and suggest merges for identical control_ids.
    
    Returns merge suggestions with confidence scores based on:
    - Description similarity (GPT-based, 70% weight)
    - TSC/COSO mapping matches (15% weight)
    - Test procedure similarity (10% weight)
    - Deviation flag agreement (5% weight)
    
    Only returns suggestions with confidence >= MERGE_SUGGESTION_MIN_CONFIDENCE (default 0.85)
    """
    try:
        result = await merge_service.suggest_control_merges(scan_id, db)
        return result
    except Exception as e:
        logging.error(f"Error suggesting merges for scan {scan_id}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/report/{scan_id}/controls/merge")
async def merge_controls(scan_id: int, data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Merge duplicate controls into a primary control with intelligent selection.
    
    Request body:
    {
        "primary_control_id": 123,  // Database ID of suggested primary (optional)
        "merge_control_ids": [456, 789]  // Database IDs of controls to merge
    }
    """
    try:
        suggested_primary_id = data.get("primary_control_id")
        merge_ids = data.get("merge_control_ids", [])
        
        result = await merge_service.merge_controls_action(
            scan_id,
            suggested_primary_id,
            merge_ids,
            db
        )
        
        if result.get("status") == "error":
            return JSONResponse(result, status_code=500)
        
        return result
        
    except Exception as e:
        await db.rollback()
        logging.error(f"Error merging controls for scan {scan_id}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/report/{scan_id}/controls/{control_db_id}/split")
async def split_control(scan_id: int, control_db_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Undo a control merge by restoring merged controls.
    """
    try:
        result = await merge_service.split_control(scan_id, control_db_id, db)
        
        if result.get("status") == "error":
            return JSONResponse(result, status_code=400 if "not merged" in result.get("error", "") else 500)
        
        return result
        
    except Exception as e:
        await db.rollback()
        logging.error(f"Error splitting control {control_db_id} for scan {scan_id}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/report/{scan_id}/controls/link")
@router.post("/report/{scan_id}/controls/link_instances")  # Alias for frontend compatibility
async def link_control_instances(scan_id: int, data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Link controls as instances of the same control (for CRITERIA_VARIANT or TEST_VARIANT).
    
    Request body:
    {
        "control_db_ids": [123, 456, 789],  // Database IDs to link
        "instance_differentiator": "TSC criteria"  // Optional description of what varies
    }
    """
    try:
        # Accept both control_ids and control_db_ids for frontend compatibility
        control_ids = data.get("control_db_ids") or data.get("control_ids", [])
        differentiator = data.get("instance_differentiator", "")
        
        if len(control_ids) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 controls to link")
        
        # Get all controls
        result = await db.execute(
            select(Control).where(Control.scan_id == scan_id, Control.id.in_(control_ids))
        )
        controls = result.scalars().all()
        
        if len(controls) < 2:
            raise HTTPException(status_code=404, detail="Not all controls found")
        
        # Generate group ID
        import uuid
        group_id = str(uuid.uuid4())
        
        # Mark all as duplicate instances
        for ctrl in controls:
            ctrl.is_duplicate_instance = True
            ctrl.duplicate_group_id = group_id
            ctrl.instance_differentiator = differentiator
            ctrl.merged_to_control_id = 'DUPLICATE_INSTANCE'  # Special marker
            db.add(ctrl)
        
        await mark_executive_summary_stale(scan_id, db)
        await db.commit()
        
        return {
            "status": "ok",
            "linked_count": len(controls),
            "group_id": group_id,
            "linked_ids": [c.id for c in controls]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"Error linking controls for scan {scan_id}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/report/{scan_id}/controls/{control_id}/unlink")
async def unlink_control_instance(scan_id: int, control_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Remove a control from its duplicate instance group."""
    try:
        ctrl = (await db.execute(
            select(Control).where(Control.scan_id == scan_id, Control.id == control_id)
        )).scalar_one_or_none()
        
        if not ctrl:
            raise HTTPException(status_code=404, detail="Control not found")
        
        ctrl.is_duplicate_instance = False
        ctrl.duplicate_group_id = None
        ctrl.instance_differentiator = None
        ctrl.merged_to_control_id = None
        db.add(ctrl)
        
        await mark_executive_summary_stale(scan_id, db)
        await db.commit()
        
        return {"status": "ok", "control_id": control_id}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"Error unlinking control {control_id}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/report/{scan_id}/controls/dismiss-merge")
@router.post("/report/{scan_id}/controls/dismiss_merge_suggestion")  # Alias for frontend compatibility
async def dismiss_merge_suggestion(scan_id: int, data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Mark a merge suggestion as dismissed (user reviewed and rejected)."""
    try:
        # This is a no-op endpoint for frontend workflow
        # In the future, could track dismissed suggestions in a separate table
        return {"status": "ok", "message": "Merge suggestion dismissed"}
    except Exception as e:
        logging.error(f"Error dismissing merge suggestion: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/report/{scan_id}/controls/duplicate-groups")
async def get_duplicate_groups(scan_id: int, db=Depends(get_db)):
    """Get all duplicate instance groups for a scan."""
    try:
        result = await db.execute(
            select(Control).where(
                Control.scan_id == scan_id,
                Control.is_duplicate_instance == True,
                Control.duplicate_group_id != None
            ).order_by(Control.duplicate_group_id, Control.control_seq)
        )
        duplicate_controls = result.scalars().all()
        
        # Group by duplicate_group_id
        groups = {}
        for ctrl in duplicate_controls:
            group_id = ctrl.duplicate_group_id
            if group_id not in groups:
                groups[group_id] = {
                    "group_id": group_id,
                    "control_id": ctrl.control_id,
                    "controls": []
                }
            
            groups[group_id]["controls"].append({
                "id": ctrl.id,
                "control_seq": ctrl.control_seq,
                "control_desc": ctrl.control_desc,
                "control_test": ctrl.control_test,
                "framework_mappings": ctrl.framework_mappings,
                "primary_framework": ctrl.primary_framework,
                "primary_criterion_id": ctrl.primary_criterion_id,
                "control_confidence": ctrl.control_confidence,
                "instance_differentiator": ctrl.instance_differentiator
            })
        
        return {
            "success": True,
            "total_groups": len(groups),
            "groups": list(groups.values())
        }
        
    except Exception as e:
        logging.error(f"Error fetching duplicate groups: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/report/{scan_id}/controls/{control_db_id}/recompute_frameworks")
@router.post("/report/{scan_id}/controls/id/{control_db_id}/recompute_frameworks")  # Alias for frontend
async def recompute_control_frameworks(scan_id: int, control_db_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Recompute framework mappings for a control using dynamic multi-framework system."""
    try:
        from ..services.framework_mapping_service import recompute_control_framework_mappings
        
        result = await recompute_control_framework_mappings(scan_id, control_db_id, db)
        
        if result.get("success"):
            return result
        else:
            return JSONResponse(result, status_code=500)
            
    except Exception as e:
        logging.error(f"Error recomputing control frameworks for {control_db_id}: {e}")
        return JSONResponse({"error": str(e), "success": False}, status_code=500)


@router.post("/report/{scan_id}/controls/batch_recompute")
async def batch_recompute_control_frameworks(scan_id: int, data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Batch recompute framework mappings for multiple controls."""
    try:
        control_ids = data.get("control_ids", [])
        
        if not control_ids:
            raise HTTPException(status_code=400, detail="control_ids required")
        
        from ..services.framework_mapping_service import recompute_control_framework_mappings
        
        results = []
        for control_id in control_ids:
            try:
                result = await recompute_control_framework_mappings(scan_id, control_id, db)
                results.append(result)
            except Exception as e:
                logging.error(f"Error recomputing frameworks for control {control_id}: {e}")
                results.append({"success": False, "control_id": control_id, "error": str(e)})
        
        success_count = sum(1 for r in results if r.get("success"))
        
        return {
            "success": True,
            "total": len(control_ids),
            "success_count": success_count,
            "failed_count": len(control_ids) - success_count,
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in batch recompute: {e}")
        return JSONResponse({"error": str(e), "success": False}, status_code=500)


@router.post("/report/{scan_id}/controls/recompute_all_high_confidence")
async def recompute_all_high_confidence_controls(scan_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Recompute framework mappings for all high confidence controls (confidence > 70%)."""
    try:
        # Get all high confidence controls for this scan
        result = await db.execute(
            select(Control).where(
                Control.scan_id == scan_id,
                Control.control_confidence > 0.7
            )
        )
        high_conf_controls = result.scalars().all()
        
        if not high_conf_controls:
            return {
                "success": True,
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "message": "No high confidence controls found (confidence > 70%)"
            }
        
        from ..services.framework_mapping_service import recompute_control_framework_mappings
        
        results = []
        success_count = 0
        failed_count = 0
        
        for control in high_conf_controls:
            try:
                result = await recompute_control_framework_mappings(scan_id, control.id, db)
                results.append(result)
                if result.get("success"):
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logging.error(f"Error recomputing frameworks for control {control.id}: {e}")
                results.append({"success": False, "control_id": control.id, "error": str(e)})
                failed_count += 1
        
        return {
            "success": True,
            "total": len(high_conf_controls),
            "success_count": success_count,
            "failed_count": failed_count,
            "message": f"Recomputed {success_count} of {len(high_conf_controls)} high confidence controls",
            "results": results
        }
        
    except Exception as e:
        logging.error(f"Error in bulk recompute for high confidence controls: {e}")
        return JSONResponse({"error": str(e), "success": False}, status_code=500)


@router.post("/report/{scan_id}/controls/preview_mappings")
async def preview_framework_mappings(scan_id: int, data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Preview framework mappings without persisting (for testing/debugging)."""
    try:
        control_desc = data.get("control_desc", "")
        
        if not control_desc:
            raise HTTPException(status_code=400, detail="control_desc required")
        
        from ..services.framework_mapping_service import compute_framework_mappings
        
        # Get scan to determine report type
        scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        report_type = scan.report_type.value if scan.report_type else "SOC2"
        
        mappings = await compute_framework_mappings(control_desc, report_type, db)
        
        return {
            "success": True,
            "mappings": mappings,
            "report_type": report_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error previewing mappings: {e}")
        return JSONResponse({"error": str(e), "success": False}, status_code=500)
