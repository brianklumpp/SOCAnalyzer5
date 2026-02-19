"""
Backfill objective page_refs using get_page_for_line() method (same as controls).

This script:
1. Loads extracted text with page markers for scan 3
2. For each objective with a line_ref, uses get_page_for_line() to find the correct page
3. Updates the page_refs column with the corrected values
4. Also sets toc_page_offset to 0 for scan 3
"""
import sys
import asyncio
sys.path.insert(0, 'backend')

from app.database import AsyncSessionLocal
from app.models import ControlObjective, Scan
from app.pdf_handler import get_page_for_line
from sqlalchemy import select, update
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def backfill_page_refs():
    """Backfill page_refs for objectives using get_page_for_line"""
    async with AsyncSessionLocal() as session:
        try:
            # Step 1: Update toc_page_offset to 0 for scan 3
            logger.info("Updating toc_page_offset to 0 for scan 3...")
            await session.execute(
                update(Scan).where(Scan.id == 3).values(toc_page_offset=0)
            )
            await session.commit()
            logger.info("✅ Updated toc_page_offset to 0")
            
            # Step 2: Load extracted text from scan 3's file
            scan = await session.execute(select(Scan).where(Scan.id == 3))
            scan = scan.scalar_one_or_none()
            
            if not scan:
                logger.error("❌ Scan 3 not found")
                return
            
            # Get text file path from scan
            import os
            from pathlib import Path
            txt_path = Path('data') / 'tmp' / f"{scan.id}" / "extracted.txt"
            
            if not txt_path.exists():
                logger.error(f"❌ Text file not found: {txt_path}")
                return
            
            logger.info(f"Loading extracted text from {txt_path}...")
            with open(txt_path, 'r', encoding='utf-8') as f:
                full_text = f.read()
            
            full_doc_lines = full_text.split('\n')
            logger.info(f"Loaded {len(full_doc_lines)} lines from extracted text")
            
            # Step 3: Load objectives for scan 3
            result = await session.execute(
                select(ControlObjective).where(ControlObjective.scan_id == 3)
            )
            objectives = result.scalars().all()
            
            logger.info(f"Found {len(objectives)} objectives for scan 3")
            
            # Step 4: Update page_refs using get_page_for_line
            updated = 0
            failed = 0
            
            for obj in objectives:
                if obj.line_ref is None:
                    logger.warning(f"Objective {obj.objective_id}: No line_ref available, skipping")
                    failed += 1
                    continue
                
                try:
                    # Use get_page_for_line (same method as controls)
                    page_num = get_page_for_line(full_doc_lines, obj.line_ref)
                    
                    if page_num:
                        old_page_refs = obj.page_refs
                        obj.page_refs = [page_num]
                        logger.info(
                            f"Objective {obj.objective_id}: "
                            f"line_ref={obj.line_ref}, "
                            f"old_page_refs={old_page_refs}, "
                            f"new_page_refs=[{page_num}]"
                        )
                        updated += 1
                    else:
                        logger.warning(f"Objective {obj.objective_id}: Could not find page for line_ref={obj.line_ref}")
                        failed += 1
                        
                except Exception as e:
                    logger.error(f"Objective {obj.objective_id}: Error - {e}")
                    failed += 1
            
            # Commit changes
            await session.commit()
            
            logger.info("=" * 80)
            logger.info(f"✅ Backfill complete:")
            logger.info(f"   Total objectives: {len(objectives)}")
            logger.info(f"   Updated: {updated}")
            logger.info(f"   Failed: {failed}")
            
            # Show sample results
            result = await session.execute(
                select(ControlObjective)
                .where(ControlObjective.scan_id == 3)
                .where(ControlObjective.page_refs.isnot(None))
                .limit(10)
            )
            samples = result.scalars().all()
            
            logger.info("\nSample results:")
            for obj in samples:
                logger.info(f"  {obj.objective_id}: line_ref={obj.line_ref}, page_refs={obj.page_refs}")
                
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            await session.rollback()

if __name__ == "__main__":
    asyncio.run(backfill_page_refs())
