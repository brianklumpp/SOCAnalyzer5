import json
import sys
from pathlib import Path
proj = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(proj))
from backend.app.extractors.subservice_orgs import extract_subservice_orgs, filter_third_parties_with_gpt
from backend.app.extractors.subservice_orgs import OUTPUT_JSON_PATH

so_path = Path(OUTPUT_JSON_PATH)
try:
    before = None
    if so_path.exists():
        with so_path.open('r', encoding='utf-8') as f:
            d = json.load(f)
        before = len(d.get('subservice_orgs', []))
except Exception as e:
    print('BEFORE_COUNT', 'ERROR', str(e))
    before = None
print('BEFORE_COUNT', before)

# Run extraction and filtering
print('Running extract_subservice_orgs()...')
res1 = extract_subservice_orgs()
print('extract_subservice_orgs() returned:', 'OK' if res1 is not None else 'None')
print('Running filter_third_parties_with_gpt()...')
try:
    filter_third_parties_with_gpt()
    print('filter_third_parties_with_gpt() returned: OK')
except Exception as e:
    print('filter_third_parties_with_gpt() raised:', str(e))

# Read result
try:
    with so_path.open('r', encoding='utf-8') as f:
        d2 = json.load(f)
    after = len(d2.get('subservice_orgs', []))
except Exception as e:
    print('AFTER_COUNT', 'ERROR', str(e))
    after = None
print('AFTER_COUNT', after)

# Print small sample of resulting names and confidences
if after and after > 0:
    print('\nTOP SUBSERVICE ORGS:')
    for entry in d2.get('subservice_orgs', [])[:20]:
        name = entry.get('third_party_name')
        conf = entry.get('third_party_confidence')
        print(f" - {name} (conf={conf})")

# Tail the GPT log files for visibility
log_paths = [proj / 'data' / 'logs' / 'subservice_orgs_gpt.log', proj / 'data' / 'logs' / 'subservice_orgs_extractor.log']
for lp in log_paths:
    try:
        print('\n== Log:', lp)
        if lp.exists():
            with lp.open('r', encoding='utf-8') as f:
                tail = f.read().splitlines()[-40:]
                print('\n'.join(tail))
        else:
            print('Log not found:', lp)
    except Exception as e:
        print('Failed to read log', lp, e)
