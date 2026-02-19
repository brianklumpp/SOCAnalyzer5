"""
Fast objective extraction test - extract ~10 objectives in seconds
Run: docker exec -it socanalyzer-backend python /app/backend/app/test_objectives_fast.py
"""
import sys
import os

# Critical: Add /app to path FIRST before any backend imports
sys.path.insert(0, '/app')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.models import Scan, ControlObjective
from backend.app.extractors.objective_extractor import extract_objectives
import logging

# Configure logging - CRITICAL only to reduce noise
logging.basicConfig(
    level=logging.CRITICAL,
    format='%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s'
)
logger = logging.getLogger(__name__)

# Database connection
SYNC_DB = "postgresql+psycopg2://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"

def main():
    print("\n" + "="*80)
    print("FAST OBJECTIVE EXTRACTION TEST (~10 objectives)")
    print("="*80 + "\n")
    
    engine = create_engine(SYNC_DB)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # Get scan 2 (has extracted text)
        scan = db.query(Scan).filter_by(id=2).first()
        if not scan or not scan.extracted_text:
            print("ERROR: Scan 2 not found or has no extracted text")
            return 1
        
        print(f"✓ Using scan 2: {len(scan.extracted_text)} chars of extracted text")
        
        # Take just first 15000 chars (~10 objectives worth)
        sample_text = scan.extracted_text[:15000]
        print(f"✓ Testing with first 15000 chars (sample)")
        
        # Create minimal section def (assume Control_Descriptions starts at line 1)
        sections = [
            {
                'topic': 'Control_Descriptions',
                'start_line': 1,
                'end_line': sample_text.count('\n') + 1,
                'type': 'mapped'
            }
        ]
        
        # Create test scan if it doesn't exist
        test_scan_id = 999
        test_scan = db.query(Scan).filter(Scan.id == test_scan_id).first()
        if not test_scan:
            print(f"✓ Creating test scan {test_scan_id}...")
            test_scan = Scan(
                id=test_scan_id,
                pdf_filename="FAST_TEST_DO_NOT_USE.pdf",
                extracted_text="Test scan for rapid iteration testing",
                report_type="SOC2"
            )
            db.add(test_scan)
            db.commit()
            db.refresh(test_scan)
        
        # Delete old test objectives
        existing = db.query(ControlObjective).filter_by(scan_id=test_scan_id).count()
        if existing > 0:
            print(f"✓ Cleaning {existing} old test objectives...")
            db.query(ControlObjective).filter_by(scan_id=test_scan_id).delete()
            db.commit()
                # Diagnostic: Check for objective keywords
        from backend.app import config
        print(f"\n✓ Checking for objective section keywords...")
        keywords_found = []
        for keyword in config.OBJECTIVE_SECTION_KEYWORDS:
            if keyword in sample_text.lower():
                keywords_found.append(keyword)
        
        if keywords_found:
            print(f"  ✓ Found keywords: {', '.join(keywords_found)}")
        else:
            print(f"  ⚠ WARNING: No objective section keywords found in sample text!")
            print(f"  This means distance_confidence will be 0 for all objectives.")
                # Extract
        print("\n" + "="*80)
        print("EXTRACTING OBJECTIVES...")
        print("="*80 + "\n")
        
        objectives = extract_objectives(
            extracted_text=sample_text,
            scan_id=test_scan_id,
            db_session=db,
            sections=sections,
            job_id=None,
            redis_client=None
        )
        
        print("\n" + "="*80)
        print("RESULTS")
        print("="*80 + "\n")
        
        print(f"✓ Extracted {len(objectives)} objectives\n")
        
        if objectives:
            for idx, obj in enumerate(objectives, 1):
                print(f"[{idx}] {obj.objective_id or '(no ID)'}")
                text = obj.objective_text[:100] + "..." if len(obj.objective_text) > 100 else obj.objective_text
                print(f"    {text}")
                print(f"    Confidence: {obj.final_confidence:.3f} | Status: {obj.status}")
        
        # Check database
        db_count = db.query(ControlObjective).filter_by(scan_id=test_scan_id).count()
        print(f"\n✓ Database contains {db_count} objectives for test scan {test_scan_id}")
        
        if db_count > 0:
            print("\n✅ TEST PASSED - Objectives extracted and saved!")
            return 0
        else:
            print("\n❌ TEST FAILED - No objectives in database")
            return 1
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()
        engine.dispose()

if __name__ == "__main__":
    sys.exit(main())
