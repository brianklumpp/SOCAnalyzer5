"""
Extractor for tested controls in the SOC report (Control_Descriptions section).
- Multi-threaded, chunked, and GPT-assisted extraction.
- Aligns controls to TSC and COSO frameworks, sections, and domains.
- Output: JSON with all required fields for each control.
"""
import os
import json
import logging
from app import config
from app.gpt_client import gpt_extract
from difflib import SequenceMatcher
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

SECTION_JSON_PATH = os.path.join('data', 'json', 'section_results.json')
PDF_TXT_PATH = os.path.join('data', 'output', 'output.txt')
OUTPUT_JSON_PATH = os.path.join('data', 'json', 'control_result.json')
LOG_PATH = os.path.join('data', 'logs', 'control_extractor.log')
GPT_LOG_PATH = os.path.join('data', 'logs', 'control_gpt.log')

# Always start fresh for log files
with open(LOG_PATH, 'w', encoding='utf-8') as log_reset:
    log_reset.write('')
logging.basicConfig(filename=LOG_PATH, level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
with open(GPT_LOG_PATH, 'w', encoding='utf-8') as gptlog:
    gptlog.write('')

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
    cuec_emb = get_openai_embedding(control_desc)
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
    chunk_size = getattr(config, 'SUBSERVICE_CHUNK_SIZE', 3000)
    overlap = getattr(config, 'TEXT_OVERLAP', 1000)
    chunks = chunk_text_with_overlap(text, chunk_size, overlap)
    logging.info(f'Chunking text: chunk_size={chunk_size}, overlap={overlap}, total_chunks={len(chunks)}')
    for idx, chunk in enumerate(chunks):
        logging.info(f'CHUNK {idx} LENGTH: {len(chunk)}. PREVIEW: {chunk[:300]!r}')
    tsc_criteria = getattr(config, 'TSC_CRITERIA', [])
    coso_criteria = getattr(config, 'COSO_2013_CRITERIA', [])
    results = []
    def process_chunk(idx, chunk):
        prompt = config.CONTROL_EXTRACTION_PROMPT.format(text=chunk)
        # Log the chunk and prompt
        logging.info(f'PROCESSING CHUNK {idx}:\nCHUNK TEXT (first 500 chars):\n{chunk[:500]}')
        logging.info(f'CHUNK {idx} PROMPT:\n{prompt}')
        response = gpt_extract(prompt)
        with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
            gptlog.write(f'CHUNK {idx} PROMPT:\n{prompt}\nRESPONSE:\n{response}\n---\n')
        logging.debug(f'Chunk {idx} response: {response}')
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
            data = json.loads(clean_response)
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
    for i, ctrl in enumerate(results, 1):
        desc = ctrl.get('control_desc', '')
        tsc_id, coso_id, tsc_sim, coso_sim = map_control_to_frameworks(desc, tsc_criteria, coso_criteria)
        ctrl['control_seq'] = i
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
        logging.info(f'CONTROL {i}: ID={ctrl.get("control_id")}, DESC={desc[:80]}, TSC_ID={tsc_id}, COSO_ID={coso_id}, TSC_SIM={tsc_sim}, COSO_SIM={coso_sim}')
    # TODO: Batch consolidate and re-map calculated fields if needed
    # Sort results by control_id (None/empty last)
    def control_id_sort_key(ctrl):
        cid = ctrl.get('control_id')
        return (cid is None or cid == '', str(cid))
    results_sorted = sorted(results, key=control_id_sort_key)
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump({'controls': results_sorted}, f, indent=2, ensure_ascii=False)
    logging.info(f'Control extraction result: {results_sorted}')

if __name__ == "__main__":
    extract_controls()
