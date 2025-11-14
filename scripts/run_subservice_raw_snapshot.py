"""Run the subservice org extractor and snapshot the raw output before GPT filtering.

This imports the extractor module and calls `extract_subservice_orgs()` directly (not the module __main__),
then copies the generated JSON to `data/json/subservice_orgs_raw_snapshot.json` for audit.
"""
import json
import shutil
import sys
from pathlib import Path

# Ensure repo root on sys.path so package imports resolve when run as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import as package so relative imports inside the module resolve
from backend.app.extractors import subservice_orgs

OUTPUT = ROOT / 'data' / 'json' / 'subservice_orgs_result.json'
SNAP = ROOT / 'data' / 'json' / 'subservice_orgs_raw_snapshot.json'

if __name__ == '__main__':
    print('Running raw extractor (this will call extract_subservice_orgs)')
    # Run extraction only
    subservice_orgs.extract_subservice_orgs()
    if OUTPUT.exists():
        print(f'Found output at: {OUTPUT}. Writing snapshot to: {SNAP}')
        shutil.copy2(OUTPUT, SNAP)
        d = json.load(open(SNAP, encoding='utf-8'))
        print('SNAPSHOT_COUNT:'+str(len(d.get('subservice_orgs', []))))
    else:
        print('ERROR: expected output file not found:', OUTPUT)
