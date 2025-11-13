import json
import os
from pathlib import Path
proj = Path(__file__).resolve().parents[1]
so_path = proj / 'data' / 'json' / 'subservice_orgs_result.json'
import sys
sys.path.insert(0, str(proj))
try:
    with so_path.open('r', encoding='utf-8') as f:
        d = json.load(f)
    before = len(d.get('subservice_orgs', []))
except Exception as e:
    print('BEFORE_COUNT', 'ERROR', str(e))
    before = None
print('BEFORE_COUNT', before)

# Find first PDF in soc2_reports
pdf_dir = proj / 'soc2_reports'
pdf_files = [p for p in pdf_dir.iterdir() if p.suffix.lower() == '.pdf']
if not pdf_files:
    print('No PDFs found in', pdf_dir)
    raise SystemExit(1)
pdf = str(pdf_files[0])
print('RUNNING analyze_pdf_file on', pdf)

from backend.app.analyze import analyze_pdf_file
res = analyze_pdf_file(pdf)
after = len(res.get('subservice_orgs', [])) if isinstance(res.get('subservice_orgs'), list) else None
print('AFTER_COUNT', after)

# Also write the combined_result.json count for quick verification
combined = proj / 'data' / 'json' / 'combined_result.json'
if combined.exists():
    try:
        cj = json.load(combined.open('r', encoding='utf-8'))
        print('COMBINED_SUBSERVICE_ORGS_COUNT', len(cj.get('subservice_orgs', [])) if isinstance(cj.get('subservice_orgs'), list) else None)
    except Exception as e:
        print('COMBINED_READ_ERROR', str(e))
