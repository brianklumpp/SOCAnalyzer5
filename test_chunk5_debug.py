import sys
sys.path.insert(0, 'backend')
from app import config
import json

# Load section boundaries
with open(config.SECTION_JSON_PATH, 'r', encoding='utf-8') as f:
    sections = json.load(f)

control_section = next((s for s in sections if s["topic"] == "Control_Descriptions"), None)
section_start = control_section["start_line"]
section_end = control_section["end_line"]

# Load document
with open(config.PDF_TXT_PATH, 'r', encoding='utf-8') as f:
    text_lines = f.readlines()

# Extract section
section_lines = text_lines[section_start-1:section_end]
full_text = '\n'.join(section_lines)

print(f"Section: lines {section_start}-{section_end}")
print(f"Section has {len(section_lines)} lines")
print(f"Full text length: {len(full_text)} chars")

# Manually create chunk 5 to debug
tokens_per_chunk = 1000
overlap_tokens = 200
chars_per_chunk = tokens_per_chunk * 4
overlap_chars = overlap_tokens * 4

# Chunk 5 should be around position (4 * 4000) = 16000 with some adjustments
# Let's calculate what position chunk 5 starts at
position = 0
for chunk_num in range(1, 6):
    if chunk_num > 1:
        effective_advance = chars_per_chunk - overlap_chars
        position += effective_advance
    
    chunk_start = max(0, position - overlap_chars)
    chunk_end = min(len(full_text), position + chars_per_chunk)
    
    # Calculate line numbers
    chars_before = len(full_text[:chunk_start])
    chars_after = len(full_text[:chunk_end])
    chunk_start_line = section_start + full_text[:chunk_start].count('\n')
    chunk_end_line = section_start + full_text[:chunk_end].count('\n')
    
    if chunk_num == 5:
        print(f"\nChunk 5 details:")
        print(f"  Position: {position}")
        print(f"  Chunk start char: {chunk_start}, end char: {chunk_end}")
        print(f"  Calculated lines: {chunk_start_line}-{chunk_end_line}")
        print(f"  Chunk text length: {chunk_end - chunk_start}")
        
        chunk_text = full_text[chunk_start:chunk_end]
        print(f"\n  First 300 chars of chunk:\n{chunk_text[:300]}")
        print(f"\n  Last 300 chars of chunk:\n{chunk_text[-300:]}")
        
        # Check for CHM-03-01
        if "CHM-03-01" in chunk_text:
            print(f"\n  ✓ CHM-03-01 FOUND in chunk text!")
        else:
            print(f"\n  ✗ CHM-03-01 NOT FOUND in chunk text")
            
            # Check what's at the position where line 2576 should be
            target_line_in_section = 2576 - section_start  # = 678
            # Count newlines to find character position of line 678 in full_text
            lines_so_far = 0
            char_pos = 0
            for char in full_text:
                if lines_so_far == target_line_in_section:
                    break
                if char == '\n':
                    lines_so_far += 1
                char_pos += 1
            
            print(f"\n  Line 2576 should be at char position {char_pos} in full_text")
            print(f"  Chunk covers char positions {chunk_start}-{chunk_end}")
            print(f"  Line 2576 in chunk range: {chunk_start <= char_pos <= chunk_end}")
            
            if chunk_start <= char_pos <= chunk_end:
                print(f"\n  Text at position {char_pos} (±100 chars):")
                print(f"  {full_text[max(0,char_pos-100):char_pos+100]}")
