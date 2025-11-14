import json
path='data/json/subservice_orgs_enhanced_preserve.json'
with open(path,encoding='utf-8') as f:
    j=json.load(f)
    items = j.get('subservice_orgs') if isinstance(j,dict) and 'subservice_orgs' in j else (j if isinstance(j,list) else [])

targets=[
 'Amazon Web Services, Inc.','Microsoft Corporation','Google LLC',
 'Cyxtera Technologies, Inc.','Digital Realty Trust, Inc.','Equinix, Inc.','NTT ltd.'
]

print('Total enhanced items:', len(items))

# build lookup by various name forms
by_name={}
for it in items:
    names=set()
    for k in ('third_party_name','canonical_name','third_party'):
        v=it.get(k)
        if isinstance(v,str): names.add(v)
        if isinstance(v,list):
            for x in v:
                names.add(str(x))
    # also include normalized lower
    for n in list(names):
        by_name.setdefault(n.strip(),[]).append(it)
        by_name.setdefault(n.strip().lower(),[]).append(it)


def show_list(lst):
    for it in lst:
        print(' - name:', it.get('third_party_name') or it.get('canonical_name') or '')
        print('   is_canonical_summary:', it.get('is_canonical_summary'))
        print('   third_party_confidence:', it.get('third_party_confidence'))
        print('   canonical_name:', it.get('canonical_name'))
        print('   confidence_justification:', it.get('confidence_justification'))
        print('   page_ref:', it.get('third_party_page_ref'))
        print('')

for t in targets:
    print('\n====',t,'====')
    direct = by_name.get(t,[]) + by_name.get(t.lower(),[])
    if direct:
        show_list(direct)
    else:
        print(' no direct entries found in enhanced for exact name')
    # search canonical summaries matching corporate root
    matches=[it for it in items if it.get('canonical_name') and t.split(',')[0] in it.get('canonical_name')]
    if matches:
        print(' canonical summaries containing root:')
        show_list(matches)

# Also list top canonical summaries (is_canonical_summary True) for context
print('\n==== Canonical summaries (is_canonical_summary True) count:')
can=[it for it in items if it.get('is_canonical_summary')]
print(len(can))
for it in can[:50]:
    print('-', it.get('canonical_name') or it.get('third_party_name'), 'conf:', it.get('third_party_confidence'))
