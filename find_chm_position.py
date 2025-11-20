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

print(f"Searching for CHM-03-01 in full_text...")
pos = full_text.find("CHM-03-01")

if pos >= 0:
    print(f"Found at char position: {pos}")
    print(f"Context: {full_text[max(0,pos-100):pos+150]}")
    
    # Count what line this is
    lines_before = full_text[:pos].count('\n')
    absolute_line = section_start + lines_before
    print(f"\nLines before: {lines_before}")
    print(f"Absolute line: {absolute_line}")
    print(f"Expected: 2576")
    print(f"Difference: {absolute_line - 2576}")
else:
    print("NOT FOUND in full_text!")
    print("\nSearching in original text_lines...")
    for i, line in enumerate(text_lines):
        if "CHM-03-01" in line:
            print(f"Found at line {i+1}: '{line.strip()}'")
            break
