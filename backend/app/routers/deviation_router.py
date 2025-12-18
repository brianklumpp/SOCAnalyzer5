"""
Router for deviation-related operations.
"""
import logging
import asyncio
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.future import select

from ..models import Control
from ..models import User
from ..database import get_db, AsyncSessionLocal
from ..auth.dependencies import get_current_active_user
from .. import config as cfg

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/report/{scan_id}/deviations")
async def get_deviations(scan_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Get all high-confidence deviation controls for a scan.
    """
    try:
        result = await db.execute(
            select(Control)
            .where(Control.scan_id == scan_id)
            .where(Control.has_deviation == True)
            .where(Control.control_confidence >= cfg.HIGH_CONFIDENCE_THRESHOLD)
            .order_by(Control.control_seq)
        )
        deviation_controls = result.scalars().all()
        
        # Serialize controls - map database columns to frontend field names
        deviations = []
        for ctrl in deviation_controls:
            # Get first page ref from the JSON array if available
            page_ref = None
            if ctrl.control_page_refs and isinstance(ctrl.control_page_refs, list) and len(ctrl.control_page_refs) > 0:
                page_ref = ctrl.control_page_refs[0]
            
            deviations.append({
                "id": ctrl.id,
                "control_id": ctrl.control_id,
                "page_ref": page_ref,
                "control_description": ctrl.control_desc,
                "test_procedure": ctrl.control_test,
                "test_result": ctrl.control_test_results,
                "deviation": ctrl.has_deviation,
                "deviation_summary": ctrl.deviation_summary,
                "management_response_text": ctrl.management_response_text,
                "management_response_page_refs": ctrl.management_response_page_refs,
                "management_response_confidence": ctrl.management_response_confidence,
                "response_detection_method": ctrl.response_detection_method,
                "scan_id": ctrl.scan_id,
            })
        
        return deviations
        
    except Exception as e:
        logging.error(f"Error fetching deviations for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/report/{scan_id}/deviations/{control_id}")
async def update_deviation_summary(scan_id: int, control_id: int, data: dict, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Update the deviation_summary field for a control.
    """
    try:
        result = await db.execute(select(Control).where(Control.id == control_id))
        control = result.scalar_one_or_none()
        
        if not control:
            raise HTTPException(status_code=404, detail="Control not found")
        
        if "deviation_summary" in data:
            summary = data["deviation_summary"]
            # Truncate to 300 characters if needed
            if summary and len(summary) > 300:
                summary = summary[:297] + "..."
            control.deviation_summary = summary
            await db.commit()
            
            return {"status": "success", "deviation_summary": control.deviation_summary}
        
        return {"status": "no_change"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating deviation summary for control {control_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/deviations/{control_id}/regenerate")
async def regenerate_deviation_summary(scan_id: int, control_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Regenerate AI summary for a single deviation control.
    """
    try:
        from ..post_processors.deviation_summarizer import regenerate_single_summary
        
        summary = await regenerate_single_summary(control_id, db)
        
        if summary:
            return {"status": "success", "deviation_summary": summary}
        else:
            raise HTTPException(status_code=500, detail="Failed to generate summary")
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error regenerating deviation summary for control {control_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/deviations/regenerate_all")
@router.post("/report/{scan_id}/deviations/regenerate-all")  # Alias for frontend compatibility
async def regenerate_all_deviation_summaries(scan_id: int, background_tasks: BackgroundTasks, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Start background task to regenerate all deviation summaries for a scan.
    Returns immediately with status.
    """
    try:
        from ..post_processors.deviation_summarizer import generate_summaries
        import redis.asyncio as aioredis
        
        # Get Redis client
        redis_client = None
        try:
            redis_client = aioredis.from_url("redis://redis:6379", decode_responses=True)
        except Exception as e:
            logging.warning(f"Redis not available: {e}")
        
        # Start background task using asyncio.create_task
        async def background_regenerate():
            try:
                logging.info(f"Background task started for scan {scan_id}")
                async with AsyncSessionLocal() as db_session:
                    result = await generate_summaries(scan_id, db_session, redis_client)
                    logging.info(f"Background task completed for scan {scan_id}: {result}")
                if redis_client:
                    await redis_client.close()
            except Exception as e:
                logging.error(f"Background task error for scan {scan_id}: {e}")
        
        # Use asyncio.create_task instead of BackgroundTasks for async functions
        asyncio.create_task(background_regenerate())
        
        return {"status": "started", "scan_id": scan_id}
        
    except Exception as e:
        logging.error(f"Error starting regenerate all for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{scan_id}/deviations/regenerate_progress")
@router.get("/report/{scan_id}/deviations/regenerate-progress")  # Alias for frontend compatibility
async def get_regenerate_progress(scan_id: int, current_user: User = Depends(get_current_active_user)):
    """
    Get progress of deviation summary regeneration.
    Returns progress data from Redis.
    """
    try:
        import redis.asyncio as aioredis
        import json
        
        redis_client = aioredis.from_url("redis://redis:6379", decode_responses=True)
        redis_key = f"scan:{scan_id}:deviation_regen"
        
        progress_data = await redis_client.get(redis_key)
        await redis_client.close()
        
        if progress_data:
            return json.loads(progress_data)
        else:
            return {
                "current": 0,
                "total": 0,
                "status": "not_started",
                "timestamp": None
            }
            
    except Exception as e:
        logging.error(f"Error fetching regenerate progress for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/deviations/create")
async def create_deviation(scan_id: int, data: dict, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Create a new deviation control manually.
    Requires control_id reference for consistency.
    """
    try:
        # Validate required fields
        required_fields = ["control_id", "page_ref", "test_result"]
        for field in required_fields:
            if field not in data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Create new control with deviation=True
        new_control = Control(
            scan_id=scan_id,
            control_id=data.get("control_id"),
            page_ref=data.get("page_ref"),
            control_description=data.get("control_description"),
            test_procedure=data.get("test_procedure"),
            test_result=data.get("test_result"),
            deviation=True,
            deviation_summary=data.get("deviation_summary")  # Optional, can be None
        )
        
        db.add(new_control)
        await db.commit()
        await db.refresh(new_control)
        
        return {
            "status": "success",
            "control_id": new_control.id,
            "deviation_summary": new_control.deviation_summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error creating deviation for scan {scan_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{scan_id}/deviations/{control_id}/management-response")
async def get_management_response(
    scan_id: int,
    control_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get management response details for a specific deviation control.
    
    Returns:
        Dict with management response text, page refs, confidence, detection method, and related controls
    """
    try:
        # Fetch control
        result = await db.execute(select(Control).where(Control.id == control_id, Control.scan_id == scan_id))
        control = result.scalar_one_or_none()
        
        if not control:
            raise HTTPException(status_code=404, detail="Control not found")
        
        if not control.has_deviation:
            raise HTTPException(status_code=400, detail="Control does not have a deviation")
        
        # Get related controls (controls with same management response text)
        related_control_ids = []
        if control.management_response_text:
            result = await db.execute(
                select(Control)
                .where(
                    Control.scan_id == scan_id,
                    Control.management_response_text == control.management_response_text,
                    Control.id != control_id
                )
            )
            related_controls = result.scalars().all()
            related_control_ids = [ctrl.control_id for ctrl in related_controls if ctrl.control_id]
        
        return {
            "text": control.management_response_text,
            "page_refs": control.management_response_page_refs or [],
            "line_ref": control.management_response_line_ref,
            "confidence": control.management_response_confidence,
            "detection_method": control.response_detection_method,
            "related_control_ids": related_control_ids
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching management response for control {control_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/report/{scan_id}/deviations/{control_id}/management-response")
async def update_management_response(
    scan_id: int,
    control_id: int,
    data: dict,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Manually update or add management response for a deviation control.
    
    Request body:
        {
            "management_response_text": "Management's response text..."
        }
    """
    try:
        # Fetch control
        result = await db.execute(select(Control).where(Control.id == control_id, Control.scan_id == scan_id))
        control = result.scalar_one_or_none()
        
        if not control:
            raise HTTPException(status_code=404, detail="Control not found")
        
        if "management_response_text" in data:
            response_text = data["management_response_text"]
            
            # Update management response fields
            control.management_response_text = response_text if response_text else None
            control.response_detection_method = "manual"
            control.management_response_confidence = 1.0  # Manual entries have 100% confidence
            
            # Optionally update page refs if provided
            if "management_response_page_refs" in data:
                control.management_response_page_refs = data["management_response_page_refs"]
            
            await db.commit()
            
            return {
                "status": "success",
                "management_response_text": control.management_response_text,
                "confidence": control.management_response_confidence,
                "detection_method": control.response_detection_method
            }
        
        return {"status": "no_change"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating management response for control {control_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/deviations/{control_id}/regenerate-management-response")
async def regenerate_management_response(
    scan_id: int,
    control_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Re-run management response extraction for a single deviation control.
    
    Uses all fallback strategies to find the management response.
    """
    logging.error(f"[Regenerate Mgmt Response] Starting for scan_id={scan_id}, control_id={control_id}")
    try:
        # Fetch control
        result = await db.execute(select(Control).where(Control.id == control_id, Control.scan_id == scan_id))
        control = result.scalar_one_or_none()
        
        if not control:
            raise HTTPException(status_code=404, detail="Control not found")
        
        if not control.has_deviation:
            raise HTTPException(status_code=400, detail="Control does not have a deviation")
        
        # Load extracted text from scan record
        from sqlalchemy import select as sql_select
        from ..models import Scan
        
        # Get scan
        scan_result = await db.execute(sql_select(Scan).where(Scan.id == scan_id))
        scan = scan_result.scalar_one_or_none()
        
        if not scan:
            logging.error(f"[Regenerate] Scan {scan_id} not found")
            raise HTTPException(status_code=404, detail="Scan not found")
        
        logging.error(f"[Regenerate] Scan loaded, has extracted_text: {scan.extracted_text is not None}, length: {len(scan.extracted_text) if scan.extracted_text else 0}")
        
        if not scan.extracted_text:
            logging.error(f"[Regenerate] No extracted text for scan {scan_id}")
            raise HTTPException(status_code=404, detail="Extracted text not found - scan may be incomplete")
        
        # Convert extracted text to lines
        txt_lines = scan.extracted_text.split('\n')
        logging.error(f"[Regenerate] Split into {len(txt_lines)} lines")
        
        # Count total pages
        total_pages = 0
        for line in txt_lines:
            if line.strip().startswith('=== PAGE '):
                try:
                    page_num = int(line.strip().split()[2])
                    total_pages = max(total_pages, page_num)
                except (IndexError, ValueError):
                    continue
        
        logging.error(f"[Regenerate] Counted {total_pages} pages, about to call extractor")
        
        # Re-run extraction for this control
        from ..extractors.management_response_extractor import extract_management_responses_for_scan
        import redis.asyncio as aioredis
        
        # Get Redis client
        redis_client = None
        try:
            redis_client = aioredis.from_url("redis://redis:6379", decode_responses=True)
        except Exception:
            pass
        
        # Convert control to dict format expected by extractor
        control_dict = {
            'control_id': control.control_id,
            'control_desc': control.control_desc,
            'deviation_desc': control.deviation_desc,
            'has_deviation': control.has_deviation,
            'control_page_refs': control.control_page_refs or []
        }
        
        logging.error(f"[Regenerate] Calling extract_management_responses_for_scan with control_id={control.control_id}")
        response_results = await extract_management_responses_for_scan(
            controls=[control_dict],
            txt_lines=txt_lines,
            total_pages=total_pages,
            scan_id=scan_id,
            redis_client=redis_client
        )
        logging.error(f"[Regenerate] Extraction returned, type: {type(response_results)}, value: {response_results}")
        
        if redis_client:
            await redis_client.close()
        
        # Update control with new response data
        if control.control_id in response_results:
            response_data = response_results[control.control_id]
            control.management_response_text = response_data['text']
            control.management_response_page_refs = response_data['page_refs']
            control.management_response_line_ref = response_data.get('line_ref')
            control.management_response_confidence = response_data['confidence']
            control.response_detection_method = response_data['method']
            
            await db.commit()
            
            return {
                "status": "success",
                "management_response_text": control.management_response_text,
                "confidence": control.management_response_confidence,
                "detection_method": control.response_detection_method
            }
        else:
            return {
                "status": "not_found",
                "message": "No management response found for this deviation"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logging.error(f"[Regenerate] ERROR caught: {e}")
        logging.error(f"[Regenerate] Traceback: {traceback.format_exc()}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
