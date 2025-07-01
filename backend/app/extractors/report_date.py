import os
import json
import logging
from app import config
from app.gpt_client import gpt_extract

SECTION_JSON_PATH = os.path.join('data', 'json', 'section_results.json')
OUTPUT_JSON_PATH = os.path.join('data', 'json', 'report_date_result.json')
PDF_TXT_PATH = os.path.join('data', 'output', 'output.txt')
LOG_PATH = os.path.join('data', 'logs', 'report_date_extractor.log')
logging.basicConfig(filename=LOG_PATH, level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

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
    section_results = load_json(SECTION_JSON_PATH)
    auditor_section = next((s for s in section_results if s.get('topic') == 'Service_Auditor_Report'), None)
    if not auditor_section:
        logging.error('No Service_Auditor_Report section found.')
        return None
    start_line = auditor_section.get('line')
    end_line = auditor_section.get('end_line')
    with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    if start_line and end_line:
        text = extract_text_for_lines(txt_lines, start_line, end_line)
    else:
        # fallback to page-based extraction
        start = auditor_section['DOC_page_ref']
        end = auditor_section['end_DOC_page_ref']
        pages = list(range(start, end + 1))
        text = extract_text_for_pages(txt_lines, pages)
    # Get last 5 non-empty lines
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    last_lines = '\n'.join(lines[-5:])
    prompt = config.REPORT_DATE_EXTRACTION_PROMPT.format(text=last_lines)
    response = gpt_extract(prompt)
    if not response:
        logging.error('No response from GPT.')
        result = {'report_date': None, 'explanation': 'No response from GPT.', 'raw_gpt_response': response}
    else:
        try:
            data = json.loads(response)
            result = {
                'report_date': data.get('report_date'),
                'explanation': data.get('explanation', ''),
                'raw_gpt_response': response
            }
        except Exception as e:
            logging.error(f'Failed to parse GPT response: {response} | Error: {e}')
            result = {'report_date': None, 'explanation': 'Failed to parse GPT response.', 'raw_gpt_response': response}
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logging.info(f'Report date extraction result: {result}')
    return result

if __name__ == '__main__':
    extract_report_date()
