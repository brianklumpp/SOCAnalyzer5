#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from sqlalchemy import create_engine
from backend.app.models import Scan, ControlObjective
from sqlalchemy.orm import sessionmaker
import re

DB_URL = "postgresql://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
sess = Session()

# Get latest scan
scan = sess.query(Scan).order_by(Scan.id.desc()).first()
if not scan:
    print("No scan found")
    sys.exit(1)

print(f"Scan ID: {scan.id}")
print(f"PDF: {scan.pdf_filename}\n")

# Get all objectives for this scan
objectives = sess.query(ControlObjective).filter_by(scan_id=scan.id).all()
print(f"Total objectives extracted: {len(objectives)}\n")

# Group by prefix
from collections import defaultdict
by_prefix = defaultdict(list)
for obj in objectives:
    # Extract prefix (e.g., "CC1", "CC7", "C1", "A1")
    match = re.match(r'^([A-Z]+)(\d+)', obj.objective_id)
    if match:
        prefix = match.group(1) + match.group(2)
        by_prefix[prefix].append(obj.objective_id)

# Show what was extracted
print("Extracted objectives by prefix:")
for prefix in sorted(by_prefix.keys()):
    obj_ids = sorted(by_prefix[prefix])
    print(f"  {prefix}: {', '.join(obj_ids)}")

# Check for missing common prefixes
print("\nMissing common prefixes:")
expected_prefixes = ['CC1', 'CC2', 'CC3', 'CC4', 'CC5', 'CC6', 'CC7', 'CC8', 'CC9', 'C1', 'A1', 'P1', 'PI1']
missing = [p for p in expected_prefixes if p not in by_prefix]
if missing:
    for m in missing:
        print(f"  ✗ {m}")
else:
    print("  ✓ All expected prefixes found!")

# Show extraction method breakdown
print("\nExtraction method breakdown:")
method_counts = {}
for obj in objectives:
    method = obj.extraction_method or 'unknown'
    method_counts[method] = method_counts.get(method, 0) + 1
for method, count in sorted(method_counts.items()):
    print(f"  {method}: {count}")
