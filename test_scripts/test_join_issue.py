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

print(f"Section boundaries: {section_start}-{section_end}")
print(f"Expected lines: {section_end - section_start + 1}")
print(f"Actual section_lines count: {len(section_lines)}")

print(f"\nFirst line of section_lines[0]: '{section_lines[0].strip()}'")
print(f"Line 678 of section_lines[678]: '{section_lines[678].strip()}'")
print(f"Last line section_lines[-1]: '{section_lines[-1].strip()}'")

# Now join and check
full_text = '\n'.join(section_lines)
print(f"\nAfter joining with newlines:")
print(f"full_text length: {len(full_text)} chars")

# Check if joining preserves lines
rebuilt_lines = full_text.split('\n')
print(f"Splitting full_text back gives: {len(rebuilt_lines)} lines")

if len(rebuilt_lines) != len(section_lines):
    print(f"\n⚠️  LINE COUNT MISMATCH!")
    print(f"Original: {len(section_lines)}, After split: {len(rebuilt_lines)}")
    
    # Check if any lines have embedded newlines
    for i, line in enumerate(section_lines[:100]):
        if '\n' in line[:-1]:  # Exclude trailing newline
            print(f"Line {i} has embedded newline!")
