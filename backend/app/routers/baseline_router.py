"""
Router for validation and baseline operations.

Handles baseline creation, comparison, pattern learning, and verification workflows.
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import JSONResponse
from sqlalchemy.future import select
from sqlalchemy import and_, or_

from ..models import Scan, PatternReviewQueue, Baseline, OrganizationPattern
from ..models import User
from ..database import get_db
from ..services import scan_service
from ..auth.dependencies import get_current_active_user
from .. import config as cfg

router = APIRouter()


@router.post("/baseline/create")
async def create_baseline(data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Create a new baseline from a scan."""
    try:
        scan_id = data.get("scan_id")
        name = data.get("name")
        description = data.get("description", "")
        reviewer_notes = data.get("reviewer_notes", "")
        
        if not scan_id or not name:
            raise HTTPException(status_code=400, detail="scan_id and name are required")
        
        # Verify scan exists
        scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Create baseline snapshot (store minimal data for now)
        snapshot = {
            "scan_id": scan_id,
            "company": scan.company,
            "product": scan.product,
            "created_at": datetime.utcnow().isoformat()
        }
        
        baseline = Baseline(
            name=name,
            scan_id=scan_id,
            description=description,
            reviewer_notes=reviewer_notes,
            snapshot_data=snapshot,
            created_by=data.get("created_by", "system")
        )
        
        db.add(baseline)
        await db.commit()
        await db.refresh(baseline)
        
        return {
            "id": baseline.id,
            "name": baseline.name,
            "scan_id": baseline.scan_id,
            "message": "Baseline created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"Error creating baseline: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/baseline/list")
async def list_baselines(db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """List all available baselines."""
    try:
        result = await db.execute(select(Baseline).order_by(Baseline.created_at.desc()))
        baselines = result.scalars().all()
        
        return [
            {
                "id": b.id,
                "name": b.name,
                "scan_id": b.scan_id,
                "description": b.description,
                "created_at": b.created_at.isoformat() if b.created_at else None
            }
            for b in baselines
        ]
        
    except Exception as e:
        logging.error(f"Error listing baselines: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/baseline/{baseline_id}")
async def get_baseline(baseline_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Get a specific baseline."""
    try:
        baseline = (await db.execute(
            select(Baseline).where(Baseline.id == baseline_id)
        )).scalar_one_or_none()
        
        if not baseline:
            raise HTTPException(status_code=404, detail="Baseline not found")
        
        return {
            "id": baseline.id,
            "name": baseline.name,
            "scan_id": baseline.scan_id,
            "description": baseline.description,
            "created_at": baseline.created_at.isoformat() if baseline.created_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting baseline: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/baseline/compare")
async def compare_to_baseline(data: Dict[str, Any] = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Compare a scan against a baseline."""
    try:
        scan_id = data.get("scan_id")
        baseline_id = data.get("baseline_id")
        
        if not scan_id or not baseline_id:
            raise HTTPException(status_code=400, detail="scan_id and baseline_id required")
        
        # Verify both exist
        scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        baseline = (await db.execute(select(Baseline).where(Baseline.id == baseline_id))).scalar_one_or_none()
        
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        if not baseline:
            raise HTTPException(status_code=404, detail="Baseline not found")
        
        # Comparison logic would go here
        # For now, return placeholder
        return {
            "scan_id": scan_id,
            "baseline_id": baseline_id,
            "differences": [],
            "similarity_score": 0.0,
            "message": "Comparison not yet implemented"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error comparing to baseline: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/baseline/{baseline_id}")
async def delete_baseline(baseline_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Delete a baseline."""
    try:
        baseline = (await db.execute(
            select(Baseline).where(Baseline.id == baseline_id)
        )).scalar_one_or_none()
        
        if not baseline:
            raise HTTPException(status_code=404, detail="Baseline not found")
        
        await db.delete(baseline)
        await db.commit()
        
        return {"message": "Baseline deleted successfully", "id": baseline_id}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"Error deleting baseline: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

# REMOVED: All verification and pattern management endpoints (no longer used)
