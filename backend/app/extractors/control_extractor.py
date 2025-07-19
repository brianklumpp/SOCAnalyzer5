import os
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from .. import config
from ..gpt_client import gpt_extract
from difflib import SequenceMatcher
import requests
import time

# Use centralized config paths
SECTION_JSON_PATH = config.SECTION_JSON_PATH
PDF_TXT_PATH = config.PDF_TXT_PATH
OUTPUT_JSON_PATH = config.CONTROL_JSON_PATH
GPT_LOG_PATH = config.CONTROL_GPT_LOG_PATH

# Helper functions

def load_text_lines(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.readlines()


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_control_section(section_results):
    return next((s for s in section_results if s.get('topic') == 'Control_Descriptions'), None)


def extract_text_for_lines(txt_lines, start_line, end_line):
    return ''.join(txt_lines[start_line-1:end_line])


def line_based_chunking(txt_lines, start_line, end_line, lines_per_chunk=150):
    """
    Splits the section into chunks based on line numbers for predictable coverage.
    Returns a list of (chunk_text, chunk_start_line, chunk_end_line) tuples.
    """
    chunks = []
    current = start_line
    while current <= end_line:
        chunk_start = current
        chunk_end = min(current + lines_per_chunk - 1, end_line)
        chunk_text = ''.join(txt_lines[chunk_start-1:chunk_end])
        chunks.append((chunk_text, chunk_start, chunk_end))
        logging.info(f"[LINE CHUNKING] Chunk: start_line={chunk_start}, end_line={chunk_end}, num_lines={chunk_end-chunk_start+1}")
        current = chunk_end + 1
    return chunks


def process_chunks(chunks, txt_lines, start_line, end_line):
    all_json_records = []
    current_line = start_line
    for idx, chunk in enumerate(chunks):
        # Calculate the chunk's starting line relative to the full section
        chunk_start_line = current_line
        prompt = config.CONTROL_EXTRACTION_PROMPT.format(text=chunk, start_line=chunk_start_line)
        logging.debug(f"[CONTROL] Chunk {idx}: start_line={chunk_start_line}, end_line={end_line}, chunk_len={len(chunk)}, chunk_preview={chunk[:200]!r}")
        logging.info(f'Processing chunk {idx}: {chunk[:200]}...')
        response = gpt_extract(prompt, 'control_extractor')
        logging.info(f'CHUNK {idx} PROMPT:\n{prompt}')
        logging.info(f'CHUNK {idx} GPT response length: {len(response) if response else 0}')
        # Optionally, parse and update current_line if end_line is returned in response
        classified_segments = classify_text_segments(chunk)
        json_records = structure_json_records(classified_segments)
        all_json_records.extend(json_records)
        # For now, increment current_line by the number of lines in the chunk
        current_line += chunk.count('\n')
    return all_json_records


def write_json_output(data, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'controls': data}, f, ensure_ascii=False, indent=2)


def parse_breakpoints(response):
    breakpoints = []
    try:
        lines = response.split('\n')
        for line in lines:
            if 'Control Section Start' in line or 'Control Section End' in line:
                parts = line.split(':')
                if len(parts) > 1:
                    position_str = parts[-1].strip()
                    if position_str.isdigit():
                        position = int(position_str)
                        breakpoints.append(position)
                    else:
                        logging.warning(f'Non-numeric position found: {position_str}')
    except Exception as e:
        logging.error(f'Error parsing breakpoints: {e}')
    return breakpoints


def classify_text_segments(chunk):
    prompt = config.SEGMENT_CLASSIFICATION_PROMPT.format(text=chunk, context="SOC report control section")
    response = gpt_extract(prompt, 'control_extractor')
    if not response:
        logging.error('Empty GPT response for classification. Returning empty segments.')
        return []
    classified_segments = parse_classified_segments(response)
    if not classified_segments:
        logging.error('No classified segments found in GPT response. Returning empty segments.')
    return classified_segments


def parse_classified_segments(response):
    segments = []
    try:
        lines = response.split('\n')
        current_segment = {}
        for line in lines:
            if line.startswith('Control ID:'):
                if current_segment:
                    segments.append(current_segment)
                    current_segment = {}
                current_segment['type'] = 'control_id'
                current_segment['text'] = line.split(':', 1)[1].strip()
            elif line.startswith('Control Description:'):
                current_segment['type'] = 'control_description'
                current_segment['text'] = line.split(':', 1)[1].strip()
            elif line.startswith('Test Procedure:'):
                current_segment['type'] = 'test_procedure'
                current_segment['text'] = line.split(':', 1)[1].strip()
            elif line.startswith('Test Result:'):
                current_segment['type'] = 'test_result'
                current_segment['text'] = line.split(':', 1)[1].strip()
        if current_segment:
            segments.append(current_segment)
    except Exception as e:
        logging.error(f'Error parsing classified segments: {e}')
    return segments


def structure_json_records(classified_segments):
    json_records = []
    current_record = {}
    for segment in classified_segments:
        segment_type = segment.get('type')
        segment_text = segment.get('text')
        if segment_type == 'control_id':
            if current_record:
                json_records.append(current_record)
                current_record = {}
            current_record['control_id'] = segment_text
        elif segment_type == 'control_description':
            current_record['control_desc'] = segment_text
        elif segment_type == 'test_procedure':
            current_record['control_test'] = segment_text
        elif segment_type == 'test_result':
            current_record['control_test_results'] = segment_text
    if current_record:
        json_records.append(current_record)
    logging.info("Entering final JSON records logging.")
    logging.info(f"Final JSON records: {json_records}")
    logging.info("Exiting final JSON records logging.")
    return json_records


def extract_controls():
    """
    Main function to extract controls using the new strategic approach.
    """
    txt_lines = load_text_lines(PDF_TXT_PATH)
    section_results = load_json(SECTION_JSON_PATH)
    ctrl_section = find_control_section(section_results)
    if not ctrl_section:
        logging.error('No Control_Descriptions section found.')
        return None

    start_line, end_line = ctrl_section.get('start_line'), ctrl_section.get('end_line')
    if start_line is None or end_line is None:
        logging.error('Control section lines are not properly defined. start_line or end_line is None.')
        return None

    # Use line-based chunking for predictability
    chunks = line_based_chunking(txt_lines, start_line, end_line, lines_per_chunk=150)
    logging.info(f'Line-based chunking produced {len(chunks)} chunks.')

    tsc_criteria = getattr(config, 'TSC_CRITERIA', [])
    coso_criteria = getattr(config, 'COSO_2013_CRITERIA', [])
    logging.info(f"Loaded {len(tsc_criteria)} TSC criteria and {len(coso_criteria)} COSO criteria.")
    results = []
    bad_chunks = []
    def process_chunk(idx, chunk_tuple):
        chunk, chunk_start_line, chunk_end_line = chunk_tuple
        prompt = config.CONTROL_EXTRACTION_PROMPT.format(text=chunk, start_line=chunk_start_line)
        logging.info(f'[PROCESSING] Chunk {idx}: start_line={chunk_start_line}, end_line={chunk_end_line}, num_lines={chunk_end_line-chunk_start_line+1}')
        logging.info(f'CHUNK {idx} PROMPT:\n{prompt[:500]}')
        response = gpt_extract(prompt, 'control_extractor')
        with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
            gptlog.write(f'CHUNK {idx} PROMPT:\n{prompt}\nRESPONSE:\n{response}\n---\n')
        logging.debug(f'Chunk {idx} response: {response}')
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
            try:
                data = json.loads(clean_response)
            except Exception as e1:
                json_sub = extract_json(clean_response)
                try:
                    data = json.loads(json_sub)
                except Exception as e2:
                    repaired = json_sub
                    if not repaired.strip().endswith(']') and repaired.strip().startswith('['):
                        repaired = repaired.strip() + ']'
                    try:
                        data = json.loads(repaired)
                    except Exception as e3:
                        objs = re.findall(r'\{[^}]*\}', clean_response)
                        data = [json.loads(obj) for obj in objs if obj.strip().startswith('{')]
                        if not data:
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
                            bad_chunks.append(bad_chunk_info)
                            return []
            # Only add dicts or lists of dicts to results
            if isinstance(data, dict):
                return [data]
            elif isinstance(data, list):
                dicts_only = [item for item in data if isinstance(item, dict)]
                if len(dicts_only) < len(data):
                    logging.error(f"Non-dict items found in GPT response list for chunk {idx}: {data}")
                return dicts_only
            else:
                logging.error(f"Unexpected GPT response type for chunk {idx}: {type(data)} - {data}")
                return []
        except Exception as e:
            logging.error(f'Failed to parse GPT response for chunk {idx}: {response} | Error: {e}')
            return []
    logging.info(f'STARTING MULTI-THREADED EXTRACTION: {len(chunks)} chunks')
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_chunk, idx, chunk_tuple) for idx, chunk_tuple in enumerate(chunks)]
        for future in as_completed(futures):
            chunk_results = future.result()
            # Only extend with dicts
            if isinstance(chunk_results, list):
                results.extend([item for item in chunk_results if isinstance(item, dict)])
            elif isinstance(chunk_results, dict):
                results.append(chunk_results)
            else:
                logging.error(f"Unexpected result type from process_chunk: {type(chunk_results)} - {chunk_results}")
    logging.info(f'ALL CHUNKS PROCESSED. TOTAL CONTROLS EXTRACTED: {len(results)}')
    seq = 1
    for ctrl in results:
        if not isinstance(ctrl, dict):
            logging.error(f"Expected dict for control, got {type(ctrl)}: {ctrl}")
            continue
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
    results_sorted = deduplicate_controls(results)
    logging.info(f"Deduplicated controls: {len(results)} -> {len(results_sorted)}")
    controls_with_id = [c for c in results_sorted if c.get('control_id')]
    controls_no_id = [c for c in results_sorted if not c.get('control_id')]
    aligned_results = []
    for ctrl in controls_with_id:
        ctrl['control_status'] = 'complete'
        aligned_results.append(ctrl)
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
        likely_test = False
        for test_txt in control_tests_set:
            if frag_desc == test_txt:
                likely_test = True
                break
            if len(frag_desc) > 20 and len(test_txt) > 20:
                sim = SequenceMatcher(None, frag_desc, test_txt).ratio()
                if sim >= 0.9:
                    likely_test = True
                    break
        if likely_test:
            frag['control_status'] = 'partial - likely test language'
            aligned_results.append(frag)
            continue
        matches = [main for main in controls_with_id if frag_desc in (main.get('control_desc') or '')]
        if len(matches) == 1:
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
        frag['control_status'] = 'partial - no match'
        aligned_results.append(frag)
    results_sorted = sorted(aligned_results, key=control_id_sort_key)
    logging.info(f"Final sorted controls: {len(results_sorted)}")
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(results_sorted, f, ensure_ascii=False, indent=2)
    logging.info(f"Control extraction completed. Results written to {OUTPUT_JSON_PATH}")

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
    for crit in getattr(config, 'COSO_2013_CRITERIA', []):
        if crit['id'] == coso_id:
            return crit['component']
    return None


def deduplicate_controls(controls):
    seen_ids = set()
    seen_descs = set()
    deduped = []
    for ctrl in controls:
        if not isinstance(ctrl, dict):
            logging.error(f"Expected dict for control in deduplication, got {type(ctrl)}: {ctrl}")
            continue
        cid = ctrl.get('control_id')
        desc = (ctrl.get('control_desc') or '').strip()
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            deduped.append(ctrl)
        elif not cid and desc and desc not in seen_descs:
            seen_descs.add(desc)
            deduped.append(ctrl)
    return deduped


def control_id_sort_key(ctrl):
    cid = ctrl.get('control_id')
    return (cid is None or cid == '', str(cid))


def fuzzy_match(a, b):
    return SequenceMatcher(None, a, b).ratio()


def map_control_to_frameworks(control_desc, tsc_criteria, coso_criteria):
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


_embedding_cache = {}
def get_openai_embedding(text):
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        result = extract_controls()
        if result is not None:
            print("Control extraction completed successfully.")
        else:
            print("Control extraction failed or returned no results.")
    except Exception as e:
        print(f"Error running control extractor: {e}")
        import traceback
        traceback.print_exc() 