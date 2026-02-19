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

# Get sections from result_json
if scan.result_json:
    result_json = json.loads(scan.result_json) if isinstance(scan.result_json, str) else scan.result_json
    sections = result_json.get('sections', [])
    print(f"Sections found: {len(sections)}\n")
    for sec in sections:
        print(f"  {sec.get('section_name')}: lines {sec.get('start_line')}-{sec.get('end_line')}")
    
    # Find Control_Descriptions
    ctrl_desc = next((s for s in sections if 'Control' in s.get('section_name', '') and 'Description' in s.get('section_name', '')), None)
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
    print("No result_json found")