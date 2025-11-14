"""Load the raw extractor snapshot and run enhancement without dropping entries.

Outputs to: data/json/subservice_orgs_enhanced_preserve.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RAW = ROOT / 'data' / 'json' / 'subservice_orgs_raw_snapshot.json'
OUT = ROOT / 'data' / 'json' / 'subservice_orgs_enhanced_preserve.json'

# Import the enhancement function
from backend.app.extractors.subservice_orgs_dedup import enhance_subservice_orgs

if __name__ == '__main__':
    if not RAW.exists():
        print('ERROR: raw snapshot not found at', RAW)
        sys.exit(1)
    data = json.load(open(RAW, encoding='utf-8'))
    orgs = data.get('subservice_orgs', [])
    # Ensure each entry has expected fields
    for o in orgs:
        if 'third_party_confidence' not in o:
            o['third_party_confidence'] = o.get('third_party_confidence', 0.5)
        if 'confidence_justification' not in o:
            o['confidence_justification'] = []
    print('Running enhancement on', len(orgs), 'raw entries...')
    enhanced = enhance_subservice_orgs(orgs)
    # Write output
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'subservice_orgs': enhanced}, f, indent=2, ensure_ascii=False)
    print('Wrote enhanced (preserve) to', OUT)
    print('ENHANCED_COUNT:'+str(len(enhanced)))
