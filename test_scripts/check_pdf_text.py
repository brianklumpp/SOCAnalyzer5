#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from sqlalchemy import create_engine
from backend.app.models import Scan
from sqlalchemy.orm import sessionmaker
import re

DB_URL = "postgresql://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
sess = Session()

scan = sess.query(Scan).order_by(Scan.id.desc()).first()
if not scan or not scan.extracted_text:
    print("No scan or extracted text found")
    sys.exit(1)

text = scan.extracted_text
print(f"Scan ID: {scan.id}, PDF: {scan.pdf_filename}\n")

# Check for missing series
cc4 = len(re.findall(r'\bCC4\.', text, re.IGNORECASE))
cc5 = len(re.findall(r'\bCC5\.', text, re.IGNORECASE))
cc7 = len(re.findall(r'\bCC7\.', text, re.IGNORECASE))
cc8 = len(re.findall(r'\bCC8\.', text, re.IGNORECASE))
cc9 = len(re.findall(r'\bCC9\.', text, re.IGNORECASE))
c1_series = len(re.findall(r'\bC1\.[2-9]', text, re.IGNORECASE))

print("Occurrence count in PDF text:")
print(f"  CC4.*: {cc4}")
print(f"  CC5.*: {cc5}")
print(f"  CC7.*: {cc7}")
print(f"  CC8.*: {cc8}")
print(f"  CC9.*: {cc9}")
print(f"  C1.2-C1.9: {c1_series}")

if cc4 > 0:
    print(f"\nCC4 samples:")
    matches = re.findall(r'.{0,100}\bCC4\.\d+.{0,100}', text, re.IGNORECASE)[:3]
    for m in matches:
        print(f"  {m.strip()}")

if c1_series > 0:
    print(f"\nC1.x samples:")
    matches = re.findall(r'.{0,100}\bC1\.[2-9].{0,100}', text, re.IGNORECASE)[:3]
    for m in matches:
        print(f"  {m.strip()}")
