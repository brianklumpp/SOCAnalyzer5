"""
Debug watermark detection to see if dates are being filtered
"""
import sys
sys.path.insert(0, 'backend')

import fitz
import collections
import re
from app.pdf_handler import REGEX_PATTERNS

pdf_path = "soc1_reports/SAP ARIBA 2024.09.30 SOC 1 Type 2 Report EV Final SECURED.pdf"
doc = fitz.open(pdf_path)

date_regex = REGEX_PATTERNS['date']
email_regex = REGEX_PATTERNS['email']
time_regex = REGEX_PATTERNS['time']

page_patterns = []
for page_num in range(len(doc)):
    text = doc[page_num].get_text() or ""
    patterns = set()
    for regex in [date_regex, email_regex, time_regex]:
        for match in re.findall(regex, text):
            patterns.add(match.strip())
    page_patterns.append(patterns)

# Count pattern occurrences
pattern_counter = collections.Counter()
for patterns in page_patterns:
    pattern_counter.update(patterns)

num_pages = len(page_patterns)

# Identify patterns appearing on >80% of pages
watermark_patterns = set([
    pat for pat, count in pattern_counter.items() if count / num_pages > 0.8
])

print(f"Total pages: {num_pages}")
print(f"\n=== Patterns appearing on >80% of pages (watermarks) ===")
for pat in sorted(watermark_patterns):
    count = pattern_counter[pat]
    percentage = (count / num_pages) * 100
    print(f"  '{pat}' - appears on {count}/{num_pages} pages ({percentage:.1f}%)")

# Check if coverage period dates are being caught
coverage_dates = ['April 1, 2024', 'September 30, 2024']
print(f"\n=== Checking coverage period dates ===")
for date in coverage_dates:
    if date in watermark_patterns:
        count = pattern_counter[date]
        print(f"  ⚠️  '{date}' is marked as watermark (appears on {count} pages)")
    else:
        count = pattern_counter.get(date, 0)
        print(f"  ✓ '{date}' is NOT a watermark (appears on {count} pages)")

# Check page 7 specifically
print(f"\n=== Page 7 content sample ===")
page7_text = doc[6].get_text()
if 'April 1, 2024' in page7_text:
    print("✓ 'April 1, 2024' found in page 7")
    # Find context
    idx = page7_text.find('April 1, 2024')
    print(f"Context: ...{page7_text[idx-50:idx+100]}...")
else:
    print("✗ 'April 1, 2024' NOT found in page 7")
    
if 'throughout the period' in page7_text:
    print("✓ 'throughout the period' found in page 7")
    idx = page7_text.find('throughout the period')
    print(f"Context: ...{page7_text[idx-20:idx+150]}...")
else:
    print("✗ 'throughout the period' NOT found in page 7")

doc.close()
