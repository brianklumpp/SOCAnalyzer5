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
    # Reset output file at the start of extraction
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        f.write('{}\n')
    section_results = load_json(SECTION_JSON_PATH)
    auditor_section = next((s for s in section_results if s.get('topic') == 'Service_Auditor_Report'), None)
    if not auditor_section:
        logging.warning('No Service_Auditor_Report section found. Falling back to full-document scan for coverage period.')
    start_line = auditor_section.get('start_line') if auditor_section else None
    end_line = auditor_section.get('end_line') if auditor_section else None
    with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    if start_line and end_line:
        text = extract_text_for_lines(txt_lines, start_line, end_line)
    elif auditor_section and auditor_section.get('DOC_page_ref') is not None and auditor_section.get('end_DOC_page_ref') is not None:
        start = auditor_section['DOC_page_ref']
        end = auditor_section['end_DOC_page_ref']
        pages = list(range(start, end + 1))
        text = extract_text_for_pages(txt_lines, pages)
    else:
        logging.error('DOC_page_ref or end_DOC_page_ref is None for auditor section. Using entire document for heuristic extraction.')
        with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f2:
            text = f2.read()
    # Primary path: GPT extraction
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

    # Fallback: heuristic parsing (disabled by default – see config.ALLOW_REGEX_FALLBACKS)
    def _parse_month_date(s):
        try:
            # Accept formats like 'January 1, 2024' or 'January 2024'
            import datetime as _dt
            s = s.strip().replace('\u00a0', ' ')
            # Normalize double spaces
            s = re.sub(r"\s+", " ", s)
            # Try Month D, YYYY
            m = re.match(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", s)
            if m:
                month, day, year = m.groups()
                day = int(day)
                month_num = _dt.datetime.strptime(month[:3], '%b').month
                return f"{int(year):04d}-{int(month_num):02d}-{int(day):02d}"
            # Try Month YYYY (use first of month)
            m = re.match(r"([A-Za-z]+)\s+(\d{4})", s)
            if m:
                month, year = m.groups()
                month_num = _dt.datetime.strptime(month[:3], '%b').month
                return f"{int(year):04d}-{int(month_num):02d}-01"
        except Exception:
            return None
        return None

    try:
        need_fallback = not result['type'] or (not result['start_date'] and not result['end_date'])
    except Exception:
        need_fallback = True

    if need_fallback and getattr(config, 'ALLOW_REGEX_FALLBACKS', False):
        full_ctx = text  # use the broader auditor-section text gathered above
        # Pattern: For the period January 1, 2024 through November 30, 2024
        m = re.search(r"For the period\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})\s+(?:to|through|thru|-)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})", full_ctx, re.IGNORECASE)
        if m:
            start_raw, end_raw = m.groups()
            start_iso = _parse_month_date(start_raw)
            end_iso = _parse_month_date(end_raw)
            if end_iso:
                result['type'] = result.get('type') or 'Type 2'
                result['start_date'] = result.get('start_date') or start_iso
                result['end_date'] = result.get('end_date') or end_iso
                if not result.get('explanation'):
                    result['explanation'] = 'Heuristic parse: matched "For the period ... through ..."'
        else:
            # Pattern: As of January 31, 2024 (Type 1)
            m2 = re.search(r"As of\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})", full_ctx, re.IGNORECASE)
            if m2:
                end_raw = m2.group(1)
                end_iso = _parse_month_date(end_raw)
                result['type'] = result.get('type') or 'Type 1'
                result['start_date'] = result.get('start_date') or None
                result['end_date'] = result.get('end_date') or end_iso
                if not result.get('explanation'):
                    result['explanation'] = 'Heuristic parse: matched "As of <date>"'

    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logging.info(f'Coverage period extraction result: {result}')
    return result

__all__ = ["extract_coverage_period"]

if __name__ == '__main__':
    extract_coverage_period()
