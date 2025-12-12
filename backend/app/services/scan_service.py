"""
Service module for scan lifecycle management.

Handles scan-level operations including GPT usage tracking and executive summary staleness.
"""
import logging
from typing import Optional
from sqlalchemy.future import select

from ..models import Scan


async def mark_executive_summary_stale(scan_id: int, db) -> None:
    """
    Mark the executive summary as stale when data changes that could impact it.
    
    Args:
        scan_id: Scan identifier
        db: Async database session
    """
    scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if scan_row:
        scan_row.executive_summary_stale = True
        db.add(scan_row)


async def update_scan_gpt_fields(
    scan_id: int, 
    gpt_cost: Optional[float] = None, 
    gpt_model: Optional[str] = None, 
    estimated_time_seconds: Optional[float] = None, 
    db = None
) -> None:
    """
    Update GPT-related fields on a scan.
    
    Args:
        scan_id: Scan identifier
        gpt_cost: Total GPT cost
        gpt_model: GPT model name
        estimated_time_seconds: Estimated processing time
        db: Async database session (required)
        
    Raises:
        ValueError: If db is None
    """
    if db is None:
        raise ValueError("A valid async database session (db) must be provided.")
    
    update_fields = {}
    if gpt_cost is not None:
        update_fields['gpt_cost'] = gpt_cost
    if gpt_model is not None:
        update_fields['gpt_model'] = gpt_model
    if estimated_time_seconds is not None:
        update_fields['estimated_time_seconds'] = estimated_time_seconds
    
    if not update_fields:
        return
    
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan_row = result.scalar_one_or_none()
    if scan_row:
        for k, v in update_fields.items():
            setattr(scan_row, k, v)
        db.add(scan_row)
        await db.commit()


async def add_gpt_usage(scan_id: int, model: str, cost: float, seconds: float, db) -> None:
    """
    Add GPT usage entry to scan's usage details array.
    
    Args:
        scan_id: Scan identifier
        model: GPT model name
        cost: Cost of this GPT call
        seconds: Estimated time for this call
        db: Async database session
    """
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan_row = result.scalar_one_or_none()
    if scan_row:
        usage = scan_row.gpt_usage_details or []
        usage.append({
            "model": model, 
            "cost": cost, 
            "estimated_time_seconds": seconds
        })
        scan_row.gpt_usage_details = usage
        db.add(scan_row)
        await db.commit()
