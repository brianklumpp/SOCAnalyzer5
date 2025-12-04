import sys
sys.path.insert(0, 'backend')
from app import config

# Load document
with open(config.PDF_TXT_PATH, 'r', encoding='utf-8') as f:
    text_lines = f.readlines()

print(f"Total lines: {len(text_lines)}")

# Check specific lines
check_lines = [1897, 1898, 2575, 2576, 5611, 5612]
for line_num in check_lines:
    if line_num < len(text_lines):
        print(f"Line {line_num+1} (index {line_num}): '{text_lines[line_num].strip()}'")
    else:
        print(f"Line {line_num+1} (index {line_num}): OUT OF BOUNDS")

# Test slicing
section_start = 1898
section_end = 5612

section_lines = text_lines[section_start-1:section_end]
print(f"\nSection slice [1897:5612] gives {len(section_lines)} lines")
print(f"Expected: 5612 - 1898 + 1 = {5612 - 1898 + 1} lines")

print(f"\nFirst line of section (should be line 1898): '{section_lines[0].strip()}'")
print(f"Last line of section (should be line 5612): '{section_lines[-1].strip()}'")

# Check where CHM-03-01 is in the section
target_absolute_line = 2576
target_section_index = target_absolute_line - section_start  # 2576 - 1898 = 678
print(f"\nCHM-03-01 should be at section index {target_section_index}")
if target_section_index < len(section_lines):
    print(f"Line at that index: '{section_lines[target_section_index].strip()}'")
