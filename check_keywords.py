"""Quick check for objective section keywords in scan text."""
from backend.app.database import SessionLocal
from backend.app.models import Scan

db = SessionLocal()
scan = db.query(Scan).filter(Scan.id == 2).first()

if scan and scan.extracted_text:
    text = scan.extracted_text
    print(f"Total text length: {len(text)} chars")
    print(f"\nSearching for objective section keywords...")
    
    keywords = [
        "control objective",
        "control objectives",
        "description of service organization's system",
        "system objective",
    ]
    
    for keyword in keywords:
        count = text.lower().count(keyword)
        if count > 0:
            print(f"  ✓ Found '{keyword}': {count} occurrences")
            # Find first occurrence line
            lines = text.split('\n')
            for i, line in enumerate(lines[:500]):  # Check first 500 lines
                if keyword in line.lower():
                    print(f"    First at line {i}: {line[:100]}")
                    break
        else:
            print(f"  ✗ '{keyword}': NOT FOUND")
    
    # Check distance for first 15000 chars (test sample)
    sample = text[:15000]
    sample_lines = sample.split('\n')
    print(f"\nIn first 15000 chars ({len(sample_lines)} lines):")
    for keyword in keywords:
        found = False
        for i, line in enumerate(sample_lines):
            if keyword in line.lower():
                print(f"  ✓ '{keyword}' at line {i}")
                found = True
                break
        if not found:
            print(f"  ✗ '{keyword}' NOT in sample")

db.close()
