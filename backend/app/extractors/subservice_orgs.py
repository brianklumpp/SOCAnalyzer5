

import os
import json
import logging
import time
import re
from difflib import SequenceMatcher
from .. import config
from ..gpt_client import gpt_extract
from ..config import HEURISTIC_EXCLUDE_KEYWORDS, THIRD_PARTY_ALIAS_MAP, SO_KEYWORDS, SUBSERVICE_ORG_GPT_FILTER_PROMPT, SUBSERVICE_ORG_ADVANCED_EXTRACTION_PROMPT

# Use centralized config paths
SECTION_JSON_PATH = config.SECTION_JSON_PATH
OUTPUT_JSON_PATH = config.JSON_DIR / "subservice_orgs_result.json"
PDF_TXT_PATH = config.PDF_TXT_PATH

logger = logging.getLogger(__name__)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_text_for_lines(txt_lines, start_line, end_line):
    return ''.join(txt_lines[start_line-1:end_line])

def extract_text_for_pages(txt_lines, page_numbers):
    result = []
    current_page = 1
    for line in txt_lines:
        if line.strip().startswith('=== PAGE '):
            try:
                current_page = int(line.strip().split()[2])
            except Exception:
                continue
        if current_page in page_numbers:
            result.append(line)
    return ''.join(result)

def chunk_text_with_overlap(text, chunk_size, overlap):
    chunks = []
    i = 0
    text_len = len(text)
    while i < text_len:
        chunk = text[i:i+chunk_size]
        chunks.append(chunk)
        if i + chunk_size >= text_len:
            break
        i += chunk_size - overlap
    return chunks

def chunk_text(text, max_tokens=None):
    if max_tokens is None:
        max_tokens = getattr(config, 'GPT_CHUNK_TOKENS', None)
        if max_tokens is None:
            max_tokens = getattr(config, 'DEFAULT_CHUNK_SIZE', 1500)
    chunk_size = max_tokens * 4
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def load_common_so_list(path):
    with open(path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def extract_subservice_orgs():
    section_results = load_json(SECTION_JSON_PATH)
    desc_section = next((s for s in section_results if s.get('topic') == 'Description_of_System'), None)
    if not desc_section:
        logging.error('No Description_of_System section found.')
        return None
    start_line = desc_section.get('line')
    end_line = desc_section.get('end_line')
    with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    if start_line and end_line:
        text = extract_text_for_lines(txt_lines, start_line, end_line)
    else:
        start = desc_section['DOC_page_ref']
        end = desc_section['end_DOC_page_ref']
        pages = list(range(start, end + 1))
        text = extract_text_for_pages(txt_lines, pages)
    # Cap chunk size for GPT safety and add overlap
    chunk_size = min(getattr(config, 'SUBSERVICE_CHUNK_SIZE', 3000), 1500)
    overlap = getattr(config, 'TEXT_OVERLAP', 1000)
    chunks = chunk_text_with_overlap(text, chunk_size, overlap)
    chunk_results = []
    bad_chunks = []
    for idx, chunk in enumerate(chunks):
        logging.debug(f'Chunk {idx} text: {chunk[:1000]}...')
        prompt = SUBSERVICE_ORG_ADVANCED_EXTRACTION_PROMPT.format(
            text=chunk
        )
        logging.debug(f'Chunk {idx} prompt: {prompt[:500]}...')
        response = gpt_extract(prompt)
        logging.debug(f'Chunk {idx} response: {response}')
        # Log response length for truncation analysis
        logging.info(f'Chunk {idx} GPT response length: {len(response) if response else 0}')
        if not response:
            logging.error(f'No response from GPT for chunk {idx}.')
            bad_chunk_info = {
                'chunk_index': idx,
                'chunk_text': chunk[:500],
                'gpt_response': '',
                'error': 'No response from GPT',
                'response_length': 0,
                'chunk_size': len(chunk),
                'prompt_length': len(prompt)
            }
            bad_chunks.append(bad_chunk_info)
            continue
        try:
            clean_response = response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:]
            if clean_response.startswith('```'):
                clean_response = clean_response[3:]
            if clean_response.endswith('```'):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            def extract_json(text):
                obj_match = re.search(r'(\{.*?\})', text, re.DOTALL)
                if obj_match:
                    return obj_match.group(1)
                array_match = re.search(r'(\[.*?\])', text, re.DOTALL)
                if array_match:
                    return array_match.group(1)
                return text
            # Try direct parse
            try:
                data = json.loads(clean_response)
            except Exception as e1:
                # Try to extract a valid JSON object/array
                json_sub = extract_json(clean_response)
                try:
                    data = json.loads(json_sub)
                except Exception as e2:
                    # Try to repair unterminated array (common GPT truncation)
                    repaired = json_sub
                    if not repaired.strip().endswith(']') and repaired.strip().startswith('['):
                        repaired = repaired.strip() + ']'
                    try:
                        data = json.loads(repaired)
                    except Exception as e3:
                        # Try to recover as much as possible: find all valid JSON objects in the text
                        objs = re.findall(r'\{[^}]*\}', clean_response)
                        data = [json.loads(obj) for obj in objs if obj.strip().startswith('{')]
                        if not data:
                            # Log the bad chunk and response for inspection
                            bad_chunk_info = {
                                'chunk_index': idx,
                                'chunk_text': chunk[:500],
                                'gpt_response': response[:1000],
                                'error': f"e1: {e1}; e2: {e2}; e3: {e3}",
                                'response_length': len(response) if response else 0,
                                'chunk_size': len(chunk),
                                'prompt_length': len(prompt)
                            }
                            logging.error(f"Failed to parse GPT response as JSON. Raw response: {response}")
                            bad_chunks.append(bad_chunk_info)
                            continue
            if isinstance(data, list):
                for org in data:
                    org['source_context'] = chunk[:1000]
                chunk_results.extend(data)
        except Exception as e:
            logging.error(f'Failed to parse GPT response for chunk {idx}: {response} | Error: {e}')
            bad_chunk_info = {
                'chunk_index': idx,
                'chunk_text': chunk[:500],
                'gpt_response': response[:1000],
                'error': str(e),
                'response_length': len(response) if response else 0,
                'chunk_size': len(chunk),
                'prompt_length': len(prompt)
            }
            bad_chunks.append(bad_chunk_info)
    # Deduplicate by third_party_name and merge page refs/controls
    seen = {}
    for org in chunk_results:
        name = org.get('third_party_name')
        if not name:
            continue
        key = name.lower()
        if key in seen:
            # Merge page refs and controls
            prev = seen[key]
            if org.get('third_party_page_ref') and prev.get('third_party_page_ref'):
                prev['third_party_page_ref'] += ',' + org['third_party_page_ref']
            if org.get('third_party_controls') and prev.get('third_party_controls'):
                prev['third_party_controls'] += org['third_party_controls']
        else:
            seen[key] = org

    # --- POST-EXTRACTION ANALYSIS: Rescue Check for Bad Chunks ---
    def fuzzy_match(a, b):
        return SequenceMatcher(None, a, b).ratio()

    rescue_report = []
    if bad_chunks:

        recovered_orgs = []
        for bad in bad_chunks:
            bad_descs = []
            try:
                matches = re.findall(r'"third_party_name"\s*:\s*"([^\"]+)"', bad.get('chunk_text', ''))
                bad_descs.extend(matches)
            except Exception:
                pass
            if not bad_descs and bad.get('chunk_text'):
                bad_descs.append(bad['chunk_text'][:100])
            for bad_desc in bad_descs:
                found = False
                exact_match = None
                fuzzy_best = None
                fuzzy_score = 0.0
                for good in seen.values():
                    good_desc = good.get('third_party_name', '')
                    if not good_desc:
                        continue
                    if bad_desc.strip() == good_desc.strip():
                        exact_match = good_desc
                        found = True
                        break
                    score = fuzzy_match(bad_desc.strip(), good_desc.strip())
                    if score > fuzzy_score:
                        fuzzy_score = score
                        fuzzy_best = good_desc
                if found:
                    rescue_report.append({
                        'bad_chunk_desc': bad_desc,
                        'rescue_type': 'exact',
                        'matched_desc': exact_match,
                        'confidence_pct': 100
                    })
                elif fuzzy_score > 0.7:
                    rescue_report.append({
                        'bad_chunk_desc': bad_desc,
                        'rescue_type': 'fuzzy',
                        'matched_desc': fuzzy_best,
                        'confidence_pct': int(round(fuzzy_score * 100))
                    })
                    # Add high-confidence rescue if confidence >= 0.9
                    if fuzzy_score >= 0.9 and fuzzy_best:
                        # Only add if not already present
                        if not any((o.get('third_party_name', '').strip() == fuzzy_best.strip()) for o in seen.values()):
                            recovered_orgs.append({
                                'third_party_name': fuzzy_best,
                                'org_source': 'recovered_fuzzy',
                                'org_confidence': round(fuzzy_score, 3),
                                'org_confidence_justification': ['Recovered by fuzzy match with confidence {:.1f}%'.format(fuzzy_score*100)]
                            })
                else:
                    rescue_report.append({
                        'bad_chunk_desc': bad_desc,
                        'rescue_type': 'unmatched',
                        'matched_desc': None,
                        'confidence_pct': int(round(fuzzy_score * 100))
                    })
        # Add recovered orgs to seen
        if recovered_orgs:
            for rc in recovered_orgs:
                key = rc['third_party_name'].lower()
                if key not in seen:
                    seen[key] = rc

        logging.info("SUBSERVICE ORGS POST-EXTRACTION RESCUE ANALYSIS:")
        for entry in rescue_report:
            logging.info(f"Bad chunk desc: {entry['bad_chunk_desc'][:80]}... | Rescue: {entry['rescue_type']} | Confidence: {entry['confidence_pct']}% | Matched: {entry['matched_desc'][:80] if entry['matched_desc'] else None}")

    output = {'third_parties': list(seen.values())}
    if bad_chunks:
        output['bad_chunks'] = bad_chunks
        output['bad_chunk_rescue_report'] = rescue_report
        output['bad_chunk_count'] = len(bad_chunks) # type: ignore
        output['rescued_chunk_count'] = len([r for r in rescue_report if r.get('confidence_pct', 0) >= 90]) # type: ignore
        output['unrecoverable_chunks'] = [r for r in rescue_report if r.get('rescue_type') == 'unmatched'] # type: ignore
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logging.info(f'Subservice orgs extraction result: {output}')
    return output

def normalize_third_party_names(third_parties):
    """
    Deduplicate third parties by mapping common/shortened names to canonical names and merging their data.
    """
    alias_map = THIRD_PARTY_ALIAS_MAP
    def canonical(name):
        if not name:
            return None
        key = name.strip().lower()
        return alias_map.get(key, name.strip())

    merged = {}
    for entry in third_parties:
        canon = canonical(entry.get('third_party_name'))
        if not canon:
            continue
        if canon not in merged:
            merged[canon] = entry.copy()
            merged[canon]['third_party_name'] = canon
        else:
            # Merge page refs
            prev = merged[canon]
            if entry.get('third_party_page_ref') and prev.get('third_party_page_ref'):
                prev['third_party_page_ref'] += ',' + entry['third_party_page_ref']
            elif entry.get('third_party_page_ref'):
                prev['third_party_page_ref'] = entry['third_party_page_ref']
            # Merge controls
            if entry.get('third_party_controls') and prev.get('third_party_controls'):
                prev['third_party_controls'] += entry['third_party_controls']
            elif entry.get('third_party_controls'):
                prev['third_party_controls'] = entry['third_party_controls']
            # Optionally, merge/average confidence, etc.
    return list(merged.values())

def filter_company_references(third_parties, company_names):
    """
    Remove any third parties whose name matches the company being audited or its parent.
    """
    company_names_lower = {n.lower() for n in company_names if n}
    filtered = []
    for entry in third_parties:
        name = entry.get('third_party_name', '').lower()
        if any(cn in name for cn in company_names_lower):
            continue
        filtered.append(entry)
    return filtered

def is_heuristic_excluded(entry, company_names):
    desc = (entry.get('third_party_description') or '').lower()
    name = (entry.get('third_party_name') or '').lower()
    # Heuristic: exclude if description or name contains any keyword
    for kw in HEURISTIC_EXCLUDE_KEYWORDS:
        if kw in desc or kw in name:
            return True
    # Fuzzy match for company/parent
    for cname in company_names:
        cname = cname.lower()
        if cname and (cname in name or cname in desc or SequenceMatcher(None, cname, name).ratio() > 0.85):
            return True
    return False

def levenshtein_distance(a, b):
    # Simple Levenshtein distance implementation
    if a == b:
        return 0
    if len(a) == 0:
        return len(b)
    if len(b) == 0:
        return len(a)
    v0 = list(range(len(b) + 1))
    v1 = [0] * (len(b) + 1)
    for i in range(len(a)):
        v1[0] = i + 1
        for j in range(len(b)):
            cost = 0 if a[i] == b[j] else 1
            v1[j + 1] = min(v1[j] + 1, v0[j + 1] + 1, v0[j] + cost)
        v0, v1 = v1, v0
    return v0[len(b)]

def calculate_distance_from_so_keywords(entry):
    name = (entry.get('third_party_name') or '').lower()
    context = (entry.get('source_context') or '').lower()
    min_dist = 999
    for kw in SO_KEYWORDS:
        for word in context.split():
            dist = levenshtein_distance(kw, word)
            if dist < min_dist:
                min_dist = dist
    return min_dist

def clean_company_name(name):
    if not name:
        return ''
    base = re.sub(r'[.,]', '', name.lower())
    base = re.sub(r'\b(inc|llc|ltd|corp|corporation|incorporated|plc|gmbh|sarl|sa|bv|lp|llp|co)\b', '', base)
    return base.strip()

def calculate_confidence(entry, company_names, so_list, likely_so, common_so, top2_distance_names):
    conf = 0.3
    name = (entry.get('third_party_name') or '').strip().lower()
    cleaned_name = clean_company_name(name)
    cleaned_company_names = [clean_company_name(n) for n in company_names if n]
    # Reduce by 0.8 if name matches company or parent (fuzzy)
    for cname in cleaned_company_names:
        if cname and (cname == cleaned_name or cname in cleaned_name or cleaned_name in cname or SequenceMatcher(None, cname, cleaned_name).ratio() > 0.85):
            conf -= 0.8
            break
    if name in {so.strip().lower() for so in so_list}:
        conf += 0.4
    if likely_so == 'Yes':
        conf += 0.1
    elif likely_so == 'No':
        conf -= 0.1
    if common_so == 'Yes':
        conf += 0.1
    if name in top2_distance_names:
        conf += 0.1
    return conf

def postprocess_third_parties(third_parties, company_names, so_list, heuristic_exclusions_log_path=None):
    processed = []
    heuristic_exclusions = []
    so_names_lower = {so.strip().lower() for so in so_list}
    # Calculate distance_from_so_keywords for all entries
    for entry in third_parties:
        entry['distance_from_so_keywords'] = calculate_distance_from_so_keywords(entry)
    # Find top 2 closest (lowest distance)
    sorted_by_distance = sorted(third_parties, key=lambda x: x['distance_from_so_keywords'])
    top2_distance_names = set((entry.get('third_party_name') or '').strip().lower() for entry in sorted_by_distance[:2])
    for entry in third_parties:
        name_lower = (entry.get('third_party_name') or '').strip().lower()
        is_common_so = name_lower in so_names_lower
        likely_so = entry.get('likely_so', 'Yes')
        common_so = 'Yes' if is_common_so else 'No'
        if is_common_so:
            entry['common_so'] = 'Yes'
        else:
            entry['common_so'] = calculate_common_so(entry, so_list)
        if is_heuristic_excluded(entry, company_names) and not is_common_so:
            heuristic_exclusions.append({'entry': entry, 'reason': 'Python heuristic exclusion (keyword/company match)'})
            continue
        conf = calculate_confidence(entry, company_names, so_list, likely_so, entry['common_so'], top2_distance_names)
        conf = min(1.0, max(0.0, conf))  # Clamp after all calcs
        entry['third_party_confidence'] = round(conf, 3)
        processed.append(entry)
    if heuristic_exclusions_log_path and heuristic_exclusions:
        with open(heuristic_exclusions_log_path, 'a', encoding='utf-8') as logf:
            for ex in heuristic_exclusions:
                logf.write(json.dumps(ex, ensure_ascii=False) + '\n')
    processed.sort(key=lambda x: x.get('third_party_confidence', 0), reverse=True)
    return processed

def clean_company_names(company_names):
    # Remove punctuation and common suffixes for fuzzy matching
    cleaned = set()
    for name in company_names:
        if not name:
            continue
        base = re.sub(r'[.,]', '', name.lower())
        base = re.sub(r'\b(inc|llc|ltd|corp|corporation|incorporated|plc|gmbh|sarl|sa|bv|lp|llp|co)\b', '', base)
        base = base.strip()
        cleaned.add(base)
    return cleaned

def set_likely_so_for_company_and_parent(third_parties, company_names):
    cleaned_names = clean_company_names(company_names)
    for entry in third_parties:
        name = re.sub(r'[.,]', '', (entry.get('third_party_name') or '').lower())
        desc = re.sub(r'[.,]', '', (entry.get('third_party_description') or '').lower())
        for cn in cleaned_names:
            # Fuzzy: substring or high similarity
            if cn and (cn in name or cn in desc or SequenceMatcher(None, cn, name).ratio() > 0.85 or SequenceMatcher(None, cn, desc).ratio() > 0.85):
                entry['likely_so'] = 'No'
    return third_parties

def filter_third_parties_with_gpt():
    """
    Post-processes extracted third parties using GPT to filter out non-companies (frameworks, departments, generic terms, software, etc.).
    Logs exclusions with reasons. Overwrites the JSON with filtered results.
    """
    # gpt_extract already imported at top
    
    INPUT_JSON_PATH = OUTPUT_JSON_PATH
    FILTER_LOG_PATH = os.path.join('data', 'logs', 'subservice_orgs_filter.log')
    HEURISTIC_LOG_PATH = os.path.join('data', 'logs', 'subservice_orgs_heuristic_filter.log')
    GPT_LOG_PATH = os.path.join('data', 'logs', 'subservice_orgs_gpt.log')
    with open(GPT_LOG_PATH, 'w', encoding='utf-8') as gptlog:
        gptlog.write('')  # Reset GPT log
    with open(FILTER_LOG_PATH, 'w', encoding='utf-8') as flog:
        flog.write('')  # Reset filter log
    with open(HEURISTIC_LOG_PATH, 'w', encoding='utf-8') as hlog:
        hlog.write('')  # Reset heuristic log
    with open(INPUT_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    third_parties = data.get('third_parties', [])
    # Normalize/deduplicate before filtering
    third_parties = normalize_third_party_names(third_parties)
    # Filter out company being audited and parent
    company_json_path = str(config.JSON_DIR / 'company_result.json')
    try:
        with open(company_json_path, 'r', encoding='utf-8') as cf:
            company_data = json.load(cf)
        company_names = [company_data.get('company', ''), company_data.get('parent_company', '')]
    except Exception:
        company_names = []
    third_parties = filter_company_references(third_parties, company_names)
    # Heuristic and post-processing blocklist
    so_list = load_common_so_list(os.path.join('app', 'extractors', 'subservice_orgs.txt'))
    # Enhanced GPT prompt
    filtered = []
    exclusions = []
    for entry in third_parties:
        name = entry.get('third_party_name')
        desc = entry.get('third_party_description')
        context = entry.get('source_context', '')
        prompt = SUBSERVICE_ORG_GPT_FILTER_PROMPT.format(name=name, desc=desc, context=context)
        response = ""
        try:
            response = gpt_extract(prompt)
            with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
                gptlog.write(f'PROMPT:\n{prompt}\nRESPONSE:\n{response}\n---\n')
            if response:
                result = json.loads(response)
                if result.get('keep') and result.get('type', '').lower() == 'company':
                    filtered.append(entry)
                else:
                    exclusions.append({'entry': entry, 'reason': result.get('reason', 'No reason provided'), 'type': result.get('type', '')})
            else:
                exclusions.append({'entry': entry, 'reason': 'No response from GPT.'})
        except Exception as e:
            with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
                gptlog.write(f'PROMPT:\n{prompt}\nRESPONSE:\n{response}\nERROR: {e}\n---\n')
            exclusions.append({'entry': entry, 'reason': f'GPT error or parse error: {e}. Response: {response}'})
        time.sleep(0.7)  # avoid rate limits
    # Post-process: heuristics, confidence, common_so, distance, sort
    filtered = postprocess_third_parties(filtered, company_names, so_list, heuristic_exclusions_log_path=HEURISTIC_LOG_PATH)
    # Set likely_so to 'No' for company/parent
    filtered = set_likely_so_for_company_and_parent(filtered, company_names)
    # Write filtered results
    with open(INPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump({'third_parties': filtered}, f, indent=2, ensure_ascii=False)
    # Log exclusions
    with open(FILTER_LOG_PATH, 'a', encoding='utf-8') as logf:
        for ex in exclusions:
            logf.write(json.dumps(ex, ensure_ascii=False) + '\n')
    logging.info(f"Filtered third parties. Kept: {len(filtered)}. Excluded: {len(exclusions)}. See {FILTER_LOG_PATH} for details. Heuristic exclusions in {HEURISTIC_LOG_PATH}.")

def elevate_and_group_control_ids(json_path=OUTPUT_JSON_PATH):
    """
    Post-processes the JSON to elevate and group all unique, non-null third_party_control_id values into a new
    comma-separated field 'third_party_control_ids', and rewrites 'third_party_controls' to only include seq and desc.
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for entry in data.get('third_parties', []):
        controls = entry.get('third_party_controls')
        if controls and isinstance(controls, list):
            control_ids = [c.get('third_party_control_id') for c in controls if c.get('third_party_control_id')]
            unique_ids = sorted(set(control_ids))
            entry['third_party_control_ids'] = ','.join(unique_ids) if unique_ids else None
            # Rebuild controls with only seq and desc, renumber seq if needed, and filter out instructional artifacts
            new_controls = []
            seq_counter = 1
            for c in controls:
                desc = c.get('third_party_control_desc')
                if desc is not None:
                    desc_stripped = str(desc).strip().lower()
                    if 'repeat for each control' in desc_stripped or desc_stripped.startswith('//'):
                        continue  # skip instructional artifacts
                    new_controls.append({
                        'third_party_control_seq': seq_counter,
                        'third_party_control_desc': desc
                    })
                    seq_counter += 1
            entry['third_party_controls'] = new_controls if new_controls else None
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logging.info(f"Elevated and grouped control IDs for all third parties in {json_path}.")

def calculate_common_so(entry, so_list):
    name = (entry.get('third_party_name') or '').strip().lower()
    return 'Yes' if any(name == so.strip().lower() for so in so_list) else 'No'

__all__ = ["extract_subservice_orgs"]

if __name__ == '__main__':
    extract_subservice_orgs()
    filter_third_parties_with_gpt()
    elevate_and_group_control_ids()
