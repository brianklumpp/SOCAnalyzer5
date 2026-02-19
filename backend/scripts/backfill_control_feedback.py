"""
Backfill control_feedback table from existing edit_log entries.

Parses edit_log text on controls to retroactively populate the ControlFeedback
learning system from historical manual review data (scans 2 and 3).

Usage:
    cd backend
    python -m scripts.backfill_control_feedback
"""

import re
import sys
import os
import datetime

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# Use the same DB URL as the app
DATABASE_URL = os.environ.get(
    "DATABASE_URL_ASYNC",
    "postgresql+asyncpg://soc2_analyzer:puntitforthewin@localhost:5433/soc2analyzer"
).replace("postgresql+asyncpg", "postgresql")

engine = create_engine(DATABASE_URL)

# TSC criteria pattern
TSC_PATTERN = re.compile(r'^(CC|A|C|P|PI)\d+\.\d+$', re.IGNORECASE)

# Auditor test language
AUDITOR_VERBS = ("inspected", "observed", "tested", "inquired", "examined", "reviewed the")


def classify_rejection_reason(control_id_text, control_desc):
    """Classify why a control was rejected based on its content."""
    cid = (control_id_text or "").strip()
    desc = (control_desc or "").strip().lower()

    if TSC_PATTERN.match(cid):
        return "tsc_criteria"
    if any(desc.startswith(v) for v in AUDITOR_VERBS):
        return "auditor_test_procedure"
    if "to determine whether" in desc:
        return "auditor_test_procedure"
    if len(desc) < 200 and any(desc.startswith(n) for n in ("the company's", "the organization's", "according to")):
        return "narrative_statement"
    if len(desc) < 80:
        return "enumeration_fragment"
    if len(desc) < 120:
        return "generic_statement"
    return "other"


def backfill():
    """Parse edit_logs and create ControlFeedback records."""
    with engine.connect() as conn:
        # Check existing feedback count
        existing = conn.execute(text("SELECT COUNT(*) FROM control_feedback")).scalar()
        print(f"Existing control_feedback rows: {existing}")
        
        if existing > 0:
            print("⚠️  Feedback table not empty. Skipping backfill to avoid duplicates.")
            print("   To force re-backfill, run: DELETE FROM control_feedback;")
            return
        
        # Get all controls with edit_logs
        rows = conn.execute(text("""
            SELECT c.id, c.scan_id, c.control_id, c.control_desc,
                   c.control_confidence, c.edit_log,
                   s.company
            FROM control c
            JOIN scan s ON c.scan_id = s.id
            WHERE c.edit_log IS NOT NULL AND c.edit_log != ''
            ORDER BY c.scan_id, c.id
        """)).fetchall()
        
        print(f"Found {len(rows)} controls with edit_logs")
        
        inserted = 0
        
        for row in rows:
            ctrl_id = row[0]
            scan_id = row[1]
            control_id_text = row[2] or ""
            control_desc = row[3] or ""
            current_confidence = row[4]
            edit_log = row[5] or ""
            company = row[6] or ""
            
            desc_snippet = control_desc[:300]
            
            # Parse edit_log for actions
            # Pattern 1: "Converted to control objective"
            if "Converted to control objective" in edit_log:
                reason = "tsc_criteria" if TSC_PATTERN.match(control_id_text.strip()) else "other"
                conn.execute(text("""
                    INSERT INTO control_feedback 
                    (scan_id, control_db_id, action, original_confidence,
                     control_id_text, control_desc_snippet, rejection_reason, created_at)
                    VALUES (:scan_id, :control_db_id, 'converted_to_objective', :orig_conf,
                            :cid_text, :desc_snippet, :reason, :created_at)
                """), {
                    "scan_id": scan_id,
                    "control_db_id": ctrl_id,
                    "orig_conf": current_confidence,  # May already be 0, but best we have
                    "cid_text": control_id_text[:128],
                    "desc_snippet": desc_snippet,
                    "reason": reason,
                    "created_at": datetime.datetime.utcnow(),
                })
                inserted += 1
                print(f"  [{scan_id}] converted_to_objective: {control_id_text} ({reason})")
                continue
            
            # Pattern 2: "UI edit: control_confidence X -> 0" or "confidence 0.9 -> 0.0"
            conf_match = re.search(r'control_confidence\s+([\d.]+)\s*->\s*([\d.]+)', edit_log)
            if conf_match:
                old_conf = float(conf_match.group(1))
                new_conf = float(conf_match.group(2))
                
                if new_conf < 0.01:
                    # Rejected (zeroed)
                    reason = classify_rejection_reason(control_id_text, control_desc)
                    conn.execute(text("""
                        INSERT INTO control_feedback 
                        (scan_id, control_db_id, action, original_confidence,
                         control_id_text, control_desc_snippet, rejection_reason, created_at)
                        VALUES (:scan_id, :control_db_id, 'rejected', :orig_conf,
                                :cid_text, :desc_snippet, :reason, :created_at)
                    """), {
                        "scan_id": scan_id,
                        "control_db_id": ctrl_id,
                        "orig_conf": old_conf,
                        "cid_text": control_id_text[:128],
                        "desc_snippet": desc_snippet,
                        "reason": reason,
                        "created_at": datetime.datetime.utcnow(),
                    })
                    inserted += 1
                    print(f"  [{scan_id}] rejected: {control_id_text} (conf {old_conf}->{new_conf}, {reason})")
                    continue
            
            # Pattern 3: "UI edit: control_id X -> Y"
            id_match = re.search(r'control_id\s+(.+?)\s*->\s*(.+?)(?:\s+by|\s*$)', edit_log)
            if id_match:
                old_id = id_match.group(1).strip()
                new_id = id_match.group(2).strip()
                if old_id != new_id:
                    conn.execute(text("""
                        INSERT INTO control_feedback 
                        (scan_id, control_db_id, action, original_confidence,
                         control_id_text, control_desc_snippet, corrected_control_id, created_at)
                        VALUES (:scan_id, :control_db_id, 'id_corrected', :orig_conf,
                                :old_id, :desc_snippet, :new_id, :created_at)
                    """), {
                        "scan_id": scan_id,
                        "control_db_id": ctrl_id,
                        "orig_conf": current_confidence,
                        "old_id": old_id[:128],
                        "desc_snippet": desc_snippet,
                        "new_id": new_id[:128],
                        "created_at": datetime.datetime.utcnow(),
                    })
                    inserted += 1
                    print(f"  [{scan_id}] id_corrected: {old_id} -> {new_id}")
                    continue
        
        conn.commit()
        print(f"\n✅ Backfilled {inserted} control_feedback records")
        
        # Summary by scan and action
        summary = conn.execute(text("""
            SELECT scan_id, action, rejection_reason, COUNT(*)
            FROM control_feedback
            GROUP BY scan_id, action, rejection_reason
            ORDER BY scan_id, action
        """)).fetchall()
        
        print("\nSummary:")
        for r in summary:
            reason_str = f" ({r[2]})" if r[2] else ""
            print(f"  Scan {r[0]}: {r[1]}{reason_str} = {r[3]}")


if __name__ == "__main__":
    backfill()
