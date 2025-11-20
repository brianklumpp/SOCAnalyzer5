import sys
sys.path.insert(0, 'backend')

from app.extractors.control_extractor_v4 import create_aware_chunks
from app import config
import json

# Load section boundaries
with open(config.SECTION_JSON_PATH, 'r', encoding='utf-8') as f:
    sections = json.load(f)

control_section = next((s for s in sections if s["topic"] == "Control_Descriptions"), None)

if not control_section:
    print("ERROR: Control_Descriptions section not found!")
    exit(1)

section_start = control_section["start_line"]
section_end = control_section["end_line"]

print(f"Control_Descriptions section: lines {section_start} to {section_end}")

# Load document
with open(config.PDF_TXT_PATH, 'r', encoding='utf-8') as f:
    text_lines = f.readlines()

print(f"Total lines in document: {len(text_lines)}")

# Create chunks
chunks = create_aware_chunks(
    text_lines,
    section_start,
    section_end,
    tokens_per_chunk=1000,
    overlap_tokens=200
)

print(f"\nCreated {len(chunks)} chunks")

# Check if CHM-03-01 is in any chunk
target_line = 2576
for i, chunk in enumerate(chunks):
    start = chunk["start_line"]
    end = chunk["end_line"]
    print(f"\nChunk {i+1}: lines {start}-{end} ({end-start+1} lines)")
    
    if start <= target_line <= end:
        print(f"  *** This chunk contains CHM-03-01 (line {target_line})! ***")
        
        # Show snippet of chunk text around CHM-03-01
        chunk_text = chunk["text"]
        chm_pos = chunk_text.find("CHM-03-01")
        if chm_pos >= 0:
            print(f"  CHM-03-01 found at position {chm_pos} in chunk text")
            print(f"  Context: {chunk_text[max(0, chm_pos-200):chm_pos+300]}")
        else:
            print(f"  WARNING: Line {target_line} in range but CHM-03-01 not found in chunk text!")
            # Debug: check what's actually in the chunk
            print(f"  Chunk text length: {len(chunk_text)} chars")
            print(f"  First 500 chars of chunk:\n{chunk_text[:500]}")
            print(f"\n  Last 500 chars of chunk:\n{chunk_text[-500:]}")
            
            # Check if CHM-03-01 is in the source lines
            actual_line = text_lines[target_line - 1]
            print(f"\n  Actual line {target_line} from file: '{actual_line.strip()}'")
