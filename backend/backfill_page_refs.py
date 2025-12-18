"""
Backfill cuec_page_refs for existing CUECs and third_party_page_ref for existing subservice orgs.

This script updates all existing CUECs and subservice organizations in the database 
to populate their page reference fields based on their line references.
"""

import sys
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.pdf_handler import get_page_for_line

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def backfill_page_refs():
    """Backfill page references for all CUECs and subservice orgs."""
    # Use sync database URL (convert async URL to sync)
    database_url = os.getenv("DATABASE_URL_ASYNC", "")
    if database_url.startswith("postgresql+asyncpg://"):
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Get all scans
        scans_result = db.execute(text("SELECT id, extracted_text FROM scan ORDER BY id"))
        scans = scans_result.fetchall()
        
        logger.info(f"Found {len(scans)} scans to process")
        
        total_cuecs_updated = 0
        total_suborgs_updated = 0
        
        for scan_id, extracted_text in scans:
            logger.info(f"\nProcessing scan {scan_id}")
            
            # Load text from scan record
            if not extracted_text:
                logger.warning(f"  No extracted text for scan {scan_id}")
                continue
            
            try:
                txt_lines = extracted_text.split('\n')
                logger.info(f"  Loaded {len(txt_lines)} lines from extracted text")
            except Exception as e:
                logger.error(f"  Failed to process extracted text: {e}")
                continue
            
            # Update CUECs for this scan
            cuecs_result = db.execute(
                text("SELECT id, cuec_line_ref FROM cuec WHERE scan_id = :scan_id"),
                {"scan_id": scan_id}
            )
            cuecs = cuecs_result.fetchall()
            
            cuecs_updated = 0
            for cuec_id, cuec_line_ref in cuecs:
                if cuec_line_ref is None:
                    continue
                
                try:
                    page_num = get_page_for_line(txt_lines, cuec_line_ref)
                    if page_num:
                        # Update cuec_page_refs as a PostgreSQL array of integers
                        db.execute(
                            text("UPDATE cuec SET cuec_page_refs = :page_refs::json WHERE id = :cuec_id"),
                            {"page_refs": f"[{page_num}]", "cuec_id": cuec_id}
                        )
                        cuecs_updated += 1
                except Exception as e:
                    logger.error(f"  Error updating CUEC {cuec_id}: {e}")
            
            if cuecs_updated > 0:
                db.commit()
                logger.info(f"  Updated {cuecs_updated} CUECs")
                total_cuecs_updated += cuecs_updated
        
        logger.info(f"\n✅ Backfill complete!")
        logger.info(f"Total CUECs updated: {total_cuecs_updated}")
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    backfill_page_refs()
