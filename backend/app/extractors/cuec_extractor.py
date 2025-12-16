"""Unified CUEC Extractor for SOC1 and SOC2 Reports

Extracts Complementary User Entity Controls (CUECs) from SOC reports.
Supports both SOC1 and SOC2 report types with appropriate keyword sets
and framework mappings.

Usage:
    from .cuec_extractor import extract_cuecs
    
    # SOC2 report
    extract_cuecs(report_type="SOC2")
    
    # SOC1 report  
    extract_cuecs(report_type="SOC1")
"""

# All imports at the top
import os
import json
import logging
import re
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any
from .. import config
from ..gpt_client import gpt_extract

# Use centralized config paths
SECTION_JSON_PATH = config.SECTION_JSON_PATH
PDF_TXT_PATH = config.PDF_TXT_PATH
OUTPUT_JSON_PATH = config.JSON_DIR / "cuec_result.json"
GPT_LOG_PATH = config.LOGS_DIR / "cuec_gpt.log"

# Configure logging to overwrite the log file each time the script runs
CUEC_EXTRACTOR_LOG_PATH = config.LOGS_DIR / "cuec_extractor.log"
logging.basicConfig(
    filename=str(CUEC_EXTRACTOR_LOG_PATH),
    filemode='w',  # Overwrite the log file
    level=logging.INFO,  # Set to INFO to reduce log verbosity
    format='%(asctime)s [CUEC_EXTRACTOR] %(levelname)s %(message)s',
)

logger = logging.getLogger(__name__)
# Always start fresh for GPT log file
os.makedirs(GPT_LOG_PATH.parent, exist_ok=True)
with open(GPT_LOG_PATH, 'w', encoding='utf-8') as gptlog:
    gptlog.write('')

# Extraction prompt (same for all report types)
CUEC_EXTRACTION_PROMPT = config.CUEC_EXTRACTION_PROMPT

# Removed: numpy, _embedding_cache, OPENAI_EMBEDDING_MODEL, OPENAI_EMBEDDING_URL
# Now using GPT-based framework mapping instead of embeddings

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

def calculate_distance_from_cuec_keywords(desc, cuec_keywords):
    desc = (desc or '').lower()
    min_dist = 999
    desc_words = desc.split()
    for kw in cuec_keywords:
        kw_words = kw.split()
        n = len(kw_words)
        # Slide a window of length n over the description words
        for i in range(len(desc_words) - n + 1):
            ngram = ' '.join(desc_words[i:i+n])
            dist = levenshtein_distance(kw, ngram)
            if dist < min_dist:
                min_dist = dist
    return min_dist

def extract_cuecs(report_type: str = "SOC2", job_id: Optional[str] = None, redis_client: Optional[Any] = None):
    """Unified CUEC extraction for SOC1 and SOC2 reports.
    
    Args:
        report_type: Report type ("SOC1", "SOC2", or "COMBINED"), defaults to "SOC2"
        
    Returns:
        None (writes results to config.CUEC_JSON_PATH)
    """
    # Reset output file at the start of extraction
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        f.write('[]')
    section_results = load_json(SECTION_JSON_PATH)
    desc_section = next((s for s in section_results if s.get('topic') == 'Description_of_System'), None)
    if not desc_section:
        logging.error('No Description_of_System section found.')
        return None
    start_line, end_line = desc_section.get('start_line'), desc_section.get('end_line')
    with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    chunk_line_refs = []
    chunks = []
    if desc_section:
        start_line = desc_section.get('start_line')
        end_line = desc_section.get('end_line')
        if start_line and end_line:
            text_with_refs = extract_text_for_lines(txt_lines, start_line, end_line)
            logging.info(f"[DEBUG] Extracted text length: {len(text_with_refs)} | Preview: {text_with_refs[:300]}")
        elif desc_section.get('DOC_page_ref') is not None and desc_section.get('end_DOC_page_ref') is not None:
            start = desc_section['DOC_page_ref']
            end = desc_section['end_DOC_page_ref']
            pages = list(range(start, end + 1))
            text_with_refs = extract_text_for_pages_with_refs(txt_lines, pages)
            logging.info(f"[DEBUG] Extracted text (by pages) length: {len(text_with_refs)} | Preview: {str(text_with_refs)[:300]}")
        else:
            logging.error('DOC_page_ref or end_DOC_page_ref is None for description section.')
    # Add chunking debug log
    if isinstance(text_with_refs, str):
        chunk_size = 1000
        overlap = 200
        logging.info(f"[DEBUG] Using chunk_size={chunk_size}, overlap={overlap} for CUEC extraction.")
        chunks = chunk_text_with_overlap(text_with_refs, chunk_size, overlap)
        logging.info(f"[DEBUG] Number of chunks created: {len(chunks)}")
    elif isinstance(text_with_refs, list):
        # If using page-based extraction, treat each page as a chunk
        chunks = [t[0] for t in text_with_refs]
        logging.info(f"[DEBUG] Number of page-based chunks created: {len(chunks)}")
    else:
        logging.error("[DEBUG] Unexpected type for text_with_refs.")
    logging.info("[DEBUG] Entering main chunk processing loop for CUEC extraction.")
    cuec_results = []
    bad_chunks = []
    seq = 1
    
    # Load frameworks dynamically based on report type
    from ..frameworks import get_available_frameworks
    
    # Select appropriate CUEC keywords based on report type
    cuec_keywords = config.CUEC_KEYWORDS_SOC1 if report_type == "SOC1" else config.CUEC_KEYWORDS
    logging.info(f"Using CUEC keywords for {report_type}: {cuec_keywords[:5]}...")
    
    try:
        available_frameworks = get_available_frameworks(report_type=report_type)
        logging.info(f"Loaded {len(available_frameworks)} frameworks for {report_type} CUEC mapping: {list(available_frameworks.keys())}")
    except Exception as e:
        logging.error(f"Failed to load frameworks: {e}, falling back to config TSC/COSO")
        available_frameworks = {
            "TSC": {"criteria": getattr(config, 'TSC_CRITERIA', [])},
            "COSO": {"criteria": getattr(config, 'COSO_2013_CRITERIA', [])}
        }
    
    # Load company names from company_result.json
    company_json_path = str(config.JSON_DIR / 'company_result.json')
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
    def process_chunk(idx, chunk, chunk_line_refs, seq, available_frameworks, cuec_keywords):
        # This is the body of your current for idx, chunk in enumerate(chunks): loop
        # Returns filtered_data, seq
        logging.debug(f"[CUEC] Chunk {idx}: start_line={start_line}, end_line={end_line}, chunk_len={len(chunk)}, chunk_preview={chunk[:200]!r}")
        prompt = CUEC_EXTRACTION_PROMPT.format(
            text=chunk,
            company_names=company_names_str,
            parent_company_names=parent_company_names_str
        )
        # Automated retry logic for truncated responses
        max_retries = 2
        min_chunk_size = 500
        cur_chunk = chunk
        response = None
        for attempt in range(max_retries + 1):
            response = gpt_extract(CUEC_EXTRACTION_PROMPT.format(
                text=cur_chunk,
                company_names=company_names_str,
                parent_company_names=parent_company_names_str
            ), 'cuec_extractor')
            # Log full prompt and response for debugging
            with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
                gptlog.write(f'CHUNK {idx} ATTEMPT {attempt+1} PROMPT:\n{prompt}\nRESPONSE:\n{response}\n---\n')
            logging.debug(f'Chunk {idx} attempt {attempt+1} response: {response}')
            logging.info(f'Chunk {idx} attempt {attempt+1} GPT response length: {len(response) if response else 0}')
            # Heuristic: consider response truncated if it ends with an open array/object or is very close to max length
            is_truncated = False
            if response:
                resp_strip = response.strip()
                if resp_strip.endswith(',') or resp_strip.endswith('[') or resp_strip.endswith('{') or resp_strip.endswith('...'):
                    is_truncated = True
                # Also, if response is very long (e.g., >3500 chars), likely truncated
                if len(resp_strip) > 3500:
                    is_truncated = True
            if not response or not is_truncated:
                break
            # If truncated and chunk is still large, split and retry
            if len(cur_chunk) > min_chunk_size:
                mid = len(cur_chunk) // 2
                # Try left half first, then right half in next retry
                cur_chunk = cur_chunk[:mid] if attempt == 0 else cur_chunk[mid:]
            else:
                break
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

            # Robust normalization similar to control_extractor_v2
            import re as _re
            def _normalize_json_like(text: str) -> str:
                t = text.replace('\u201c', '"').replace('\u201d', '"').replace('\u2019', "'")
                t = t.replace('“', '"').replace('”', '"').replace('’', "'")
                t = t.replace('`', '').replace('\u200b', '').replace('\ufeff', '')
                # Remove trailing commas before } or ]
                t = _re.sub(r',\s*([}\]])', r'\1', t)
                return t.strip()

            def _extract_bracket_matched_json(text: str) -> str:
                start = None
                opener = None
                for i, ch in enumerate(text):
                    if ch in '{[':
                        start = i
                        opener = ch
                        break
                if start is None:
                    return text
                closer = '}' if opener == '{' else ']'
                depth = 0
                in_string = False
                escape = False
                for j in range(start, len(text)):
                    c = text[j]
                    if in_string:
                        if escape:
                            escape = False
                        elif c == '\\':
                            escape = True
                        elif c == '"':
                            in_string = False
                        continue
                    else:
                        if c == '"':
                            in_string = True
                            continue
                        if c == opener:
                            depth += 1
                        elif c == closer:
                            depth -= 1
                            if depth == 0:
                                return text[start:j+1]
                return text[start:]

            clean_response = _normalize_json_like(clean_response)

            # Try direct parse
            try:
                data = json.loads(clean_response)
            except Exception as e1:
                # Extract a valid JSON object/array
                json_sub = _extract_bracket_matched_json(clean_response)
                try:
                    data = json.loads(json_sub)
                except Exception as e2:
                    # Try to repair unterminated array/object by trimming and closing
                    repaired = _re.sub(r',\s*([}\]])', r'\1', json_sub)
                    if repaired.strip().startswith('[') and not repaired.strip().endswith(']'):
                        repaired = repaired.strip() + ']'
                    if repaired.strip().startswith('{') and not repaired.strip().endswith('}'):
                        repaired = repaired.strip() + '}'
                    try:
                        data = json.loads(repaired)
                    except Exception as e3:
                        # Recover individual objects if possible
                        objs = _re.findall(r'\{[\s\S]*?\}', clean_response)
                        try:
                            data = [json.loads(obj) for obj in objs if obj.strip().startswith('{')]
                        except Exception:
                            data = []
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
                            logging.warning(f"Failed to parse GPT response as JSON. Raw response truncated: {response[:300]}")
                            with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
                                gptlog.write(f"\n--- BAD CHUNK {idx} ---\nCHUNK TEXT (truncated):\n{chunk[:500]}\nGPT RESPONSE (truncated):\n{response[:1000]}\nERRORS: e1: {e1}; e2: {e2}; e3: {e3}\nRESPONSE LENGTH: {len(response) if response else 0}\nCHUNK SIZE: {len(chunk)}\nPROMPT LENGTH: {len(prompt)}\n")
                            bad_chunks.append(bad_chunk_info)
                            return [], seq
            # Handle dict with cuecs/excluded
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
                desc_lower = (desc or '').lower()
                
                # Track if CUEC should be marked as low confidence (but still included)
                should_set_zero_confidence = False
                zero_conf_reasons = []
                
                # Filter 1: Company/parent company responsibilities
                if refers_to_company(desc) or refers_to_parent_company(desc):
                    should_set_zero_confidence = True
                    zero_conf_reasons.append("Refers to service organization, not user entity")
                    logging.info(f"Low confidence CUEC (company reference): '{desc[:80]}...'")
                
                # Filter 2: Incomplete fragments (too short, no ending punctuation)
                is_fragment = len(desc.strip()) < 30 or (
                    not desc.strip().endswith('.') and 
                    not desc.strip().endswith(';') and 
                    len(desc.strip()) < 80
                )
                if is_fragment:
                    should_set_zero_confidence = True
                    zero_conf_reasons.append("Text fragment, not a complete CUEC statement")
                    logging.info(f"Low confidence CUEC (fragment): '{desc[:80]}...'")
                
                # Filter 3: System description fragments (not user responsibilities)
                system_desc_indicators = [
                    'core capabilities', 'extends the power', 'configuration management',
                    'chef –', 'utilized to provision', 'data is captured', 
                    'maintained historically', 'internal audit function',
                    'is assigned the responsibility for', 'section ', 'identity as a service',
                    'the following:', 'includes the following'
                ]
                is_system_desc = any(indicator in desc_lower for indicator in system_desc_indicators)
                if is_system_desc:
                    should_set_zero_confidence = True
                    zero_conf_reasons.append("System description fragment, not a user entity control")
                    logging.info(f"Low confidence CUEC (system description): '{desc[:80]}...'")
                
                # Filter 4: Must have some CUEC indicators for low-base-confidence items
                has_cuec_keywords = any(kw in desc_lower for kw in [
                    'user entity', 'user entities', 'user organization', 'client', 'customer',
                    'responsible for', 'must ', 'shall ', 'should ', 'ensure', 'required to'
                ])
                # Allow through if GPT says yes, otherwise require keywords
                gpt_says_yes = cuec.get('cuec_gpt_opinion', '').lower() == 'yes'
                if not has_cuec_keywords and not gpt_says_yes:
                    should_set_zero_confidence = True
                    zero_conf_reasons.append("Lacks CUEC responsibility indicators")
                    logging.info(f"Low confidence CUEC (no indicators): '{desc[:80]}...'")
                
                # Passed all filters - add to results and process
                cuec['cuec_seq'] = seq
                cuec['cuec_distance_from_cuec_keywords'] = calculate_distance_from_cuec_keywords(desc, cuec_keywords)
                desc_snippet = ' '.join(desc.split()[:10])
                chunk_lines = chunk.splitlines()
                found_line = None
                for i, line in enumerate(chunk_lines):
                    if desc_snippet and desc_snippet.lower() in line.lower():
                        found_line = i + 1
                        break
                # Patch: Make line reference assignment non-fatal and index safe
                try:
                    if found_line is not None and idx < len(chunk_line_refs) and chunk_line_refs[idx] is not None:
                        cuec['cuec_line_ref'] = chunk_line_refs[idx] + found_line - 1
                    elif idx < len(chunk_line_refs):
                        cuec['cuec_line_ref'] = chunk_line_refs[idx]
                    else:
                        cuec['cuec_line_ref'] = None
                except Exception as e:
                    logging.error(f"[PATCH] Error assigning cuec_line_ref in process_chunk: {e}")
                    cuec['cuec_line_ref'] = None
                cuec.pop('cuec_page_ref', None)
                tsc_id, coso_id, tsc_sim, coso_sim, mapping_result = map_cuec_to_frameworks(cuec.get('cuec_description', ''), available_frameworks)
                
                # Store full framework mappings (new multi-framework support)
                cuec['framework_mappings'] = mapping_result.get('framework_mappings', {})
                cuec['primary_framework'] = mapping_result.get('primary_framework')
                cuec['primary_criterion_id'] = mapping_result.get('primary_criterion_id')
                cuec['primary_confidence'] = mapping_result.get('primary_confidence', 0.0)
                
                # Multi-match mapping arrays for backward compatibility
                cuec['cuec_tsc_mappings'] = mapping_result.get('framework_mappings', {}).get('TSC', [])
                cuec['cuec_coso_mappings'] = mapping_result.get('framework_mappings', {}).get('COSO', [])
                
                # Legacy single-match fields for backward compatibility
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
                # Check if CUEC should be marked as zero confidence
                if should_set_zero_confidence:
                    conf = 0.0
                    justification = ["Confidence set to 0: " + "; ".join(zero_conf_reasons)]
                else:
                    # Normal confidence calculation
                    conf = 0.3
                    justification = [f"Base score: 0.3"]
                    gpt_opinion = cuec.get('cuec_gpt_opinion', '').lower()
                    if gpt_opinion == 'yes':
                        conf += 0.2
                        justification.append("+0.2: cuec_gpt_opinion is 'yes'")
                    elif gpt_opinion == 'no':
                        conf -= 0.1
                        justification.append("-0.1: cuec_gpt_opinion is 'no'")
                    if cuec['cuec_distance_from_cuec_keywords'] < 5:
                        conf += 0.2
                        justification.append(f"+0.2: cuec_distance_from_cuec_keywords < 5 (actual: {cuec['cuec_distance_from_cuec_keywords']})")
                    desc_lower = (cuec.get('cuec_description', '') or '').lower()
                    if any(kw in desc_lower for kw in cuec_keywords):
                        conf += 0.2
                        justification.append("+0.2: CUEC keyword present in description")
                    # Framework alignment check now includes cuec_framework_alignment_id
                    if tsc_id or coso_id or cuec.get('cuec_framework_alignment_id'):
                        conf += 0.2
                        justification.append("+0.2: Framework alignment found (TSC, COSO, or other ID)")
                    else:
                        conf -= 0.2
                        justification.append("-0.2: Framework alignment undetermined")
                
                cuec['cuec_confidence'] = round(min(conf, 1.0), 3)
                cuec['cuec_confidence_justification'] = justification
                # Add percent confidence for TSC and COSO similarity
                cuec['cuec_tsc_confidence_pct'] = int(round(100 * (tsc_sim + 1) / 2)) if tsc_sim != -1 else None
                cuec['cuec_coso_confidence_pct'] = int(round(100 * (coso_sim + 1) / 2)) if coso_sim != -1 else None
                logging.info(f"CUEC seq={cuec['cuec_seq']} confidence scoring: {justification} final={cuec['cuec_confidence']} | GPT reasoning: {cuec.get('cuec_gpt_reasoning', None)}")
                
                # Finally add to filtered results
                filtered_data.append(cuec)
            return filtered_data, seq
        except Exception as e:
            logging.error(f'Failed to parse GPT response for chunk {idx}: {response} | Error: {e}')
            return [], seq
    # Multi-threaded chunk processing
    cuec_results = []
    seq = 1
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_chunk, idx, chunk, chunk_line_refs, seq, available_frameworks, cuec_keywords) for idx, chunk in enumerate(chunks)]
        for future in as_completed(futures):
            filtered_data, seq = future.result()
            for cuec in filtered_data:
                # Extract page number from cuec_line_ref using get_page_for_line
                try:
                    from ..pdf_handler import get_page_for_line
                    if cuec.get('cuec_line_ref') is not None:
                        page_num = get_page_for_line(txt_lines, cuec['cuec_line_ref'])
                        cuec['cuec_page_refs'] = [page_num] if page_num else []
                    else:
                        cuec['cuec_page_refs'] = []
                except Exception as e:
                    logging.warning(f"Failed to extract page ref for CUEC seq={cuec.get('cuec_seq')}: {e}")
                    cuec['cuec_page_refs'] = []
                # Patch: Make embedding failures non-fatal
                try:
                    desc = cuec.get('cuec_description', '')
                    tsc_id, coso_id, tsc_sim, coso_sim = None, None, -1, -1
                    try:
                        tsc_id, coso_id, tsc_sim, coso_sim, _ = map_cuec_to_frameworks(desc, available_frameworks)
                    except Exception as emb_err:
                        logging.error(f"[PATCH] Embedding error for CUEC: {desc[:80]}... | {emb_err}")
                    cuec['cuec_tsc_id'] = tsc_id
                    cuec['cuec_coso_id'] = coso_id
                    cuec['cuec_tsc_similarity'] = tsc_sim
                    cuec['cuec_coso_similarity'] = coso_sim
                    cuec['cuec_tsc_confidence_pct'] = int(round(100 * (tsc_sim + 1) / 2)) if tsc_sim != -1 else None
                    cuec['cuec_coso_confidence_pct'] = int(round(100 * (coso_sim + 1) / 2)) if coso_sim != -1 else None
                    if tsc_sim > coso_sim:
                        cuec['cuec_closest_framework'] = 'TSC'
                    elif coso_sim > tsc_sim:
                        cuec['cuec_closest_framework'] = 'COSO'
                    elif tsc_sim == coso_sim and tsc_sim != -1:
                        cuec['cuec_closest_framework'] = 'Equal'
                    else:
                        cuec['cuec_closest_framework'] = 'Undetermined'
                except Exception as e:
                    logging.error(f"[PATCH] Error in framework mapping for CUEC: {desc[:80]}... | {e}")
                    cuec['cuec_tsc_id'] = None
                    cuec['cuec_coso_id'] = None
                    cuec['cuec_tsc_similarity'] = None
                    cuec['cuec_coso_similarity'] = None
                    cuec['cuec_tsc_confidence_pct'] = None
                    cuec['cuec_coso_confidence_pct'] = None
                    cuec['cuec_closest_framework'] = 'Undetermined'
                # Patch: Make line reference assignment non-fatal
                try:
                    if 'cuec_line_ref' not in cuec or cuec['cuec_line_ref'] is None:
                        cuec['cuec_line_ref'] = None
                except Exception as e:
                    logging.error(f"[PATCH] Error assigning cuec_line_ref: {e}")
                    cuec['cuec_line_ref'] = None
                cuec_results.append(cuec)
                
                # Update Redis progress every 5 CUECs
                if job_id and redis_client and len(cuec_results) % 5 == 0:
                    try:
                        cuecs_count = len(cuec_results)
                        job_json = redis_client.get(f"job:{job_id}")
                        if job_json:
                            job_data = json.loads(job_json)
                            if "counters" not in job_data:
                                job_data["counters"] = {}
                            job_data["counters"]["cuecs_count"] = cuecs_count
                            
                            # Update status every 5 CUECs
                            if cuecs_count % 5 == 0:
                                job_data["status"] = f"Extracting CUECs: {cuecs_count} found..."
                            
                            redis_client.set(f"job:{job_id}", json.dumps(job_data), ex=86400)
                            logging.info(f"[PROGRESS] {cuecs_count} CUECs identified...")
                    except Exception as progress_err:
                        logging.warning(f"Could not update CUEC progress: {progress_err}")
                
                # Streaming write to JSON file
                with open(OUTPUT_JSON_PATH, 'a', encoding='utf-8') as f:
                    json.dump(cuec, f, ensure_ascii=False, indent=2)
                logging.info(f"[PATCH] Wrote CUEC seq={cuec.get('cuec_seq')} to {OUTPUT_JSON_PATH}")
    # Close the JSON array at the end
    with open(OUTPUT_JSON_PATH, 'a', encoding='utf-8') as f:
        f.write('\n]\n')

    # --- POST-EXTRACTION ANALYSIS: Rescue Check for Bad Chunks ---
    def fuzzy_match(a, b):
        # Use SequenceMatcher for fuzzy ratio (0-1)
        return SequenceMatcher(None, a, b).ratio()


    rescue_report = []
    output_txt_path = str(config.OUTPUT_DIR / "output.txt") if hasattr(config, 'OUTPUT_DIR') else os.path.join(os.path.dirname(OUTPUT_JSON_PATH), '..', 'output', 'output.txt')
    output_txt_lines = []
    output_txt = ''
    if os.path.exists(output_txt_path):
        with open(output_txt_path, 'r', encoding='utf-8') as f:
            output_txt = f.read()
            output_txt_lines = output_txt.splitlines()


    recovered_cuecs = []
    if bad_chunks:
        for bad in bad_chunks:
            bad_descs = []
            # Try to extract possible cuec_descriptions from the bad chunk text (if JSON-like)
            try:
                matches = re.findall(r'"cuec_description"\s*:\s*"([^"]+)"', bad.get('chunk_text', ''))
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
                for good in cuec_results:
                    good_desc = good.get('cuec_description', '')
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
                    continue
                elif fuzzy_score > 0.7:
                    rescue_report.append({
                        'bad_chunk_desc': bad_desc,
                        'rescue_type': 'fuzzy',
                        'matched_desc': fuzzy_best,
                        'confidence_pct': int(round(fuzzy_score * 100))
                    })
                    continue
                # Try to recover from output.txt as last resort (multi-line aware)
                output_txt_match = None
                output_txt_score = 0.0
                # Search for best match in output.txt using sliding window of up to 3 lines
                bad_desc_norm = bad_desc.strip().replace('\n', ' ')
                output_txt_lines_clean = [l.strip() for l in output_txt_lines]
                for i in range(len(output_txt_lines_clean)):
                    for window in range(1, 4):
                        candidate = ' '.join(output_txt_lines_clean[i:i+window]).replace('\n', ' ').strip()
                        if not candidate:
                            continue
                        # Exact match
                        if bad_desc_norm == candidate:
                            output_txt_match = candidate
                            output_txt_score = 1.0
                            break
                        # Fuzzy match
                        score = fuzzy_match(bad_desc_norm, candidate)
                        if score > output_txt_score:
                            output_txt_score = score
                            output_txt_match = candidate
                    if output_txt_score == 1.0:
                        break
                if output_txt_score > 0.7:
                    rescue_type = 'output_txt_fuzzy' if output_txt_score < 1.0 else 'output_txt_exact'
                    rescue_report.append({
                        'bad_chunk_desc': bad_desc,
                        'rescue_type': rescue_type,
                        'matched_desc': output_txt_match,
                        'confidence_pct': int(round(output_txt_score * 100))
                    })
                    # STRICT VALIDATION: Only recover if it looks like a legitimate CUEC
                    # Must be a complete sentence with CUEC-related keywords and reasonable length
                    if output_txt_score >= 0.95:  # Require 95%+ match, not 90%
                        matched_lower = (output_txt_match or '').lower()
                        # Must contain CUEC responsibility indicators
                        has_cuec_indicators = any(indicator in matched_lower for indicator in [
                            'responsible for', 'must ', 'shall ', 'should ', 'ensure', 
                            'required to', 'user entity', 'client ', 'customer ', 
                            'organization should', 'user organization'
                        ])
                        # Must be reasonably complete (50+ chars, ends with period or meaningful punctuation)
                        is_complete = len(output_txt_match) >= 50 and (
                            output_txt_match.strip().endswith('.') or 
                            output_txt_match.strip().endswith(';') or
                            len(output_txt_match) >= 100
                        )
                        # Must NOT be a fragment describing the service provider's system
                        is_system_description = any(fragment in matched_lower for fragment in [
                            'configuration management', 'chef –', 'utilized to provision',
                            'core capabilities', 'the system', 'internal audit function',
                            'is assigned the responsibility', 'maintained historically'
                        ])
                        
                        if has_cuec_indicators and is_complete and not is_system_description:
                            # Assign conservative confidence based on match score and content
                            base_conf = 0.3
                            if has_cuec_indicators:
                                base_conf += 0.2
                            if is_complete:
                                base_conf += 0.1
                            # Cap at 0.7 max for recovered items (they need manual review)
                            final_conf = min(base_conf, 0.7)
                            
                            recovered_cuecs.append({
                                'cuec_description': output_txt_match,
                                'cuec_source': 'recovered_from_output_txt',
                                'cuec_confidence': round(final_conf, 3),
                                'cuec_confidence_justification': [
                                    f'Recovered from output.txt with {output_txt_score*100:.1f}% fuzzy match',
                                    f'Base confidence: {final_conf:.1f} (capped at 0.7 for manual review)',
                                    '+0.2: Contains CUEC responsibility indicators' if has_cuec_indicators else '',
                                    '+0.1: Complete sentence structure' if is_complete else ''
                                ]
                            })
                        else:
                            logging.info(f"Rejected recovered CUEC fragment: '{output_txt_match[:80]}...' (indicators={has_cuec_indicators}, complete={is_complete}, system_desc={is_system_description})")
                else:
                    rescue_report.append({
                        'bad_chunk_desc': bad_desc,
                        'rescue_type': 'unmatched',
                        'matched_desc': None,
                        'confidence_pct': int(round(output_txt_score * 100))
                    })
        logging.info("CUEC POST-EXTRACTION RESCUE ANALYSIS:")
        for entry in rescue_report:
            logging.info(f"Bad chunk desc: {entry['bad_chunk_desc'][:80]}... | Rescue: {entry['rescue_type']} | Confidence: {entry['confidence_pct']}% | Matched: {entry['matched_desc'][:80] if entry['matched_desc'] else None}")

    # Add high-confidence recovered CUECs to output
    if recovered_cuecs:
        # Optionally, deduplicate by description
        existing_descs = set((c.get('cuec_description','') or '').strip() for c in cuec_results)
        for rc in recovered_cuecs:
            if rc['cuec_description'] and rc['cuec_description'].strip() not in existing_descs:
                cuec_results.append(rc)
                existing_descs.add(rc['cuec_description'].strip())


    # Minimal heuristic fallback (disabled by default – see config.ALLOW_REGEX_FALLBACKS)
    if not cuec_results and getattr(config, 'ALLOW_REGEX_FALLBACKS', False):
        try:
            full_text = ''
            try:
                with open(str(config.OUTPUT_DIR / 'output.txt'), 'r', encoding='utf-8') as tf:
                    full_text = tf.read()
            except Exception:
                pass
            if not full_text:
                with open(PDF_TXT_PATH, 'r', encoding='utf-8') as tf:
                    full_text = tf.read()
            # Find the UER/CUEC section
            m = re.search(r"(User Entity Responsibilities|Complementary User-?Entity Controls|Complementary User Entity Responsibilities)", full_text, re.IGNORECASE)
            if m:
                start_idx = m.start()
                tail = full_text[start_idx:start_idx + 15000]  # scan forward a reasonable window
                # Stop at likely next heading
                stop = re.search(r"\n\s*(Subservice Organization|Complementary Subservice|Management's Assertion|Independent Service Auditor)", tail, re.IGNORECASE)
                if stop:
                    tail = tail[:stop.start()]
                lines = [l.strip() for l in tail.splitlines() if l.strip()]
                candidates = []
                for l in lines:
                    base = l.lstrip('•-*\u2022').strip()
                    if len(base) < 20:
                        continue
                    low = base.lower()
                    if ('responsible for' in low) or ('must ' in low) or ('shall ' in low) or ('should ' in low) or ('ensure ' in low):
                        candidates.append(base)
                seq_f = 1
                for c in candidates:
                    cuec_results.append({
                        'cuec_description': c,
                        'cuec_seq': seq_f,
                        'cuec_confidence': 0.5,
                        'cuec_confidence_justification': ['+0.5: heuristic from UER section; GPT returned no CUECs'],
                        'cuec_source': 'heuristic_fallback',
                        'cuec_tsc_id': None,
                        'cuec_coso_id': None,
                        'cuec_tsc_similarity': -1,
                        'cuec_coso_similarity': -1,
                        'cuec_closest_framework': 'Undetermined',
                        'cuec_tsc_confidence_pct': None,
                        'cuec_coso_confidence_pct': None,
                        'cuec_line_ref': None,
                    })
                    seq_f += 1
        except Exception as _e:
            logging.error(f"[FALLBACK] CUEC heuristic fallback failed: {_e}")

    # Generate PDF snippets for PDF viewer search (if enabled)
    if config.ENABLE_PDF_SNIPPETS:
        for cuec in cuec_results:
            text = cuec.get('cuec_description', '') or cuec.get('text', '')
            if text:
                # Simple 150-char truncation with whitespace cleanup
                snippet = ' '.join(text.split())[:150]
                if len(' '.join(text.split())) > 150:
                    snippet += '...'
                cuec['pdf_snippet'] = snippet
        logging.info(f"Generated PDF snippets for {sum(1 for c in cuec_results if 'pdf_snippet' in c)} CUECs")
    
    output_obj = {'cuecs': cuec_results}
    if bad_chunks:
        output_obj['bad_chunks'] = bad_chunks
        output_obj['bad_chunk_rescue_report'] = rescue_report
        output_obj['bad_chunk_count'] = len(bad_chunks)  # type: ignore  # pylance: ignore
        output_obj['rescued_chunk_count'] = len([r for r in rescue_report if r.get('confidence_pct', 0) >= 90])  # type: ignore  # pylance: ignore
        output_obj['unrecoverable_chunks'] = [r for r in rescue_report if r.get('rescue_type') == 'unmatched']  # type: ignore  # pylance: ignore
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(output_obj, f, indent=2, ensure_ascii=False)
    logging.info(f'CUEC extraction result: {cuec_results}')

    # --- Post-extraction analysis: Check if CUECs from bad chunks were rescued by overlap ---
    def analyze_bad_chunks_coverage(cuec_results, bad_chunks):
        print("\n=== CUEC Bad Chunk Rescue Analysis ===")
        # Build set of all successful CUEC descriptions (lowercased, stripped)
        successful_descs = set((c.get('cuec_description', '') or '').strip().lower() for c in cuec_results if c.get('cuec_description'))
        # For fuzzy matching, keep a list
        successful_descs_list = [(c.get('cuec_description', ''), c) for c in cuec_results if c.get('cuec_description')]
        from difflib import SequenceMatcher
        for idx, bad in enumerate(bad_chunks):
            chunk_text = bad.get('chunk_text', '')
            print(f"\n--- Bad Chunk {idx} ---")
            print(f"Chunk index: {bad.get('chunk_index')}")
            print(f"Error: {bad.get('error')}")
            # Heuristic: try to extract possible CUEC descriptions from the chunk text (look for quoted lines, or lines with 'responsible', etc.)
            possible_cuecs = []
            for line in chunk_text.split('\n'):
                line_strip = line.strip()
                if not line_strip:
                    continue
                # Look for lines that look like CUEC descriptions
                if 'responsible' in line_strip.lower() or 'must' in line_strip.lower() or 'required' in line_strip.lower() or 'ensure' in line_strip.lower():
                    possible_cuecs.append(line_strip)
                # Or lines in quotes
                elif line_strip.startswith('"') and line_strip.endswith('"'):
                    possible_cuecs.append(line_strip.strip('"'))
            if not possible_cuecs:
                print("No candidate CUEC descriptions found in bad chunk text.")
                continue
            for cuec_desc in possible_cuecs:
                cuec_desc_norm = cuec_desc.strip().lower()
                found_exact = cuec_desc_norm in successful_descs
                if found_exact:
                    print(f"[EXACT MATCH] CUEC rescued: '{cuec_desc}'")
                else:
                    # Fuzzy match: find best match in successful_descs_list
                    best_score = 0.0
                    best_match = None
                    for desc, c in successful_descs_list:
                        score = SequenceMatcher(None, cuec_desc_norm, desc.strip().lower()).ratio()
                        if score > best_score:
                            best_score = score
                            best_match = desc
                    if best_score > 0.7:
                        print(f"[FUZZY MATCH] CUEC rescued: '{cuec_desc}' ~ '{best_match}' (confidence: {int(best_score*100)}%)")
                    else:
                        print(f"[NOT RESCUED] CUEC not found: '{cuec_desc}' (best fuzzy match: '{best_match}', confidence: {int(best_score*100)}%)")
        print("\n=== End of Rescue Analysis ===\n")

    if bad_chunks:
        analyze_bad_chunks_coverage(cuec_results, bad_chunks)

def batch_consolidate_cuecs_with_gpt(cuec_results, max_per_batch=5, max_rounds=5, bad_chunks=None):
    """
    Iteratively consolidates CUECs in batches to avoid GPT input size limits.
    If a batch fails consolidation, adds a bad_chunk entry for frontend flagging.
    """
    if bad_chunks is None:
        bad_chunks = []
    round_num = 1
    prev_count = -1
    current = cuec_results
    while len(current) > max_per_batch and round_num <= max_rounds and len(current) != prev_count:
        prev_count = len(current)
        batches = [current[i:i+max_per_batch] for i in range(0, len(current), max_per_batch)]
        consolidated = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(consolidate_cuecs_with_gpt, batch, 1, bad_chunks) for batch in batches]
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
    if len(current) > max_per_batch:
        result = consolidate_cuecs_with_gpt(current, 1, bad_chunks)
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

def sort_cuecs_by_confidence_and_seq(cuec_list):
    return sorted(cuec_list, key=lambda c: (-c.get('cuec_confidence', 0), c.get('cuec_seq', 0)))

def consolidate_cuecs_with_gpt(cuec_list, min_batch_size=1, bad_chunks=None):
    """
    Consolidate and deduplicate CUECs using GPT, logging all prompts and responses.
    If parsing fails, recursively split the batch until it succeeds or reaches min_batch_size.
    """
    if bad_chunks is None:
        bad_chunks = []
    cuecs_json = json.dumps(cuec_list, ensure_ascii=False, indent=2)
    prompt = config.CUEC_CONSOLIDATION_PROMPT.format(cuecs=cuecs_json)
    with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
        gptlog.write(f"\n--- CUEC CONSOLIDATION PROMPT ---\n{prompt}\n")
    logging.info(f"Sending CUEC consolidation prompt to GPT. Batch size: {len(cuec_list)}")
    try:
        response = gpt_extract(prompt, 'cuec_extractor')
        if not response:
            raise ValueError("GPT returned no response")
    except Exception as e:
        logging.error(f"Error during GPT extraction: {e}")
        with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
            gptlog.write(f"\n--- CUEC CONSOLIDATION GPT ERROR ---\n{e}\n")
        bad_chunks.append({
            'chunk_index': None,
            'chunk_text': json.dumps(cuec_list, ensure_ascii=False)[:500],
            'gpt_response': '',
            'error': f'Consolidation GPT error: {e}',
            'response_length': 0,
            'chunk_size': len(json.dumps(cuec_list, ensure_ascii=False)),
            'prompt_length': len(prompt),
            'consolidation': True
        })
        return cuec_list
    with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
        gptlog.write(f"\n--- CUEC CONSOLIDATION RESPONSE ---\n{response}\n")
    try:
        data = json.loads(response)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return v
        raise ValueError("GPT did not return a list of CUECs")
    except Exception as e:
        array_match = re.search(r'(\[.*?\])', response, re.DOTALL)
        if array_match:
            json_sub = array_match.group(1)
            try:
                data = json.loads(json_sub)
                if isinstance(data, list):
                    return data
            except Exception as e2:
                repaired = json_sub
                if not repaired.strip().endswith(']'):
                    repaired = repaired.strip() + ']'
                try:
                    data = json.loads(repaired)
                    if isinstance(data, list):
                        return data
                except Exception:
                    pass
        logging.error(f"Failed to parse GPT response as JSON array: {e}\nRaw response: {response}")
        with open(GPT_LOG_PATH, 'a', encoding='utf-8') as gptlog:
            gptlog.write(f"\n--- CUEC CONSOLIDATION JSON ERROR ---\n{e}\nRAW RESPONSE:\n{response}\n")
        bad_chunks.append({
            'chunk_index': None,
            'chunk_text': json.dumps(cuec_list, ensure_ascii=False)[:500],
            'gpt_response': response[:1000],
            'error': f'Consolidation parse error: {e}',
            'response_length': len(response) if response else 0,
            'chunk_size': len(json.dumps(cuec_list, ensure_ascii=False)),
            'prompt_length': len(prompt),
            'consolidation': True
        })
    if len(cuec_list) > min_batch_size:
        mid = len(cuec_list) // 2
        left = consolidate_cuecs_with_gpt(cuec_list[:mid], min_batch_size, bad_chunks)
        right = consolidate_cuecs_with_gpt(cuec_list[mid:], min_batch_size, bad_chunks)
        return left + right
    return cuec_list

# --- Removed embedding functions (replaced with GPT-based classification) ---
# Previously: get_openai_embedding(), cosine_similarity(), _embedding_cache
# Now using GPT direct reasoning for framework mapping

def map_cuec_to_frameworks(cuec_desc, available_frameworks):
    """
    Map a CUEC description to best-matching framework criteria using new dynamic mapper.
    
    Args:
        cuec_desc: CUEC description text
        available_frameworks: Dict from get_available_frameworks()
        
    Returns: (best_tsc_id, best_coso_id, confidence_tsc, confidence_coso)
             Note: For backward compatibility, returns TSC/COSO as primary matches
    """
    from ..frameworks import map_cuec_to_frameworks_dynamic
    
    if not available_frameworks:
        logging.warning("No frameworks available for CUEC mapping")
        return None, None, -1, -1
    
    try:
        # Use new dynamic mapper
        result = map_cuec_to_frameworks_dynamic(
            cuec_desc=cuec_desc,
            cuec_id="CUEC",
            available_frameworks=available_frameworks,
            top_k=5
        )
        
        # Extract TSC and COSO matches for backward compatibility
        tsc_matches = result.get("framework_mappings", {}).get("TSC", [])
        coso_matches = result.get("framework_mappings", {}).get("COSO", [])
        
        best_tsc_id = tsc_matches[0].get("id") if tsc_matches else None
        tsc_conf = tsc_matches[0].get("confidence", 0.0) if tsc_matches else -1
        
        best_coso_id = coso_matches[0].get("id") if coso_matches else None
        coso_conf = coso_matches[0].get("confidence", 0.0) if coso_matches else -1
        
        logging.info(f"map_cuec_to_frameworks: desc='{cuec_desc[:80]}...' | best_tsc_id={best_tsc_id} (conf={tsc_conf}) | best_coso_id={best_coso_id} (conf={coso_conf})")
        
        # Return full result plus legacy format
        return best_tsc_id, best_coso_id, tsc_conf, coso_conf, result
        
    except Exception as e:
        logging.error(f"Dynamic CUEC framework mapping failed: {e}", exc_info=True)
        return None, None, -1, -1, {}

def main():
    extract_cuecs()

if __name__ == "__main__":
    main()

__all__ = ["extract_cuecs"]
