import os
import json
import logging
import re
from .. import config
from ..gpt_client import gpt_extract

# Use centralized config paths
SECTION_JSON_PATH = config.SECTION_JSON_PATH
OUTPUT_JSON_PATH = config.JSON_DIR / "report_date_result.json"
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

def extract_report_date():
    # Reset output file at the start of extraction
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        f.write('{}\n')
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
    # Get last 5 non-empty lines
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    last_lines = '\n'.join(lines[-5:])
    prompt = config.REPORT_DATE_EXTRACTION_PROMPT.format(text=last_lines)
    response = gpt_extract(prompt, 'report_date_extractor')
    result = {'report_date': None, 'explanation': '', 'raw_gpt_response': response}
    if not response:
        logging.error('No response from GPT.')
        result['explanation'] = 'No response from GPT.'
    else:
        try:
            data = json.loads(response)
            result['report_date'] = data.get('report_date')
            result['explanation'] = data.get('explanation', '')
        except Exception as e:
            logging.error(f'Failed to parse GPT response: {response} | Error: {e}')
            result['explanation'] = f'Failed to parse GPT response: {e}'
        # Fallback: try to extract report_date from raw response if missing
        if not result['report_date'] and response:
            date_patterns = [
                r"['\"]?report_date['\"]?\s*[:=]\s*['\"]([0-9]{4}-[0-9]{2}-[0-9]{2})['\"]",
                r"([0-9]{2}/[0-9]{2}/[0-9]{4})",
                r"([0-9]{4}/[0-9]{2}/[0-9]{2})",
                r"([A-Za-z]+\s+[0-9]{1,2},\s*[0-9]{4})",
                r"([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})"
            ]
            found_date = None
            for pat in date_patterns:
                date_match = re.search(pat, response)
                if date_match:
                    found_date = date_match.group(1)
                    break
            if found_date:
                result['report_date'] = found_date
                result['explanation'] = 'Extracted from raw response by regex.'
            elif not result['explanation']:
                result['explanation'] = 'Failed to parse GPT response and no date found.'
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logging.info(f'Report date extraction result: {result}')
    return result

__all__ = ["extract_report_date"]

if __name__ == '__main__':
    extract_report_date()
