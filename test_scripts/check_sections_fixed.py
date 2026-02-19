#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from sqlalchemy import create_engine
from backend.app.models import Scan
from sqlalchemy.orm import sessionmaker
import re
import json

DB_URL = "postgresql://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
sess = Session()

scan = sess.query(Scan).order_by(Scan.id.desc()).first()
if not scan:
    print("No scan found")
    sys.exit(1)

print(f"Scan ID: {scan.id}")
print(f"PDF: {scan.pdf_filename}\n")

# Get sections from result_json
if scan.result_json:
    result_json = json.loads(scan.result_json) if isinstance(scan.result_json, str) else scan.result_json
    sections = result_json.get('sections', [])
    print(f"Sections found: {len(sections)}\n")
    
    # Show ALL field names from first section to understand structure
    if sections:
        print("First section structure (keys):")
        print(f"  {list(sections[0].keys())}\n")
    
    # Print all sections with their topic field (not section_name!)
    for sec in sections:
        topic = sec.get('topic', 'NO_TOPIC_FIELD')
        start = sec.get('start_line', '?')
        end = sec.get('end_line', '?')
        print(f"  {topic}: lines {start}-{end}")
    
    # Find Control_Descriptions using 'topic' field
    ctrl_desc = next((s for s in sections if s.get('topic') == 'Control_Descriptions'), None)
    if ctrl_desc:
        print(f"\nControl_Descriptions section: lines {ctrl_desc['start_line']}-{ctrl_desc['end_line']}")
        
        # Check if CC4, CC7, C1.2 are in that range
        text = scan.extracted_text
        lines = text.split('\n')
        
        for pattern, label in [(r'\bCC4\.', 'CC4'), (r'\bCC7\.', 'CC7'), (r'\bC1\.[2-9]', 'C1.x')]:
            matches = []
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    in_section = ctrl_desc['start_line'] <= i <= ctrl_desc['end_line']
                    matches.append((i, in_section, line[:100]))
            if matches:
                print(f"\n{label} occurrences:")
                for line_num, in_sec, content in matches:
                    status = "✓ IN SECTION" if in_sec else "✗ OUTSIDE"
                    print(f"  Line {line_num} {status}: {content.strip()}")
    else:
        print("\n✗ NO Control_Descriptions section found!")
        print("This is the ROOT CAUSE - objectives cannot be extracted without this section")
else:
    print("No result_json found")
