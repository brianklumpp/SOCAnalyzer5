"""
Router for executive summary operations.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.future import select

from ..models import Scan
from ..models import User
from ..database import get_db
from ..gpt_client import gpt_extract
from ..auth.dependencies import get_current_active_user

router = APIRouter()


@router.get("/report/{scan_id}/executive_summary")
async def get_executive_summary(scan_id: int, force_regenerate: bool = False, db=Depends(get_db)):
    """
    Get executive summary for a scan.
    
    Args:
        scan_id: Scan identifier
        force_regenerate: Force regeneration even if cached summary exists
        
    Returns:
        Executive summary text or generates new one if stale/missing
    """
    try:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Return cached summary if available and not stale (unless force_regenerate)
        if not force_regenerate and scan.executive_summary and not scan.executive_summary_stale:
            return {"executive_summary": scan.executive_summary, "is_stale": False, "regenerated": False}
        
        # Generate new summary
        from ..services.executive_summary_service import generate_executive_summary
        
        summary = await generate_executive_summary(scan_id, db)
        
        # Update scan with new summary
        scan.executive_summary = summary
        scan.executive_summary_stale = False
        await db.commit()
        
        return {"executive_summary": summary, "is_stale": False, "regenerated": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting executive summary for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/executive_summary/regenerate")
async def regenerate_executive_summary(scan_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Force regeneration of executive summary for a scan.
    """
    try:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Generate new summary
        from ..services.executive_summary_service import generate_executive_summary
        
        summary = await generate_executive_summary(scan_id, db)
        
        # Update scan
        scan.executive_summary = summary
        scan.executive_summary_stale = False
        await db.commit()
        
        return {"status": "success", "executive_summary": summary}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error regenerating executive summary for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/report/{scan_id}/executive_summary")
async def update_executive_summary(scan_id: int, data: dict, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Manually update executive summary text.
    """
    try:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        if "executive_summary" in data:
            scan.executive_summary = data["executive_summary"]
            scan.executive_summary_stale = False  # Manual update clears stale flag
            await db.commit()
            
            return {"status": "success", "executive_summary": scan.executive_summary}
        
        return {"status": "no_change"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating executive summary for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
