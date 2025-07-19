
"""
Extractor for tested controls in the SOC report (Control_Descriptions section).
- Multi-threaded, chunked, and GPT-assisted extraction.
- Aligns controls to TSC and COSO frameworks, sections, and domains.
- Output: JSON with all required fields for each control.
"""


# --- All imports at the top (PEP8 best practice) ---
import os
import json
import logging
import time
import datetime
import requests
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from .. import config
    from ..gpt_client import gpt_extract
except Exception as import_err:
    print(f"[CONTROL_EXTRACTOR] Import error: {import_err}")
    raise


# Use centralized config paths
try:
    SECTION_JSON_PATH = config.SECTION_JSON_PATH
    PDF_TXT_PATH = config.PDF_TXT_PATH
    OUTPUT_JSON_PATH = config.CONTROL_JSON_PATH
    GPT_LOG_PATH = config.CONTROL_GPT_LOG_PATH
except Exception as config_err:
    print(f"[CONTROL_EXTRACTOR] Config error: {config_err}")
    logging.error(f"[CONTROL_EXTRACTOR] Config error: {config_err}")
    raise


# --- Logger configuration: ensure logs are always written ---
try:
    # Always create the log directory relative to project root
    log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../data/logs'))
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, 'control_extractor.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(log_file_path, encoding='utf-8', mode='a'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    print(f"[CONTROL_EXTRACTOR] Logger configured. Log file: {log_file_path}")
    logging.info(f"[CONTROL_EXTRACTOR] Logger configured. Log file: {log_file_path}")
    # Always start fresh for GPT log file
    os.makedirs(GPT_LOG_PATH.parent, exist_ok=True)
    with open(GPT_LOG_PATH, 'w', encoding='utf-8') as gptlog:
        gptlog.write('')
except Exception as log_err:
    print(f"[CONTROL_EXTRACTOR] Logger setup error: {log_err}")
    logging.error(f"[CONTROL_EXTRACTOR] Logger setup error: {log_err}")
    raise

# --- Helper functions (chunking, embedding, similarity, etc.) ---
def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_text_for_lines(txt_lines, start_line, end_line):
    return ''.join(txt_lines[start_line-1:end_line])

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

_embedding_cache = {}
def get_openai_embedding(text):
    """
    Get embedding for a given text using OpenAI API. Caches results for efficiency.
    """
    global _embedding_cache
    if text in _embedding_cache:
        return _embedding_cache[text]
    headers = {
        'Authorization': f'Bearer {os.getenv("OPENAI_API_KEY")}',
        'Content-Type': 'application/json',
    }
    data = {
        'input': text,
        'model': getattr(config, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-ada-002'),
    }
    for attempt in range(3):
        try:
            resp = requests.post('https://api.openai.com/v1/embeddings', headers=headers, json=data)
            resp.raise_for_status()
            embedding = resp.json()['data'][0]['embedding']
            _embedding_cache[text] = embedding
            return embedding
        except Exception as e:
            time.sleep(1 + attempt)
    raise RuntimeError(f'Failed to get embedding for text: {text}')

def cosine_similarity(vec1, vec2):
    import numpy as np
    v1 = np.array(vec1)
    v2_ = np.array(vec2)
    return float(np.dot(v1, v2_) / (np.linalg.norm(v1) * np.linalg.norm(v2_)))

def map_control_to_frameworks(control_desc, tsc_criteria, coso_criteria):
    import logging
    if not tsc_criteria:
        logging.error("TSC criteria list is empty! Cannot map control to TSC framework.")
    if not coso_criteria:
        logging.error("COSO criteria list is empty! Cannot map control to COSO framework.")
    try:
        cuec_emb = get_openai_embedding(control_desc)
    except Exception as e:
        logging.error(f"Failed to get embedding for control_desc: {control_desc[:80]}... Error: {e}")
        return None, None, -1, -1
    # TSC
    best_tsc_id = None
    best_tsc_sim = -1
    for crit in tsc_criteria:
        try:
            emb = get_openai_embedding(crit['description'])
            sim = cosine_similarity(cuec_emb, emb)
            if sim > best_tsc_sim:
                best_tsc_sim = sim
                best_tsc_id = crit['id']
        except Exception as e:
            logging.error(f"Failed to get embedding or similarity for TSC criteria: {crit.get('id', 'unknown')}. Error: {e}")
            continue
    # COSO
    best_coso_id = None
    best_coso_sim = -1
    for crit in coso_criteria:
        try:
            emb = get_openai_embedding(crit['description'])
            sim = cosine_similarity(cuec_emb, emb)
            if sim > best_coso_sim:
                best_coso_sim = sim
                best_coso_id = crit['id']
        except Exception as e:
            logging.error(f"Failed to get embedding or similarity for COSO criteria: {crit.get('id', 'unknown')}. Error: {e}")
            continue
    if best_tsc_id is None:
        logging.warning(f"No TSC match found for control: {control_desc[:80]}...")
    if best_coso_id is None:
        logging.warning(f"No COSO match found for control: {control_desc[:80]}...")
    return best_tsc_id, best_coso_id, best_tsc_sim, best_coso_sim

def get_tsc_section(tsc_id):
    for section, ids in getattr(config, 'control_tsc_sections', {}).items():
        if tsc_id in ids:
            return section
    return None

def get_coso_section(coso_id):
    for section, ids in getattr(config, 'control_coso_sections', {}).items():
        if coso_id in ids:
            return section
    return None

def get_tsc_domain(tsc_id):
    for domain, prefixes in getattr(config, 'control_tsc_domain', {}).items():
        for prefix in prefixes:
            if tsc_id and tsc_id.startswith(prefix):
                return domain
    return None

def get_coso_domain(coso_id):
    # For COSO, use the component/principle mapping
    for crit in getattr(config, 'COSO_2013_CRITERIA', []):
        if crit['id'] == coso_id:
            return crit['component']
    return None

# --- Main extraction logic ---
def extract_controls():
    section_results = load_json(SECTION_JSON_PATH)
    ctrl_section = next((s for s in section_results if s.get('topic') == 'Control_Descriptions'), None)
    if not ctrl_section:
        logging.error('No Control_Descriptions section found.')
        return None
    start_line = ctrl_section.get('line')
    end_line = ctrl_section.get('end_line')
    with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    logging.info(f'Loaded {len(txt_lines)} lines from {PDF_TXT_PATH}.')
    if start_line and end_line:
        text = extract_text_for_lines(txt_lines, start_line, end_line)
        logging.info(f'Extracted lines {start_line} to {end_line} (inclusive). Text length: {len(text)}. Preview: {text[:300]!r}')
    else:
        text = ''.join(txt_lines)
        logging.info(f'No section lines specified, using full text. Length: {len(text)}. Preview: {text[:300]!r}')
    # Cap chunk size for safety to avoid GPT truncation
    chunk_size = min(getattr(config, 'SUBSERVICE_CHUNK_SIZE', 3000), 1500)
    overlap = getattr(config, 'TEXT_OVERLAP', 1000)
    chunks = chunk_text_with_overlap(text, chunk_size, overlap)
    logging.info(f'Chunking text: chunk_size={chunk_size}, overlap={overlap}, total_chunks={len(chunks)}')
    for idx, chunk in enumerate(chunks):
        logging.info(f'CHUNK {idx} LENGTH: {len(chunk)}. PREVIEW: {chunk[:300]!r}')
    tsc_criteria = getattr(config, 'TSC_CRITERIA', [])
    coso_criteria = getattr(config, 'COSO_2013_CRITERIA', [])
    logging.info(f"Loaded {len(tsc_criteria)} TSC criteria and {len(coso_criteria)} COSO criteria.")
    results = []
    bad_chunks = []
    def process_chunk(idx, chunk):
        prompt = config.CONTROL_EXTRACTION_PROMPT.format(text=chunk)
        # Log the chunk and prompt
        logging.info(f'PROCESSING CHUNK {idx}:\nCHUNK TEXT (first 500 chars):\n{chunk[:500]}')
        logging.info(f'CHUNK {idx} PROMPT:\n{prompt}')
        response = gpt_extract(prompt)
        with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
            gptlog.write(f'CHUNK {idx} PROMPT:\n{prompt}\nRESPONSE:\n{response}\n---\n')
        logging.debug(f'Chunk {idx} response: {response}')
        # Log response length for truncation analysis
        logging.info(f'Chunk {idx} GPT response length: {len(response) if response else 0}')
        if not response:
            logging.warning(f'No response from GPT for chunk {idx}')
            return []
        try:
            clean_response = response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:]
            if clean_response.startswith('```'):
                clean_response = clean_response[3:]
            if clean_response.endswith('```'):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            import re
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
                            with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
                                gptlog.write(f"\n--- BAD CHUNK {idx} ---\nCHUNK TEXT (truncated):\n{chunk[:500]}\nGPT RESPONSE (truncated):\n{response[:1000]}\nERRORS: e1: {e1}; e2: {e2}; e3: {e3}\nRESPONSE LENGTH: {len(response) if response else 0}\nCHUNK SIZE: {len(chunk)}\nPROMPT LENGTH: {len(prompt)}\n")
                            # Add to bad_chunks for frontend flagging
                            bad_chunks.append(bad_chunk_info)
                            return []
            if isinstance(data, dict) and 'controls' in data:
                data = data['controls']
            logging.info(f'CHUNK {idx} EXTRACTED {len(data) if isinstance(data, list) else 0} CONTROLS')
            return data
        except Exception as e:
            logging.error(f'Failed to parse GPT response for chunk {idx}: {response} | Error: {e}')
            return []
    # Multi-threaded chunk processing
    logging.info(f'STARTING MULTI-THREADED EXTRACTION: {len(chunks)} chunks')
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_chunk, idx, chunk) for idx, chunk in enumerate(chunks)]
        for future in as_completed(futures):
            chunk_results = future.result()
            results.extend(chunk_results)
    logging.info(f'ALL CHUNKS PROCESSED. TOTAL CONTROLS EXTRACTED: {len(results)}')
    # Post-processing: align to frameworks, sections, domains, add calculated fields
    seq = 1
    for ctrl in results:
        desc = ctrl.get('control_desc', None)
        if not desc or not isinstance(desc, str) or not desc.strip():
            logging.warning(f"Skipping control with missing or empty control_desc: {ctrl}")
            ctrl['control_seq'] = None
            ctrl['control_tsc_id'] = None
            ctrl['control_coso_id'] = None
            ctrl['control_tsc_similarity'] = None
            ctrl['control_coso_similarity'] = None
            ctrl['control_tsc_confidence_pct'] = None
            ctrl['control_coso_confidence_pct'] = None
            ctrl['control_closest_framework'] = 'Undetermined'
            ctrl['control_tsc_section'] = None
            ctrl['control_coso_section'] = None
            ctrl['control_soc_domain'] = None
            continue
        tsc_id, coso_id, tsc_sim, coso_sim = map_control_to_frameworks(desc, tsc_criteria, coso_criteria)
        ctrl['control_seq'] = seq
        seq += 1
        ctrl['control_tsc_id'] = tsc_id
        ctrl['control_coso_id'] = coso_id
        ctrl['control_tsc_similarity'] = tsc_sim
        ctrl['control_coso_similarity'] = coso_sim
        ctrl['control_tsc_confidence_pct'] = int(round(100 * (tsc_sim + 1) / 2)) if tsc_sim != -1 else None
        ctrl['control_coso_confidence_pct'] = int(round(100 * (coso_sim + 1) / 2)) if coso_sim != -1 else None
        if tsc_sim > coso_sim:
            ctrl['control_closest_framework'] = 'TSC'
        elif coso_sim > tsc_sim:
            ctrl['control_closest_framework'] = 'COSO'
        elif tsc_sim == coso_sim and tsc_sim != -1:
            ctrl['control_closest_framework'] = 'Equal'
        else:
            ctrl['control_closest_framework'] = 'Undetermined'
        ctrl['control_tsc_section'] = get_tsc_section(tsc_id)
        ctrl['control_coso_section'] = get_coso_section(coso_id)
        ctrl['control_soc_domain'] = get_tsc_domain(tsc_id) or get_coso_domain(coso_id)
        logging.info(f'CONTROL {ctrl.get("control_seq")}: ID={ctrl.get("control_id")}, DESC={desc[:80]}, TSC_ID={tsc_id}, COSO_ID={coso_id}, TSC_SIM={tsc_sim}, COSO_SIM={coso_sim}')

    # --- Deduplicate controls by control_id and control_desc before consolidation ---
    def deduplicate_controls(controls):
        seen_ids = set()
        seen_descs = set()
        deduped = []
        for ctrl in controls:
            cid = ctrl.get('control_id')
            desc = (ctrl.get('control_desc') or '').strip()
            if cid and cid not in seen_ids:
                seen_ids.add(cid)
                deduped.append(ctrl)
            elif not cid and desc and desc not in seen_descs:
                seen_descs.add(desc)
                deduped.append(ctrl)
        return deduped

    results_sorted = deduplicate_controls(results)
    logging.info(f"Deduplicated controls: {len(results)} -> {len(results_sorted)}")


    # --- Local alignment/merging of controls without control_id ---

    # --- Improved partial fragment matching logic ---
    controls_with_id = [c for c in results_sorted if c.get('control_id')]
    controls_no_id = [c for c in results_sorted if not c.get('control_id')]
    aligned_results = []
    for ctrl in controls_with_id:
        ctrl['control_status'] = 'complete'
        aligned_results.append(ctrl)

    # Build a set of all control_test fields from controls_with_id for quick lookup
    control_tests_set = set()
    for main in controls_with_id:
        test_txt = (main.get('control_test') or '').strip()
        if test_txt:
            control_tests_set.add(test_txt)

    for frag in controls_no_id:
        frag_desc = (frag.get('control_desc') or '').strip()
        if not frag_desc:
            frag['control_status'] = 'partial - no match'
            aligned_results.append(frag)
            continue

        # New step: If the fragment's control_desc matches any control_test, mark as likely test language
        # Use exact match or high similarity (>=0.9)
        likely_test = False
        for test_txt in control_tests_set:
            if frag_desc == test_txt:
                likely_test = True
                break
            # Fuzzy match if not exact
            if len(frag_desc) > 20 and len(test_txt) > 20:
                sim = SequenceMatcher(None, frag_desc, test_txt).ratio()
                if sim >= 0.9:
                    likely_test = True
                    break
        if likely_test:
            frag['control_status'] = 'partial - likely test language'
            aligned_results.append(frag)
            continue

        # 1. Filter controls_with_id for those whose control_desc contains the fragment's control_desc
        matches = [main for main in controls_with_id if frag_desc in (main.get('control_desc') or '')]

        if len(matches) == 1:
            # Reconcile: fill in missing fields in the primary from the partial
            main = matches[0]
            updated = False
            for k, v in frag.items():
                if (k not in main or main[k] in (None, '', [])) and v not in (None, '', []):
                    main[k] = v
                    updated = True
            frag['control_status'] = f"partial - matched with {main.get('control_id')}"
            frag['merged_to_control_id'] = main.get('control_id')
            aligned_results.append(frag)
            continue

        # 2. If multiple matches, try to narrow by tsc/coso id
        if len(matches) > 1:
            tsc_id = frag.get('control_tsc_id')
            coso_id = frag.get('control_coso_id')
            narrowed = [m for m in matches if (not tsc_id or m.get('control_tsc_id') == tsc_id) and (not coso_id or m.get('control_coso_id') == coso_id)]
            if len(narrowed) == 1:
                main = narrowed[0]
                updated = False
                for k, v in frag.items():
                    if (k not in main or main[k] in (None, '', [])) and v not in (None, '', []):
                        main[k] = v
                        updated = True
                frag['control_status'] = f"partial - matched with {main.get('control_id')}"
                frag['merged_to_control_id'] = main.get('control_id')
                aligned_results.append(frag)
                continue

        # 3. If still ambiguous or no match, mark as no match
        frag['control_status'] = 'partial - no match'
        aligned_results.append(frag)

    # Sort results by control_id (None/empty last)
    def control_id_sort_key(ctrl):
        cid = ctrl.get('control_id')
        return (cid is None or cid == '', str(cid))
    results_sorted = sorted(aligned_results, key=control_id_sort_key)

    # --- POST-EXTRACTION ANALYSIS: Rescue Check for Bad Chunks ---
    import re
    def fuzzy_match(a, b):
        return SequenceMatcher(None, a, b).ratio()

    rescue_report = []
    if bad_chunks:

        recovered_controls = []
        for bad in bad_chunks:
            bad_descs = []
            try:
                matches = re.findall(r'"control_desc"\s*:\s*"([^\"]+)"', bad.get('chunk_text', ''))
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
                for good in results_sorted:
                    good_desc = good.get('control_desc', '')
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
                else:
                    rescue_report.append({
                        'bad_chunk_desc': bad_desc,
                        'rescue_type': 'unmatched',
                        'matched_desc': None,
                        'confidence_pct': int(round(fuzzy_score * 100))
                    })
                # Add high-confidence rescue if confidence >= 0.9
                if fuzzy_score >= 0.9 and fuzzy_best:
                    # Only add if not already present
                    if not any((c.get('control_desc', '').strip() == fuzzy_best.strip()) for c in results_sorted):
                        recovered_controls.append({
                            'control_desc': fuzzy_best,
                            'control_source': 'recovered_fuzzy',
                            'control_confidence': round(fuzzy_score, 3),
                            'control_confidence_justification': ['Recovered by fuzzy match with confidence {:.1f}%'.format(fuzzy_score*100)]
                        })
        # Add recovered controls to results_sorted
        if recovered_controls:
            existing_descs = set((c.get('control_desc','') or '').strip() for c in results_sorted)
            for rc in recovered_controls:
                if rc['control_desc'] and rc['control_desc'].strip() not in existing_descs:
                    results_sorted.append(rc)
                    existing_descs.add(rc['control_desc'].strip())

        logging.info("CONTROL POST-EXTRACTION RESCUE ANALYSIS:")
        for entry in rescue_report:
            logging.info(f"Bad chunk desc: {entry['bad_chunk_desc'][:80]}... | Rescue: {entry['rescue_type']} | Confidence: {entry['confidence_pct']}% | Matched: {entry['matched_desc'][:80] if entry['matched_desc'] else None}")

    # --- Ensure all required fields are present for every control ---
    REQUIRED_FIELDS = [
        'control_seq', 'control_id', 'control_desc', 'control_test', 'control_test_results',
        'control_page_ref', 'control_line_ref', 'control_gpt_opinion', 'control_gpt_reasoning',
        'control_tsc_id', 'control_coso_id', 'control_tsc_similarity', 'control_coso_similarity',
        'control_tsc_confidence_pct', 'control_coso_confidence_pct', 'control_closest_framework',
        'control_tsc_section', 'control_coso_section', 'control_soc_domain'
    ]
    for ctrl in results_sorted:
        for field in REQUIRED_FIELDS:
            if field not in ctrl:
                ctrl[field] = None

    output_obj = {'controls': results_sorted}
    if bad_chunks:
        output_obj['bad_chunks'] = bad_chunks
        output_obj['bad_chunk_rescue_report'] = rescue_report
        output_obj['bad_chunk_count'] = len(bad_chunks) # type: ignore
        output_obj['rescued_chunk_count'] = len([r for r in rescue_report if r.get('confidence_pct', 0) >= 90]) # type: ignore
        output_obj['unrecoverable_chunks'] = [r for r in rescue_report if r.get('rescue_type') == 'unmatched'] # type: ignore
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(output_obj, f, indent=2, ensure_ascii=False)
    logging.info(f'Control extraction result: {results_sorted}')

def batch_consolidate_controls_with_gpt(control_results, max_per_batch=5, max_rounds=5, bad_chunks=None):
    """
    Iteratively consolidates controls in batches to avoid GPT input size limits.
    If a batch fails consolidation, adds a bad_chunk entry for frontend flagging.
    """
    import math
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if bad_chunks is None:
        bad_chunks = []
    round_num = 1
    prev_count = -1
    current = control_results
    # Retry logic: reduce batch size if context error occurs
    min_batch_size = 1
    retry_batch_size = max_per_batch
    while True:
        try:
            round_num = 1
            prev_count = -1
            current = control_results
            while len(current) > retry_batch_size and round_num <= max_rounds and len(current) != prev_count:
                prev_count = len(current)
                batches = [current[i:i+retry_batch_size] for i in range(0, len(current), retry_batch_size)]
                consolidated = []
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(consolidate_controls_with_gpt, batch, min_batch_size, bad_chunks) for batch in batches]
                    for future, batch in zip(as_completed(futures), batches):
                        result = future.result()
                        if result == batch:
                            bad_chunks.append({
                                'chunk_index': None,
                                'chunk_text': json.dumps(batch, ensure_ascii=False)[:500],
                                'gpt_response': '',
                                'error': 'Failed to consolidate batch with GPT',
                                'response_length': 0,
                                'chunk_size': len(json.dumps(batch, ensure_ascii=False)),
                                'prompt_length': None,
                                'consolidation': True
                            })
                        consolidated.extend(result)
                current = consolidated
                round_num += 1
            if len(current) > retry_batch_size:
                result = consolidate_controls_with_gpt(current, min_batch_size, bad_chunks)
                if result == current:
                    bad_chunks.append({
                        'chunk_index': None,
                        'chunk_text': json.dumps(current, ensure_ascii=False)[:500],
                        'gpt_response': '',
                        'error': 'Failed to consolidate final batch with GPT',
                        'response_length': 0,
                        'chunk_size': len(json.dumps(current, ensure_ascii=False)),
                        'prompt_length': None,
                        'consolidation': True
                    })
                current = result
            return current
        except Exception as e:
            import logging
            if 'context_length_exceeded' in str(e) or 'maximum context length' in str(e):
                logging.error(f"Context length exceeded during consolidation. Reducing batch size from {retry_batch_size}.")
                if retry_batch_size > 1:
                    retry_batch_size = max(1, retry_batch_size // 2)
                    continue
            raise

def consolidate_controls_with_gpt(control_list, min_batch_size=1, bad_chunks=None):
    """
    Consolidate and deduplicate controls using GPT, logging all prompts and responses.
    If parsing fails, recursively split the batch until it succeeds or reaches min_batch_size.
    """
    import json
    import logging
    from .. import config
    if bad_chunks is None:
        bad_chunks = []
    controls_json = json.dumps(control_list, ensure_ascii=False, indent=2)
    logging.info(f"Consolidation batch: {len(control_list)} controls, {len(controls_json)} characters.")
    prompt = config.CONTROL_CONSOLIDATION_PROMPT.format(controls=controls_json)
    with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
        gptlog.write(f"\n--- CONTROL CONSOLIDATION PROMPT ---\n{prompt}\n")
    logging.info(f"Sending CONTROL consolidation prompt to GPT. Batch size: {len(control_list)}")
    try:
        response = gpt_extract(prompt)
        if not response:
            raise ValueError("GPT returned no response")
    except Exception as e:
        logging.error(f"Error during GPT extraction: {e}")
        with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
            gptlog.write(f"\n--- CONTROL CONSOLIDATION GPT ERROR ---\n{e}\n")
        bad_chunks.append({
            'chunk_index': None,
            'chunk_text': json.dumps(control_list, ensure_ascii=False)[:500],
            'gpt_response': '',
            'error': f'Consolidation GPT error: {e}',
            'response_length': 0,
            'chunk_size': len(json.dumps(control_list, ensure_ascii=False)),
            'prompt_length': len(prompt),
            'consolidation': True
        })
        return control_list
    with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
        gptlog.write(f"\n--- CONTROL CONSOLIDATION RESPONSE ---\n{response}\n")
    import re
    def remove_trailing_commas(json_str):
        # Remove trailing commas before } or ]
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
        return json_str
    try:
        clean_response = remove_trailing_commas(response)
        data = json.loads(clean_response)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return v
        raise ValueError("GPT did not return a list of controls")
    except Exception as e:
        array_match = re.search(r'(\[.*?\])', response, re.DOTALL)
        if array_match:
            json_sub = array_match.group(1)
            try:
                json_sub = remove_trailing_commas(json_sub)
                data = json.loads(json_sub)
                if isinstance(data, list):
                    return data
            except Exception as e2:
                repaired = json_sub
                if not repaired.strip().endswith(']'):
                    repaired = repaired.strip() + ']'
                try:
                    repaired = remove_trailing_commas(repaired)
                    data = json.loads(repaired)
                    if isinstance(data, list):
                        return data
                except Exception:
                    pass
        logging.error(f"Failed to parse GPT response as JSON array: {e}\nRaw response: {response}")
        with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
            gptlog.write(f"\n--- CONTROL CONSOLIDATION JSON ERROR ---\n{e}\nRAW RESPONSE:\n{response}\n")
        bad_chunks.append({
            'chunk_index': None,
            'chunk_text': json.dumps(control_list, ensure_ascii=False)[:500],
            'gpt_response': response[:1000],
            'error': f'Consolidation parse error: {e}',
            'response_length': len(response) if response else 0,
            'chunk_size': len(json.dumps(control_list, ensure_ascii=False)),
            'prompt_length': len(prompt),
            'consolidation': True
        })
    if len(control_list) > min_batch_size:
        mid = len(control_list) // 2
        left = consolidate_controls_with_gpt(control_list[:mid], min_batch_size, bad_chunks)
        right = consolidate_controls_with_gpt(control_list[mid:], min_batch_size, bad_chunks)
        return left + right
    return control_list

__all__ = ["extract_controls"]

# Only run extract_controls() if executed directly, not on import
if __name__ == "__main__":
    # Heartbeat: write to a file to prove script execution
    try:
        with open("data/logs/control_extractor_heartbeat.txt", "a", encoding="utf-8") as hb:
            import datetime
            hb.write(f"Heartbeat at {datetime.datetime.now().isoformat()}\n")
    except Exception as hb_err:
        pass
    try:
        print("[CONTROL_EXTRACTOR] Running extract_controls() due to __name__ == '__main__'.")
        logging.info("[CONTROL_EXTRACTOR] Running extract_controls() due to __name__ == '__main__'.")
        extract_controls()
    except Exception as main_err:
        # Write any exception to a file for debugging
        with open("data/logs/control_extractor_top_error.txt", "a", encoding="utf-8") as errf:
            import traceback
            errf.write(f"Exception at {datetime.datetime.now().isoformat()}:\n{traceback.format_exc()}\n")
