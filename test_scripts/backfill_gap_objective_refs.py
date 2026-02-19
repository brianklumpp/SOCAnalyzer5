"""
Backfill line_ref and page_refs for existing gap-extracted objectives.
"""
import sys
import asyncio
sys.path.insert(0, '/app/backend')
from app.database import get_db
from app.models import ControlObjective, Scan
from sqlalchemy import select
from typing import Optional, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def backfill_gap_objective_refs():
    """Find and update all gap-extracted objectives missing line/page refs."""
    async for db in get_db():
        # Get all gap-extracted objectives missing line_ref OR page_refs
        result = await db.execute(
            select(ControlObjective)
            .where(
                ControlObjective.extraction_method == 'gap_search',
                (ControlObjective.line_ref.is_(None)) | (ControlObjective.page_refs.is_(None))
            )
        )
        objectives = result.scalars().all()
        
        logger.info(f'Found {len(objectives)} gap objectives missing line_ref or page_refs')
        
        # Group by scan_id to batch process
        by_scan = {}
        for obj in objectives:
            if obj.scan_id not in by_scan:
                by_scan[obj.scan_id] = []
            by_scan[obj.scan_id].append(obj)
        
        total_updated = 0
        total_failed = 0
        
        for scan_id, objs in by_scan.items():
            logger.info(f'\nProcessing scan {scan_id} with {len(objs)} objectives')
            
            # Get scan and full text
            scan_result = await db.execute(
                select(Scan).where(Scan.id == scan_id)
            )
            scan = scan_result.scalars().first()
            
            if not scan or not scan.extracted_text:
                logger.warning(f'Scan {scan_id} has no extracted_text, skipping')
                total_failed += len(objs)
                continue
            
            text = scan.extracted_text
            text_lower = text.lower()
            
            for obj in objs:
                try:
                    line_ref, page_refs = find_line_and_page_refs(
                        text, text_lower, obj.objective_text, obj.objective_id, scan
                    )
                    
                    if line_ref:
                        obj.line_ref = line_ref
                        obj.page_refs = page_refs
                        total_updated += 1
                        logger.info(f'  ✓ {obj.objective_id}: line {line_ref}, pages {page_refs}')
                    else:
                        total_failed += 1
                        logger.warning(f'  ✗ {obj.objective_id}: not found in document')
                
                except Exception as e:
                    total_failed += 1
                    logger.error(f'  ✗ {obj.objective_id}: error - {e}')
        
        # Commit all updates
        await db.commit()
        
        logger.info(f'\n=== SUMMARY ===')
        logger.info(f'Total objectives: {len(objectives)}')
        logger.info(f'Updated: {total_updated}')
        logger.info(f'Failed: {total_failed}')
        
        break


def find_line_and_page_refs(
    text: str, 
    text_lower: str, 
    objective_text: str, 
    objective_id: str,
    scan: Scan
) -> tuple[Optional[int], Optional[List[int]]]:
    """Search the full document for the objective text and return line/page refs."""
    idx = -1
    
    # FIXED: Search for objective ID FIRST (more precise), then fall back to text
    if objective_id:
        # Use word boundaries to ensure exact match (e.g., "C1.2" won't match "CC1.2")
        import re
        pattern = r'\b' + re.escape(objective_id.lower()) + r'\b'
        match = re.search(pattern, text_lower)
        if match:
            idx = match.start()
    
    # Fall back to text search if ID not found
    if idx == -1 and objective_text and len(objective_text) >= 20:
        search_text = objective_text[:100].lower().strip()
        idx = text_lower.find(search_text)
    
    if idx == -1:
        logger.debug(f"Could not find objective ID or text in document for: {objective_id}")
        return None, None
    
    # Count lines up to this position
    line_number = text[:idx].count('\n') + 1
    
    # Find page number by scanning backwards for page markers
    page_number = None
    try:
        # Look backwards from the found position for the most recent page marker
        text_before = text[:idx]
        # Find all page markers like "==== Page 5 ====" or "=== PAGE 5 ==="
        import re
        page_markers = list(re.finditer(r'====?\s*(?:Page|PAGE)\s+(\d+)\s*====?', text_before))
        if page_markers:
            # Get the last page marker before this position
            last_marker = page_markers[-1]
            page_number = int(last_marker.group(1))
    except Exception as e:
        logger.warning(f"Error finding page number: {e}")
    
    return line_number, [page_number] if page_number else None


if __name__ == '__main__':
    asyncio.run(backfill_gap_objective_refs())
