import os
import json
import logging
from app import config
from app.gpt_client import gpt_extract
import re
from difflib import SequenceMatcher
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

SECTION_JSON_PATH = os.path.join('data', 'json', 'section_results.json')
PDF_TXT_PATH = os.path.join('data', 'output', 'output.txt')
OUTPUT_JSON_PATH = os.path.join('data', 'json', 'cuec_result.json')
LOG_PATH = os.path.join('data', 'logs', 'cuec_extractor.log')
GPT_LOG_PATH = os.path.join('data', 'logs', 'cuec_gpt.log')

# Always start fresh for log files
with open(LOG_PATH, 'w', encoding='utf-8') as log_reset:
    log_reset.write('')
logging.basicConfig(filename=LOG_PATH, level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

with open(GPT_LOG_PATH, 'w', encoding='utf-8') as gptlog:
    gptlog.write('')  # Reset GPT log

CUEC_KEYWORDS = config.CUEC_KEYWORDS
CUEC_EXTRACTION_PROMPT = config.CUEC_EXTRACTION_PROMPT
OPENAI_EMBEDDING_MODEL = getattr(config, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-ada-002')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_EMBEDDING_URL = 'https://api.openai.com/v1/embeddings'

_embedding_cache = {}

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

def extract_text_for_pages_with_refs(txt_lines, page_numbers):
    result = []
    current_page = 1
    for line in txt_lines:
        if line.strip().startswith('=== PAGE '):
            try:
                current_page = int(line.strip().split()[2])
            except Exception:
                continue
        if current_page in page_numbers:
            result.append((line, current_page))
    return result

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

def levenshtein_distance(a, b):
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

def calculate_distance_from_cuec_keywords(desc):
    desc = (desc or '').lower()
    min_dist = 999
    desc_words = desc.split()
    for kw in CUEC_KEYWORDS:
        kw_words = kw.split()
        n = len(kw_words)
        # Slide a window of length n over the description words
        for i in range(len(desc_words) - n + 1):
            ngram = ' '.join(desc_words[i:i+n])
            dist = levenshtein_distance(kw, ngram)
            if dist < min_dist:
                min_dist = dist
    return min_dist

def extract_cuecs():
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
        chunk_size = getattr(config, 'SUBSERVICE_CHUNK_SIZE', 3000)
        overlap = getattr(config, 'TEXT_OVERLAP', 1000)
        chunks = chunk_text_with_overlap(text, chunk_size, overlap)
        chunk_line_refs = []
        char_count = 0
        for chunk in chunks:
            chunk_start = text.find(chunk)
            if chunk_start == -1:
                chunk_line = None
            else:
                char_count = 0
                chunk_line = 1
                for i, line in enumerate(txt_lines):
                    char_count += len(line)
                    if char_count >= chunk_start:
                        chunk_line = i + 1
                        break
            chunk_line_refs.append(chunk_line)
    else:
        start = desc_section['DOC_page_ref']
        end = desc_section['end_DOC_page_ref']
        pages = list(range(start, end + 1))
        text_with_refs = extract_text_for_pages_with_refs(txt_lines, pages)
        page_chunks = {}
        for line, page in text_with_refs:
            page_chunks.setdefault(page, []).append(line)
        chunk_size = getattr(config, 'SUBSERVICE_CHUNK_SIZE', 3000)
        overlap = getattr(config, 'TEXT_OVERLAP', 1000)
        chunks = []
        chunk_line_refs = []
        line_num = 1
        for page, lines in page_chunks.items():
            page_text = ''.join(lines)
            page_chunks_list = chunk_text_with_overlap(page_text, chunk_size, overlap)
            for chunk in page_chunks_list:
                chunks.append(chunk)
                chunk_line_refs.append(line_num)
                line_num += len(chunk.splitlines())
    cuec_results = []
    seq = 1
    tsc_criteria = getattr(config, 'TSC_CRITERIA', [])
    coso_criteria = getattr(config, 'COSO_2013_CRITERIA', [])
    # Load company names from company_result.json
    company_json_path = os.path.join('data', 'json', 'company_result.json')
    try:
        with open(company_json_path, 'r', encoding='utf-8') as f:
            company_info = json.load(f)
        company_names = []
        parent_company_names = []
        if 'company' in company_info and company_info['company']:
            company_names.append(company_info['company'])
        if 'parent_company' in company_info and company_info['parent_company']:
            parent_company_names.append(company_info['parent_company'])
        # Add common aliases
        company_names += ['the Company', 'the service organization', 'service organization']
        parent_company_names += ['the parent company']
    except Exception as e:
        logging.error(f"Failed to load company names from company_result.json: {e}")
        company_names = ['the Company', 'the service organization', 'service organization']
        parent_company_names = ['the parent company']
    def refers_to_company(text):
        if not text:
            return False
        text_lower = text.lower()
        # Only filter if the responsibility is explicitly assigned to the company
        for name in company_names:
            name_lower = name.lower()
            # Look for explicit responsibility assignment
            patterns = [
                f"{name_lower} is responsible for",
                f"{name_lower} must ",
                f"{name_lower} shall ",
                f"{name_lower} are responsible for",
                f"{name_lower} has responsibility for",
                f"{name_lower} is required to",
                f"{name_lower} must ensure",
                f"{name_lower} will ",
            ]
            for pat in patterns:
                if pat in text_lower:
                    return True
        return False
    def refers_to_parent_company(text):
        if not text:
            return False
        text_lower = text.lower()
        for name in parent_company_names:
            name_lower = name.lower()
            if name_lower in text_lower:
                return True
            if f"{name_lower} employees" in text_lower:
                return True
            if f"at {name_lower}" in text_lower:
                return True
        return False
    # Prepare company and parent company names for prompt
    company_names_str = ', '.join(company_names) if company_names else 'the company'
    parent_company_names_str = ', '.join(parent_company_names) if parent_company_names else 'the parent company'
    def process_chunk(idx, chunk, chunk_line_refs, seq, tsc_criteria, coso_criteria):
        # This is the body of your current for idx, chunk in enumerate(chunks): loop
        # Returns filtered_data, seq
        prompt = CUEC_EXTRACTION_PROMPT.format(
            text=chunk,
            company_names=company_names_str,
            parent_company_names=parent_company_names_str
        )
        response = gpt_extract(prompt)
        with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
            gptlog.write(f'CHUNK {idx} PROMPT:\n{prompt}\nRESPONSE:\n{response}\n---\n')
        logging.debug(f'Chunk {idx} response: {response}')
        if not response:
            return [], seq
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
            try:
                data = json.loads(clean_response)
            except Exception:
                json_sub = extract_json(clean_response)
                data = json.loads(json_sub)
            if isinstance(data, dict) and ('cuecs' in data or 'excluded' in data):
                cuecs = data.get('cuecs', [])
                excluded = data.get('excluded', [])
                if excluded:
                    for ex in excluded:
                        desc = ex.get('cuec_description', '')
                        reason = ex.get('reason', ex.get('cuec_exclusion_reason', ''))
                        logging.info(f"GPT excluded: desc={desc} reason={reason}")
                        with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
                            gptlog.write(f"GPT EXCLUDED: desc={desc} reason={reason}\n")
                data = cuecs
            filtered_data = []
            for cuec in data:
                desc = cuec.get('cuec_description', '')
                filtered_data.append(cuec)
                cuec['cuec_seq'] = seq
                cuec['cuec_distance_from_cuec_keywords'] = calculate_distance_from_cuec_keywords(desc)
                desc_snippet = ' '.join(desc.split()[:10])
                chunk_lines = chunk.splitlines()
                found_line = None
                for i, line in enumerate(chunk_lines):
                    if desc_snippet and desc_snippet.lower() in line.lower():
                        found_line = i + 1
                        break
                if found_line is not None and chunk_line_refs[idx] is not None:
                    cuec['cuec_line_ref'] = chunk_line_refs[idx] + found_line - 1
                else:
                    cuec['cuec_line_ref'] = chunk_line_refs[idx] if idx < len(chunk_line_refs) else None
                cuec.pop('cuec_page_ref', None)
                tsc_id, coso_id, tsc_sim, coso_sim = map_cuec_to_frameworks(cuec.get('cuec_description', ''), tsc_criteria, coso_criteria)
                # Always set both TSC and COSO IDs for output
                cuec['cuec_tsc_id'] = tsc_id
                cuec['cuec_coso_id'] = coso_id
                cuec['cuec_tsc_similarity'] = tsc_sim
                cuec['cuec_coso_similarity'] = coso_sim
                # Add closest framework field
                if tsc_sim > coso_sim:
                    cuec['cuec_closest_framework'] = 'TSC'
                elif coso_sim > tsc_sim:
                    cuec['cuec_closest_framework'] = 'COSO'
                elif tsc_sim == coso_sim and tsc_sim != -1:
                    cuec['cuec_closest_framework'] = 'Equal'
                else:
                    cuec['cuec_closest_framework'] = 'Undetermined'
                # Set framework_alignment fields to indicate the best match, but do not remove either ID
                if tsc_id and coso_id:
                    cuec['cuec_framework_alignment'] = 'TSC'
                    cuec['cuec_framework_alignment_id'] = tsc_id
                elif tsc_id:
                    cuec['cuec_framework_alignment'] = 'TSC'
                    cuec['cuec_framework_alignment_id'] = tsc_id
                elif coso_id:
                    cuec['cuec_framework_alignment'] = 'COSO'
                    cuec['cuec_framework_alignment_id'] = coso_id
                else:
                    cuec['cuec_framework_alignment'] = 'Undetermined'
                    cuec['cuec_framework_alignment_id'] = None
                conf = 0.3
                justification = [f"Base score: 0.3"]
                gpt_opinion = cuec.get('cuec_gpt_opinion', '').lower()
                if gpt_opinion == 'yes':
                    conf += 0.1
                    justification.append("+0.1: cuec_gpt_opinion is 'yes'")
                elif gpt_opinion == 'no':
                    conf -= 0.1
                    justification.append("-0.1: cuec_gpt_opinion is 'no'")
                if cuec['cuec_distance_from_cuec_keywords'] < 5:
                    conf += 0.1
                    justification.append(f"+0.1: cuec_distance_from_cuec_keywords < 5 (actual: {cuec['cuec_distance_from_cuec_keywords']})")
                desc_lower = (cuec.get('cuec_description', '') or '').lower()
                if any(kw in desc_lower for kw in CUEC_KEYWORDS):
                    conf += 0.2
                    justification.append("+0.2: CUEC keyword present in description")
                # Framework alignment check now includes cuec_framework_alignment_id
                if tsc_id or coso_id or cuec.get('cuec_framework_alignment_id'):
                    conf += 0.2
                    justification.append("+0.2: Framework alignment found (TSC, COSO, or other ID)")
                else:
                    conf -= 0.2
                    justification.append("-0.2: Framework alignment undetermined")
                cuec['cuec_confidence'] = round(conf, 3)
                cuec['cuec_confidence_justification'] = justification
                # Add percent confidence for TSC and COSO similarity
                cuec['cuec_tsc_confidence_pct'] = int(round(100 * (tsc_sim + 1) / 2)) if tsc_sim != -1 else None
                cuec['cuec_coso_confidence_pct'] = int(round(100 * (coso_sim + 1) / 2)) if coso_sim != -1 else None
                logging.info(f"CUEC seq={cuec['cuec_seq']} confidence scoring: {justification} final={cuec['cuec_confidence']} | GPT reasoning: {cuec.get('cuec_gpt_reasoning', None)}")
            return filtered_data, seq
        except Exception as e:
            logging.error(f'Failed to parse GPT response for chunk {idx}: {response} | Error: {e}')
            return [], seq
    # Multi-threaded chunk processing
    cuec_results = []
    seq = 1
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_chunk, idx, chunk, chunk_line_refs, seq, tsc_criteria, coso_criteria) for idx, chunk in enumerate(chunks)]
        for future in as_completed(futures):
            filtered_data, seq = future.result()
            cuec_results.extend(filtered_data)
    # DEBUG: Log initial cuec_results after chunk processing
    logging.info(f"DEBUG: cuec_results after chunk processing: {len(cuec_results)} items")
    # Filter out CUECs whose line_ref is not within a page or two of the majority (use mode instead of median)
    line_refs = [c.get('cuec_line_ref') for c in cuec_results if c.get('cuec_line_ref') is not None]
    logging.info(f"CUEC post-processing: line_refs={line_refs} (total={len(line_refs)})")
    # Bin-based mode calculation for cuec_line_ref
    BIN_SIZE = 40
    if line_refs:
        line_refs_sorted = sorted(line_refs)
        max_count = 0
        mode_center = None
        for i, ref in enumerate(line_refs_sorted):
            # Count how many refs are within BIN_SIZE of this ref
            count = sum(1 for r in line_refs_sorted if abs(r - ref) <= BIN_SIZE)
            if count > max_count:
                max_count = count
                # Set mode to the center of the window
                window = [r for r in line_refs_sorted if abs(r - ref) <= BIN_SIZE]
                mode_center = int(sum(window) / len(window)) if window else ref
        mode_line = mode_center if mode_center is not None else line_refs_sorted[len(line_refs_sorted)//2]
        logging.info(f"CUEC post-processing: bin_mode_line={mode_line} (bin size=+/-{BIN_SIZE}, max_count={max_count})")
        before_count = len(cuec_results)
        # Instead of filtering out, adjust confidence
        for c in cuec_results:
            if c.get('cuec_line_ref') is not None and abs(c['cuec_line_ref'] - mode_line) <= BIN_SIZE * 2:
                # Inside the bounds: increase confidence by 0.1
                old_conf = c.get('cuec_confidence', 0)
                c['cuec_confidence'] = round(old_conf + 0.1, 3)
                just = c.get('cuec_confidence_justification', [])
                if not isinstance(just, list):
                    just = [str(just)]
                just.append(f"+0.1: cuec_line_ref within ±{BIN_SIZE*2} of mode ({mode_line})")
                c['cuec_confidence_justification'] = just
            else:
                # Outside the bounds: reduce confidence by 0.2
                old_conf = c.get('cuec_confidence', 0)
                c['cuec_confidence'] = round(old_conf - 0.2, 3)
                just = c.get('cuec_confidence_justification', [])
                if not isinstance(just, list):
                    just = [str(just)]
                just.append(f"-0.2: cuec_line_ref outside ±{BIN_SIZE*2} of mode ({mode_line})")
                c['cuec_confidence_justification'] = just
        # Log the confidence adjustment
        logging.info(f"CUEC post-processing: confidence adjusted for all cuecs based on bin mode check")
    # DEBUG: Log cuec_results after mode/median filtering
    logging.info(f"DEBUG: cuec_results after mode/median filtering: {len(cuec_results)} items")
    # Consolidate and deduplicate with GPT in batches
    cuec_results = batch_consolidate_cuecs_with_gpt(cuec_results)
    # DEBUG: Log cuec_results after batch consolidation
    logging.info(f"DEBUG: cuec_results after batch_consolidate_cuecs_with_gpt: {len(cuec_results)} items")
    # --- POST-CONSOLIDATION: Re-map and re-attach all calculated fields for every CUEC ---
    tsc_criteria = getattr(config, 'TSC_CRITERIA', [])
    coso_criteria = getattr(config, 'COSO_2013_CRITERIA', [])
    for cuec in cuec_results:
        desc = cuec.get('cuec_description', '')
        # Always set both TSC and COSO IDs and similarities
        tsc_id, coso_id, tsc_sim, coso_sim = map_cuec_to_frameworks(desc, tsc_criteria, coso_criteria)
        cuec['cuec_tsc_id'] = tsc_id
        cuec['cuec_coso_id'] = coso_id
        cuec['cuec_tsc_similarity'] = tsc_sim
        cuec['cuec_coso_similarity'] = coso_sim
        cuec['cuec_tsc_confidence_pct'] = int(round(100 * (tsc_sim + 1) / 2)) if tsc_sim != -1 else None
        cuec['cuec_coso_confidence_pct'] = int(round(100 * (coso_sim + 1) / 2)) if coso_sim != -1 else None
        # Add closest framework field
        if tsc_sim > coso_sim:
            cuec['cuec_closest_framework'] = 'TSC'
        elif coso_sim > tsc_sim:
            cuec['cuec_closest_framework'] = 'COSO'
        elif tsc_sim == coso_sim and tsc_sim != -1:
            cuec['cuec_closest_framework'] = 'Equal'
        else:
            cuec['cuec_closest_framework'] = 'Undetermined'
        # Framework alignment fields for backward compatibility
        if tsc_id and coso_id:
            cuec['cuec_framework_alignment'] = 'TSC'
            cuec['cuec_framework_alignment_id'] = tsc_id
        elif tsc_id:
            cuec['cuec_framework_alignment'] = 'TSC'
            cuec['cuec_framework_alignment_id'] = tsc_id
        elif coso_id:
            cuec['cuec_framework_alignment'] = 'COSO'
            cuec['cuec_framework_alignment_id'] = coso_id
        else:
            cuec['cuec_framework_alignment'] = 'Undetermined'
            cuec['cuec_framework_alignment_id'] = None
        # Ensure every CUEC has cuec_confidence_justification
        if 'cuec_confidence_justification' not in cuec or not cuec['cuec_confidence_justification']:
            justification = [f"Base score: 0.1"]
            gpt_opinion = cuec.get('cuec_gpt_opinion', '').lower()
            if gpt_opinion == 'yes':
                justification.append("+0.1: cuec_gpt_opinion is 'yes'")
            elif gpt_opinion == 'no':
                justification.append("-0.2: cuec_gpt_opinion is 'no'")
            if cuec.get('cuec_distance_from_cuec_keywords', 999) < 5:
                justification.append(f"+0.1: cuec_distance_from_cuec_keywords < 5 (actual: {cuec.get('cuec_distance_from_cuec_keywords')})")
            desc_lower = (cuec.get('cuec_description', '') or '').lower()
            if any(kw in desc_lower for kw in CUEC_KEYWORDS):
                justification.append("+0.2: CUEC keyword present in description")
            # Framework alignment check now includes cuec_framework_alignment_id and general alignment
            if cuec.get('cuec_tsc_id') or cuec.get('cuec_coso_id') or cuec.get('cuec_framework_alignment_id'):
                justification.append("+0.2: Framework alignment found (TSC, COSO, or other ID)")
            else:
                justification.append("-0.1: Framework alignment undetermined")
            cuec['cuec_confidence_justification'] = justification
    # Sort by confidence descending, then by cuec_seq ascending
    cuec_results = sort_cuecs_by_confidence_and_seq(cuec_results)
    # DEBUG: Log cuec_results after sorting
    logging.info(f"DEBUG: cuec_results after sorting: {len(cuec_results)} items")
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump({'cuecs': cuec_results}, f, indent=2, ensure_ascii=False)
    logging.info(f'CUEC extraction result: {cuec_results}')

def batch_consolidate_cuecs_with_gpt(cuec_results, max_per_batch=5, max_rounds=5):
    """
    Iteratively consolidates CUECs in batches to avoid GPT input size limits.
    """
    import math
    from concurrent.futures import ThreadPoolExecutor, as_completed
    round_num = 1
    prev_count = -1
    current = cuec_results
    while len(current) > max_per_batch and round_num <= max_rounds and len(current) != prev_count:
        prev_count = len(current)
        batches = [current[i:i+max_per_batch] for i in range(0, len(current), max_per_batch)]
        consolidated = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(consolidate_cuecs_with_gpt, batch) for batch in batches]
            for future in as_completed(futures):
                result = future.result()
                consolidated.extend(result)
        current = consolidated
        round_num += 1
    # Final pass on all if still too many, or just return
    if len(current) > max_per_batch:
        current = consolidate_cuecs_with_gpt(current)
    return current

def sort_cuecs_by_confidence_and_seq(cuec_list):
    return sorted(cuec_list, key=lambda c: (-c.get('cuec_confidence', 0), c.get('cuec_seq', 0)))

def consolidate_cuecs_with_gpt(cuec_list, min_batch_size=1):
    """
    Consolidate and deduplicate CUECs using GPT, logging all prompts and responses.
    If parsing fails, recursively split the batch until it succeeds or reaches min_batch_size.
    """
    import json
    import logging
    from app import config
    from app.gpt_client import gpt_extract
    
    # Prepare prompt
    cuecs_json = json.dumps(cuec_list, ensure_ascii=False, indent=2)
    prompt = config.CUEC_CONSOLIDATION_PROMPT.format(cuecs=cuecs_json)
    
    # Log prompt
    with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
        gptlog.write(f"\n--- CUEC CONSOLIDATION PROMPT ---\n{prompt}\n")
    logging.info(f"Sending CUEC consolidation prompt to GPT. Batch size: {len(cuec_list)}")
    
    # Call GPT
    try:
        response = gpt_extract(prompt)
        if not response:
            raise ValueError("GPT returned no response")
        # Log response
        with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
            gptlog.write(f"\n--- CUEC CONSOLIDATION RESPONSE ---\n{response}\n")
        # Parse response
        data = json.loads(response)
        if not isinstance(data, list):
            raise ValueError("GPT did not return a list of CUECs")
        return data
    except Exception as e:
        logging.error(f"Failed to consolidate CUECs with GPT: {e}")
        with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
            gptlog.write(f"\n--- CUEC CONSOLIDATION ERROR ---\n{e}\n")
        # Recursive fallback: split batch if possible
        if len(cuec_list) > min_batch_size:
            mid = len(cuec_list) // 2
            left = consolidate_cuecs_with_gpt(cuec_list[:mid], min_batch_size)
            right = consolidate_cuecs_with_gpt(cuec_list[mid:], min_batch_size)
            return left + right
        # Return input unchanged if error and cannot split further
        return cuec_list

def get_openai_embedding(text):
    """
    Get embedding for a given text using OpenAI API. Caches results for efficiency.
    """
    global _embedding_cache
    if text in _embedding_cache:
        return _embedding_cache[text]
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json',
    }
    data = {
        'input': text,
        'model': OPENAI_EMBEDDING_MODEL,
    }
    for attempt in range(3):
        try:
            resp = requests.post(OPENAI_EMBEDDING_URL, headers=headers, json=data)
            resp.raise_for_status()
            embedding = resp.json()['data'][0]['embedding']
            _embedding_cache[text] = embedding
            return embedding
        except Exception as e:
            time.sleep(1 + attempt)
    raise RuntimeError(f'Failed to get embedding for text: {text}')

def cosine_similarity(vec1, vec2):
    import numpy as np  # type: ignore  # pylance: ignore-reportMissingImports
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))

def map_cuec_to_frameworks(cuec_desc, tsc_criteria, coso_criteria):
    cuec_emb = get_openai_embedding(cuec_desc)
    # TSC
    best_tsc_id = None
    best_tsc_sim = -1
    for crit in tsc_criteria:
        emb = get_openai_embedding(crit['description'])
        sim = cosine_similarity(cuec_emb, emb)
        if sim > best_tsc_sim:
            best_tsc_sim = sim
            best_tsc_id = crit['id']
    # COSO
    best_coso_id = None
    best_coso_sim = -1
    for crit in coso_criteria:
        emb = get_openai_embedding(crit['description'])
        sim = cosine_similarity(cuec_emb, emb)
        if sim > best_coso_sim:
            best_coso_sim = sim
            best_coso_id = crit['id']
    # Add debug logging for framework mapping
    logging.info(f"map_cuec_to_frameworks: desc='{cuec_desc[:80]}...' | best_tsc_id={best_tsc_id} (sim={best_tsc_sim}) | best_coso_id={best_coso_id} (sim={best_coso_sim})")
    return best_tsc_id, best_coso_id, best_tsc_sim, best_coso_sim

def main():
    extract_cuecs()

if __name__ == "__main__":
    main()
