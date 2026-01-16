import json
import logging
import re
from pathlib import Path
from .. import config
from ..gpt_client import gpt_extract

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

def extract_report_date(job_paths=None, job_id=None):
    """Extract report date from SOC report.
    
    Args:
        job_paths: Dict with 'json_dir', 'logs_dir', 'temp_dir' Path objects
        job_id: Unique job identifier for logging
    """
    if not job_paths:
        raise ValueError("[REPORT_DATE] job_paths parameter is required for job isolation")
    if not job_id:
        raise ValueError("[REPORT_DATE] job_id parameter is required for logging")
    
    # Set up job-specific paths
    section_json_path = str(job_paths['json_dir'] / 'section_results.json')
    output_json_path = str(job_paths['json_dir'] / 'report_date_result.json')
    pdf_txt_path = str(job_paths['temp_dir'] / 'output.txt')
    
    logger.info(f"[JOB {job_id}] Starting report date extraction")
    
    # Reset output file at the start of extraction
    with open(output_json_path, 'w', encoding='utf-8') as f:
        f.write('{}\n')
    section_results = load_json(section_json_path)
    auditor_section = next((s for s in section_results if s.get('topic') == 'Service_Auditor_Report'), None)
    if not auditor_section:
        logger.info(f"[JOB {job_id}] No Service_Auditor_Report section found. Falling back to full-document scan for report date.")
    start_line = auditor_section.get('start_line') if auditor_section else None
    end_line = auditor_section.get('end_line') if auditor_section else None
    with open(pdf_txt_path, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    if start_line and end_line:
        text = extract_text_for_lines(txt_lines, start_line, end_line)
    elif auditor_section and auditor_section.get('DOC_page_ref') is not None and auditor_section.get('end_DOC_page_ref') is not None:
        start = auditor_section['DOC_page_ref']
        end = auditor_section['end_DOC_page_ref']
        pages = list(range(start, end + 1))
        text = extract_text_for_pages(txt_lines, pages)
    else:
        logger.info(f"[JOB {job_id}] DOC_page_ref or end_DOC_page_ref is None for auditor section. Using entire document for GPT-only extraction context.")
        with open(pdf_txt_path, 'r', encoding='utf-8') as f2:
            text = f2.read()
    # Primary path: GPT extraction on last lines of the auditor section
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    last_lines = '\n'.join(lines[-5:])
    prompt = config.REPORT_DATE_EXTRACTION_PROMPT.format(text=last_lines)
    response = gpt_extract(prompt, 'report_date_extractor')
    result = {'report_date': None, 'explanation': '', 'raw_gpt_response': response}
    if not response:
        logger.info(f'[JOB {job_id}] No response from GPT.')
        result['explanation'] = 'No response from GPT.'
    else:
        try:
            # Handle markdown code blocks from GPT
            response_clean = response.strip()
            if response_clean.startswith('```'):
                # Extract JSON from markdown code block (handle with or without newline before closing ```)
                json_match = re.search(r'```(?:json)?\s*\n(.*?)\s*```', response_clean, re.DOTALL)
                if json_match:
                    response_clean = json_match.group(1).strip()
            
            data = json.loads(response_clean)
            result['report_date'] = data.get('report_date')
            result['explanation'] = data.get('explanation', '')
        except Exception as e:
            logger.info(f'[JOB {job_id}] Failed to parse GPT response: {response[:200]}... | Error: {e}')
            result['explanation'] = f'Failed to parse GPT response: {e}'
    # Fallback: heuristic search (disabled by default – see config.ALLOW_REGEX_FALLBACKS)
    def _parse_month_date(s):
        try:
            import datetime as _dt
            s = s.strip().replace('\u00a0', ' ')
            s = re.sub(r"\s+", " ", s)
            m = re.match(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", s)
            if m:
                month, day, year = m.groups()
                day = int(day)
                month_num = _dt.datetime.strptime(month[:3], '%b').month
                return f"{int(year):04d}-{int(month_num):02d}-{int(day):02d}"
        except Exception:
            return None
        return None

    if not result.get('report_date') and getattr(config, 'ALLOW_REGEX_FALLBACKS', False):
        # Look farther back than the last 5 lines to be safe
        tail = '\n'.join(lines[-50:]) if lines else text
        matches = list(re.finditer(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})", tail))
        if not matches:
            # As a broader fallback, scan the whole section text
            matches = list(re.finditer(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})", text))
        if matches:
            last_date_str = matches[-1].group(1)
            iso = _parse_month_date(last_date_str)
            if iso:
                result['report_date'] = iso
                if not result.get('explanation'):
                    result['explanation'] = 'Heuristic parse: last date in auditor section'
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info(f'[JOB {job_id}] Report date extraction result: {result}')
    return result

__all__ = ["extract_report_date"]

if __name__ == '__main__':
    extract_report_date()
