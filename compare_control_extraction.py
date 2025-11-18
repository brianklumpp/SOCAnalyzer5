#!/usr/bin/env python3
"""
Enhanced control ID extraction and comparison tool.
Extracts control IDs from output.txt more precisely and compares with extractor results.
"""

import re
import json
from collections import Counter
from pathlib import Path

def extract_control_ids_precise(file_path):
    """Extract control IDs more precisely by looking in control sections."""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    control_ids = []
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Look for control ID patterns on their own line or at start of line
        # ELC-02-04 format (must be on own line to avoid false positives)
        if re.match(r'^[A-Z]{2,5}-\d{2}-\d{2}\s*$', line_stripped):
            control_ids.append(line_stripped)
            continue
        
        # CC.1.1, HC.3.0, AM.1.0 format (can be at start of line)
        match = re.match(r'^([A-Z]{2,3}\.\d{1,2}\.\d{1,2})\b', line_stripped)
        if match:
            cid = match.group(1)
            # Exclude AWS/tech terms
            if not re.match(r'^(AES|EC2|S3)\.', cid):
                control_ids.append(cid)
    
    unique_ids = sorted(set(control_ids))
    return unique_ids, Counter(control_ids), control_ids

def load_extracted_controls():
    """Load control IDs from control_result.json."""
    json_path = Path('data/json/control_result.json')
    
    if not json_path.exists():
        return None, None
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    controls = data.get('controls', [])
    all_ids = [c.get('control_id') for c in controls]
    valid_ids = [cid for cid in all_ids if cid]
    null_count = len([c for c in all_ids if not c])
    
    return valid_ids, null_count

def main():
    print("=" * 80)
    print("CONTROL EXTRACTION COMPARISON")
    print("=" * 80)
    print()
    
    # Extract from TXT
    print("📄 Analyzing output.txt...")
    txt_ids, _, _ = extract_control_ids_precise(Path('data/output/output.txt'))
    print(f"   Found {len(txt_ids)} unique control IDs")
    
    # Load from JSON
    print("\n📊 Loading control_result.json...")
    json_ids, null_count = load_extracted_controls()
    
    if json_ids:
        print(f"   Found {len(json_ids)} controls with IDs")
        print(f"   Found {null_count} controls without IDs (null/None)")
        
        # Compare
        txt_set = set(txt_ids)
        json_set = set(json_ids)
        
        in_both = txt_set & json_set
        missing = txt_set - json_set
        extra = json_set - txt_set
        
        print("\n" + "=" * 80)
        print("COMPARISON RESULTS")
        print("=" * 80)
        
        extraction_rate = (len(in_both) / len(txt_ids) * 100) if txt_ids else 0
        print(f"\n✅ Successfully extracted: {len(in_both)}/{len(txt_ids)} ({extraction_rate:.1f}%)")
        
        if missing:
            print(f"\n⚠️  MISSED by extractor ({len(missing)} controls):")
            print("-" * 80)
            for cid in sorted(missing):
                print(f"   {cid}")
        
        if extra:
            print(f"\n❓ Found by extractor but not in source txt ({len(extra)} controls):")
            print("-" * 80)
            for cid in sorted(extra)[:20]:
                print(f"   {cid}")
            if len(extra) > 20:
                print(f"   ... and {len(extra) - 20} more")
        
        print("\n" + "=" * 80)
        print(f"📋 ALL CONTROL IDs FROM OUTPUT.TXT ({len(txt_ids)} total):")
        print("-" * 80)
        
        # Display in 5 columns
        for i in range(0, len(txt_ids), 5):
            row = txt_ids[i:i+5]
            print("   " + "    ".join(f"{cid:15}" for cid in row))
        
        # Save detailed report
        output_file = Path('data/output/control_extraction_comparison.txt')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("CONTROL EXTRACTION COMPARISON REPORT\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Source TXT unique IDs: {len(txt_ids)}\n")
            f.write(f"Extracted JSON IDs: {len(json_ids)}\n")
            f.write(f"Controls without IDs: {null_count}\n\n")
            f.write(f"Successfully extracted: {len(in_both)} ({extraction_rate:.1f}%)\n")
            f.write(f"Missing from extraction: {len(missing)}\n")
            f.write(f"Extra in extraction: {len(extra)}\n\n")
            
            if missing:
                f.write("MISSING FROM EXTRACTION:\n")
                f.write("-" * 80 + "\n")
                for cid in sorted(missing):
                    f.write(f"{cid}\n")
                f.write("\n")
            
            if extra:
                f.write("EXTRA IN EXTRACTION (not found in source):\n")
                f.write("-" * 80 + "\n")
                for cid in sorted(extra):
                    f.write(f"{cid}\n")
                f.write("\n")
            
            f.write("ALL CONTROL IDs FROM OUTPUT.TXT:\n")
            f.write("-" * 80 + "\n")
            for cid in txt_ids:
                f.write(f"{cid}\n")
        
        print(f"\n💾 Detailed report saved to: {output_file}")
    else:
        print("   ⚠️  control_result.json not found - cannot compare")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
