"""
Deviation Summarizer Post-Processor

Generates AI-powered plain-language summaries for controls with deviations.
Runs after control extraction completes, creating "What it Means" explanations
for controls where deviation=true.
"""

import logging
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def call_gpt_async(prompt: str, model: str, temperature: float, max_tokens: int) -> str:
    """Async wrapper for synchronous GPT call."""
    from ..gpt_client import _chat_completion
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: _chat_completion(
            prompt,
            extractor_name="deviation_summary",
            override_model=model,
            override_temperature=temperature
        )
    )


async def generate_summaries(
    scan_id: int,
    db: AsyncSession,
    redis_client: Optional[Any] = None
) -> Dict[str, int]:
    """
    Generate AI summaries for all deviation controls in a scan.
    
    Args:
        scan_id: ID of the scan to process
        db: Database session
        redis_client: Optional Redis client for progress tracking
        
    Returns:
        Dict with keys: success (int), failed (int), total (int)
    """
    from ..models import Control, Scan
    
    logger.info(f"Starting deviation summary generation for scan {scan_id}")
    
    # Fetch scan to get report_type
    scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = scan_result.scalar_one_or_none()
    
    if not scan:
        logger.error(f"Scan {scan_id} not found")
        return {"success": 0, "failed": 0, "total": 0}
    
    report_type = scan.report_type.value if scan.report_type else "SOC2"
    
    # Query controls with deviations AND high confidence (>= 0.7)
    result = await db.execute(
        select(Control)
        .where(Control.scan_id == scan_id)
        .where(Control.has_deviation == True)
        .where(Control.control_confidence >= 0.7)
        .order_by(Control.id)
    )
    deviation_controls = result.scalars().all()
    
    total = len(deviation_controls)
    success = 0
    failed = 0
    
    if total == 0:
        logger.info(f"No deviation controls found for scan {scan_id}")
        return {"success": 0, "failed": 0, "total": 0}
    
    logger.info(f"Found {total} deviation controls to summarize")
    
    # Set Redis progress key with 1 hour TTL
    redis_key = f"scan:{scan_id}:deviation_regen"
    if redis_client:
        try:
            await redis_client.setex(
                redis_key,
                3600,  # 1 hour TTL
                json.dumps({
                    "current": 0,
                    "total": total,
                    "status": "processing",
                    "timestamp": datetime.utcnow().isoformat()
                })
            )
        except Exception as e:
            logger.warning(f"Failed to set Redis progress: {e}")
    
    # Process each deviation sequentially
    for idx, control in enumerate(deviation_controls, 1):
        try:
            # Update Redis progress
            if redis_client:
                try:
                    await redis_client.setex(
                        redis_key,
                        3600,
                        json.dumps({
                            "current": idx,
                            "total": total,
                            "status": "processing",
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    )
                except Exception as e:
                    logger.warning(f"Failed to update Redis progress: {e}")
            
            # Build GPT prompt
            prompt = f"""Report Type: {report_type}
Control: {control.control_id or 'N/A'}
Description: {control.control_desc or 'N/A'}
Test Procedure: {control.control_test or 'N/A'}
Test Result: {control.control_test_results or 'N/A'}

In under 300 characters, explain in plain language what this deviation means for the organization. For SOC 1, focus on financial reporting impact; for SOC 2, focus on security/availability impact."""
            
            # Call GPT
            response = await call_gpt_async(
                prompt=prompt,
                model="gpt-3.5-turbo",
                temperature=0.3,
                max_tokens=150
            )
            
            if response and response.strip():
                # Truncate to 300 characters with ellipsis if needed
                summary = response.strip()
                if len(summary) > 300:
                    summary = summary[:297] + "..."
                
                # Update control
                control.deviation_summary = summary
                await db.commit()
                
                success += 1
                logger.info(f"Generated summary for control {control.control_id} ({idx}/{total})")
            else:
                failed += 1
                logger.warning(f"Empty response from GPT for control {control.control_id}")
                
        except Exception as e:
            failed += 1
            logger.error(f"Error generating summary for control {control.control_id}: {e}")
            # Continue processing remaining controls
    
    # Set final Redis status
    if redis_client:
        try:
            await redis_client.setex(
                redis_key,
                3600,
                json.dumps({
                    "current": total,
                    "total": total,
                    "status": "complete",
                    "timestamp": datetime.utcnow().isoformat(),
                    "success": success,
                    "failed": failed
                })
            )
        except Exception as e:
            logger.warning(f"Failed to set final Redis status: {e}")
    
    logger.info(f"Deviation summary generation complete: {success}/{total} successful, {failed} failed")
    
    return {
        "success": success,
        "failed": failed,
        "total": total
    }


async def regenerate_single_summary(
    control_id: int,
    db: AsyncSession
) -> Optional[str]:
    """
    Regenerate AI summary for a single deviation control.
    
    Args:
        control_id: ID of the control to regenerate
        db: Database session
        
    Returns:
        Generated summary string or None if failed
    """
    from ..models import Control, Scan
    
    # Fetch control
    result = await db.execute(select(Control).where(Control.id == control_id))
    control = result.scalar_one_or_none()
    
    if not control:
        logger.error(f"Control {control_id} not found")
        return None
    
    # Fetch scan for report_type
    scan_result = await db.execute(select(Scan).where(Scan.id == control.scan_id))
    scan = scan_result.scalar_one_or_none()
    report_type = scan.report_type.value if scan and scan.report_type else "SOC2"
    
    # Build GPT prompt
    prompt = f"""Report Type: {report_type}
Control: {control.control_id or 'N/A'}
Description: {control.control_desc or 'N/A'}
Test Procedure: {control.control_test or 'N/A'}
Test Result: {control.control_test_results or 'N/A'}

In under 300 characters, explain in plain language what this deviation means for the organization. For SOC 1, focus on financial reporting impact; for SOC 2, focus on security/availability impact."""
    
    try:
        # Call GPT
        response = await call_gpt_async(
            prompt=prompt,
            model="gpt-3.5-turbo",
            temperature=0.3,
            max_tokens=150
        )
        
        if response and response.strip():
            # Truncate to 300 characters with ellipsis if needed
            summary = response.strip()
            if len(summary) > 300:
                summary = summary[:297] + "..."
            
            # Update control
            control.deviation_summary = summary
            await db.commit()
            
            logger.info(f"Regenerated summary for control {control.control_id}")
            return summary
        else:
            logger.warning(f"Empty response from GPT for control {control.control_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error regenerating summary for control {control.control_id}: {e}")
        return None
