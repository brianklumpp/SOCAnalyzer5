"""
Debug script to examine PDF page 7 extraction and see what's happening with dates
"""
import fitz  # PyMuPDF
import sys

pdf_path = "soc1_reports/SAP ARIBA 2024.09.30 SOC 1 Type 2 Report EV Final SECURED.pdf"

doc = fitz.open(pdf_path)

# Page 7 (0-indexed, so page 6)
page_num = 6
page = doc[page_num]

print(f"=== PAGE {page_num + 1} - Basic get_text() ===")
basic_text = page.get_text()
print(basic_text[:2000])

print("\n\n=== PAGE {page_num + 1} - Blocks Method ===")
blocks = page.get_text("blocks")
print(f"Total blocks: {len(blocks)}")

# Sort blocks by position
sorted_blocks = sorted(blocks, key=lambda b: (b[1], b[0]))

for i, block in enumerate(sorted_blocks[:30]):  # First 30 blocks
    x0, y0, x1, y1, text, block_no, block_type = block
    print(f"\nBlock {i} (pos: y={y0:.1f}, x={x0:.1f}):")
    print(f"  {text[:200]}")

print("\n\n=== PAGE {page_num + 1} - Dict Method ===")
dict_data = page.get_text("dict")
print(f"Blocks in dict: {len(dict_data.get('blocks', []))}")

# Look for date patterns in blocks
print("\n\n=== Searching for Date Patterns ===")
import re
date_pattern = re.compile(r'(October|September)\s+\d+,?\s+\d{4}')

for i, block in enumerate(sorted_blocks):
    text = block[4]
    if date_pattern.search(text) or '2023' in text or '2024' in text:
        print(f"\nBlock {i} contains date/year:")
        print(f"  Position: y={block[1]:.1f}, x={block[0]:.1f}")
        print(f"  Text: {text[:300]}")

doc.close()
