"""
Framework Mappings Migration Helper

Utility functions to migrate legacy control_tsc_mappings/control_coso_mappings
into the new unified framework_mappings structure.
"""

import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from ..models import Control, CUEC, Scan


def consolidate_framework_mappings(
    control_tsc_mappings: Optional[List[Dict[str, Any]]],
    control_coso_mappings: Optional[List[Dict[str, Any]]],
    financial_assertions: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Consolidate legacy framework mapping columns into unified framework_mappings structure.
    
    Args:
        control_tsc_mappings: Legacy TSC mappings array
        control_coso_mappings: Legacy COSO mappings array
        financial_assertions: SOC1 financial assertions array
        
    Returns:
        Dict with structure:
        {
            "framework_mappings": {"TSC": [...], "COSO": [...], "FINANCIAL_ASSERTIONS": [...]},
            "primary_framework": "TSC",
            "primary_criterion_id": "CC7.2",
            "primary_confidence": 0.95
        }
    """
    framework_mappings = {}
    
    # Add TSC mappings
    if control_tsc_mappings and isinstance(control_tsc_mappings, list):
        framework_mappings["TSC"] = control_tsc_mappings
    
    # Add COSO mappings
    if control_coso_mappings and isinstance(control_coso_mappings, list):
        framework_mappings["COSO"] = control_coso_mappings
    
    # Add Financial Assertions
    if financial_assertions and isinstance(financial_assertions, list):
        framework_mappings["FINANCIAL_ASSERTIONS"] = financial_assertions
    
    # Calculate primary framework/criterion (highest confidence across all frameworks)
    primary_framework = None
    primary_criterion_id = None
    primary_confidence = 0.0
    
    for fw_name, matches in framework_mappings.items():
        if matches and isinstance(matches, list):
            for match in matches:
                confidence = match.get("confidence", 0)
                if confidence > primary_confidence:
                    primary_confidence = confidence
                    primary_framework = fw_name
                    primary_criterion_id = match.get("id")
    
    return {
        "framework_mappings": framework_mappings,
        "primary_framework": primary_framework,
        "primary_criterion_id": primary_criterion_id,
        "primary_confidence": primary_confidence
    }


async def migrate_control_frameworks(
    db: AsyncSession,
    scan_id: Optional[int] = None,
    control_id: Optional[int] = None
) -> Dict[str, int]:
    """
    Migrate controls from legacy mapping columns to unified framework_mappings.
    
    Args:
        db: Database session
        scan_id: Optional - migrate only controls from specific scan
        control_id: Optional - migrate only specific control
        
    Returns:
        Dict with migration statistics
    """
    logging.info(f"[MIGRATE] Starting control framework migration (scan_id={scan_id}, control_id={control_id})")
    
    # Build query
    query = select(Control)
    if control_id:
        query = query.where(Control.id == control_id)
    elif scan_id:
        query = query.where(Control.scan_id == scan_id)
    
    result = await db.execute(query)
    controls = result.scalars().all()
    
    migrated = 0
    skipped = 0
    errors = 0
    
    for ctrl in controls:
        try:
            # Skip if already migrated
            if ctrl.framework_mappings:
                logging.info(f"[MIGRATE] Control {ctrl.id} already has framework_mappings, skipping")
                skipped += 1
                continue
            
            # Consolidate mappings
            result = consolidate_framework_mappings(
                ctrl.control_tsc_mappings,
                ctrl.control_coso_mappings,
                ctrl.financial_assertions
            )
            
            # Update control
            ctrl.framework_mappings = result["framework_mappings"]
            ctrl.primary_framework = result["primary_framework"]
            ctrl.primary_criterion_id = result["primary_criterion_id"]
            ctrl.primary_confidence = result["primary_confidence"]
            
            db.add(ctrl)
            migrated += 1
            
        except Exception as e:
            logging.error(f"[MIGRATE] Failed to migrate control {ctrl.id}: {e}")
            errors += 1
    
    await db.commit()
    
    logging.info(f"[MIGRATE] Control migration complete: {migrated} migrated, {skipped} skipped, {errors} errors")
    
    return {
        "migrated": migrated,
        "skipped": skipped,
        "errors": errors,
        "total": len(controls)
    }


async def migrate_cuec_frameworks(
    db: AsyncSession,
    scan_id: Optional[int] = None,
    cuec_id: Optional[int] = None
) -> Dict[str, int]:
    """
    Migrate CUECs from legacy mapping columns to unified framework_mappings.
    
    Args:
        db: Database session
        scan_id: Optional - migrate only CUECs from specific scan
        cuec_id: Optional - migrate only specific CUEC
        
    Returns:
        Dict with migration statistics
    """
    logging.info(f"[MIGRATE] Starting CUEC framework migration (scan_id={scan_id}, cuec_id={cuec_id})")
    
    # Build query
    query = select(CUEC)
    if cuec_id:
        query = query.where(CUEC.id == cuec_id)
    elif scan_id:
        query = query.where(CUEC.scan_id == scan_id)
    
    result = await db.execute(query)
    cuecs = result.scalars().all()
    
    migrated = 0
    skipped = 0
    errors = 0
    
    for cuec in cuecs:
        try:
            # Skip if already migrated
            if cuec.framework_mappings:
                logging.info(f"[MIGRATE] CUEC {cuec.id} already has framework_mappings, skipping")
                skipped += 1
                continue
            
            # Consolidate mappings
            result = consolidate_framework_mappings(
                cuec.cuec_tsc_mappings,
                cuec.cuec_coso_mappings
            )
            
            # Update CUEC
            cuec.framework_mappings = result["framework_mappings"]
            cuec.primary_framework = result["primary_framework"]
            cuec.primary_criterion_id = result["primary_criterion_id"]
            cuec.primary_confidence = result["primary_confidence"]
            
            db.add(cuec)
            migrated += 1
            
        except Exception as e:
            logging.error(f"[MIGRATE] Failed to migrate CUEC {cuec.id}: {e}")
            errors += 1
    
    await db.commit()
    
    logging.info(f"[MIGRATE] CUEC migration complete: {migrated} migrated, {skipped} skipped, {errors} errors")
    
    return {
        "migrated": migrated,
        "skipped": skipped,
        "errors": errors,
        "total": len(cuecs)
    }


async def migrate_scan_frameworks(
    db: AsyncSession,
    scan_id: int
) -> Dict[str, Any]:
    """
    Migrate all controls and CUECs for a specific scan.
    
    Args:
        db: Database session
        scan_id: Scan ID to migrate
        
    Returns:
        Dict with combined statistics
    """
    logging.info(f"[MIGRATE] Starting full scan migration for scan_id={scan_id}")
    
    control_stats = await migrate_control_frameworks(db, scan_id=scan_id)
    cuec_stats = await migrate_cuec_frameworks(db, scan_id=scan_id)
    
    return {
        "scan_id": scan_id,
        "controls": control_stats,
        "cuecs": cuec_stats
    }
