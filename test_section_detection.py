"""Test script to re-run section detection on CitiDirect report"""
import sys
sys.path.insert(0, 'backend')

from backend.app.pdf_handler import find_section_candidates
import pathlib

# Read the output.txt
output_file = pathlib.Path('data/output/output.txt')
text = output_file.read_text(encoding='utf-8')

print("Running section detection on CitiDirect report...")
print(f"Text length: {len(text)} characters")
print("-" * 80)

try:
    sections = find_section_candidates(text)
    print(f"\n✓ Found {len(sections)} sections")
    print("\nSection Results:")
    for section in sections:
        print(f"\n  {section['topic']}: {section['clean_heading']}")
        print(f"    TOC_page_ref: {section.get('TOC_page_ref')}")
        print(f"    DOC_page_ref: {section.get('DOC_page_ref')}")
        print(f"    end_TOC_page_ref: {section.get('end_TOC_page_ref')}")
        print(f"    end_DOC_page_ref: {section.get('end_DOC_page_ref')}")
        print(f"    start_line: {section.get('start_line')}, end_line: {section.get('end_line')}")
        
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "-" * 80)
print("Check data/logs/section_identification.log for detailed GPT response")
