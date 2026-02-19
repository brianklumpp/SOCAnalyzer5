"""
Framework Mapping Service
Handles recomputation of framework mappings for controls and CUECs.
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models import Control, CUEC, Scan
from ..frameworks import map_control_to_frameworks_dynamic, get_available_frameworks
from ..utils.objective_id_normalizer import normalize_objective_id

logger = logging.getLogger(__name__)


async def recompute_control_framework_mappings(
    scan_id: int,
    control_db_id: int,
    db: Session
) -> Dict[str, Any]:
    """
    Recompute framework mappings for a single control.
    
    Args:
        scan_id: Scan ID
        control_db_id: Control database ID
        db: Database session
        
    Returns:
        Dict with success status, control data, and mapping results
    """
    try:
        # Get control
        result = await db.execute(
            select(Control).where(
                Control.id == control_db_id,
                Control.scan_id == scan_id
            )
        )
        control = result.scalar_one_or_none()
        
        if not control:
            return {
                "success": False,
                "error": f"Control {control_db_id} not found in scan {scan_id}"
            }
        
        # Get scan to determine report type
        scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = scan_result.scalar_one_or_none()
        if not scan:
            return {"success": False, "error": f"Scan {scan_id} not found"}
        
        report_type = scan.report_type or "SOC2"
        
        # Get available frameworks for this report type
        available_frameworks = get_available_frameworks(report_type)
        
        if not available_frameworks:
            return {
                "success": False,
                "error": f"No frameworks available for report type: {report_type}"
            }
        
        # Perform mapping
        logger.info(f"Recomputing framework mappings for control {control_db_id} (scan {scan_id})")
        
        mapping_result = map_control_to_frameworks_dynamic(
            control_desc=control.control_desc or "",
            control_id=control.control_id or str(control_db_id),
            available_frameworks=available_frameworks,
            has_deviation=control.has_deviation or False,
            deviation_desc=control.deviation_desc,
            top_k=5
        )
        
        # Update control with new mappings
        control.framework_mappings = mapping_result.get("framework_mappings", {})
        control.primary_framework = mapping_result.get("primary_framework")
        
        # Normalize the criterion ID
        original_criterion_id = mapping_result.get("primary_criterion_id")
        control.primary_criterion_id = original_criterion_id
        control.primary_criterion_id_normalized = normalize_objective_id(original_criterion_id) if original_criterion_id else None
        control.primary_criterion_id_original = original_criterion_id
        control.primary_confidence = mapping_result.get("primary_confidence")
        
        await db.commit()
        await db.refresh(control)
        
        # Count total mappings across all frameworks
        total_mappings = 0
        framework_names = []
        if control.framework_mappings:
            for fw_name, fw_mappings in control.framework_mappings.items():
                if fw_mappings and len(fw_mappings) > 0:
                    total_mappings += len(fw_mappings)
                    framework_names.append(fw_name)
        
        logger.info(f"Successfully recomputed framework mappings for control {control_db_id}: {total_mappings} mappings across {len(framework_names)} frameworks")
        
        return {
            "success": True,
            "control": {
                "id": control.id,
                "control_id": control.control_id,
                "framework_mappings": control.framework_mappings,
                "primary_framework": control.primary_framework,
                "primary_criterion_id": control.primary_criterion_id,
                "primary_confidence": control.primary_confidence
            },
            "token_usage": mapping_result.get("token_usage", {}),
            "mapping_count": total_mappings,
            "frameworks": framework_names,
            "message": f"Found {total_mappings} framework mapping{'s' if total_mappings != 1 else ''} across {len(framework_names)} framework{'s' if len(framework_names) != 1 else ''}" if total_mappings > 0 else "No framework mappings found"
        }
        
    except Exception as e:
        logger.error(f"Error recomputing framework mappings for control {control_db_id}: {e}", exc_info=True)
        await db.rollback()
        return {
            "success": False,
            "error": str(e)
        }


async def recompute_cuec_framework_mappings(
    scan_id: int,
    cuec_id: int,
    db: Session
) -> Dict[str, Any]:
    """
    Recompute framework mappings for a single CUEC.
    
    Args:
        scan_id: Scan ID
        cuec_id: CUEC database ID
        db: Database session
        
    Returns:
        Dict with success status and CUEC data
    """
    try:
        # Get CUEC
        result = await db.execute(
            select(CUEC).where(
                CUEC.id == cuec_id,
                CUEC.scan_id == scan_id
            )
        )
        cuec = result.scalar_one_or_none()
        
        if not cuec:
            return {
                "success": False,
                "error": f"CUEC {cuec_id} not found in scan {scan_id}"
            }
        
        # Get scan to determine report type
        scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = scan_result.scalar_one_or_none()
        if not scan:
            return {"success": False, "error": f"Scan {scan_id} not found"}
        
        report_type = scan.report_type or "SOC2"
        
        # Get available frameworks
        available_frameworks = get_available_frameworks(report_type)
        
        if not available_frameworks:
            return {
                "success": False,
                "error": f"No frameworks available for report type: {report_type}"
            }
        
        # Perform mapping (CUECs use same mapper as controls)
        logger.info(f"Recomputing framework mappings for CUEC {cuec_id} (scan {scan_id})")
        
        mapping_result = map_control_to_frameworks_dynamic(
            control_desc=cuec.cuec_description or "",
            control_id=str(cuec_id),
            available_frameworks=available_frameworks,
            has_deviation=False,
            deviation_desc=None,
            top_k=5
        )
        
        # Update CUEC with new Phase 1 multi-framework mappings
        cuec.framework_mappings = mapping_result.get("framework_mappings", {})
        cuec.primary_framework = mapping_result.get("primary_framework")
        
        # Normalize the criterion ID
        original_criterion_id = mapping_result.get("primary_criterion_id")
        cuec.primary_criterion_id = original_criterion_id
        cuec.primary_criterion_id_normalized = normalize_objective_id(original_criterion_id) if original_criterion_id else None
        cuec.primary_criterion_id_original = original_criterion_id
        cuec.primary_confidence = mapping_result.get("primary_confidence")
        
        await db.commit()
        await db.refresh(cuec)
        
        # Count total mappings across all frameworks
        total_mappings = 0
        framework_names = []
        if cuec.framework_mappings:
            for fw_name, fw_mappings in cuec.framework_mappings.items():
                if fw_mappings and len(fw_mappings) > 0:
                    total_mappings += len(fw_mappings)
                    framework_names.append(fw_name)
        
        logger.info(f"Successfully recomputed framework mappings for CUEC {cuec_id}: {total_mappings} mappings across {len(framework_names)} frameworks")
        
        return {
            "success": True,
            "cuec": {
                "id": cuec.id,
                "cuec_seq": cuec.cuec_seq,
                # Phase 1 multi-framework fields (no cuec_ prefix - matches database model)
                "framework_mappings": cuec.framework_mappings,
                "primary_framework": cuec.primary_framework,
                "primary_criterion_id": cuec.primary_criterion_id,
                "primary_confidence": cuec.primary_confidence,
            },
            "token_usage": mapping_result.get("token_usage", {}),
            "mapping_count": total_mappings,
            "frameworks": framework_names,
            "message": f"Found {total_mappings} framework mapping{'s' if total_mappings != 1 else ''} across {len(framework_names)} framework{'s' if len(framework_names) != 1 else ''}" if total_mappings > 0 else "No framework mappings found"
        }
        
    except Exception as e:
        logger.error(f"Error recomputing framework mappings for CUEC {cuec_id}: {e}", exc_info=True)
        await db.rollback()
        return {
            "success": False,
            "error": str(e)
        }


async def compute_framework_mappings(
    control_desc: str,
    report_type: str,
    db: Session
) -> Dict[str, Any]:
    """
    Compute framework mappings for a control description (preview/test mode).
    Does not save to database.
    
    Args:
        control_desc: Control description text
        report_type: Report type (SOC1, SOC2, etc.)
        db: Database session
        
    Returns:
        Dict with framework mappings
    """
    try:
        available_frameworks = get_available_frameworks(report_type)
        
        if not available_frameworks:
            return {
                "success": False,
                "error": f"No frameworks available for report type: {report_type}",
                "framework_mappings": {}
            }
        
        mapping_result = map_control_to_frameworks_dynamic(
            control_desc=control_desc,
            control_id="preview",
            available_frameworks=available_frameworks,
            has_deviation=False,
            deviation_desc=None,
            top_k=5
        )
        
        return {
            "success": True,
            "framework_mappings": mapping_result.get("framework_mappings", {}),
            "primary_framework": mapping_result.get("primary_framework"),
            "primary_criterion_id": mapping_result.get("primary_criterion_id"),
            "primary_confidence": mapping_result.get("primary_confidence"),
            "token_usage": mapping_result.get("token_usage", {})
        }
        
    except Exception as e:
        logger.error(f"Error computing framework mappings: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "framework_mappings": {}
        }


async def map_all_frameworks_for_scan(
    scan_id: int,
    db: Session,
    entity_type: str = "controls",
    framework_keys: Optional[List[str]] = None,
    min_confidence: float = 0.0
) -> Dict[str, Any]:
    """
    Map all controls or CUECs in a scan to ALL available frameworks.
    
    This is the on-demand "full framework mapping" triggered from the frontend
    after the scan pipeline completes with only default frameworks (TSC+COSO).
    
    Uses the batched mapping function for efficiency (single GPT call per item).
    
    Args:
        scan_id: Scan ID
        db: Database session
        entity_type: "controls" or "cuecs"
        framework_keys: Optional explicit list of framework keys to map to.
                       If None, maps to ALL frameworks for the report type.
        min_confidence: Only map items with confidence >= this value (default: 0.0 = all)
        
    Returns:
        Dict with success count, failed count, and results per item
    """
    from ..frameworks import map_control_to_all_frameworks_batched, extract_mapping_fields_for_db
    
    try:
        # Get scan for report type
        scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = scan_result.scalar_one_or_none()
        if not scan:
            return {"success": False, "error": f"Scan {scan_id} not found"}
        
        report_type = scan.report_type.value if scan.report_type else "SOC2"
        
        # Load ALL frameworks (not scan_default_only)
        available_frameworks = get_available_frameworks(
            report_type=report_type,
            scan_default_only=False,
            framework_keys=framework_keys
        )
        
        if not available_frameworks:
            return {"success": False, "error": f"No frameworks available for report type: {report_type}"}
        
        fw_names = list(available_frameworks.keys())
        logger.info(f"[MAP_ALL_FRAMEWORKS] Mapping {entity_type} in scan {scan_id} to {len(fw_names)} frameworks: {fw_names}")
        
        # Get items to map
        if entity_type == "controls":
            query = select(Control).where(Control.scan_id == scan_id)
            if min_confidence > 0:
                query = query.where(Control.control_confidence >= min_confidence)
            result = await db.execute(query)
            items = result.scalars().all()
        elif entity_type == "cuecs":
            query = select(CUEC).where(CUEC.scan_id == scan_id)
            if min_confidence > 0:
                query = query.where(CUEC.cuec_confidence >= min_confidence)
            result = await db.execute(query)
            items = result.scalars().all()
        else:
            return {"success": False, "error": f"Invalid entity_type: {entity_type}"}
        
        if not items:
            return {
                "success": True,
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "frameworks": fw_names,
                "message": f"No {entity_type} found in scan {scan_id}"
            }
        
        logger.info(f"[MAP_ALL_FRAMEWORKS] Processing {len(items)} {entity_type}")
        
        success_count = 0
        failed_count = 0
        
        for item in items:
            try:
                if entity_type == "controls":
                    desc = item.control_desc or ""
                    item_id = item.control_id or str(item.id)
                    has_deviation = item.has_deviation or False
                    deviation_desc = item.deviation_desc
                else:
                    desc = item.cuec_description or ""
                    item_id = f"CUEC-{item.cuec_seq or item.id}"
                    has_deviation = False
                    deviation_desc = None
                
                if not desc:
                    logger.warning(f"[MAP_ALL_FRAMEWORKS] Skipping {item_id}: no description")
                    continue
                
                # Use batched mapping (single GPT call for all frameworks)
                mapping_result = map_control_to_all_frameworks_batched(
                    control_desc=desc,
                    control_id=item_id,
                    available_frameworks=available_frameworks,
                    has_deviation=has_deviation,
                    deviation_desc=deviation_desc,
                    top_k=5
                )
                
                # Merge new framework mappings with existing ones
                existing_mappings = item.framework_mappings or {}
                new_mappings = mapping_result.get("framework_mappings", {})
                
                # Merge: new frameworks override, existing frameworks preserved if not in new
                merged_mappings = {**existing_mappings, **new_mappings}
                
                # Update item
                item.framework_mappings = merged_mappings
                item.primary_framework = mapping_result.get("primary_framework") or item.primary_framework
                
                original_criterion_id = mapping_result.get("primary_criterion_id")
                if original_criterion_id:
                    item.primary_criterion_id = original_criterion_id
                    item.primary_criterion_id_normalized = normalize_objective_id(original_criterion_id)
                    item.primary_criterion_id_original = original_criterion_id
                    item.primary_confidence = mapping_result.get("primary_confidence")
                
                success_count += 1
                
                if success_count % 10 == 0:
                    logger.info(f"[MAP_ALL_FRAMEWORKS] Progress: {success_count}/{len(items)} {entity_type} mapped")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"[MAP_ALL_FRAMEWORKS] Failed to map {item_id}: {e}")
        
        await db.commit()
        
        logger.info(f"[MAP_ALL_FRAMEWORKS] Complete: {success_count} mapped, {failed_count} failed out of {len(items)} {entity_type}")
        
        return {
            "success": True,
            "total": len(items),
            "success_count": success_count,
            "failed_count": failed_count,
            "frameworks": fw_names,
            "message": f"Mapped {success_count} of {len(items)} {entity_type} to {len(fw_names)} frameworks ({', '.join(fw_names)})"
        }
        
    except Exception as e:
        logger.error(f"[MAP_ALL_FRAMEWORKS] Error: {e}", exc_info=True)
        await db.rollback()
        return {"success": False, "error": str(e)}
