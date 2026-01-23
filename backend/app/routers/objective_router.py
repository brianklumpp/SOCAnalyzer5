"""
Router for control objective operations including CRUD, mapping, and workflow operations.
"""
import logging
import datetime
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, Body, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.future import select
from sqlalchemy import and_, func

from ..models import ControlObjective, ControlObjectiveMapping, Control, Scan, User
from ..database import get_db
from ..services.scan_service import mark_executive_summary_stale
from ..auth.dependencies import get_current_active_user

router = APIRouter()

logger = logging.getLogger(__name__)


# ============================================================================
# CRUD Operations for Control Objectives
# ============================================================================

@router.get("/report/{scan_id}/objectives")
async def get_objectives(
    scan_id: int,
    status: Optional[str] = Query(None, description="Filter by status (pending/approved/rejected)"),
    min_confidence: Optional[float] = Query(None, description="Minimum confidence threshold"),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all control objectives for a scan.
    
    Query Parameters:
    - status: Filter by status (pending, approved, rejected, converted_to_control)
    - min_confidence: Minimum confidence threshold (0.0-1.0)
    """
    try:
        # Build query with filters
        query = select(ControlObjective).where(ControlObjective.scan_id == scan_id)
        
        if status:
            query = query.where(ControlObjective.status == status)
        
        if min_confidence is not None:
            query = query.where(ControlObjective.final_confidence >= min_confidence)
        
        query = query.order_by(ControlObjective.final_confidence.desc())
        
        result = await db.execute(query)
        objectives = result.scalars().all()
        
        # Convert to dict with mapping counts
        objectives_data = []
        for obj in objectives:
            # Count linked controls
            mapping_count_query = select(func.count(ControlObjectiveMapping.id)).where(
                ControlObjectiveMapping.objective_id == obj.id
            )
            mapping_count_result = await db.execute(mapping_count_query)
            mapping_count = mapping_count_result.scalar()
            
            objectives_data.append({
                "id": obj.id,
                "scan_id": obj.scan_id,
                "objective_id": obj.objective_id,
                "objective_text": obj.objective_text,
                "keyword_confidence": obj.keyword_confidence,
                "distance_confidence": obj.distance_confidence,
                "gpt_confidence": obj.gpt_confidence,
                "alignment_confidence": obj.alignment_confidence,
                "format_confidence": obj.format_confidence,
                "final_confidence": obj.final_confidence,
                "confidence_calc": obj.confidence_calc,
                "gpt_reasoning": obj.gpt_reasoning,
                "page_refs": obj.page_refs,
                "line_ref": obj.line_ref,
                "source_context": obj.source_context,
                "extraction_method": obj.extraction_method,
                "section_heading": obj.section_heading,
                "status": obj.status,
                "created_at": obj.created_at.isoformat() if obj.created_at else None,
                "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
                "linked_controls_count": mapping_count
            })
        
        return {"objectives": objectives_data, "total": len(objectives_data)}
        
    except Exception as e:
        logger.error(f"Failed to fetch objectives for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{scan_id}/objectives/{objective_id}")
async def get_objective(
    scan_id: int,
    objective_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a single control objective with its linked controls."""
    try:
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        # Get linked controls
        mappings_result = await db.execute(
            select(ControlObjectiveMapping, Control).join(
                Control, ControlObjectiveMapping.control_id == Control.id
            ).where(ControlObjectiveMapping.objective_id == objective_id)
        )
        mappings = mappings_result.all()
        
        linked_controls = []
        for mapping, control in mappings:
            linked_controls.append({
                "control_id": control.control_id,
                "control_db_id": control.id,
                "control_desc": control.control_desc,
                "mapping_confidence": mapping.mapping_confidence,
                "mapping_method": mapping.mapping_method,
                "is_primary": mapping.is_primary,
                "created_at": mapping.created_at.isoformat() if mapping.created_at else None
            })
        
        return {
            "id": obj.id,
            "scan_id": obj.scan_id,
            "objective_id": obj.objective_id,
            "objective_text": obj.objective_text,
            "keyword_confidence": obj.keyword_confidence,
            "distance_confidence": obj.distance_confidence,
            "gpt_confidence": obj.gpt_confidence,
            "alignment_confidence": obj.alignment_confidence,
            "format_confidence": obj.format_confidence,
            "final_confidence": obj.final_confidence,
            "confidence_calc": obj.confidence_calc,
            "gpt_reasoning": obj.gpt_reasoning,
            "page_refs": obj.page_refs,
            "line_ref": obj.line_ref,
            "source_context": obj.source_context,
            "extraction_method": obj.extraction_method,
            "section_heading": obj.section_heading,
            "status": obj.status,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
            "linked_controls": linked_controls
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch objective {objective_id} for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/report/{scan_id}/objectives/{objective_id}")
async def update_objective(
    scan_id: int,
    objective_id: int,
    data: Dict[str, Any] = Body(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update a control objective.
    
    Allowed fields:
    - objective_id: Identifier string
    - objective_text: Full objective description
    - status: pending/approved/rejected/converted_to_control
    """
    try:
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        # Update allowed fields
        if "objective_id" in data:
            obj.objective_id = data["objective_id"]
        
        if "objective_text" in data:
            obj.objective_text = data["objective_text"]
        
        if "status" in data:
            valid_statuses = ['pending', 'approved', 'rejected', 'converted_to_control']
            if data["status"] not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
                )
            obj.status = data["status"]
        
        # Update audit fields
        obj.updated_at = datetime.datetime.utcnow()
        obj.updated_by_user_id = current_user.id
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        
        return {
            "id": obj.id,
            "objective_id": obj.objective_id,
            "objective_text": obj.objective_text,
            "status": obj.status,
            "final_confidence": obj.final_confidence,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/report/{scan_id}/objectives/{objective_id}")
async def delete_objective(
    scan_id: int,
    objective_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a control objective and all its mappings (cascade)."""
    try:
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        # Delete (cascades to mappings)
        await db.delete(obj)
        await db.commit()
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        
        return {"status": "deleted", "objective_id": objective_id}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Control-Objective Mapping Operations
# ============================================================================

@router.get("/report/{scan_id}/objectives/{objective_id}/controls")
async def get_objective_controls(
    scan_id: int,
    objective_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all controls linked to an objective."""
    try:
        # Verify objective exists
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        # Get mappings with control details
        mappings_result = await db.execute(
            select(ControlObjectiveMapping, Control).join(
                Control, ControlObjectiveMapping.control_id == Control.id
            ).where(ControlObjectiveMapping.objective_id == objective_id)
            .order_by(ControlObjectiveMapping.is_primary.desc(), ControlObjectiveMapping.mapping_confidence.desc())
        )
        mappings = mappings_result.all()
        
        controls = []
        for mapping, control in mappings:
            controls.append({
                "mapping_id": mapping.id,
                "control_id": control.control_id,
                "control_db_id": control.id,
                "control_desc": control.control_desc,
                "control_confidence": control.control_confidence,
                "mapping_confidence": mapping.mapping_confidence,
                "mapping_method": mapping.mapping_method,
                "is_primary": mapping.is_primary,
                "created_at": mapping.created_at.isoformat() if mapping.created_at else None
            })
        
        return {
            "objective_id": objective_id,
            "objective_text": obj.objective_text,
            "controls": controls,
            "total": len(controls)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch controls for objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/objectives/{objective_id}/controls/{control_db_id}")
async def link_control_to_objective(
    scan_id: int,
    objective_id: int,
    control_db_id: int,
    data: Dict[str, Any] = Body(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Link a control to an objective (create mapping).
    
    Body:
    - mapping_confidence: Optional confidence score (0.0-1.0), defaults to 1.0
    - is_primary: Optional bool, defaults to False
    """
    try:
        # Verify objective exists
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        # Verify control exists
        control = (await db.execute(
            select(Control).where(
                and_(
                    Control.scan_id == scan_id,
                    Control.id == control_db_id
                )
            )
        )).scalar_one_or_none()
        
        if not control:
            raise HTTPException(status_code=404, detail="Control not found")
        
        # Check if mapping already exists
        existing = (await db.execute(
            select(ControlObjectiveMapping).where(
                and_(
                    ControlObjectiveMapping.objective_id == objective_id,
                    ControlObjectiveMapping.control_id == control_db_id
                )
            )
        )).scalar_one_or_none()
        
        if existing:
            raise HTTPException(status_code=409, detail="Mapping already exists")
        
        # Create mapping
        mapping = ControlObjectiveMapping(
            control_id=control_db_id,
            objective_id=objective_id,
            mapping_confidence=data.get("mapping_confidence", 1.0),
            mapping_method='manual',
            is_primary=data.get("is_primary", False),
            created_at=datetime.datetime.utcnow(),
            created_by_user_id=current_user.id
        )
        
        db.add(mapping)
        await db.commit()
        await db.refresh(mapping)
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        
        return {
            "status": "linked",
            "mapping_id": mapping.id,
            "objective_id": objective_id,
            "control_id": control.control_id,
            "control_db_id": control_db_id,
            "mapping_confidence": mapping.mapping_confidence,
            "is_primary": mapping.is_primary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to link control {control_db_id} to objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/report/{scan_id}/objectives/{objective_id}/controls/{control_db_id}")
async def unlink_control_from_objective(
    scan_id: int,
    objective_id: int,
    control_db_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Remove a control-objective mapping."""
    try:
        # Verify mapping exists
        mapping = (await db.execute(
            select(ControlObjectiveMapping).where(
                and_(
                    ControlObjectiveMapping.objective_id == objective_id,
                    ControlObjectiveMapping.control_id == control_db_id
                )
            )
        )).scalar_one_or_none()
        
        if not mapping:
            raise HTTPException(status_code=404, detail="Mapping not found")
        
        await db.delete(mapping)
        await db.commit()
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        
        return {
            "status": "unlinked",
            "objective_id": objective_id,
            "control_db_id": control_db_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to unlink control {control_db_id} from objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/report/{scan_id}/mappings/{mapping_id}")
async def update_mapping(
    scan_id: int,
    mapping_id: int,
    data: Dict[str, Any] = Body(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update a control-objective mapping.
    
    Allowed fields:
    - mapping_confidence: Confidence score (0.0-1.0)
    - is_primary: Whether this is the primary objective for the control
    """
    try:
        mapping = (await db.execute(
            select(ControlObjectiveMapping).where(ControlObjectiveMapping.id == mapping_id)
        )).scalar_one_or_none()
        
        if not mapping:
            raise HTTPException(status_code=404, detail="Mapping not found")
        
        # Update allowed fields
        if "mapping_confidence" in data:
            confidence = data["mapping_confidence"]
            if not (0.0 <= confidence <= 1.0):
                raise HTTPException(status_code=400, detail="mapping_confidence must be between 0.0 and 1.0")
            mapping.mapping_confidence = confidence
        
        if "is_primary" in data:
            mapping.is_primary = data["is_primary"]
        
        db.add(mapping)
        await db.commit()
        await db.refresh(mapping)
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        
        return {
            "id": mapping.id,
            "mapping_confidence": mapping.mapping_confidence,
            "is_primary": mapping.is_primary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update mapping {mapping_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Workflow Operations
# ============================================================================

@router.post("/report/{scan_id}/objectives/{objective_id}/approve")
async def approve_objective(
    scan_id: int,
    objective_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Approve an objective (set status to 'approved')."""
    try:
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        obj.status = 'approved'
        obj.updated_at = datetime.datetime.utcnow()
        obj.updated_by_user_id = current_user.id
        
        db.add(obj)
        await db.commit()
        
        return {"status": "approved", "objective_id": objective_id}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to approve objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/objectives/{objective_id}/reject")
async def reject_objective(
    scan_id: int,
    objective_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Reject an objective (set status to 'rejected')."""
    try:
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        obj.status = 'rejected'
        obj.updated_at = datetime.datetime.utcnow()
        obj.updated_by_user_id = current_user.id
        
        db.add(obj)
        await db.commit()
        
        return {"status": "rejected", "objective_id": objective_id}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to reject objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/objectives/{objective_id}/convert-to-control")
async def convert_objective_to_control(
    scan_id: int,
    objective_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Convert an objective to a control.
    
    This creates a new control from the objective text and marks the objective
    as 'converted_to_control'. The objective is preserved for audit purposes.
    """
    try:
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        if obj.status == 'converted_to_control':
            raise HTTPException(status_code=409, detail="Objective already converted to control")
        
        # Get next control sequence number
        max_seq_result = await db.execute(
            select(func.max(Control.control_seq)).where(Control.scan_id == scan_id)
        )
        max_seq = max_seq_result.scalar() or 0
        
        # Create new control from objective
        new_control = Control(
            scan_id=scan_id,
            control_id=obj.objective_id or f"OBJ-{objective_id}",
            control_desc=obj.objective_text,
            control_test="[Converted from control objective]",
            control_test_results="",
            has_deviation=False,
            deviation_desc=None,
            control_page_refs=obj.page_refs,
            control_line_ref=obj.line_ref,
            control_seq=max_seq + 1,
            control_confidence=obj.final_confidence,
            confidence_calc=f"Converted from objective: {obj.confidence_calc}",
            control_gpt_opinion="converted_from_objective",
            control_gpt_reasoning=f"Converted from objective by {current_user.username}",
            annotation=f"Converted from control objective (ID: {objective_id})",
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow(),
            updated_by_user_id=current_user.id
        )
        
        db.add(new_control)
        
        # Update objective status
        obj.status = 'converted_to_control'
        obj.updated_at = datetime.datetime.utcnow()
        obj.updated_by_user_id = current_user.id
        
        db.add(obj)
        await db.commit()
        await db.refresh(new_control)
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        
        return {
            "status": "converted",
            "objective_id": objective_id,
            "new_control_id": new_control.control_id,
            "new_control_db_id": new_control.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to convert objective {objective_id} to control: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Bulk Operations
# ============================================================================

@router.post("/report/{scan_id}/objectives/bulk-approve")
async def bulk_approve_objectives(
    scan_id: int,
    data: Dict[str, List[int]] = Body(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Approve multiple objectives at once.
    
    Body:
    - objective_ids: List of objective IDs to approve
    """
    try:
        objective_ids = data.get("objective_ids", [])
        if not objective_ids:
            raise HTTPException(status_code=400, detail="objective_ids required")
        
        # Update all objectives
        result = await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id.in_(objective_ids)
                )
            )
        )
        objectives = result.scalars().all()
        
        if len(objectives) != len(objective_ids):
            raise HTTPException(status_code=404, detail="Some objectives not found")
        
        for obj in objectives:
            obj.status = 'approved'
            obj.updated_at = datetime.datetime.utcnow()
            obj.updated_by_user_id = current_user.id
            db.add(obj)
        
        await db.commit()
        
        return {"status": "approved", "count": len(objectives), "objective_ids": objective_ids}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to bulk approve objectives: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/objectives/bulk-reject")
async def bulk_reject_objectives(
    scan_id: int,
    data: Dict[str, List[int]] = Body(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Reject multiple objectives at once.
    
    Body:
    - objective_ids: List of objective IDs to reject
    """
    try:
        objective_ids = data.get("objective_ids", [])
        if not objective_ids:
            raise HTTPException(status_code=400, detail="objective_ids required")
        
        # Update all objectives
        result = await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id.in_(objective_ids)
                )
            )
        )
        objectives = result.scalars().all()
        
        if len(objectives) != len(objective_ids):
            raise HTTPException(status_code=404, detail="Some objectives not found")
        
        for obj in objectives:
            obj.status = 'rejected'
            obj.updated_at = datetime.datetime.utcnow()
            obj.updated_by_user_id = current_user.id
            db.add(obj)
        
        await db.commit()
        
        return {"status": "rejected", "count": len(objectives), "objective_ids": objective_ids}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to bulk reject objectives: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Statistics & Summary
# ============================================================================

@router.get("/report/{scan_id}/objectives/stats")
async def get_objectives_stats(
    scan_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get statistics about objectives for a scan."""
    try:
        # Count by status
        total_result = await db.execute(
            select(func.count(ControlObjective.id)).where(ControlObjective.scan_id == scan_id)
        )
        total = total_result.scalar()
        
        pending_result = await db.execute(
            select(func.count(ControlObjective.id)).where(
                and_(ControlObjective.scan_id == scan_id, ControlObjective.status == 'pending')
            )
        )
        pending = pending_result.scalar()
        
        approved_result = await db.execute(
            select(func.count(ControlObjective.id)).where(
                and_(ControlObjective.scan_id == scan_id, ControlObjective.status == 'approved')
            )
        )
        approved = approved_result.scalar()
        
        rejected_result = await db.execute(
            select(func.count(ControlObjective.id)).where(
                and_(ControlObjective.scan_id == scan_id, ControlObjective.status == 'rejected')
            )
        )
        rejected = rejected_result.scalar()
        
        converted_result = await db.execute(
            select(func.count(ControlObjective.id)).where(
                and_(ControlObjective.scan_id == scan_id, ControlObjective.status == 'converted_to_control')
            )
        )
        converted = converted_result.scalar()
        
        # Average confidence
        avg_confidence_result = await db.execute(
            select(func.avg(ControlObjective.final_confidence)).where(ControlObjective.scan_id == scan_id)
        )
        avg_confidence = avg_confidence_result.scalar() or 0.0
        
        # Count objectives with mappings
        mapped_result = await db.execute(
            select(func.count(func.distinct(ControlObjectiveMapping.objective_id))).where(
                ControlObjectiveMapping.objective_id.in_(
                    select(ControlObjective.id).where(ControlObjective.scan_id == scan_id)
                )
            )
        )
        mapped = mapped_result.scalar()
        
        return {
            "scan_id": scan_id,
            "total": total,
            "by_status": {
                "pending": pending,
                "approved": approved,
                "rejected": rejected,
                "converted_to_control": converted
            },
            "average_confidence": round(avg_confidence, 3),
            "with_control_mappings": mapped,
            "without_mappings": total - mapped
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch objectives stats for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
