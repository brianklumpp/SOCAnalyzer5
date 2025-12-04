"""
Test PDF extraction with the updated method to verify dates are preserved
"""
import sys
sys.path.insert(0, 'backend')

from app.pdf_handler import extract_text_from_pdf
import re

pdf_path = "soc1_reports/SAP ARIBA 2024.09.30 SOC 1 Type 2 Report EV Final SECURED.pdf"
output_path = "data/output/test_output.txt"

print("Extracting PDF with updated method...")
extract_text_from_pdf(pdf_path, output_path)

print("\nSearching for coverage period dates...")
with open(output_path, 'r', encoding='utf-8') as f:
    content = f.read()
    
# Search for date patterns
date_patterns = [
    r'April\s+1,?\s+2024\s+to\s+September\s+30,?\s+2024',
    r'October\s+1,?\s+2023',
    r'September\s+30,?\s+2024',
    r'throughout the period.*?\d{4}'
]

print("\n=== Date Pattern Matches ===")
for pattern in date_patterns:
    matches = re.findall(pattern, content, re.IGNORECASE)
    if matches:
        print(f"\nPattern '{pattern}':")
        for match in matches[:5]:  # Show first 5 matches
            print(f"  - {match}")
    else:
        print(f"\nPattern '{pattern}': No matches")

# Check specific section around page 7
print("\n=== Page 7 Content (Opinion Section) ===")
page7_match = re.search(r'=== PAGE 7 ===(.{0,1500})', content, re.DOTALL)
if page7_match:
    print(page7_match.group(1))
else:
    print("Page 7 not found")

print("\n=== Checking for broken dates ===")
broken_patterns = [
    r'April\s+1,?\s+2024\s+to\s*$',  # Date ending abruptly
    r'September\s+30,?\s*$',  # Incomplete date
    r'2024\s*$.*?and if',  # Year at end of line
]

for pattern in broken_patterns:
    matches = re.findall(pattern, content, re.MULTILINE)
    if matches:
        print(f"\n⚠️  Found broken pattern: {pattern}")
        for match in matches[:3]:
            print(f"  - {repr(match)}")
