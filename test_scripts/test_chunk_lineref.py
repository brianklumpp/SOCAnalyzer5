#!/usr/bin/env python3
"""
Test just the chunk_line_refs population logic
"""
import sys
from pathlib import Path
import json

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

# Use the most recent scan
SCAN_ID = "6d8534eb-9b05-4b49-8087-b3b2085a5fb8"
JOB_ID = 1
BASE_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs" / str(JOB_ID) / SCAN_ID

# Read section results
section_json_path = BASE_PATH / "json" / "section_results.json"
with open(section_json_path, 'r', encoding='utf-8') as f:
    section_results = json.load(f)

# Find Description_of_System section
desc_section = next((s for s in section_results if s.get('topic') == 'Description_of_System'), None)

if not desc_section:
    print("ERROR: Description_of_System section not found!")
    sys.exit(1)

print(f"Found Description_of_System section:")
print(f"  start_line: {desc_section.get('start_line')}")
print(f"  end_line: {desc_section.get('end_line')}")
print(f"  DOC_page_ref: {desc_section.get('DOC_page_ref')}")
print(f"  end_DOC_page_ref: {desc_section.get('end_DOC_page_ref')}")

start_line = desc_section.get('start_line')
end_line = desc_section.get('end_line')

# Simulate the extraction logic from cuec_extractor.py lines 313-323
if start_line and end_line:
    print(f"\n✓ Using LINE-BASED extraction (start_line={start_line}, end_line={end_line})")
    text_with_refs = "STRING"  # It would return a string
elif desc_section.get('DOC_page_ref') is not None:
    print(f"\n✓ Using PAGE-BASED extraction")
    text_with_refs = "LIST"  # It would return a list
else:
    print(f"\nERROR: No extraction method available!")
    text_with_refs = None

# Simulate chunking logic
if text_with_refs == "STRING":
    print(f"\n  → text_with_refs is string, chunking...")
    # Simulate: chunks = chunk_text_with_overlap(text_with_refs, 1000, 200)
    num_chunks = 100  # Simulated
    print(f"  → Created {num_chunks} chunks")
    
    # THIS IS THE KEY LINE: lines 343-344 of cuec_extractor.py
    chunk_line_refs = []
    if start_line:
        chunk_line_refs = [start_line] + [None] * (num_chunks - 1)
        print(f"  → chunk_line_refs populated: length={len(chunk_line_refs)}")
        print(f"     First 5 elements: {chunk_line_refs[:5]}")
    else:
        print(f"  ✗ start_line is falsy, chunk_line_refs NOT populated!")
    
elif text_with_refs == "LIST":
    print(f"\n  → text_with_refs is list (page-based)")
    # Would populate chunk_line_refs from page groups
    chunk_line_refs = [247, 260, 275]  # Example
    print(f"  → chunk_line_refs populated with {len(chunk_line_refs)} page starts")

print(f"\n[RESULT] Final chunk_line_refs length: {len(chunk_line_refs)}")
if chunk_line_refs:
    print(f"[RESULT] This should allow line ref tracking ✓")
else:
    print(f"[RESULT] chunk_line_refs is EMPTY - line refs will be NULL ✗")
