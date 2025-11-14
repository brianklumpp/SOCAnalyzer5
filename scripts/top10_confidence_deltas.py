import json
import os

RAW = 'data/json/subservice_orgs_raw_snapshot.json'
ENH = 'data/json/subservice_orgs_enhanced_preserve.json'


def load(path):
    if not os.path.exists(path):
        return []
    j = json.load(open(path, encoding='utf-8'))
    if isinstance(j, dict):
        if 'subservice_orgs' in j and isinstance(j['subservice_orgs'], list):
            return j['subservice_orgs']
        for v in j.values():
            if isinstance(v, list):
                return v
        return []
    if isinstance(j, list):
        return j
    return []


def key_of(item):
    for k in ('canonical_name', 'third_party_name', 'third_party', 'name'):
        v = item.get(k)
        if v:
            return str(v).strip()
    return None


def conf_of(item):
    if item is None:
        return None
    v = item.get('third_party_confidence')
    # Sometimes confidence stored as string
    try:
        return float(v) if v is not None else None
    except Exception:
        try:
            return float(str(v).strip())
        except Exception:
            return None


def main():
    raw = load(RAW)
    enh = load(ENH)

    raw_idx = {key_of(it) or f'__row_{i}': it for i, it in enumerate(raw)}
    enh_idx = {key_of(it) or f'__row_{i}': it for i, it in enumerate(enh)}

    # union of keys
    keys = set(list(raw_idx.keys()) + list(enh_idx.keys()))

    deltas = []
    for k in keys:
        a = raw_idx.get(k)
        b = enh_idx.get(k)
        a_conf = conf_of(a) if a else None
        b_conf = conf_of(b) if b else None
        # only consider entries where at least one confidence is present
        if a_conf is None and b_conf is None:
            continue
        # treat missing as 0.0? keep None and compute only when both present or one present
        # We'll compute delta treating None as 0.0 to surface big changes
        a_val = a_conf if a_conf is not None else 0.0
        b_val = b_conf if b_conf is not None else 0.0
        delta = b_val - a_val
        deltas.append((abs(delta), delta, k, a_conf, b_conf, a, b))

    deltas.sort(reverse=True, key=lambda x: x[0])

    top = deltas[:10]

    out_lines = []
    out_lines.append('Top 10 confidence changes (raw -> enhanced)')
    out_lines.append('Format: name | raw_conf | enhanced_conf | delta (enh - raw)')
    out_lines.append('')
    for rank, (absd, d, k, a_conf, b_conf, a, b) in enumerate(top, start=1):
        out_lines.append(f'{rank}. {k} | {a_conf} -> {b_conf} | delta={d}')
        # show justification lines if present in enhanced
        if b and isinstance(b.get('confidence_justification'), list) and b.get('confidence_justification'):
            out_lines.append('   enhanced confidence_justification:')
            for j in b.get('confidence_justification')[:5]:
                out_lines.append('     - ' + str(j))
        elif a and isinstance(a.get('confidence_justification'), list) and a.get('confidence_justification'):
            out_lines.append('   raw confidence_justification:')
            for j in a.get('confidence_justification')[:5]:
                out_lines.append('     - ' + str(j))
        # show raw and enhanced page refs briefly
        pr = (a.get('third_party_page_ref') if a else None)
        pe = (b.get('third_party_page_ref') if b else None)
        if pr or pe:
            out_lines.append(f'   page_ref raw: {pr} | enhanced: {pe}')
        out_lines.append('')

    report = '\n'.join(out_lines)
    print(report)

    # also write to file
    out_path = 'data/json/subservice_orgs_top10_confidence_changes.txt'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print('\nWrote:', out_path)


if __name__ == '__main__':
    main()
