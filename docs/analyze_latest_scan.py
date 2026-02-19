#!/usr/bin/env python3
"""Analyze the latest scan's objective extraction."""

import sys
import os
sys.path.insert(0, '/app/backend')

from sqlalchemy import create_engine, text
import re
from collections import defaultdict

DATABASE_URL = "postgresql://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Get the latest scan
    result = conn.execute(text("""
        SELECT id, scan_date, progress_status, pdf_filename
        FROM scan
        ORDER BY id DESC
        LIMIT 1
    """))
    
    scan = result.fetchone()
    
    if not scan:
        print("No scans found")
        sys.exit(1)
    
    scan_id = scan[0]
    
    print("=" * 80)
    print("LATEST SCAN OBJECTIVE EXTRACTION ANALYSIS")
    print("=" * 80)
    print(f"\nScan ID:  {scan[0]}")
    print(f"Date:     {scan[1]}")
    print(f"Status:   {scan[2]}")
    print(f"PDF:      {scan[3]}")
    
    # Get objectives for this scan
    result = conn.execute(text("""
        SELECT objective_id, extraction_method, final_confidence, line_ref
        FROM control_objectives
        WHERE scan_id = :scan_id
        ORDER BY objective_id
    """), {"scan_id": scan_id})
    
    objectives = result.fetchall()
    
    print(f"\n{'=' * 80}")
    print(f"TOTAL OBJECTIVES EXTRACTED: {len(objectives)}")
    print("=" * 80)
    
    if len(objectives) == 0:
        print("\n⚠️  NO OBJECTIVES EXTRACTED")
        print("This could mean:")
        print("  1. Scan is still in progress")
        print("  2. Objective extraction failed")
        print("  3. No objectives found in PDF")
        sys.exit(0)
    
    # Group by prefix
    by_prefix = defaultdict(list)
    for obj in objectives:
        obj_id = obj[0]
        # Extract prefix (e.g., CC1, CC2, A1, C1)
        match = re.match(r'^([A-Z]+\d+)', obj_id)
        if match:
            prefix = match.group(1)
            by_prefix[prefix].append(obj_id)
    
    # Sort prefixes for display
    sorted_prefixes = sorted(by_prefix.keys(), key=lambda x: (x[0], int(re.search(r'\d+', x).group())))
    
    print("\nObjectives by Series:")
    for prefix in sorted_prefixes:
        ids = sorted(by_prefix[prefix])
        print(f"  {prefix}: {', '.join(ids)} ({len(ids)} objectives)")
    
    # Check for critical series
    print("\nCritical Series Status:")
    critical_series = {
        'CC1': '✓ CC1 series',
        'CC2': '✓ CC2 series',
        'CC3': '✓ CC3 series',
        'CC4': '⚠️  CC4 series (historically missing)',
        'CC5': '⚠️  CC5 series (historically missing)',
        'CC6': '✓ CC6 series',
        'CC7': '⚠️  CC7 series (historically missing)',
        'CC8': '⚠️  CC8 series (historically missing)',
        'CC9': '⚠️  CC9 series (historically missing)',
    }
    
    for series, label in critical_series.items():
        if series in by_prefix:
            count = len(by_prefix[series])
            print(f"  ✓ {series}: FOUND ({count} objectives) - {', '.join(sorted(by_prefix[series]))}")
        else:
            print(f"  ✗ {series}: MISSING")
    
    # Show extraction methods
    method_counts = defaultdict(int)
    for obj in objectives:
        method_counts[obj[1]] += 1
    
    print(f"\n{'=' * 80}")
    print("Extraction Methods:")
    print("=" * 80)
    for method, count in sorted(method_counts.items()):
        pct = (count / len(objectives) * 100) if len(objectives) > 0 else 0
        print(f"  {method}: {count} ({pct:.1f}%)")
    
    # Expected vs actual
    print(f"\n{'=' * 80}")
    print("EXPECTED IN PDF vs EXTRACTED:")
    print("=" * 80)
    
    expected = {
        'CC4': 2,
        'CC5': 3,
        'CC7': 5,  # 5 in Control_Descriptions section
        'CC8': 3,
        'CC9': 2,
    }
    
    for series, expected_count in expected.items():
        actual_count = len(by_prefix.get(series, []))
        if actual_count == expected_count:
            print(f"  ✓ {series}: {actual_count}/{expected_count} - COMPLETE")
        elif actual_count > 0:
            print(f"  ⚠️  {series}: {actual_count}/{expected_count} - PARTIAL")
        else:
            print(f"  ✗ {series}: {actual_count}/{expected_count} - MISSING")
    
    missing_count = sum(expected.values()) - sum(len(by_prefix.get(s, [])) for s in expected.keys())
    
    if missing_count == 0:
        print(f"\n✓✓✓ SUCCESS! All expected objectives extracted!")
    else:
        print(f"\n⚠️  Still missing {missing_count} expected objectives")
    
    print("\n" + "=" * 80)
