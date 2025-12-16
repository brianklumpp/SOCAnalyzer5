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
from ..models.user import User
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
async def list_baselines(db=Depends(get_db)):
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
async def get_baseline(baseline_id: int, db=Depends(get_db)):
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


@router.post("/verify/{scan_id}")
async def trigger_verification(scan_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Trigger verification workflow for a scan."""
    try:
        scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Mark as verifying
        scan.verification_status = "in_progress"
        scan.verification_started_at = datetime.utcnow()
        await db.commit()
        
        # Background verification logic would go here
        
        return {
            "scan_id": scan_id,
            "status": "verification_started",
            "message": "Verification workflow initiated"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"Error triggering verification: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/verify/{scan_id}/status")
async def get_verification_status(scan_id: int, db=Depends(get_db)):
    """Get verification status for a scan."""
    try:
        scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        return {
            "scan_id": scan_id,
            "status": getattr(scan, "verification_status", "not_started"),
            "started_at": getattr(scan, "verification_started_at", None),
            "completed_at": getattr(scan, "verification_completed_at", None)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting verification status: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/verify/{scan_id}/learn_patterns")
async def learn_patterns(scan_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Learn patterns from a verified scan."""
    try:
        scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Pattern learning logic would go here
        
        return {
            "scan_id": scan_id,
            "patterns_learned": 0,
            "message": "Pattern learning initiated"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error learning patterns: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/patterns/review-queue")
async def get_pattern_review_queue(db=Depends(get_db)):
    """Get pending pattern merge reviews."""
    try:
        result = await db.execute(
            select(PatternReviewQueue)
            .where(PatternReviewQueue.status == "pending")
            .order_by(PatternReviewQueue.created_at.desc())
        )
        reviews = result.scalars().all()
        
        return [
            {
                "id": r.id,
                "pattern_type": r.pattern_type,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in reviews
        ]
        
    except Exception as e:
        logging.error(f"Error getting review queue: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/patterns/approve-merge/{review_id}")
async def approve_pattern_merge(review_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Approve a pattern merge suggestion."""
    try:
        review = (await db.execute(
            select(PatternReviewQueue).where(PatternReviewQueue.id == review_id)
        )).scalar_one_or_none()
        
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        review.status = "approved"
        review.reviewed_at = datetime.utcnow()
        await db.commit()
        
        # Apply merge logic would go here
        
        return {
            "id": review_id,
            "status": "approved",
            "message": "Pattern merge approved"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"Error approving pattern merge: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/patterns/reject-merge/{review_id}")
async def reject_pattern_merge(review_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Reject a pattern merge suggestion."""
    try:
        review = (await db.execute(
            select(PatternReviewQueue).where(PatternReviewQueue.id == review_id)
        )).scalar_one_or_none()
        
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        review.status = "rejected"
        review.reviewed_at = datetime.utcnow()
        await db.commit()
        
        return {
            "id": review_id,
            "status": "rejected",
            "message": "Pattern merge rejected"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"Error rejecting pattern merge: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/patterns/organization/{organization}")
async def get_organization_patterns(organization: str, db=Depends(get_db)):
    """Get learned patterns for an organization."""
    try:
        result = await db.execute(
            select(OrganizationPattern)
            .where(OrganizationPattern.organization == organization)
            .order_by(OrganizationPattern.created_at.desc())
        )
        patterns = result.scalars().all()
        
        return [
            {
                "id": p.id,
                "organization": p.organization,
                "pattern_type": p.pattern_type,
                "confidence": p.confidence,
                "created_at": p.created_at.isoformat() if p.created_at else None
            }
            for p in patterns
        ]
        
    except Exception as e:
        logging.error(f"Error getting organization patterns: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)
