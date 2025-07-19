# --- All imports at the top (PEP8 best practice) ---
import os
import json
import logging
import re
from .. import config
from ..gpt_client import gpt_extract

# Use centralized config paths
SECTION_JSON_PATH = config.SECTION_JSON_PATH
OUTPUT_JSON_PATH = config.JSON_DIR / "coverage_period_result.json"
PDF_TXT_PATH = config.PDF_TXT_PATH

logger = logging.getLogger(__name__)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

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

def extract_text_for_lines(txt_lines, start_line, end_line):
    # Lines are 1-indexed in section_results.json
    return ''.join(txt_lines[start_line-1:end_line])

def extract_coverage_period():
    section_results = load_json(SECTION_JSON_PATH)
    auditor_section = next((s for s in section_results if s.get('topic') == 'Service_Auditor_Report'), None)
    if not auditor_section:
        logging.error('No Service_Auditor_Report section found.')
        return None
    start_line = auditor_section.get('start_line')
    end_line = auditor_section.get('end_line')
    with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    if start_line and end_line:
        text = extract_text_for_lines(txt_lines, start_line, end_line)
    elif auditor_section.get('DOC_page_ref') is not None and auditor_section.get('end_DOC_page_ref') is not None:
        start = auditor_section['DOC_page_ref']
        end = auditor_section['end_DOC_page_ref']
        pages = list(range(start, end + 1))
        text = extract_text_for_pages(txt_lines, pages)
    else:
        logging.error('DOC_page_ref or end_DOC_page_ref is None for auditor section.')
        return None
    # Get first 20 non-empty lines (to cover both Type 1 and Type 2 language)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    first_lines = '\n'.join(lines[:20])
    prompt = config.COVERAGE_PERIOD_EXTRACTION_PROMPT.format(text=first_lines)
    response = gpt_extract(prompt, 'coverage_period_extractor')
    result = {'type': None, 'start_date': None, 'end_date': None, 'explanation': '', 'raw_gpt_response': response}
    if not response:
        logging.error('No response from GPT.')
        result['explanation'] = 'No response from GPT.'
    else:
        try:
            data = json.loads(response)
            result['type'] = data.get('type')
            result['start_date'] = data.get('start_date')
            result['end_date'] = data.get('end_date')
            result['explanation'] = data.get('explanation', '')
        except Exception as e:
            logging.error(f'Failed to parse GPT response: {response} | Error: {e}')
            result['explanation'] = f'Failed to parse GPT response: {e}'
        # Fallback: try to extract type/start_date/end_date from raw response if missing
        import re
        if not result['type'] and response:
            type_match = re.search(r"['\"]?type['\"]?\s*[:=]\s*['\"]?(Type 1|Type 2)['\"]?", response, re.IGNORECASE)
            if type_match:
                result['type'] = type_match.group(1)
        if not result['start_date'] and response:
            start_patterns = [
                r"['\"]?start_date['\"]?\s*[:=]\s*['\"]([0-9]{4}-[0-9]{2}-[0-9]{2})['\"]",
                r"([0-9]{2}/[0-9]{2}/[0-9]{4})",
                r"([0-9]{4}/[0-9]{2}/[0-9]{2})",
                r"([A-Za-z]+\s+[0-9]{1,2},\s*[0-9]{4})",
                r"([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})"
            ]
            found_start = None
            for pat in start_patterns:
                start_match = re.search(pat, response)
                if start_match:
                    found_start = start_match.group(1)
                    break
            if found_start:
                result['start_date'] = found_start
        if not result['end_date'] and response:
            end_patterns = [
                r"['\"]?end_date['\"]?\s*[:=]\s*['\"]([0-9]{4}-[0-9]{2}-[0-9]{2})['\"]",
                r"([0-9]{2}/[0-9]{2}/[0-9]{4})",
                r"([0-9]{4}/[0-9]{2}/[0-9]{2})",
                r"([A-Za-z]+\s+[0-9]{1,2},\s*[0-9]{4})",
                r"([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})"
            ]
            found_end = None
            for pat in end_patterns:
                end_match = re.search(pat, response)
                if end_match:
                    found_end = end_match.group(1)
                    break
            if found_end:
                result['end_date'] = found_end
        if not result['type'] and not result['start_date'] and not result['end_date'] and not result['explanation']:
            result['explanation'] = 'Failed to parse GPT response and no coverage period found.'
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logging.info(f'Coverage period extraction result: {result}')
    return result

__all__ = ["extract_coverage_period"]

if __name__ == '__main__':
    extract_coverage_period()
