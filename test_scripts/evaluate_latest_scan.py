#!/usr/bin/env python3
"""Evaluate latest scan and measure objective extraction improvement."""

import sys
import os
sys.path.insert(0, '/app/backend')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import re
from collections import defaultdict

# Database connection
DATABASE_URL = "postgresql://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

try:
    # Get the two most recent scans
    result = session.execute(text("""
        SELECT id, scan_date, progress_status, pdf_filename
        FROM scan
        ORDER BY scan_date DESC
        LIMIT 2
    """))
    scans = result.fetchall()
    
    if len(scans) < 2:
        print("Not enough scans to compare")
        sys.exit(1)
    
    latest_scan = scans[0]
    previous_scan = scans[1]
    
    print("=" * 80)
    print("OBJECTIVE EXTRACTION IMPROVEMENT ANALYSIS")
    print("=" * 80)
    print(f"\nLatest Scan:   ID={latest_scan[0]}, Time={latest_scan[1]}, Status={latest_scan[2]}")
    print(f"Previous Scan: ID={previous_scan[0]}, Time={previous_scan[1]}, Status={previous_scan[2]}")
    print(f"PDF: {latest_scan[3]}")
    
    # Get objectives for both scans
    for scan_id, scan_label in [(latest_scan[0], "LATEST"), (previous_scan[0], "PREVIOUS")]:
        result = session.execute(text("""
            SELECT objective_id, extraction_method, confidence_score, line_ref
            FROM control_objectives
            WHERE scan_id = :scan_id
            ORDER BY objective_id
        """), {"scan_id": scan_id})
        
        objectives = result.fetchall()
        
        print(f"\n{'=' * 80}")
        print(f"{scan_label} SCAN (ID={scan_id}): {len(objectives)} total objectives")
        print("=" * 80)
        
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
        
        # Check for critical missing series (CC4-CC9)
        critical_series = ['CC4', 'CC5', 'CC7', 'CC8', 'CC9']
        missing_critical = [s for s in critical_series if s not in by_prefix]
        
        if missing_critical:
            print(f"\n⚠️  MISSING CRITICAL SERIES: {', '.join(missing_critical)}")
        else:
            print(f"\n✓ All critical CC series present!")
        
        # Show extraction methods
        method_counts = defaultdict(int)
        for obj in objectives:
            method_counts[obj[1]] += 1
        
        print("\nExtraction Methods:")
        for method, count in sorted(method_counts.items()):
            print(f"  {method}: {count}")
    
    # Calculate improvement
    latest_count = len(session.execute(text(
        "SELECT id FROM control_objectives WHERE scan_id = :scan_id"
    ), {"scan_id": latest_scan[0]}).fetchall())
    
    previous_count = len(session.execute(text(
        "SELECT id FROM control_objectives WHERE scan_id = :scan_id"
    ), {"scan_id": previous_scan[0]}).fetchall())
    
    improvement = latest_count - previous_count
    improvement_pct = (improvement / previous_count * 100) if previous_count > 0 else 0
    
    print(f"\n{'=' * 80}")
    print("IMPROVEMENT SUMMARY")
    print("=" * 80)
    print(f"Previous: {previous_count} objectives")
    print(f"Latest:   {latest_count} objectives")
    print(f"Change:   {'+' if improvement >= 0 else ''}{improvement} ({'+' if improvement_pct >= 0 else ''}{improvement_pct:.1f}%)")
    
    if improvement > 0:
        print(f"\n✓ IMPROVEMENT: {improvement} additional objectives extracted!")
    elif improvement == 0:
        print(f"\n⚠️  NO CHANGE: Same number of objectives")
    else:
        print(f"\n⚠️  REGRESSION: {abs(improvement)} fewer objectives")
    
    print("\n" + "=" * 80)
    
finally:
    session.close()
