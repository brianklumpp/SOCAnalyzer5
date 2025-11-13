# control_extractor_v2.py

"""
Enhanced extractor for tested controls in SOC reports using GPT and adaptive techniques.
- Implements dynamic chunking and classification of text segments.
- Uses feedback mechanisms and heuristic rules for improved accuracy.
- Outputs structured JSON records for each control section.
- ADDED: Hang prevention safeguards for non-control content
"""

import os
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..gpt_client import gpt_extract
import re
from typing import Dict, Any, Optional

try:
    from .. import config
except Exception as import_err:
    print(f"[CONTROL_EXTRACTOR_V2] Import error: {import_err}")
    raise

# Use centralized config paths
try:
    SECTION_JSON_PATH = config.SECTION_JSON_PATH
    PDF_TXT_PATH = config.PDF_TXT_PATH
    OUTPUT_JSON_PATH = config.CONTROL_JSON_PATH
    GPT_LOG_PATH = config.CONTROL_GPT_LOG_PATH
except Exception as config_err:
    print(f"[CONTROL_EXTRACTOR_V2] Config error: {config_err}")
    logging.error(f"[CONTROL_EXTRACTOR_V2] Config error: {config_err}")
    raise

# Configure logging to overwrite the log file each time the script runs
log_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'logs', 'control_extractor_v2.log')
logging.basicConfig(
    filename=log_path,
    filemode='w',  # Overwrite the log file
    level=logging.INFO,  # Set to INFO to reduce log verbosity
    format='%(asctime)s [CONTROL_EXTRACTOR_V2] %(message)s',
)

# SAFEGUARD: Pattern detection for non-control content
MAPPING_TABLE_INDICATORS = [
    r'CC\.\d+\.\d+.*The entity.*\..*[A-Z]{2,3}\.[0-9]',  # TSC criteria mapping
    r'Criteria.*Criteria Description.*Supporting Control',  # Table headers
    r'^[A-Z]{1,3}\s*\d+\.\d+.*\s+.*\s+[A-Z]{2,3}-[0-9]',  # Mapping table rows
    r'Trust.*Service.*Criteria.*Mapped',  # Section headers
    r'COSO.*Framework.*Mapped',
    r'^[A-Z]{1,3}\s*\d+\.\d+.*demonstrates.*commitment',  # Standard criteria text
]

## Removed: infer_deviation_fields (heuristic deviation detection)

# SAFEGUARD: Use configuration for processing limits
def get_safeguard_settings():
    """Get hang prevention settings from config"""
    return {
        'enabled': getattr(config, 'CONTROL_HANG_PREVENTION_ENABLED', True),
        'max_minutes': getattr(config, 'CONTROL_MAX_PROCESSING_MINUTES', 30),
        'max_failures': getattr(config, 'CONTROL_MAX_CONSECUTIVE_FAILURES', 10),
        'detect_non_control': getattr(config, 'CONTROL_DETECT_NON_CONTROL_CONTENT', True)
    }

def detect_non_control_content(text_chunk):
    """
    Detect if text chunk contains mapping tables or other non-control content
    Returns: (is_non_control, reason)
    """
    text_sample = text_chunk[:2000]  # Check first 2000 chars
    
    for pattern in MAPPING_TABLE_INDICATORS:
        if re.search(pattern, text_sample, re.IGNORECASE | re.MULTILINE):
            return True, f"Detected mapping table pattern: {pattern}"
    
    # Check for high density of criteria codes (CC.x.x, A.x.x patterns)
    criteria_matches = re.findall(r'\b[A-Z]{1,3}\.\d+\.\d+\b', text_sample)
    if len(criteria_matches) > 5:  # More than 5 criteria codes in small sample
        return True, f"High density of criteria codes: {len(criteria_matches)} found"
    
    # Check for table-like structure with consistent formatting
    lines = text_sample.split('\n')
    short_lines = [line for line in lines if len(line.strip()) > 10 and len(line.strip()) < 100]
    if len(short_lines) > 10:  # Many short structured lines suggests tables
        return True, f"Table-like structure detected: {len(short_lines)} structured lines"
    
    return False, None

# Dynamic chunking function

def dynamic_chunking(text, initial_chunk_size=3000):
    """Use GPT (optimized prompt) to identify logical breakpoints via JSON array of offsets.

    Returns list of text chunks; falls back to naive split if GPT output unusable.
    """
    chunk = text[:initial_chunk_size]
    remaining_text = text[initial_chunk_size:]
    logging.info(f'[DYNAMIC_CHUNKING] initial_chunk_size={len(chunk)} total_len={len(text)}')

    try:
        prompt = config.DYNAMIC_CHUNKING_PROMPT.format(text=chunk)
    except Exception:
        # Fallback to refined prompt if constant missing
        prompt = config.CHUNK_ANALYSIS_PROMPT_REFINED.format(text=chunk)
    logging.info(f"[GPT PROMPT][dynamic_chunking]: {prompt[:400]}...")
    response = gpt_extract(prompt, "control_extractor_v2")
    logging.info(f"[GPT RAW RESPONSE][dynamic_chunking]: {response}")

    if not response:
        logging.error('[DYNAMIC_CHUNKING] Empty GPT response; using naive split.')
        return [chunk, remaining_text] if remaining_text else [chunk]

    # Parse JSON array of integers if possible
    breakpoints = []
    try:
        data = json.loads(response.strip())
        if isinstance(data, list):
            breakpoints = [bp for bp in data if isinstance(bp, int) and 0 < bp < len(chunk)]
    except Exception as e:
        logging.warning(f'[DYNAMIC_CHUNKING] JSON parse failed: {e}; attempting legacy parsing.')
        breakpoints = parse_breakpoints(response)

    if not breakpoints:
        logging.warning('[DYNAMIC_CHUNKING] No valid breakpoints parsed; using naive split.')
        return [chunk, remaining_text] if remaining_text else [chunk]

    breakpoints = sorted(set(breakpoints))
    chunks = []
    start = 0
    for bp in breakpoints:
        if bp <= start:
            continue
        chunks.append(chunk[start:bp])
        start = bp
    chunks.append(chunk[start:])
    if remaining_text:
        chunks.append(remaining_text)
    logging.info(f'[DYNAMIC_CHUNKING] Produced {len(chunks)} chunks from initial segment.')
    return chunks

# Implement parsing logic for GPT responses

def parse_breakpoints(response):
    """
    Parse GPT response to extract breakpoints.
    """
    # Example parsing logic based on the response format
    breakpoints = []
    try:
        lines = response.split('\n')
        for line in lines:
            if 'Control Section Start' in line or 'Control Section End' in line:
                # Extract the character position from the line
                parts = line.split(':')
                if len(parts) > 1:
                    position_str = parts[-1].strip()
                    # Check if the position is numeric
                    if position_str.isdigit():
                        position = int(position_str)
                        breakpoints.append(position)
                    else:
                        logging.warning(f'Non-numeric position found: {position_str}')
    except Exception as e:
        logging.error(f'Error parsing breakpoints: {e}')
    return breakpoints

# Text classification function

def classify_text_segments(chunk):
    """
    Use GPT to classify text segments within a chunk.
    """
    prompt = config.SEGMENT_CLASSIFICATION_PROMPT.format(text=chunk, context="SOC report control section")
    logging.info(f"[GPT PROMPT][classify_text_segments]: {prompt}")
    response = gpt_extract(prompt, "control_extractor_v2")
    logging.info(f"[GPT RAW RESPONSE][classify_text_segments]: {response}")

    if not response:
        logging.error('Empty GPT response for classification. Returning empty segments.')
        return []

    classified_segments = parse_classified_segments(response)

    if not classified_segments:
        logging.error('No classified segments found in GPT response. Returning empty segments.')

    return classified_segments

# Implement parsing logic for classified segments

def parse_classified_segments(response):
    """Parse GPT classification response.

    Preferred format: JSON array of objects {"type": ..., "text": ...}.
    Fallback: legacy line-prefixed format.
    """
    # Attempt JSON first
    try:
        data = json.loads(response)
        if isinstance(data, list):
            json_segments = []
            for obj in data:
                if isinstance(obj, dict) and 'type' in obj and 'text' in obj:
                    t = obj['type'].strip()
                    txt = obj['text'].strip()
                    if t in {'control_id','control_description','test_procedure','test_result'} and txt:
                        json_segments.append({'type': t, 'text': txt})
            if json_segments:
                return json_segments
    except Exception as e:
        logging.debug(f'[CLASSIFY] JSON parse failed, falling back: {e}')

    # Legacy fallback parsing
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
        logging.error(f'[CLASSIFY] Legacy parse error: {e}')
    return segments

# JSON structuring function

def structure_json_records(classified_segments):
    """
    Organize classified segments into structured JSON records.
    """
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

        # Report progress for UI if possible
        try:
            if PROGRESS_HOOK and isinstance(current_record, dict):
                ctrl_end = current_record.get('end_line') or current_record.get('endLine')
                if isinstance(ctrl_end, int) and ctrl_end > 0:
                    PROGRESS_HOOK(ctrl_end)
        except Exception:
            pass

    if current_record:
        json_records.append(current_record)

    # Log the final json_records for verification
    logging.info("Entering final JSON records logging.")
    logging.info(f"Final JSON records: {json_records}")
    logging.info("Exiting final JSON records logging.")

    return json_records

# Update extract_controls_v2 to use JSON structuring

def extract_controls_v2(start_at_control: Optional[int] = None, start_at_line: Optional[int] = None):
    """
    Main function to extract controls using the new strategic approach, matching the old extractor's interface.
    Uses config.PDF_TXT_PATH and config.SECTION_JSON_PATH for input, and config.CONTROL_JSON_PATH for output.
    """
    # Initialize output file as valid JSON from the start to enable mid-run reads
    with open(config.CONTROL_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump({"controls": []}, f, ensure_ascii=False, indent=2)

    # Load section details from JSON
    with open(config.SECTION_JSON_PATH, 'r', encoding='utf-8') as json_file:
        sections = json.load(json_file)
    
    # Find the Control_Descriptions section
    control_section = next((section for section in sections if section["topic"] == "Control_Descriptions"), None)
    
    if control_section:
        start_line = control_section.get("start_line")
        end_line = control_section.get("end_line")
        section_start_line = start_line
        section_end_line = end_line
    else:
        logging.error("Control_Descriptions section not found in section_results.json")
        return

    file_path = str(config.PDF_TXT_PATH)
    results = []
    lines_per_chunk = getattr(config, 'CONTROL_LINES_PER_CHUNK', 160)

    # Load the text from the specified file
    with open(file_path, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()

    seq = 1  # sequence counter
    if isinstance(start_at_control, int) and start_at_control > 1:
        # If resuming by control sequence, we will skip writing existing controls and fast-forward start_line using heuristic.
        # Heuristic: load existing controls JSON (if present) and determine max end_line of already processed controls.
        try:
            if os.path.exists(config.CONTROL_JSON_PATH):
                with open(config.CONTROL_JSON_PATH, 'r', encoding='utf-8') as prevf:
                    prev_data = json.load(prevf)
                prev_controls = prev_data.get('controls') or []
                # Filter controls up to start_at_control-1
                already = [c for c in prev_controls if int(c.get('control_seq', 0)) < start_at_control]
                if already:
                    seq = start_at_control
                    # Determine resume line: max end_line among already processed controls
                    resume_line = max([c.get('end_line') or c.get('endLine') or c.get('control_line_ref') or 0 for c in already])
                    if isinstance(resume_line, int) and resume_line > 0:
                        start_line = resume_line
                        logging.info(f"[RESUME] Resuming control extraction at line {start_line} (after control_seq {start_at_control-1})")
        except Exception as _resume_err:
            logging.warning(f"[RESUME] Failed heuristic resume by control_seq: {_resume_err}")
    if isinstance(start_at_line, int) and start_at_line > 0:
        start_line = start_at_line
        logging.info(f"[RESUME] Overriding start_line via resume_start_at_line={start_at_line}")
    first = True
    start_time = time.time()
    consecutive_failures = 0
    safeguards = get_safeguard_settings()
    
    while start_line < end_line:
        # --- STALL WATCHDOG: detect lack of forward progress between outer iterations ---
        if 'last_progress_line' not in locals():
            last_progress_line = start_line
            last_progress_ts = time.time()
        else:
            if start_line <= last_progress_line:
                # No forward movement since last loop; if elapsed > threshold, force advance
                stall_idle = getattr(config, 'CONTROL_STALL_MAX_IDLE_SECONDS', 180)
                stall_advance = getattr(config, 'CONTROL_STALL_FORCE_ADVANCE_LINES', 120)
                if stall_idle > 0 and (time.time() - last_progress_ts) > stall_idle:
                    logging.warning(f"[STALL] No control progress for {stall_idle}s at line {start_line}; forcing advance by {stall_advance} lines")
                    start_line = min(end_line, start_line + stall_advance)
                    last_progress_ts = time.time()
                    try:
                        progress_path = getattr(config, 'JSON_DIR', None)
                        if progress_path:
                            progress_file = progress_path / 'control_progress.json'
                            stall_meta = {
                                "section_start_line": section_start_line,
                                "section_end_line": section_end_line,
                                "current_line": start_line,
                                "extracted_controls": len(results),
                                "stall_event": True,
                                "forced_advance": stall_advance,
                                "ts": time.time(),
                            }
                            with open(progress_file, 'w', encoding='utf-8') as pf:
                                json.dump(stall_meta, pf, ensure_ascii=False, indent=2)
                    except Exception as _serr:
                        logging.warning(f"[STALL] Failed to record stall meta: {_serr}")
            else:
                last_progress_line = start_line
                last_progress_ts = time.time()
        # SAFEGUARD: Check processing time timeout (if enabled)
        if safeguards['enabled']:
            elapsed_minutes = (time.time() - start_time) / 60
            if elapsed_minutes > safeguards['max_minutes']:
                logging.warning(f"Processing timeout reached ({safeguards['max_minutes']} minutes). Stopping control extraction.")
                logging.warning(f"Successfully extracted {len(results)} controls before timeout.")
                break
                
            # SAFEGUARD: Check consecutive failures
            if consecutive_failures >= safeguards['max_failures']:
                logging.warning(f"Too many consecutive failures ({safeguards['max_failures']}). Stopping control extraction.")
                logging.warning(f"Successfully extracted {len(results)} controls before failure limit.")
                break
        
        retry = False
        # Use overlapped chunk iterator with accurate chunk_start tracking
        for chunk_start, chunk in iter_control_chunks_with_overlap(
            txt_lines,
            start_line,
            lines_per_chunk=lines_per_chunk,
            overlap_lines=getattr(config, 'CONTROL_CHUNK_OVERLAP_LINES', 40),
            tail_guard_lines=getattr(config, 'CONTROL_CHUNK_TAIL_GUARD_LINES', 8)
        ):
            # SAFEGUARD: Check for non-control content (if enabled)
            if safeguards['enabled'] and safeguards['detect_non_control']:
                is_non_control, reason = detect_non_control_content(chunk)
                if is_non_control:
                    logging.warning(f"Non-control content detected at line {start_line}: {reason}")
                    logging.warning(f"Stopping control extraction. Successfully extracted {len(results)} controls.")
                    start_line = end_line  # Force exit from outer while loop
                    break
            try:
                logging.info(f"Processing chunk starting at line {chunk_start}")
                result, new_start_line, retry = process_chunk_with_gpt(chunk, chunk_start, txt_lines, results)
                logging.info(f"New Start Line Result: {result}")
                logging.info(f"New Start Line: {new_start_line}")
                
                if result:
                    result['control_seq'] = seq  # Assign incrementing control_seq
                    seq += 1
                    # Trust GPT-provided deviation fields as-is (no heuristic/regex post-processing)
                    results.append(result)
                    start_line = new_start_line
                    consecutive_failures = 0  # Reset failure count on success
                    logging.info(f"Appended result. Total results: {len(results)}")
                    # Persist a valid JSON object after each extracted control for downstream readers
                    try:
                        with open(config.CONTROL_JSON_PATH, 'w', encoding='utf-8') as jf:
                            json.dump({"controls": results}, jf, ensure_ascii=False, indent=2)
                        logging.info(f"Wrote {len(results)} controls to {config.CONTROL_JSON_PATH}")
                        # --- LINE PROGRESS META WRITE ---
                        try:
                            progress_meta = {
                                "section_start_line": section_start_line,
                                "section_end_line": section_end_line,
                                "current_line": start_line,
                                "extracted_controls": len(results),
                                "last_write_ts": time.time(),
                            }
                            progress_path = getattr(config, 'JSON_DIR', None)
                            if progress_path:
                                progress_file = progress_path / 'control_progress.json'
                                with open(progress_file, 'w', encoding='utf-8') as pf:
                                    json.dump(progress_meta, pf, ensure_ascii=False, indent=2)
                                logging.info(f"[PROGRESS] Updated control_progress.json current_line={start_line}")
                        except Exception as _perr:
                            logging.warning(f"Failed to write control_progress.json: {_perr}")
                    except Exception as _werr:
                        logging.warning(f"Failed mid-run write of controls JSON: {_werr}")
                    # Progress update if available
                    try:
                        if PROGRESS_HOOK and isinstance(result, dict):
                            ctrl_end = result.get('end_line') or result.get('endLine')
                            if isinstance(ctrl_end, int) and ctrl_end > 0:
                                PROGRESS_HOOK(ctrl_end)
                    except Exception:
                        pass
                    break  # Move to the next chunk after processing one control
                else:
                    # On hard failure without retry hint, advance by half-window to avoid stall
                    consecutive_failures += 1
                    advance = max(50, lines_per_chunk // 2)
                    start_line = min(end_line, start_line + advance)
                    logging.info(f"No control extracted; advancing start_line by {advance} to {start_line}")
                    # Restart inner loop with new generator at updated start_line
                    break
                    
                if retry:
                    lines_per_chunk += 25  # Increase chunk size for retry
                    logging.info(f"Retrying with larger chunk size: {lines_per_chunk}")
                    break  # Retry with the same start_line
                if config.CONTROL_TESTING_ENABLED and start_line > config.CONTROL_TESTING_MAX_LINE:
                    logging.info(f"Start line {start_line} exceeds test limit ({config.CONTROL_TESTING_MAX_LINE}). Stopping processing.")
                    break  # Ensure the outer loop also stops
            except Exception as e:
                logging.error(f"Error processing chunk: {e}")
                break
        if config.CONTROL_TESTING_ENABLED and start_line > config.CONTROL_TESTING_MAX_LINE:
            logging.info(f"Start line {start_line} exceeds test limit ({config.CONTROL_TESTING_MAX_LINE}). Stopping processing.")
            break  # Ensure the outer loop also stops

    # --- PATCH: Penalize subtext/duplicate controls ---
    for i, ctrl in enumerate(results):
        cid = ctrl.get('control_id')
        desc = (ctrl.get('control_desc') or '').strip()
        if not cid or not desc:
            continue
        for j, other in enumerate(results):
            if i == j:
                continue
            if other.get('control_id') == cid:
                other_desc = (other.get('control_desc') or '').strip()
                # If this control's desc is a subtext of another with the same id, penalize confidence
                if desc and other_desc and desc != other_desc and desc in other_desc:
                    old_conf = ctrl.get('control_confidence', 0)
                    new_conf = max(0, old_conf - 0.2)
                    ctrl['control_confidence'] = new_conf
                    ctrl['confidence_calc'] = (ctrl.get('confidence_calc', '') + f'; -0.2: subtext/possible duplicate of longer control_desc for same control_id').strip('; ')
    # Final log of results
    logging.info(f"Final results: {results}")
    # Write the controls as a dictionary with 'controls' key
    with open(config.CONTROL_JSON_PATH, 'w', encoding='utf-8') as json_file:
        json.dump({"controls": results}, json_file, ensure_ascii=False, indent=2)

def load_text_lines(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.readlines()


def find_control_section(section_results):
    return next((s for s in section_results if s.get('topic') == 'Control_Descriptions'), None)


def process_chunks(chunks, txt_lines):
    all_json_records = []
    tsc_criteria = getattr(config, 'TSC_CRITERIA', [])
    coso_criteria = getattr(config, 'COSO_2013_CRITERIA', [])
    seq = 1
    for idx, chunk in enumerate(chunks):
        logging.info(f'Processing chunk {idx}: {chunk[:200]}...')
        classified_segments = classify_text_segments(chunk)
        json_records = structure_json_records(classified_segments)
        for ctrl in json_records:
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
                ctrl['control_status'] = 'partial - no match'
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
            ctrl['control_status'] = 'complete' if ctrl.get('control_id') else 'partial - no match'
        all_json_records.extend(json_records)
    return all_json_records


def write_json_output(data, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'controls': data}, f, ensure_ascii=False, indent=2)


# Simplified process_chunk_with_gpt function

def verify_next_control_start_with_gpt(suggested_start, previous_controls, txt_lines):
    """
    Use GPT to verify if the suggested start of the next control is valid and not a duplicate.
    :param suggested_start: The line number suggested by GPT as the start of the next control.
    :param previous_controls: List of previously identified controls.
    :param txt_lines: The text lines of the document.
    :return: Validated start line or None if invalid.
    """
    if suggested_start is None or suggested_start < 1:
        logging.warning("suggested_start is None or invalid, cannot verify")
        return None
    
    # Extract the sentence or context around the suggested start
    context_snippet = txt_lines[suggested_start-1:suggested_start+2]
    context_text = ' '.join(context_snippet).strip()

    # Prepare a prompt for GPT to verify the suggested start
    prompt = (
        f"Verify if the following text is the start of a new control section. "
        f"Ensure it is not a duplicate of any previously identified controls and does not contain test-related language. "
        f"Previously identified controls: {previous_controls}. "
        f"Text to verify: {context_text}"
    )
    logging.info(f"GPT Prompt for verification: {prompt}")
    response = gpt_extract(prompt, "control_extractor_v2")
    logging.info(f"[GPT RAW RESPONSE][verify_next_control_start_with_gpt]: {response}")
    logging.info(f"GPT Response for verification: {response}")

    # Parse the response to determine if the suggested start is valid
    if response and "valid" in response.lower():
        return suggested_start
    else:
        logging.info(f"Suggested start at line {suggested_start} is not valid according to GPT.")
        return None


def find_nearest_page_ref(txt_lines, line_idx):
    """
    Given txt_lines and a 1-based line index, find the nearest '=== PAGE <Number> ===' line before line_idx.
    Returns the page number as an int, or None if not found.
    """
    if line_idx is None or line_idx < 1:
        return None
    
    page_pattern = re.compile(r"=== PAGE (\d+) ===")
    for i in range(line_idx - 1, -1, -1):
        match = page_pattern.search(txt_lines[i])
        if match:
            return int(match.group(1))
    return None


def process_chunk_with_gpt(chunk, start_line, txt_lines, previous_controls):
    # Ensure the prompt is formatted with the actual chunk and start_line
    prompt = config.CONTROL_EXTRACTION_PROMPT.format(
        text=f"Below is the text to analyze. Do not ask for more text. Only analyze what is provided.\n\n{chunk}",
        start_line=start_line
    )
    logging.info(f"[GPT PROMPT][process_chunk_with_gpt][start_line={start_line}]: {prompt}")
    try:
        response_text = gpt_extract(prompt, "control_extractor_v2")
        logging.info(f"[GPT RAW RESPONSE][process_chunk_with_gpt][start_line={start_line}]: {response_text}")
        control_data, _, _ = parse_gpt_response(response_text)

        if not control_data.get('control_id') or not control_data.get('control_desc') or not control_data.get('control_test_results'):
            logging.warning("Incomplete control data. Retrying with a larger chunk.")
            return None, start_line, True

        if not is_logically_consistent(control_data):
            logging.warning("Control data is not logically consistent.")
            control_data['unlikely_control'] = True
            return control_data, control_data['end_line'], False

        # Initialize confidence calculation
        control_confidence = control_data.get('control_confidence', 0.5)  # Default to 0.5 if not provided
        confidence_calc = [f"Initial GPT confidence: {control_confidence}"]

        # Store GPT justification for initial confidence
        control_data['control_gpt_conf_justification'] = control_data.get('control_gpt_conf_justification', 'No justification provided')

        # Check for duplicates in control_id and control_desc
        unique_control = True
        for control in previous_controls:
            if control['control_id'] == control_data['control_id'] and control['control_desc'] == control_data['control_desc']:
                control_confidence -= 0.3
                confidence_calc.append("-0.3 for duplicate control_id and control_desc")
                unique_control = False
                break
        if unique_control:
            control_confidence += 0.1
            confidence_calc.append("+0.1 for unique control_id and control_desc")

        # Check if control_id is in additional_references
        if any(control_data['control_id'] in control.get('additional_references', []) for control in previous_controls):
            control_confidence -= 0.1
            confidence_calc.append("-0.1 for control_id in additional_references")

        # Check for key test words in control_desc
        key_test_words = getattr(config, 'CONTROL_TEST_WORDS', ["examined", "inquired", "ascertained", "inspected", "reviewed"])
        if any(word in control_data['control_desc'] for word in key_test_words):
            control_confidence -= 0.3
            confidence_calc.append(f"-0.3 for key test words in control_desc ({key_test_words})")

        # Update control data with confidence information
        control_data['control_confidence'] = round(max(0, min(1, control_confidence)), 1)  # Ensure confidence is between 0 and 1, rounded to 1 decimal place
        control_data['confidence_calc'] = '; '.join(confidence_calc)

        # --- PATCH: Ensure all required fields are present ---
        tsc_criteria = getattr(config, 'TSC_CRITERIA', [])
        coso_criteria = getattr(config, 'COSO_2013_CRITERIA', [])
        desc = control_data.get('control_desc', '')
        tsc_id, coso_id, tsc_sim, coso_sim = map_control_to_frameworks(desc, tsc_criteria, coso_criteria)
        control_data['control_tsc_id'] = tsc_id
        control_data['control_coso_id'] = coso_id
        control_data['control_tsc_similarity'] = tsc_sim
        control_data['control_coso_similarity'] = coso_sim
        control_data['control_tsc_confidence_pct'] = int(round(100 * (tsc_sim + 1) / 2)) if tsc_sim != -1 else None
        control_data['control_coso_confidence_pct'] = int(round(100 * (coso_sim + 1) / 2)) if coso_sim != -1 else None
        if tsc_sim > coso_sim:
            control_data['control_closest_framework'] = 'TSC'
        elif coso_sim > tsc_sim:
            control_data['control_closest_framework'] = 'COSO'
        elif tsc_sim == coso_sim and tsc_sim != -1:
            control_data['control_closest_framework'] = 'Equal'
        else:
            control_data['control_closest_framework'] = 'Undetermined'
        control_data['control_tsc_section'] = get_tsc_section(tsc_id)
        control_data['control_coso_section'] = get_coso_section(coso_id)
        control_data['control_soc_domain'] = get_tsc_domain(tsc_id) or get_coso_domain(coso_id)
        control_data['control_status'] = 'complete' if control_data.get('control_id') else 'partial - no match'
        # Set opinion/reasoning if present in GPT response
        control_data['control_gpt_opinion'] = control_data.get('control_gpt_opinion', None)
        control_data['control_gpt_reasoning'] = control_data.get('control_gpt_reasoning', None)
        # Infer and set control_line_ref and control_page_ref
        control_data['control_line_ref'] = start_line
        control_data['control_page_ref'] = find_nearest_page_ref(txt_lines, start_line)
        # Deviation fields: confirm via a dedicated GPT pass based strictly on control_test_results
        try:
            dev_prompt = config.DEVIATION_EVAL_PROMPT.format(
                control_id=control_data.get('control_id', ''),
                control_desc=control_data.get('control_desc', ''),
                control_test=control_data.get('control_test', ''),
                control_test_results=control_data.get('control_test_results', '') or ''
            )
            logging.info(f"[GPT PROMPT][deviation_eval][start_line={start_line}]: {dev_prompt}")
            dev_resp_raw = gpt_extract(dev_prompt, "control_extractor_v2")
            logging.info(f"[GPT RAW RESPONSE][deviation_eval][start_line={start_line}]: {dev_resp_raw}")
            dev_text = (dev_resp_raw or '').strip()
            if dev_text.startswith('```json'):
                dev_text = dev_text[7:]
            elif dev_text.startswith('```'):
                dev_text = dev_text[3:]
            if dev_text.endswith('```'):
                dev_text = dev_text[:-3]
            import json as _json
            dev_json = _json.loads(dev_text)
            control_data['has_deviation'] = bool(dev_json.get('has_deviation', False))
            control_data['deviation_desc'] = dev_json.get('deviation_desc', '') if control_data['has_deviation'] else ''
        except Exception as _dev_err:
            logging.warning(f"[deviation_eval] Fallback due to error: {_dev_err}")
            # Keep whatever GPT provided in first pass; normalize types
            control_data['has_deviation'] = bool(control_data.get('has_deviation', False))
            dev_desc = control_data.get('deviation_desc')
            control_data['deviation_desc'] = dev_desc if isinstance(dev_desc, str) else ''

        # Robust defaulting for any missing fields
        required_fields = [
            "control_page_ref",
            "control_line_ref",
            "control_tsc_id",
            "control_coso_id",
            "control_tsc_similarity",
            "control_coso_similarity",
            "control_tsc_confidence_pct",
            "control_coso_confidence_pct",
            "control_closest_framework",
            "control_tsc_section",
            "control_coso_section",
            "control_soc_domain",
            "control_status",
            "control_gpt_opinion",
            "control_gpt_reasoning"
        ]
        for k in required_fields:
            if k not in control_data:
                control_data[k] = None if k != "control_status" else "complete"

        lookahead_start = control_data['end_line']
        lookahead_chunk = extract_text_for_lines(txt_lines, lookahead_start, lookahead_start + 100)

        if len(lookahead_chunk) < 1000:
            logging.warning("Lookahead chunk is shorter than expected.")

        if getattr(config, 'CONTROL_VERIFY_NEXT_START_ENABLED', False):
            next_control_start = infer_next_control_start(lookahead_chunk, 0)
            logging.info(f"Next control likely starts at line {next_control_start}")
            validated_start = verify_next_control_start_with_gpt(next_control_start, previous_controls, txt_lines)
            if validated_start is not None:
                start_line = lookahead_start + validated_start - 1
            else:
                logging.info("Suggested start was invalid. Searching for next control.")
                start_line = control_data['end_line']
        else:
            # Deterministic: always advance to the end_line of the current control
            start_line = control_data['end_line']

        # Replace hard-coded test limit with config variables
        if config.CONTROL_TESTING_ENABLED and start_line > config.CONTROL_TESTING_MAX_LINE:
            logging.info(f"Start line {start_line} exceeds test limit ({config.CONTROL_TESTING_MAX_LINE}). Stopping processing.")
            return control_data, start_line, False

        logging.info(f"Processed control ending at line {control_data['end_line']}")
        return control_data, control_data['end_line'], False
    except Exception as e:
        logging.error(f"Error calling GPT API: {e}")
        return None, start_line, False

def parse_gpt_response(response_text):
    import re
    def _normalize_json_like(text: str) -> str:
        # Remove markdown code fences
        t = text.strip()
        if t.startswith('```json'):
            t = t[7:]
        if t.startswith('```'):
            t = t[3:]
        if t.endswith('```'):
            t = t[:-3]
        # Normalize quotes and remove zero-width spaces/backticks
        t = t.replace('\u201c', '"').replace('\u201d', '"').replace('\u2019', "'")
        t = t.replace('“', '"').replace('”', '"').replace('’', "'")
        t = t.replace('`', '')
        t = t.replace('\u200b', '').replace('\ufeff', '')
        # Remove trailing commas before } or ]
        t = re.sub(r',\s*([}\]])', r'\1', t)
        return t.strip()

    def _extract_bracket_matched_json(text: str) -> str:
        # Find first '{' or '[' and return the bracket-balanced substring
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
        # Fallback: return from start to end
        return text[start:]

    try:
        if response_text is None:
            return {}, 0, 0
        if not isinstance(response_text, str):
            response_text = str(response_text)

        cleaned = _normalize_json_like(response_text)

        # Try direct parse first
        try:
            parsed = json.loads(cleaned)
        except Exception:
            candidate = _extract_bracket_matched_json(cleaned)
            # Second-pass cleanup for trailing commas
            candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
            parsed = json.loads(candidate)

        # Normalize to dict
        if isinstance(parsed, list):
            parsed_dicts = [x for x in parsed if isinstance(x, dict)]
            control_data = parsed_dicts[0] if parsed_dicts else {}
        elif isinstance(parsed, dict):
            control_data = parsed
        else:
            control_data = {}

        if not isinstance(control_data, dict):
            return {}, 0, 0

        lines_into_chunk = control_data.get('start_line', 0)
        lines_covered = control_data.get('end_line', 0)
        return control_data, lines_into_chunk, lines_covered
    except Exception as e:
        logging.error(f"Error parsing JSON response: {e}")
        return {}, 0, 0

def is_logically_consistent(control_data):
    """
    Checks if the control data is logically consistent.
    For example, ensure that the control description and test results are logically aligned.
    
    :param control_data: The control data to check.
    :return: True if logically consistent, False otherwise.
    """
    # Example logic: Check if control description and test results are aligned
    if "security policy" in control_data.get('control_desc', '').lower() and "background check" in control_data.get('control_test', '').lower():
        return False
    return True

def infer_next_control_start(chunk, current_position):
    # Ensure the chunk is not empty and the current_position is within bounds
    if not chunk or current_position >= len(chunk):
        logging.warning("Chunk is empty or current_position is out of bounds.")
        return None

    # Provide a snippet of text around the current position for context
    snippet_length = 1300  # Increase the size to provide more context
    context_snippet = chunk[current_position:current_position + snippet_length]
    
    # Use GPT to analyze the text and suggest the start of the next control
    prompt = (
        f"Based on the following text, evaluate each full sentence to identify the likely start of the next"
        f" control requirement. Sentences may spread across multiple lines, so evaluate the context of the next"
        f" sentences to determine the likely start of the next control. "
        f"There are no explicit indicators, so infer based on the context of the next sentences. "
        f"There will not be any column headers or other formatting.  It will be a single paragraph or line of text."
        f"Your job is to interpret the text and determine the likely start of the next control.  It will be a "
        f"single paragraph or line of text. May include expressions like 'required to' or 'requires' or 'must' do something."
        f"Don't confuse with a test statement (which may include words like reviewed, evaluated, inspected, inquired, etc.), "
        f"test result, deviation, or other text that may be in the same paragraph or line."
        f"Return just the line number where the next control requirement likely starts. No other text or explanation."
        f"Text snippet: {context_snippet}"
    )
    logging.info(f"GPT Prompt for next control start: {prompt}")  # Log the prompt with context_snippet
    response = gpt_extract(prompt, "control_extractor_v2")
    logging.info(f"[GPT RAW RESPONSE][infer_next_control_start]: {response}")
    logging.info(f"GPT Response for next control start: {response}")
    
    # Parse the response to find the suggested start position
    if response:
        try:
            suggested_start = int(response.strip())
            return suggested_start
        except ValueError:
            logging.warning("Could not parse suggested start position from GPT response.")
    else:
        logging.warning("Received no response for next control start inference.")
    return None

# Progress hook to report extraction progress externally
PROGRESS_HOOK = None

def set_progress_hook(hook_fn):
    global PROGRESS_HOOK
    PROGRESS_HOOK = hook_fn

def main():
    # Load section details from JSON
    with open(config.SECTION_JSON_PATH, 'r', encoding='utf-8') as json_file:
        sections = json.load(json_file)
    
    # Find the Control_Descriptions section
    control_section = next((section for section in sections if section["topic"] == "Control_Descriptions"), None)
    
    if control_section:
        start_line = control_section.get("start_line")
        end_line = control_section.get("end_line")
    else:
        logging.error("Control_Descriptions section not found in section_results.json")
        return

    file_path = str(config.PDF_TXT_PATH)
    results = []
    lines_per_chunk = 100

    # Load the text from the specified file
    with open(file_path, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()

    # Reset the output file at the start of each run
    with open(config.CONTROL_JSON_PATH, 'w', encoding='utf-8') as json_file:
        json_file.write('[\n')

    seq = 1  # Add before the while loop
    first = True
    while start_line < end_line:
        retry = False
        for chunk in extract_control_chunks(file_path, start_line, lines_per_chunk=lines_per_chunk):
            try:
                logging.info(f"Processing chunk starting at line {start_line}")
                result, new_start_line, retry = process_chunk_with_gpt(chunk, start_line, txt_lines, results)
                logging.info(f"New Start Line Result: {result}")
                logging.info(f"New Start Line: {new_start_line}")
                if result:
                    result['control_seq'] = seq  # Assign incrementing control_seq
                    seq += 1
                    results.append(result)
                    start_line = new_start_line
                    # Progress update if available
                    try:
                        if PROGRESS_HOOK and isinstance(result, dict):
                            ctrl_end = result.get('end_line') or result.get('endLine')
                            if isinstance(ctrl_end, int) and ctrl_end > 0:
                                PROGRESS_HOOK(ctrl_end)
                    except Exception:
                        pass
                    logging.info(f"Appended result. Total results: {len(results)}")
                    # Write each control as soon as it is found
                    with open(config.CONTROL_JSON_PATH, 'a', encoding='utf-8') as json_file:
                        if not first:
                            json_file.write(',\n')
                        json.dump(result, json_file, ensure_ascii=False, indent=2)
                        first = False
                    logging.info(f"Wrote control to {config.CONTROL_JSON_PATH}")
                    break  # Move to the next chunk after processing one control
                if retry:
                    lines_per_chunk += 25  # Increase chunk size for retry
                    logging.info(f"Retrying with larger chunk size: {lines_per_chunk}")
                    break  # Retry with the same start_line
                if config.CONTROL_TESTING_ENABLED and start_line > config.CONTROL_TESTING_MAX_LINE:
                    logging.info(f"Start line {start_line} exceeds test limit ({config.CONTROL_TESTING_MAX_LINE}). Stopping processing.")
                    # Close the JSON array
                    with open(config.CONTROL_JSON_PATH, 'a', encoding='utf-8') as json_file:
                        json_file.write('\n]\n')
                    break  # Ensure the outer loop also stops
            except Exception as e:
                logging.error(f"Error processing chunk: {e}")
                break
        if config.CONTROL_TESTING_ENABLED and start_line > config.CONTROL_TESTING_MAX_LINE:
            logging.info(f"Start line {start_line} exceeds test limit ({config.CONTROL_TESTING_MAX_LINE}). Stopping processing.")
            # Close the JSON array
            with open(config.CONTROL_JSON_PATH, 'a', encoding='utf-8') as json_file:
                json_file.write('\n]\n')
            break  # Ensure the outer loop also stops

    # --- PATCH: Penalize subtext/duplicate controls ---
    for i, ctrl in enumerate(results):
        cid = ctrl.get('control_id')
        desc = (ctrl.get('control_desc') or '').strip()
        if not cid or not desc:
            continue
        for j, other in enumerate(results):
            if i == j:
                continue
            if other.get('control_id') == cid:
                other_desc = (other.get('control_desc') or '').strip()
                # If this control's desc is a subtext of another with the same id, penalize confidence
                if desc and other_desc and desc != other_desc and desc in other_desc:
                    old_conf = ctrl.get('control_confidence', 0)
                    new_conf = max(0, old_conf - 0.2)
                    ctrl['control_confidence'] = new_conf
                    ctrl['confidence_calc'] = (ctrl.get('confidence_calc', '') + f'; -0.2: subtext/possible duplicate of longer control_desc for same control_id').strip('; ')
    # Final log of results
    logging.info(f"Final results: {results}")
    # Write the controls as a dictionary with 'controls' key
    with open(config.CONTROL_JSON_PATH, 'w', encoding='utf-8') as json_file:
        json.dump({"controls": results}, json_file, ensure_ascii=False, indent=2)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_text_for_lines(txt_lines, start_line, end_line):
    """
    Extract text from the specified start to end line numbers.
    """
    if start_line is None or start_line < 1:
        start_line = 1
    if end_line is None or end_line < start_line:
        end_line = start_line
    return ''.join(txt_lines[start_line-1:end_line])


def extract_control_chunks(file_path, start_line, lines_per_chunk=50):
    """
    Extracts chunks of text from a file starting from a specific line.

    :param file_path: Path to the text file.
    :param start_line: Line number to start extraction.
    :param lines_per_chunk: Number of lines per chunk (default is 50).
    :return: Generator yielding chunks of text.
    """
    if start_line is None or start_line < 1:
        start_line = 1
    
    with open(file_path, 'r', encoding='utf-8') as file:
        # Skip lines until the start line
        for _ in range(start_line - 1):
            next(file)

        # Extract chunks
        while True:
            chunk = ''.join([file.readline() for _ in range(lines_per_chunk)])
            if not chunk.strip():  # Stop if the chunk is empty
                break
            yield chunk


def iter_control_chunks_with_overlap(txt_lines, start_line, lines_per_chunk=140, overlap_lines=40, tail_guard_lines=8):
    """
    Iterate over overlapped chunks from txt_lines, yielding (chunk_start_line, chunk_text).
    - lines_per_chunk: primary window size
    - overlap_lines: number of lines to overlap between consecutive chunks
    - tail_guard_lines: extra lines appended at end of each chunk to avoid splitting conclusions (e.g., 'Deviation noted')
    """
    if start_line is None or start_line < 1:
        start_idx = 1
    else:
        start_idx = start_line
    total_lines = len(txt_lines)
    step = max(1, lines_per_chunk - max(0, overlap_lines))
    idx = start_idx
    while idx <= total_lines:
        end_idx = min(total_lines, idx + lines_per_chunk - 1 + max(0, tail_guard_lines))
        chunk = ''.join(txt_lines[idx-1:end_idx])
        if not chunk.strip():
            break
        yield idx, chunk
        idx += step

# --- Removed embedding functions (replaced with GPT-based classification) ---
# Previously: get_openai_embedding(), cosine_similarity(), _embedding_cache
# Now using _select_best_framework_match_with_gpt() for direct GPT reasoning

def classify_control_domain_with_gpt(control_desc: str) -> Dict[str, Any]:
    """Ask GPT to classify the control into a TSC/COSO domain and suggest candidate IDs.
    Returns dict: { domain: str or None, tsc_candidates: [ids], coso_candidates: [ids], reasoning: str }
    """
    try:
        prompt = (
            "You are an expert SOC 2 assessor. Classify the following single control description into a high-level domain "
            "from this set: Security, Availability, Confidentiality, Processing Integrity, Privacy. Then suggest up to 3 likely AICPA TSC IDs "
            "(e.g., CC7.2, C1.7, A1.1, PI1.3, P4.1, Conf1.3) and optionally up to 2 COSO principle IDs that best align.\n\n"
            "Respond ONLY with a JSON object with keys: domain (one of the set), tsc_candidates (array of strings), coso_candidates (array of strings), reasoning (string).\n\n"
            f"Control: {control_desc}"
        )
        raw = gpt_extract(prompt, "control_extractor_v2")
        # Reuse robust cleaner
        parsed, _, _ = parse_gpt_response(raw)
        domain = parsed.get('domain') if isinstance(parsed, dict) else None
        tsc_candidates = parsed.get('tsc_candidates') if isinstance(parsed, dict) else []
        coso_candidates = parsed.get('coso_candidates') if isinstance(parsed, dict) else []
        reasoning = parsed.get('reasoning') if isinstance(parsed, dict) else ''
        if not isinstance(tsc_candidates, list):
            tsc_candidates = []
        if not isinstance(coso_candidates, list):
            coso_candidates = []
        return {
            'domain': domain if isinstance(domain, str) else None,
            'tsc_candidates': [str(x) for x in tsc_candidates if isinstance(x, (str, int))],
            'coso_candidates': [str(x) for x in coso_candidates if isinstance(x, (str, int))],
            'reasoning': reasoning if isinstance(reasoning, str) else ''
        }
    except Exception:
        return {'domain': None, 'tsc_candidates': [], 'coso_candidates': [], 'reasoning': ''}

def _ids_by_domain(tsc_criteria: list, domain: Optional[str]) -> list:
    if not domain:
        return [c['id'] for c in tsc_criteria]
    # Map domain to id prefixes per TSC categories
    domain = domain.lower()
    prefixes = []
    if 'confidential' in domain:
        prefixes = ['Conf']
    elif 'availability' in domain:
        prefixes = ['A']
    elif 'privacy' in domain:
        prefixes = ['P']
    elif 'processing' in domain:
        prefixes = ['PI']
    else:
        # Security / Common Criteria
        prefixes = ['C', 'CC']
    return [c['id'] for c in tsc_criteria if any(c['id'].startswith(pfx) for pfx in prefixes)]

def _select_best_framework_match_with_gpt(control_desc: str, criteria_subset: list, framework_name: str, candidate_ids: set) -> tuple:
    """
    Use GPT to select the single best-matching framework criterion from a subset.
    
    Args:
        control_desc: The control description to map
        criteria_subset: List of criteria dicts with 'id' and 'description' keys
        framework_name: "TSC" or "COSO" for context
        candidate_ids: Optional set of candidate IDs from initial classification
    
    Returns:
        (best_id, confidence_score) where confidence is 0.0-1.0 or -1 on error
    """
    import logging
    
    if not criteria_subset:
        return None, -1
    
    # Limit to top 10 candidates to keep prompt manageable
    criteria_to_eval = criteria_subset[:10]
    
    # Build prompt with control and candidate criteria
    criteria_text = "\n".join([
        f"- {c['id']}: {c['description'][:200]}{'...' if len(c['description']) > 200 else ''}"
        for c in criteria_to_eval
    ])
    
    prompt = f"""You are an expert SOC 2 auditor. Select the single best-matching {framework_name} criterion for this control.

Control Description:
{control_desc}

Available {framework_name} Criteria:
{criteria_text}

Respond ONLY with a JSON object with keys:
- best_id: The ID of the best-matching criterion (must be from the list above)
- confidence: Your confidence level from 0.0 to 1.0
- reasoning: Brief explanation of why this criterion matches best

If no good match exists, return {{"best_id": null, "confidence": 0.0, "reasoning": "explanation"}}.
"""
    
    try:
        raw = gpt_extract(prompt, "control_extractor_v2")
        result = json.loads(raw.strip())
        
        best_id = result.get('best_id')
        confidence = float(result.get('confidence', 0.0))
        
        # Validate the ID exists in our subset
        if best_id and best_id not in [c['id'] for c in criteria_to_eval]:
            logging.warning(f"GPT returned invalid {framework_name} ID: {best_id}")
            return None, -1
        
        return best_id, confidence
        
    except Exception as e:
        logging.error(f"GPT framework selection failed for {framework_name}: {e}")
        return None, -1

def map_control_to_frameworks(control_desc, tsc_criteria, coso_criteria):
    """
    Map a control description to best-matching TSC and COSO criteria using GPT-based reasoning.
    
    Replaces the previous embedding + cosine similarity approach with direct GPT analysis.
    GPT-5 via Dataiku can reason about control intent and framework alignment better than
    embedding similarity, and eliminates the OpenAI API dependency.
    
    Returns: (best_tsc_id, best_coso_id, confidence_tsc, confidence_coso)
    """
    import logging
    from ..config import CONTROL_EMBEDDING_MAPPING_ENABLED
    
    if not CONTROL_EMBEDDING_MAPPING_ENABLED:
        logging.info("Framework mapping disabled by config. Skipping.")
        return None, None, -1, -1
    
    if not tsc_criteria:
        logging.error("TSC criteria list is empty! Cannot map control to TSC framework.")
        return None, None, -1, -1
    if not coso_criteria:
        logging.error("COSO criteria list is empty! Cannot map control to COSO framework.")
        return None, None, -1, -1

    # 1) Get GPT's initial domain classification and candidates
    classification = classify_control_domain_with_gpt(control_desc)
    predicted_domain = classification.get('domain')
    tsc_candidate_ids = set([x.strip() for x in classification.get('tsc_candidates', [])])
    coso_candidate_ids = set([x.strip() for x in classification.get('coso_candidates', [])])

    # 2) Restrict search space based on domain and candidates
    allowed_tsc_ids = _ids_by_domain(tsc_criteria, predicted_domain)
    if tsc_candidate_ids:
        allowed_tsc_ids = [tid for tid in allowed_tsc_ids if tid in tsc_candidate_ids] or allowed_tsc_ids
    
    # Filter criteria lists
    tsc_subset = [c for c in tsc_criteria if c['id'] in allowed_tsc_ids] if allowed_tsc_ids else tsc_criteria
    coso_subset = [c for c in coso_criteria if c['id'] in coso_candidate_ids] if coso_candidate_ids else coso_criteria

    # 3) Ask GPT to select the single best match from the subset
    best_tsc_id, tsc_confidence = _select_best_framework_match_with_gpt(
        control_desc, tsc_subset, "TSC", tsc_candidate_ids
    )
    best_coso_id, coso_confidence = _select_best_framework_match_with_gpt(
        control_desc, coso_subset, "COSO", coso_candidate_ids
    )

    if best_tsc_id is None:
        logging.warning(f"No TSC match found for control: {control_desc[:80]}...")
    if best_coso_id is None:
        logging.warning(f"No COSO match found for control: {control_desc[:80]}...")

    return best_tsc_id, best_coso_id, tsc_confidence, coso_confidence

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

if __name__ == "__main__":
    main() 