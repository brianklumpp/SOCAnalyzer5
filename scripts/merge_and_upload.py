"""Merge `subservice_orgs_enhanced_preserve.json` into `combined_result.json`, back up the original, and call DB uploader.

Usage: .venv\Scripts\python.exe scripts\merge_and_upload.py
"""
import json
import shutil
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMBINED = ROOT / 'data' / 'json' / 'combined_result.json'
ENH = ROOT / 'data' / 'json' / 'subservice_orgs_enhanced_preserve.json'
BACKUP = ROOT / 'data' / 'json' / f'combined_result.json.bak.{datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")}'

if __name__ == '__main__':
    if not ENH.exists():
        print('ERROR: enhanced preserve file not found at', ENH)
        raise SystemExit(1)
    if not COMBINED.exists():
        print('ERROR: combined_result.json not found at', COMBINED)
        raise SystemExit(1)

    print('Backing up combined_result.json to', BACKUP)
    shutil.copy2(COMBINED, BACKUP)

    combined = json.load(open(COMBINED, encoding='utf-8'))
    enhanced = json.load(open(ENH, encoding='utf-8'))

    # Determine enhanced subservice list
    enh_list = enhanced.get('subservice_orgs') if isinstance(enhanced, dict) and 'subservice_orgs' in enhanced else (enhanced if isinstance(enhanced, list) else [])

    print('Existing combined subservice_orgs count:', len(combined.get('subservice_orgs', [])))
    print('Enhanced subservice_orgs count:', len(enh_list))

    # Replace combined's subservice_orgs with the enhanced list
    combined['subservice_orgs'] = enh_list

    # Write merged combined_result.json (overwrite)
    with open(COMBINED, 'w', encoding='utf-8') as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    print('Wrote merged combined_result.json')

    # Attempt DB upload via backend.app.explicit_sql_insert.insert_extracted_data
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from backend.app.explicit_sql_insert import insert_extracted_data
        print('Calling insert_extracted_data on combined_result.json...')
        summary = insert_extracted_data(str(COMBINED))
        print('Insert summary:')
        for k, v in summary.items():
            if k != 'errors':
                print(f'  {k}: {v}')
        if summary.get('errors'):
            print('Errors:')
            for e in summary['errors']:
                print('  ', e)
    except Exception as e:
        print('DB upload failed or skipped:', e)
        raise
