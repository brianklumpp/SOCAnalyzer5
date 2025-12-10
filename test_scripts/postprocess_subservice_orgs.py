import json

INPUT_PATH = 'data/json/subservice_orgs_result.json'
OUTPUT_PATH = 'data/json/subservice_orgs_result_postprocessed.json'

def group_control_ids(third_parties):
    for entry in third_parties:
        controls = entry.get('third_party_controls', [])
        # Collect all unique, non-null control IDs
        control_ids = [c.get('third_party_control_id') for c in controls if c.get('third_party_control_id')]
        entry['third_party_control_ids'] = ','.join(sorted(set(control_ids))) if control_ids else None
        # Remove control_id from each control, keep only seq and desc
        for c in controls:
            c.pop('third_party_control_id', None)
    return third_parties

def main():
    with open(INPUT_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    third_parties = data.get('third_parties', [])
    third_parties = group_control_ids(third_parties)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump({'third_parties': third_parties}, f, indent=2, ensure_ascii=False)
    print(f'Wrote postprocessed results to {OUTPUT_PATH}')

if __name__ == '__main__':
    main()
