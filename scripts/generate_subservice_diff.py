import json
import os
from collections import defaultdict

FILES = {
    'raw': 'data/json/subservice_orgs_raw_snapshot.json',
    'enhanced': 'data/json/subservice_orgs_enhanced_preserve.json',
    'result': 'data/json/subservice_orgs_result.json'
}

OUT_PATH = 'data/json/subservice_orgs_diff_report.txt'


def load(path):
    if not os.path.exists(path):
        return []
    try:
        j = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        return []
    if isinstance(j, dict):
        # common shape: {'subservice_orgs': [...]} or direct list
        if 'subservice_orgs' in j and isinstance(j['subservice_orgs'], list):
            return j['subservice_orgs']
        # fallback: maybe top-level list
        for v in j.values():
            if isinstance(v, list):
                return v
        return []
    if isinstance(j, list):
        return j
    return []


def key_of(item):
    # Prefer canonical_name, then third_party_name, then normalized name
    for k in ('canonical_name', 'third_party_name', 'third_party'):
        v = item.get(k)
        if v:
            return str(v).strip()
    # last resort: try name-like fields
    if 'name' in item:
        return str(item['name']).strip()
    return None


def normalize_val(v):
    try:
        return json.dumps(v, sort_keys=True, ensure_ascii=False)
    except Exception:
        return str(v)


def diff_items(a, b):
    # return dict of differing fields with (a_val, b_val)
    diffs = {}
    keys = set(a.keys()) | set(b.keys())
    for k in sorted(keys):
        av = a.get(k)
        bv = b.get(k)
        if normalize_val(av) != normalize_val(bv):
            diffs[k] = (av, bv)
    return diffs


def make_index(items):
    idx = defaultdict(list)
    for it in items:
        k = key_of(it) or ''
        idx[k].append(it)
    return idx


def main():
    data = {name: load(path) for name, path in FILES.items()}
    counts = {name: len(lst) for name, lst in data.items()}

    idx = {name: make_index(lst) for name, lst in data.items()}

    all_keys = set()
    for d in idx.values():
        all_keys.update(d.keys())

    lines = []
    lines.append('Subservice Orgs Diff Report')
    lines.append('Files:')
    for name, path in FILES.items():
        lines.append(f'- {name}: {path} -> {counts[name]} entries')
    lines.append('')

    # Summary: present-only-in lists
    only_in = {}
    for name in FILES.keys():
        others = set(FILES.keys()) - {name}
        only = []
        for k in all_keys:
            if k == '':
                continue
            present_here = bool(idx[name].get(k))
            present_elsewhere = any(bool(idx[o].get(k)) for o in others)
            if present_here and not present_elsewhere:
                only.append(k)
        only_in[name] = only

    lines.append('Entries present only in one file:')
    for name, keys in only_in.items():
        lines.append(f'- Only in {name} ({len(keys)}):')
        for k in sorted(keys)[:200]:
            lines.append(f'  - {k}')
        if len(keys) > 200:
            lines.append(f'  ... (+{len(keys)-200} more)')
    lines.append('')

    # For keys present in multiple files, show diffs
    lines.append('Per-entry diffs for keys present in multiple files:')
    for k in sorted([x for x in all_keys if x]):
        presence = {name: len(idx[name].get(k, [])) for name in FILES.keys()}
        if sum(1 for v in presence.values() if v > 0) < 2:
            continue
        lines.append(f'-- {k}')
        lines.append(f'   presence: {presence}')
        # If multiple items per key in a file, note counts
        for name in FILES.keys():
            items = idx[name].get(k, [])
            if items:
                if len(items) > 1:
                    lines.append(f'   {name} has {len(items)} items (showing first)')
        # Compare to raw first item where possible
        a_items = idx['raw'].get(k, [])
        e_items = idx['enhanced'].get(k, [])
        r_items = idx['result'].get(k, [])

        # We'll compare the first item from each list
        a = a_items[0] if a_items else {}
        e = e_items[0] if e_items else {}
        r = r_items[0] if r_items else {}

        diffs_ae = diff_items(a, e)
        diffs_ar = diff_items(a, r)
        if diffs_ae:
            lines.append('   changes raw -> enhanced:')
            for fld, (av, bv) in diffs_ae.items():
                lines.append(f'     * {fld}:')
                lines.append(f'         raw: {normalize_val(av)}')
                lines.append(f'         enhanced: {normalize_val(bv)}')
        if diffs_ar:
            lines.append('   changes raw -> result:')
            for fld, (av, bv) in diffs_ar.items():
                lines.append(f'     * {fld}:')
                lines.append(f'         raw: {normalize_val(av)}')
                lines.append(f'         result: {normalize_val(bv)}')
        lines.append('')

    # Also list keys that appear duplicated within a file
    lines.append('Duplicate-name groups within each file:')
    for name in FILES.keys():
        dupes = [k for k, v in idx[name].items() if k and len(v) > 1]
        lines.append(f'- {name}: {len(dupes)} duplicates')
        for k in dupes[:200]:
            lines.append(f'  - {k} ({len(idx[name][k])} rows)')
        if len(dupes) > 200:
            lines.append(f'  ... (+{len(dupes)-200} more)')
    lines.append('')

    report = '\n'.join(lines)
    # Write
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write(report)
    print(report)


if __name__ == '__main__':
    main()
