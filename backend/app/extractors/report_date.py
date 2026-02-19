import json
import logging
import os
import re
from pathlib import Path
from .. import config
from ..gpt_client import gpt_extract

logger = logging.getLogger(__name__)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_text_for_pages(txt_lines, page_numbers):
    """Extract all lines between the first and last page in page_numbers."""
    if not page_numbers:
        return ''
    
    result = []
    current_page = None
    min_page = min(page_numbers)
    max_page = max(page_numbers)
    capturing = False
    
    for line in txt_lines:
        # Check if this line is a page marker
        if line.strip().startswith('=== PAGE '):
            try:
                current_page = int(line.strip().split()[2])
                # Start capturing when we hit the min page
                if current_page == min_page:
                    capturing = True
                # Stop capturing after we've collected all lines from max page
                # and hit the next page marker
                elif current_page > max_page:
                    break
            except Exception:
                pass
        
        # Capture all lines while we're in range
        if capturing:
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
    
    with open(pdf_txt_path, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    
    # Prefer page-based extraction over line-based for better content coverage
    if auditor_section and auditor_section.get('DOC_page_ref') is not None and auditor_section.get('end_DOC_page_ref') is not None:
        start = auditor_section['DOC_page_ref']
        end = auditor_section['end_DOC_page_ref']
        
        pages = list(range(start, end + 1))
        text = extract_text_for_pages(txt_lines, pages)
        logger.info(f"[JOB {job_id}] Extracted text from pages {start}-{end} ({len(text)} chars)")
    elif auditor_section and auditor_section.get('start_line') and auditor_section.get('end_line'):
        start_line = auditor_section['start_line']
        end_line = auditor_section['end_line']
        
        # Fix: end_line often defaults to document end. Find actual section end by looking for next section
        auditor_start = auditor_section['start_line']
        actual_end_line = end_line
        for section in section_results:
            if section.get('start_line') and section['start_line'] > auditor_start:
                # Found a section that starts after auditor section
                actual_end_line = min(actual_end_line, section['start_line'] - 1)
        
        if actual_end_line != end_line:
            logger.info(f"[JOB {job_id}] Corrected section end from {end_line} to {actual_end_line} (next section boundary)")
            end_line = actual_end_line
        
        text = extract_text_for_lines(txt_lines, start_line, end_line)
        logger.info(f"[JOB {job_id}] Extracted text from lines {start_line}-{end_line} ({len(text)} chars)")
    else:
        logger.info(f"[JOB {job_id}] No valid section boundaries. Using entire document for extraction.")
        with open(pdf_txt_path, 'r', encoding='utf-8') as f2:
            text = f2.read()
    
    # Primary path: GPT extraction - signature appears at END of auditor report section
    # Extract the last ~100 lines of the section where the signature date will be
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    
    # Extract last 100 lines (or all if less than 100)
    num_lines_to_extract = min(100, len(lines))
    start_idx = max(0, len(lines) - num_lines_to_extract)
    extraction_window = '\n'.join(lines[start_idx:])
    
    logger.info(f"[JOB {job_id}] Extracting last {num_lines_to_extract} lines from auditor section (lines {start_idx}-{len(lines)}, {len(extraction_window)} chars)")
    
    # Debug: Save the extracted text
    debug_path = str(job_paths['temp_dir'] / 'report_date_debug.txt')
    with open(debug_path, 'w', encoding='utf-8') as debug_file:
        debug_file.write(f"Auditor section info:\n")
        if auditor_section:
            debug_file.write(f"  DOC_page_ref: {auditor_section.get('DOC_page_ref')}\n")
            debug_file.write(f"  end_DOC_page_ref: {auditor_section.get('end_DOC_page_ref')}\n")
            debug_file.write(f"  start_line: {auditor_section.get('start_line')}\n")
            debug_file.write(f"  end_line: {auditor_section.get('end_line')}\n")
        debug_file.write(f"\nTotal text length: {len(text)}\n")
        debug_file.write(f"Total lines: {len(lines)}\n")
        debug_file.write(f"Extracted last {num_lines_to_extract} lines (start_idx={start_idx})\n")
        debug_file.write(f"\nExtraction window sent to GPT:\n{extraction_window}\n")
    
    prompt = config.REPORT_DATE_EXTRACTION_PROMPT.format(text=extraction_window)
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
    
    # VALIDATION: Check report_date against coverage_period if available
    # Report date should be AFTER coverage_end (typically a few days to a month later)
    if result.get('report_date'):
        coverage_period_path = job_paths['json_dir'] / 'coverage_period_result.json'
        if coverage_period_path.exists():
            try:
                from datetime import datetime
                with open(str(coverage_period_path), 'r', encoding='utf-8') as cp_file:
                    coverage_data = json.load(cp_file)
                
                coverage_end_str = coverage_data.get('end_date')
                if coverage_end_str:
                    report_date_obj = datetime.fromisoformat(result['report_date'])
                    coverage_end_obj = datetime.fromisoformat(coverage_end_str)
                    
                    days_after_coverage = (report_date_obj - coverage_end_obj).days
                    
                    # Report date should be 0-90 days AFTER coverage end
                    if days_after_coverage < 0:
                        logger.warning(f"[JOB {job_id}] VALIDATION FAILED: report_date ({result['report_date']}) is BEFORE coverage_end ({coverage_end_str}) by {abs(days_after_coverage)} days. This is likely incorrect.")
                        result['explanation'] += f" | WARNING: Report date appears to be before coverage end date (off by {abs(days_after_coverage)} days)"
                        result['validation_warning'] = f"Report date is {abs(days_after_coverage)} days BEFORE coverage end"
                    elif days_after_coverage > 90:
                        logger.warning(f"[JOB {job_id}] VALIDATION WARNING: report_date ({result['report_date']}) is {days_after_coverage} days after coverage_end ({coverage_end_str}). This is unusually long.")
                        result['explanation'] += f" | WARNING: Report date is {days_after_coverage} days after coverage end (typically 0-60 days)"
                        result['validation_warning'] = f"Report date is {days_after_coverage} days after coverage end (unusually long)"
                    else:
                        logger.info(f"[JOB {job_id}] VALIDATION PASSED: report_date is {days_after_coverage} days after coverage_end (within normal range)")
                        result['explanation'] += f" | Validated: {days_after_coverage} days after coverage end"
            except Exception as val_err:
                logger.warning(f"[JOB {job_id}] Could not validate report_date against coverage_period: {val_err}")
    
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info(f'[JOB {job_id}] Report date extraction result: {result}')
    return result

__all__ = ["extract_report_date"]

if __name__ == '__main__':
    extract_report_date()
