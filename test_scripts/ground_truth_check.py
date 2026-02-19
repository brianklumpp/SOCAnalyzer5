#!/usr/bin/env python3
"""Search for all CC series objectives in PDF to establish ground truth."""

import sys
import os
sys.path.insert(0, '/app/backend')

from sqlalchemy import create_engine, text
import re
from collections import defaultdict

DATABASE_URL = "postgresql://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT id, pdf_filename, extracted_text
        FROM scan
        ORDER BY id DESC
        LIMIT 1
    """))
    
    scan = result.fetchone()
    extracted_text = scan[2]
    
    print("=" * 80)
    print("COMPLETE CC SERIES INVENTORY IN PDF")
    print("=" * 80)
    print(f"Scan ID: {scan[0]}")
    print(f"PDF: {scan[1]}")
    
    lines = extracted_text.split('\n')
    
    # Search for all CC patterns (CC1.x through CC9.x)
    cc_pattern = re.compile(r'\bCC(\d)\.(\d+)\b')
    
    all_matches = defaultdict(set)
    
    for line_num, line in enumerate(lines, start=1):
        for match in cc_pattern.finditer(line):
            series = int(match.group(1))
            sub_num = int(match.group(2))
            obj_id = f"CC{series}.{sub_num}"
            all_matches[series].add(obj_id)
    
    print("\nGROUND TRUTH - All CC Objectives in PDF:\n")
    
    for series in range(1, 10):
        if series in all_matches:
            obj_ids = sorted(all_matches[series], key=lambda x: int(x.split('.')[1]))
            print(f"  CC{series}: {', '.join(obj_ids)} ({len(obj_ids)} objectives)")
        else:
            print(f"  CC{series}: (none found)")
    
    # Now compare with extracted
    result = conn.execute(text("""
        SELECT objective_id
        FROM control_objectives
        WHERE scan_id = :scan_id AND objective_id LIKE 'CC%'
        ORDER BY objective_id
    """), {"scan_id": scan[0]})
    
    extracted = {row[0] for row in result.fetchall()}
    
    print("\n" + "=" * 80)
    print("EXTRACTION ACCURACY:")
    print("=" * 80)
    
    total_in_pdf = sum(len(objs) for objs in all_matches.values())
    total_extracted = len(extracted)
    
    print(f"\nTotal CC objectives in PDF: {total_in_pdf}")
    print(f"Total CC objectives extracted: {total_extracted}")
    
    # Find missing
    all_in_pdf = set()
    for objs in all_matches.values():
        all_in_pdf.update(objs)
    
    missing = all_in_pdf - extracted
    false_positives = extracted - all_in_pdf
    
    if missing:
        print(f"\n⚠️  Missing (in PDF but not extracted): {', '.join(sorted(missing))}")
    else:
        print(f"\n✓ No missing objectives!")
    
    if false_positives:
        print(f"⚠️  False positives (extracted but not in PDF): {', '.join(sorted(false_positives))}")
    else:
        print(f"✓ No false positives!")
    
    accuracy = (total_extracted - len(false_positives)) / total_in_pdf * 100 if total_in_pdf > 0 else 0
    print(f"\nExtraction Accuracy: {accuracy:.1f}%")
    
    print("\n" + "=" * 80)
