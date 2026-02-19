"""
Cleanup script to fix objective IDs with trailing newlines and update missing line/page refs.
Run this once to clean existing database records.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.models import ControlObjective
from app.utils.objective_id_normalizer import normalize_objective_id
from sqlalchemy import func

def cleanup_objective_ids():
    """Remove trailing newlines and whitespace from objective IDs."""
    db = SessionLocal()
    try:
        # Find objectives with whitespace issues in any ID field
        objectives = db.query(ControlObjective).filter(
            (ControlObjective.objective_id.like('%\n%')) |
            (ControlObjective.objective_id.like('%\r%')) |
            (ControlObjective.objective_id.like('%\t%')) |
            (ControlObjective.objective_id_original.like('%\n%')) |
            (ControlObjective.objective_id_original.like('%\r%')) |
            (ControlObjective.objective_id_original.like('%\t%'))
        ).all()
        
        if not objectives:
            print("No objectives with whitespace issues found.")
            return
        
        print(f"Found {len(objectives)} objectives with whitespace issues.")
        
        for obj in objectives:
            old_id = obj.objective_id
            old_original = obj.objective_id_original
            
            # Clean objective_id
            if obj.objective_id:
                cleaned = obj.objective_id.strip().replace('\n', '').replace('\r', '').replace('\t', ' ')
                obj.objective_id = cleaned
            
            # Clean objective_id_original
            if obj.objective_id_original:
                cleaned_original = obj.objective_id_original.strip().replace('\n', '').replace('\r', '').replace('\t', ' ')
                obj.objective_id_original = cleaned_original
                # Re-normalize
                obj.objective_id_normalized = normalize_objective_id(cleaned_original)
            
            if old_id != obj.objective_id or old_original != obj.objective_id_original:
                print(f"  Cleaned: '{old_id}' -> '{obj.objective_id}'")
        
        db.commit()
        print(f"Successfully cleaned {len(objectives)} objective IDs.")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


def fix_missing_refs():
    """Find objectives with missing line_ref or page_refs and log them."""
    db = SessionLocal()
    try:
        # Find objectives with null line_ref
        missing_line = db.query(ControlObjective).filter(
            ControlObjective.line_ref.is_(None)
        ).count()
        
        # Find objectives with null or empty page_refs
        missing_page = db.query(ControlObjective).filter(
            (ControlObjective.page_refs.is_(None)) | (ControlObjective.page_refs == '')
        ).count()
        
        print(f"\nMissing references:")
        print(f"  Objectives with null line_ref: {missing_line}")
        print(f"  Objectives with null/empty page_refs: {missing_page}")
        
        if missing_line > 0 or missing_page > 0:
            print("\nThese objectives need to be re-extracted to get proper references.")
            print("The extraction logic should now properly set these values.")
        
    finally:
        db.close()


if __name__ == "__main__":
    print("Starting objective ID cleanup...")
    cleanup_objective_ids()
    fix_missing_refs()
    print("\nCleanup complete!")
