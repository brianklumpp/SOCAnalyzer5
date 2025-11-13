"""Check section boundaries for control extraction."""

import json

# Load sections
with open('data/json/section_results.json', 'r') as f:
    sections = json.load(f)

# Find control section
control_section = next((s for s in sections if s["topic"] == "Control_Descriptions"), None)

if control_section:
    print("=" * 80)
    print("CONTROL_DESCRIPTIONS SECTION")
    print("=" * 80)
    print(f"Start line: {control_section['start_line']}")
    print(f"End line: {control_section['end_line']}")
    print(f"Start page (DOC): {control_section['DOC_page_ref']}")
    print(f"End page (DOC): {control_section.get('end_DOC_page_ref', 'N/A')}")
    
    # Load the text file
    with open('data/output/output.txt', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"\nTotal lines in document: {len(lines)}")
    print(f"Lines extracted: {control_section['end_line'] - control_section['start_line']}")
    
    # Check what's at the boundaries
    start_idx = control_section['start_line'] - 1
    end_idx = control_section['end_line'] - 1
    
    print(f"\n--- Lines around START ({control_section['start_line']}) ---")
    for i in range(max(0, start_idx-2), min(len(lines), start_idx+3)):
        print(f"Line {i+1}: {lines[i][:100]}")
    
    print(f"\n--- Lines around END ({control_section['end_line']}) ---")
    for i in range(max(0, end_idx-2), min(len(lines), end_idx+3)):
        print(f"Line {i+1}: {lines[i][:100]}")
    
    # Check if there are more controls after
    print(f"\n--- What comes AFTER the section boundary ---")
    for i in range(end_idx, min(len(lines), end_idx+10)):
        line_text = lines[i].strip()
        if line_text and len(line_text) > 20:
            print(f"Line {i+1}: {line_text[:100]}")

else:
    print("ERROR: Control_Descriptions section not found!")
