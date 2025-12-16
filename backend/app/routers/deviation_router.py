"""
Router for deviation-related operations.
"""
import logging
import asyncio
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.future import select

from ..models import Control
from ..models.user import User
from ..database import get_db, AsyncSessionLocal
from ..auth.dependencies import get_current_active_user
from .. import config as cfg

router = APIRouter()


@router.get("/report/{scan_id}/deviations")
async def get_deviations(scan_id: int, db=Depends(get_db)):
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
                "scan_id": ctrl.scan_id,
            })
        
        return deviations
        
    except Exception as e:
        logging.error(f"Error fetching deviations for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/report/{scan_id}/deviations/{control_id}")
async def update_deviation_summary(scan_id: int, control_id: int, data: dict, db=Depends(get_db)):
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
            redis_client = aioredis.from_url("redis://socanalyzer-redis:6379", decode_responses=True)
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
async def get_regenerate_progress(scan_id: int):
    """
    Get progress of deviation summary regeneration.
    Returns progress data from Redis.
    """
    try:
        import redis.asyncio as aioredis
        import json
        
        redis_client = aioredis.from_url("redis://socanalyzer-redis:6379", decode_responses=True)
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
