import json, re, sys

def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'ERROR loading {path}: {e}')
        return None

paths = [
    'data/json/subservice_orgs_result.json',
    'data/json/combined_result.json'
]

companies = [
"Amazon Web Services, Inc.","Microsoft Corporation","Google LLC","Cyxtera Technologies, Inc.",
"Digital Realty Trust, Inc.","Equinix, Inc.","NTT Ltd.","AWS","Google","Microsoft",
"Amazon Web Services (AWS)","Google Cloud Platform (GCP)","Cyxtera","Digital Realty Trust",
"Equinix","NTT Ltd.","GitHub","GitLab","Splunk","Microsoft Active Directory",
"SolarWinds","Amazon Web Services","Microsoft Azure","HashiCorp Vault","Okta",
"Microsoft Active Directory (AD)","SailPoint","Workday","Rapid7 Nexpose","CrowdStrike Falcon",
"Adobe-Managed Facilities","Azure","Nexpose","Approved third-party security firms",
"Amazon Web Services, Inc.","Microsoft Corporation","Digital Realty Trust, Inc.","Equinix, Inc."
]
# dedupe
companies = list(dict.fromkeys(companies))

# compile simple normalized matcher
def norm(s):
    if s is None:
        return ''
    return re.sub(r"\s+"," ", s.strip().lower())

match_results = {c: [] for c in companies}

for path in paths:
    data = load_json(path)
    if data is None:
        continue
    # handle both top-level list or dict with key 'subservice_orgs'
    candidates = []
    if isinstance(data, dict) and 'subservice_orgs' in data:
        candidates = data.get('subservice_orgs') or []
    elif isinstance(data, list):
        candidates = data
    else:
        # scan dict values for lists of orgs
        for v in data.values():
            if isinstance(v, list):
                candidates.extend(v)
    for idx, entry in enumerate(candidates):
        # skip non-dict entries
        if not isinstance(entry, dict):
            continue
        fields = {
            'file': path,
            'index': idx,
            'third_party_name': entry.get('third_party_name'),
            'canonical_name': entry.get('canonical_name'),
            'aliases': entry.get('aliases') or [],
            'page_ref': entry.get('third_party_page_ref'),
            'confidence': entry.get('third_party_confidence'),
            'is_canonical_summary': entry.get('is_canonical_summary', False),
        }
        # build search strings to match against
        search_strings = []
        for fn in ('third_party_name','canonical_name'):
            v = entry.get(fn)
            if isinstance(v, str):
                search_strings.append(norm(v))
        # aliases
        for a in (entry.get('aliases') or []):
            if isinstance(a, str):
                search_strings.append(norm(a))
        # also include page_ref stringified
        pr = entry.get('third_party_page_ref')
        if pr:
            if isinstance(pr, list):
                search_strings.append(norm(','.join(map(str,pr))))
            else:
                search_strings.append(norm(str(pr)))
        # now test each company name for presence
        for comp in companies:
            comp_norm = norm(comp)
            found = False
            # direct substring match
            for s in search_strings:
                if comp_norm and comp_norm in s:
                    found = True
                    break
            # also test token match (e.g., 'aws' matches 'amazon web services')
            if not found:
                tokens = comp_norm.split()
                for s in search_strings:
                    if all(tok in s for tok in tokens if len(tok)>=2):
                        found = True
                        break
            if found:
                match_results[comp].append(fields)

# print results
for comp in companies:
    hits = match_results.get(comp) or []
    if not hits:
        print(f"{comp}: NOT FOUND")
    else:
        print(f"{comp}: FOUND {len(hits)} occurrence(s)")
        for h in hits:
            print(f"  - file={h['file']} index={h['index']} name={h['third_party_name']!r} canonical={h['canonical_name']!r} page_ref={h['page_ref']!r} confidence={h['confidence']} canonical_summary={h['is_canonical_summary']}")
    print()

print('SEARCH COMPLETE')
