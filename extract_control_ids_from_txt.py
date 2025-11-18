#!/usr/bin/env python3
"""
Extract and count unique control IDs from output.txt file.
Provides a double-check mechanism to verify control extraction completeness.
"""

import re
from collections import Counter
from pathlib import Path

def extract_control_ids(file_path):
    """Extract all unique control IDs from the output.txt file."""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern to match control IDs like: ELC-02-04, HC.3.0, CC.1.1, IAM-01, etc.
    pattern = r'\b([A-Z]{2,5}[-\.]?\d{1,3}[-\.]?\d{0,3})\b'
    matches = re.findall(pattern, content)
    
    # Get unique control IDs and sort them
    unique_ids = sorted(set(matches))
    id_counter = Counter(matches)
    
    return unique_ids, id_counter, matches

def main():
    output_file = Path('data/output/output.txt')
    
    if not output_file.exists():
        print(f"❌ Error: File not found: {output_file}")
        return
    
    print("=" * 80)
    print("CONTROL ID EXTRACTION FROM OUTPUT.TXT")
    print("=" * 80)
    print(f"Analyzing: {output_file}\n")
    
    # Extract control IDs
    unique_ids, id_counter, all_matches = extract_control_ids(output_file)
    
    # Display statistics
    print(f"📊 STATISTICS:")
    print(f"   Total control ID occurrences: {len(all_matches)}")
    print(f"   Unique control IDs found: {len(unique_ids)}")
    print()
    
    # Display top 15 most frequent
    print(f"🔢 TOP 15 MOST FREQUENT CONTROL IDs:")
    for control_id, count in id_counter.most_common(15):
        print(f"   {control_id:20} : {count:3} occurrences")
    print()
    
    # Display all unique control IDs
    print(f"📋 COMPLETE LIST OF UNIQUE CONTROL IDs ({len(unique_ids)} total):")
    print("-" * 80)
    
    # Display in 4 columns for better readability
    for i in range(0, len(unique_ids), 4):
        row = unique_ids[i:i+4]
        print("   " + "    ".join(f"{cid:15}" for cid in row))
    
    print()
    print("=" * 80)
    print(f"✅ EXTRACTION COMPLETE: {len(unique_ids)} unique control IDs identified")
    print("=" * 80)
    
    # Save to file for reference
    output_list_file = Path('data/output/control_ids_extracted.txt')
    with open(output_list_file, 'w', encoding='utf-8') as f:
        f.write("UNIQUE CONTROL IDs EXTRACTED FROM OUTPUT.TXT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total unique control IDs: {len(unique_ids)}\n")
        f.write(f"Total occurrences: {len(all_matches)}\n\n")
        f.write("COMPLETE LIST:\n")
        f.write("-" * 80 + "\n")
        for control_id in unique_ids:
            occurrences = id_counter[control_id]
            f.write(f"{control_id:20} (appears {occurrences} times)\n")
    
    print(f"\n💾 List saved to: {output_list_file}")

if __name__ == "__main__":
    main()
