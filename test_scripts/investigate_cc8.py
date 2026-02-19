#!/usr/bin/env python3
"""Investigate CC8 extraction details - why CC8.1 found but not CC8.2/CC8.3."""

import sys
import os
sys.path.insert(0, '/app/backend')

from sqlalchemy import create_engine, text
import re

DATABASE_URL = "postgresql://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Get latest scan
    result = conn.execute(text("""
        SELECT id, pdf_filename, extracted_text
        FROM scan
        ORDER BY id DESC
        LIMIT 1
    """))
    
    scan = result.fetchone()
    scan_id = scan[0]
    extracted_text = scan[2]
    
    print("=" * 80)
    print("CC8 EXTRACTION INVESTIGATION")
    print("=" * 80)
    print(f"Scan ID: {scan_id}")
    print(f"PDF: {scan[1]}")
    
    # Check what CC8 objectives were extracted
    result = conn.execute(text("""
        SELECT objective_id, extraction_method, final_confidence, line_ref
        FROM control_objectives
        WHERE scan_id = :scan_id AND objective_id LIKE 'CC8%'
        ORDER BY objective_id
    """), {"scan_id": scan_id})
    
    extracted_cc8 = result.fetchall()
    
    print(f"\n{'=' * 80}")
    print("EXTRACTED CC8 OBJECTIVES:")
    print("=" * 80)
    for obj in extracted_cc8:
        print(f"  {obj[0]}: method={obj[1]}, confidence={obj[2]:.2f}, line={obj[3]}")
    
    # Search for ALL CC8.* occurrences in PDF text
    print(f"\n{'=' * 80}")
    print("CC8.* OCCURRENCES IN PDF TEXT:")
    print("=" * 80)
    
    lines = extracted_text.split('\n')
    cc8_pattern = re.compile(r'\bCC8\.\d+\b')
    
    occurrences = []
    for line_num, line in enumerate(lines, start=1):
        matches = cc8_pattern.findall(line)
        if matches:
            occurrences.append((line_num, line.strip(), matches))
    
    print(f"Found {len(occurrences)} lines containing CC8.* patterns:\n")
    
    for line_num, line_text, matches in occurrences:
        print(f"Line {line_num}: {', '.join(matches)}")
        print(f"  Text: {line_text[:150]}")
        
        # Check if this line was extracted
        was_extracted = any(obj[3] == line_num for obj in extracted_cc8)
        print(f"  Status: {'✓ EXTRACTED' if was_extracted else '✗ NOT EXTRACTED'}")
        print()
    
    # Check section boundaries
    result = conn.execute(text("""
        SELECT result_json
        FROM scan
        WHERE id = :scan_id
    """), {"scan_id": scan_id})
    
    result_json = result.fetchone()[0]
    
    if result_json and 'sections' in result_json:
        sections = result_json['sections']
        control_desc_section = next((s for s in sections if s.get('topic') == 'Control_Descriptions'), None)
        
        if control_desc_section:
            section_start = control_desc_section.get('line_start') or control_desc_section.get('start_line')
            section_end = control_desc_section.get('line_end') or control_desc_section.get('end_line')
            
            print("=" * 80)
            print("SECTION BOUNDARY CHECK:")
            print("=" * 80)
            print(f"Control_Descriptions section: lines {section_start}-{section_end}\n")
            
            for line_num, line_text, matches in occurrences:
                in_section = section_start <= line_num <= section_end
                status = "IN SECTION" if in_section else "OUTSIDE SECTION"
                print(f"Line {line_num} ({', '.join(matches)}): {status}")
    
    # Check pattern_info for CC8
    result = conn.execute(text("""
        SELECT pattern_info
        FROM scan
        WHERE id = :scan_id
    """), {"scan_id": scan_id})
    
    pattern_info = result.fetchone()[0]
    
    if pattern_info and 'learned_patterns' in pattern_info:
        print(f"\n{'=' * 80}")
        print("PATTERN LEARNING INFO:")
        print("=" * 80)
        
        learned = pattern_info['learned_patterns']
        
        # Check if CC8 pattern was learned
        cc8_pattern_info = None
        for pattern in learned:
            if pattern.get('prefix') == 'CC8':
                cc8_pattern_info = pattern
                break
        
        if cc8_pattern_info:
            print("CC8 Pattern Learned:")
            print(f"  Prefix: {cc8_pattern_info.get('prefix')}")
            print(f"  Range: {cc8_pattern_info.get('min_id')} - {cc8_pattern_info.get('max_id')}")
            print(f"  Count: {cc8_pattern_info.get('count')}")
            print(f"  Confidence: {cc8_pattern_info.get('confidence')}")
            print(f"  Sample IDs: {cc8_pattern_info.get('sample_ids', [])}")
        else:
            print("⚠️  No CC8 pattern learned during pattern_rescan phase")
    
    # Check gap extraction parameters
    print(f"\n{'=' * 80}")
    print("GAP EXTRACTION ANALYSIS:")
    print("=" * 80)
    
    # See if gap extraction ran for CC8
    if pattern_info and 'gap_extraction' in pattern_info:
        gap_info = pattern_info['gap_extraction']
        print(f"Gap extraction ran: Yes")
        print(f"Ranges checked: {gap_info.get('ranges_checked', 'N/A')}")
        
        # Check if CC8 range was probed
        ranges = gap_info.get('ranges_checked', [])
        cc8_ranges = [r for r in ranges if 'CC8' in str(r)]
        if cc8_ranges:
            print(f"CC8 ranges probed: {cc8_ranges}")
        else:
            print("⚠️  No CC8 ranges in gap extraction")
    else:
        print("Gap extraction info not available in pattern_info")
    
    print("\n" + "=" * 80)
    print("HYPOTHESIS:")
    print("=" * 80)
    print("If CC8.1 was found but CC8.2/CC8.3 weren't:")
    print("1. Pattern learning found CC8.1 first")
    print("2. Gap extraction should probe CC8.1 ± 10 range")
    print("3. Check if CC8.2/CC8.3 are within section boundaries")
    print("4. Check if gap extraction ran AFTER pattern learning")
    print("=" * 80)
