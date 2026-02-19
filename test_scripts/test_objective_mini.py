"""
Fast iteration test for objective extraction with small sample.
Run directly: python test_scripts/test_objective_mini.py
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.extractors.objective_extractor import extract_objectives, map_controls_to_objectives
from backend.app.models import Control, ControlObjective, ControlObjectiveMapping
from backend.app import config
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Small sample text with 5 objectives for fast testing
SAMPLE_TEXT = """
=== PAGE 50 ===
Common Criteria Related to Security, Availability, and Confidentiality
Criteria: Trust Services Criteria

CC1.1: The entity demonstrates a commitment to integrity and ethical values.
Control EM-01-01: The Board of Directors provides corporate oversight, strategic direction, and review of management.

CC1.2: The board of directors demonstrates independence from management and exercises oversight of the development and performance of internal control.
Control EM-01-02: The Audit Committee is governed by a charter, is independent from Adobe management.

CC2.1: The entity demonstrates a commitment to attract, develop, and retain competent individuals in alignment with objectives.
Control PR-01-01: New hires are required to pass a background check as a condition of their employment.

CC3.1: The entity specifies objectives with sufficient clarity to enable the identification and assessment of risks.
Control RM-01-01: A Security Risk Management Framework is documented which defines the security risk management methodology.

CC6.1: The entity implements logical access security software, infrastructure, and architectures over protected information assets.
Control AM-01-01: Adobe maintains an inventory of system devices, which is reconciled on a periodic basis.
"""

def test_objective_extraction():
    """Test objective extraction pipeline with minimal sample."""
    print("\n" + "=" * 80)
    print("MINI OBJECTIVE EXTRACTION TEST")
    print("=" * 80)
    
    # Create database connection
    sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
    engine = create_engine(sync_db_url, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()
    
    try:
        # Use test scan ID 998
        test_scan_id = 998
        
        # Clean up
        print("\n[1/5] Cleaning previous test data...")
        db_session.query(ControlObjectiveMapping).filter(
            ControlObjectiveMapping.control_id.in_(
                db_session.query(Control.id).filter_by(scan_id=test_scan_id)
            )
        ).delete(synchronize_session=False)
        db_session.query(ControlObjective).filter_by(scan_id=test_scan_id).delete()
        db_session.query(Control).filter_by(scan_id=test_scan_id).delete()
        db_session.commit()
        print("✓ Cleanup complete")
        
        # Create test controls
        print("\n[2/5] Creating test controls...")
        test_controls = [
            Control(scan_id=test_scan_id, control_id='EM-01-01', control_desc='Board oversight', control_confidence=0.9, line_ref=52, has_deviation=False),
            Control(scan_id=test_scan_id, control_id='EM-01-02', control_desc='Audit Committee independence', control_confidence=0.9, line_ref=56, has_deviation=False),
            Control(scan_id=test_scan_id, control_id='PR-01-01', control_desc='Background checks', control_confidence=0.9, line_ref=60, has_deviation=False),
            Control(scan_id=test_scan_id, control_id='RM-01-01', control_desc='Risk framework', control_confidence=0.9, line_ref=64, has_deviation=False),
            Control(scan_id=test_scan_id, control_id='AM-01-01', control_desc='Device inventory', control_confidence=0.9, line_ref=68, has_deviation=False),
        ]
        for ctrl in test_controls:
            db_session.add(ctrl)
        db_session.commit()
        print(f"✓ Created {len(test_controls)} controls")
        
        # Extract objectives
        print("\n[3/5] Extracting objectives...")
        print("=" * 80)
        
        objectives = extract_objectives(
            extracted_text=SAMPLE_TEXT,
            scan_id=test_scan_id,
            db_session=db_session,
            sections=[],
            job_id=None,
            redis_client=None
        )
        
        print("\n" + "=" * 80)
        print(f"✓ Extracted {len(objectives)} objectives")
        
        # Show results
        if objectives:
            print("\nExtracted Objectives:")
            for idx, obj in enumerate(objectives, 1):
                print(f"  [{idx}] {obj.objective_id}")
                print(f"      Confidence: {obj.final_confidence:.3f}")
                print(f"      Status: {obj.status}")
                print(f"      Line: {obj.line_ref}, Page: {obj.page_refs}")
        
        # Verify database
        print("\n[4/5] Verifying database...")
        db_count = db_session.query(ControlObjective).filter_by(scan_id=test_scan_id).count()
        print(f"✓ Database contains {db_count} objectives")
        
        if db_count == 0:
            print("\n❌ FAILURE: No objectives saved to database!")
            print("Check logs above for errors during extraction")
            return False
        
        # Map to controls
        print("\n[5/5] Mapping controls to objectives...")
        mappings = map_controls_to_objectives(
            scan_id=test_scan_id,
            db_session=db_session,
            job_id=None,
            redis_client=None
        )
        print(f"✓ Created {mappings} mappings")
        
        # Final summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Controls:       {len(test_controls)}")
        print(f"Objectives:     {len(objectives)}")
        print(f"DB Objectives:  {db_count}")
        print(f"Mappings:       {mappings}")
        
        auto_approved = db_session.query(ControlObjective).filter_by(
            scan_id=test_scan_id, status='auto_approved'
        ).count()
        print(f"Auto-approved:  {auto_approved}")
        
        if db_count > 0:
            print("\n✅ TEST PASSED")
            return True
        else:
            print("\n❌ TEST FAILED")
            return False
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        db_session.close()
        engine.dispose()

if __name__ == "__main__":
    success = test_objective_extraction()
    sys.exit(0 if success else 1)
