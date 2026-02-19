"""
Test objective extraction standalone without full scan
Usage: docker exec -it socanalyzer-backend python /app/test_objective_extraction.py <scan_id>
"""
import sys
import os

# Add backend to path since we're in /app
sys.path.insert(0, '/app/backend')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.app.models import Scan, ControlObjective
from backend.app.extractors.objective_extractor import extract_objectives
import logging

# Configure logging to show everything
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[logging.StreamHandler()]
)

# Use postgres service name from docker-compose with correct password
SYNC_DATABASE_URL = "postgresql+psycopg2://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_objective_extraction.py <scan_id>")
        print("Example: python test_objective_extraction.py 2")
        sys.exit(1)
    
    scan_id = int(sys.argv[1])
    
    print(f"\n{'='*80}")
    print(f"OBJECTIVE EXTRACTION TEST - Scan ID: {scan_id}")
    print(f"{'='*80}\n")
    
    # Create database session (synchronous)
    engine = create_engine(SYNC_DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # Get scan
        scan = db.query(Scan).filter_by(id=scan_id).first()
        if not scan:
            print(f"ERROR: Scan {scan_id} not found")
            sys.exit(1)
        
        print(f"✓ Found scan: {scan.company} - {scan.product}")
        print(f"  Extracted text length: {len(scan.extracted_text) if scan.extracted_text else 0} characters")
        
        # Delete existing objectives for this scan
        existing_count = db.query(ControlObjective).filter_by(scan_id=scan_id).count()
        if existing_count > 0:
            print(f"\n⚠ Found {existing_count} existing objectives - deleting them first...")
            db.query(ControlObjective).filter_by(scan_id=scan_id).delete()
            db.commit()
            print(f"✓ Deleted {existing_count} objectives")
        
        # Run extraction
        print(f"\n{'='*80}")
        print("STARTING OBJECTIVE EXTRACTION")
        print(f"{'='*80}\n")
        
        objectives = extract_objectives(
            extracted_text=scan.extracted_text,
            scan_id=scan_id,
            db_session=db
        )
        
        print(f"\n{'='*80}")
        print("EXTRACTION COMPLETE")
        print(f"{'='*80}\n")
        
        print(f"✓ Extracted {len(objectives)} objectives")
        
        # Show summary
        if objectives:
            print("\nObjectives summary:")
            for i, obj in enumerate(objectives[:10], 1):  # Show first 10
                obj_id = obj.objective_id or "(no ID)"
                text_preview = obj.objective_text[:80] + "..." if len(obj.objective_text) > 80 else obj.objective_text
                print(f"  {i}. [{obj_id}] {text_preview}")
                print(f"      Confidence: {obj.final_confidence:.3f}, Method: {obj.extraction_method}, Status: {obj.status}")
            
            if len(objectives) > 10:
                print(f"  ... and {len(objectives) - 10} more")
        
        # Check database
        db_count = db.execute(
            text(f"SELECT COUNT(*) FROM control_objectives WHERE scan_id = :scan_id"),
            {"scan_id": scan_id}
        ).scalar()
        print(f"\n✓ Database shows {db_count} objectives saved for scan {scan_id}")
        
        # Show status breakdown
        status_results = db.execute(
            text(f"SELECT status, COUNT(*) FROM control_objectives WHERE scan_id = :scan_id GROUP BY status"),
            {"scan_id": scan_id}
        ).fetchall()
        if status_results:
            print("\nStatus breakdown:")
            for status, count in status_results:
                print(f"  {status}: {count}")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()
