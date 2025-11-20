import sys
sys.path.insert(0, 'backend')

from app.pdf_handler import extract_text_from_pdf
import os

# Test raw extraction
pdf_path = 'soc2_reports/Adobe.pdf'
output_path_test = 'data/tmp/test_extract.txt'

print("Extracting PDF with standard method...")
extract_text_from_pdf(pdf_path, output_path_test)

# Check result
file_size = os.path.getsize(output_path_test)
print(f"Extracted file size: {file_size} bytes")

with open(output_path_test, 'r', encoding='utf-8') as f:
    content = f.read()
    print(f"Content length: {len(content)} characters")
    
    # Find control IDs
    import re
    control_ids = re.findall(r'(CHM|IAM|ELC|EM)-\d{2}-\d{2}', content)
    print(f"Found {len(control_ids)} control IDs")
    
    # Find first control
    first_chm = content.find('CHM-03-01')
    if first_chm > 0:
        print(f"First CHM-03-01 at position: {first_chm}")
        print(f"Context: {content[first_chm-100:first_chm+100]}")
