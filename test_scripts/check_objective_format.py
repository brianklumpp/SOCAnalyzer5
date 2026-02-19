#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from sqlalchemy import create_engine
from backend.app.models import Scan
from sqlalchemy.orm import sessionmaker

DB_URL = "postgresql://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
sess = Session()

# Get latest scan
scan = sess.query(Scan).order_by(Scan.id.desc()).first()
if not scan:
    print("No scan found")
    sys.exit(1)

print(f"Scan ID: {scan.id}")
print(f"PDF: {scan.pdf_filename}\n")

# Get extracted text and split into lines
text = scan.extracted_text
lines = text.split('\n')

print(f"Total lines: {len(lines)}\n")

# Check format around CC4.1 (line 3054)
print("=" * 80)
print("CC4.1 CONTEXT (line 3054)")
print("=" * 80)
start = max(0, 3053 - 10)  # 0-indexed, so line 3054 is index 3053
end = min(len(lines), 3053 + 10)
for i in range(start, end):
    marker = ">>> " if i == 3053 else "    "
    print(f"{marker}Line {i+1}: {lines[i][:150]}")

print("\n" + "=" * 80)
print("CC4.2 CONTEXT (line 3124)")
print("=" * 80)
start = max(0, 3123 - 10)
end = min(len(lines), 3123 + 10)
for i in range(start, end):
    marker = ">>> " if i == 3123 else "    "
    print(f"{marker}Line {i+1}: {lines[i][:150]}")

print("\n" + "=" * 80)
print("CC7.1 CONTEXT (line 4237)")
print("=" * 80)
start = max(0, 4236 - 10)
end = min(len(lines), 4236 + 10)
for i in range(start, end):
    marker = ">>> " if i == 4236 else "    "
    print(f"{marker}Line {i+1}: {lines[i][:150]}")

# Now compare to a working one - CC1.1
print("\n" + "=" * 80)
print("CC1.1 CONTEXT (for comparison - this one WAS extracted)")
print("=" * 80)
# Find CC1.1
for i, line in enumerate(lines):
    if 'CC1.1' in line and i > 1837 and i < 5538:  # Within Control_Descriptions section
        start = max(0, i - 10)
        end = min(len(lines), i + 10)
        for j in range(start, end):
            marker = ">>> " if j == i else "    "
            print(f"{marker}Line {j+1}: {lines[j][:150]}")
        break
