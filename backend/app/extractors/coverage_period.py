# --- All imports at the top (PEP8 best practice) ---
import json
import logging
import re
from dateutil import parser as date_parser
from collections import Counter
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

def deduce_dates_from_candidates(txt_lines, section_results, job_id=None):
    """
    Deduce coverage period and report date using temporal relationship rules.
    
    Rules:
    - Earliest date → coverage_start
    - Latest date → report_date
    - Coverage_end must be 6-12 months after coverage_start
    - Coverage_end must be within 30 days before report_date
    - If multiple valid coverage_end candidates, pick closest to report_date
    
    Args:
        txt_lines: Full document text lines
        section_results: Section metadata from section_results.json
        job_id: Unique job identifier for logging
        
    Returns:
        Dict with type, start_date, end_date, as_of_date, explanation or None if deduction fails
    """
    log_prefix = f"[JOB {job_id}] " if job_id else ""
    logger.info(f"{log_prefix}Starting date deduction with temporal rules...")
    
    # Collect dates from Management_Assertion and Service_Auditor_Report sections
    management_section = next((s for s in section_results if s.get('topic') == 'Management_Assertion'), None)
    auditor_section = next((s for s in section_results if s.get('topic') == 'Service_Auditor_Report'), None)
    
    sections_to_scan = [s for s in [management_section, auditor_section] if s]
    if not sections_to_scan:
        logger.warning(f"{log_prefix}No Management_Assertion or Service_Auditor_Report sections found for date deduction")
        return None
    
    # Extract all dates from sections
    all_dates = []
    for section in sections_to_scan:
        start_line = section.get('start_line')
        end_line = section.get('end_line')
        if start_line and end_line:
            text = extract_text_for_lines(txt_lines, start_line, end_line)
            # Find dates using regex
            date_pattern = r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b'
            matches = re.finditer(date_pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    date_obj = date_parser.parse(match.group(0))
                    all_dates.append(date_obj)
                except:
                    pass
    
    if not all_dates:
        logger.warning(f"{log_prefix}No dates found in sections for deduction")
        return None
    
    # Count frequency to filter watermarks
    date_counter = Counter(d.date() for d in all_dates)
    watermark_threshold = config.WATERMARK_FREQUENCY_THRESHOLD
    filtered_dates = [d for d in all_dates if date_counter[d.date()] <= watermark_threshold]
    
    logger.info(f"{log_prefix}Found {len(all_dates)} total dates, {len(filtered_dates)} after watermark filtering (threshold={watermark_threshold})")
    
    if len(filtered_dates) < 1:
        logger.warning(f"{log_prefix}Insufficient dates after filtering ({len(filtered_dates)} dates). Need at least 1.")
        return None
    
    # Log all candidates with rejection reasons
    for date_obj in sorted(set(all_dates), key=lambda d: d):
        freq = date_counter[date_obj.date()]
        status = "FILTERED" if freq > watermark_threshold else "VALID"
        logger.info(f"{log_prefix}Date candidate: {date_obj.strftime('%Y-%m-%d')} (frequency={freq}, status={status})")
    
    # Sort chronologically
    sorted_dates = sorted(filtered_dates)
    
    # Handle different scenarios based on number of dates found
    if len(sorted_dates) == 1:
        # Only one date - likely Type 1 "as of" report
        logger.info(f"{log_prefix}Only one date found: {sorted_dates[0].strftime('%Y-%m-%d')}. Inferring Type 1 report.")
        return {
            'type': 'Type 1',
            'start_date': None,
            'end_date': sorted_dates[0].strftime('%Y-%m-%d'),
            'as_of_date': sorted_dates[0].strftime('%Y-%m-%d'),
            'explanation': f'Deduced Type 1: only one date found ({sorted_dates[0].strftime("%Y-%m-%d")}). Likely "as of" date.'
        }
    
    elif len(sorted_dates) == 2:
        # Two dates - could be coverage_end + report_date, need to infer start
        # Assume 6-month coverage period (typical for SOC reports)
        from dateutil.relativedelta import relativedelta
        date1 = sorted_dates[0]
        date2 = sorted_dates[1]
        
        # Check if dates are 6-12 months apart (Type 2) or within 30 days (Type 1)
        months_apart = (date2.year - date1.year) * 12 + (date2.month - date1.month)
        days_apart = (date2 - date1).days
        
        if months_apart >= 6 and months_apart <= 12:
            # Dates span 6-12 months: date1 is coverage_start, date2 is coverage_end
            logger.info(f"{log_prefix}Two dates spanning {months_apart} months: inferring Type 2 with coverage_start={date1.strftime('%Y-%m-%d')}, coverage_end={date2.strftime('%Y-%m-%d')}")
            return {
                'type': 'Type 2',
                'start_date': date1.strftime('%Y-%m-%d'),
                'end_date': date2.strftime('%Y-%m-%d'),
                'as_of_date': None,
                'explanation': f'Deduced Type 2: two dates found spanning {months_apart} months. Assuming date1=coverage_start, date2=coverage_end.'
            }
        elif days_apart <= 30:
            # Dates within 30 days: likely coverage_end + report_date, infer start as 6 months before
            inferred_start = date1 - relativedelta(months=6)
            logger.info(f"{log_prefix}Two dates within {days_apart} days: inferring coverage_start as 6 months before first date")
            logger.info(f"{log_prefix}Inferred coverage_start={inferred_start.strftime('%Y-%m-%d')}, coverage_end={date1.strftime('%Y-%m-%d')}, report_date={date2.strftime('%Y-%m-%d')}")
            return {
                'type': 'Type 2',
                'start_date': inferred_start.strftime('%Y-%m-%d'),
                'end_date': date1.strftime('%Y-%m-%d'),
                'as_of_date': None,
                'explanation': f'Deduced Type 2: two dates found {days_apart} days apart. Inferred coverage_start as 6 months before coverage_end ({date1.strftime("%Y-%m-%d")}). Report date: {date2.strftime("%Y-%m-%d")}.'
            }
        else:
            # Dates don't match expected patterns
            logger.warning(f"{log_prefix}Two dates found but spacing unclear ({months_apart} months, {days_apart} days apart). Defaulting to Type 1.")
            return {
                'type': 'Type 1',
                'start_date': None,
                'end_date': date2.strftime('%Y-%m-%d'),
                'as_of_date': date2.strftime('%Y-%m-%d'),
                'explanation': f'Two dates found but unclear relationship ({months_apart} months apart). Defaulting to Type 1 with as_of_date={date2.strftime("%Y-%m-%d")}.'
            }
    
    # Three or more dates - original logic
    coverage_start = sorted_dates[0]
    report_date = sorted_dates[-1]
    
    logger.info(f"{log_prefix}Deduced coverage_start (earliest): {coverage_start.strftime('%Y-%m-%d')}")
    logger.info(f"{log_prefix}Deduced report_date (latest): {report_date.strftime('%Y-%m-%d')}")
    
    # Find valid coverage_end candidates
    min_months = config.COVERAGE_PERIOD_MIN_MONTHS
    max_months = config.COVERAGE_PERIOD_MAX_MONTHS
    proximity_days = config.REPORT_DATE_PROXIMITY_DAYS
    
    valid_coverage_ends = []
    for date_obj in sorted_dates[1:-1]:  # Exclude earliest and latest
        # Check temporal rules
        months_after_start = (date_obj.year - coverage_start.year) * 12 + (date_obj.month - coverage_start.month)
        days_before_report = (report_date - date_obj).days
        
        reasons = []
        if months_after_start < min_months:
            reasons.append(f"only {months_after_start} months after start (min={min_months})")
        if months_after_start > max_months:
            reasons.append(f"{months_after_start} months after start exceeds max={max_months}")
        if days_before_report < 0:
            reasons.append(f"after report date by {abs(days_before_report)} days")
        if days_before_report > proximity_days:
            reasons.append(f"{days_before_report} days before report exceeds proximity={proximity_days}")
        
        if reasons:
            logger.info(f"{log_prefix}Coverage_end candidate {date_obj.strftime('%Y-%m-%d')} REJECTED: {'; '.join(reasons)}")
        else:
            logger.info(f"{log_prefix}Coverage_end candidate {date_obj.strftime('%Y-%m-%d')} VALID (months_after_start={months_after_start}, days_before_report={days_before_report})")
            valid_coverage_ends.append(date_obj)
    
    if not valid_coverage_ends:
        logger.warning(f"{log_prefix}No valid coverage_end candidates found matching temporal rules")
        return None
    
    # Pick coverage_end closest to report_date (but not later)
    coverage_end = max(valid_coverage_ends, key=lambda d: d)
    logger.info(f"{log_prefix}Selected coverage_end (closest to report_date): {coverage_end.strftime('%Y-%m-%d')}")
    
    # Determine report type
    months_duration = (coverage_end.year - coverage_start.year) * 12 + (coverage_end.month - coverage_start.month)
    report_type = 'Type 2' if months_duration >= min_months else 'Type 1'
    
    result = {
        'type': report_type,
        'start_date': coverage_start.strftime('%Y-%m-%d'),
        'end_date': coverage_end.strftime('%Y-%m-%d'),
        'as_of_date': None,
        'explanation': f'Deduced via temporal rules: earliest={coverage_start.strftime("%Y-%m-%d")}, end={coverage_end.strftime("%Y-%m-%d")} (closest to report), latest={report_date.strftime("%Y-%m-%d")}. Duration={months_duration} months.'
    }
    
    logger.info(f"{log_prefix}Date deduction successful: {result}")
    return result

def extract_coverage_period(job_paths=None, job_id=None):
    """Extract coverage period from SOC report.
    
    Args:
        job_paths: Dict with 'json_dir', 'logs_dir', 'temp_dir' Path objects
        job_id: Unique job identifier for logging
    """
    if not job_paths:
        raise ValueError("[COVERAGE_PERIOD] job_paths parameter is required for job isolation")
    if not job_id:
        raise ValueError("[COVERAGE_PERIOD] job_id parameter is required for logging")
    
    # Set up job-specific paths
    section_json_path = str(job_paths['json_dir'] / 'section_results.json')
    output_json_path = str(job_paths['json_dir'] / 'coverage_period_result.json')
    pdf_txt_path = str(job_paths['temp_dir'] / 'output.txt')
    
    logger.info(f"[JOB {job_id}] Starting coverage period extraction")
    
    # Reset output file at the start of extraction
    with open(output_json_path, 'w', encoding='utf-8') as f:
        f.write('{}\n')
    section_results = load_json(section_json_path)
    # SOC1 reports often have coverage period in Management's Assertion or Service Auditor Report
    management_section = next((s for s in section_results if s.get('topic') == 'Management_Assertion'), None)
    system_desc_section = next((s for s in section_results if s.get('topic') == 'Description_of_System'), None)
    auditor_section = next((s for s in section_results if s.get('topic') == 'Service_Auditor_Report'), None)
    
    # Check if management section is too short (likely just a header page)
    if management_section:
        section_length = management_section.get('end_line', 0) - management_section.get('start_line', 0)
        if section_length < 10:
            logger.info(f'[JOB {job_id}] Management_Assertion section too short ({section_length} lines), trying Service_Auditor_Report instead')
            management_section = None
    
    # Priority: Service Auditor Report (most reliable for dates) > Management Assertion > System Description
    target_section = auditor_section or management_section or system_desc_section
    if not target_section:
        logger.info(f'[JOB {job_id}] No system description or auditor report section found. Falling back to full-document scan.')
    
    start_line = target_section.get('start_line') if target_section else None
    end_line = target_section.get('end_line') if target_section else None
    with open(pdf_txt_path, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    if start_line and end_line:
        text = extract_text_for_lines(txt_lines, start_line, end_line)
    elif target_section and target_section.get('DOC_page_ref') is not None and target_section.get('end_DOC_page_ref') is not None:
        start = target_section['DOC_page_ref']
        end = target_section['end_DOC_page_ref']
        pages = list(range(start, end + 1))
        text = extract_text_for_pages(txt_lines, pages)
    else:
        section_name = 'system description or auditor report'
        logger.info(f'[JOB {job_id}] DOC_page_ref or end_DOC_page_ref is None for {section_name} section. Using entire document for heuristic extraction.')
        with open(pdf_txt_path, 'r', encoding='utf-8') as f2:
            text = f2.read()
    # Primary path: GPT extraction
    # Get first 40 non-empty lines (increased from 20 for better SOC1 coverage)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    first_lines = '\n'.join(lines[:40])
    
    logger.info(f'[JOB {job_id}] Section target: {target_section.get("topic") if target_section else "full document"}')
    logger.info(f'[JOB {job_id}] Extracted {len(lines[:40])} non-empty lines, {len(first_lines)} characters for GPT')
    logger.debug(f'[JOB {job_id}] Text sample (first 300 chars): {first_lines[:300]}...')
    
    # Write the actual text to a debug file for verification
    debug_file = job_paths['logs_dir'] / "coverage_period_gpt_input.txt"
    try:
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(f"=== TEXT SENT TO GPT FOR COVERAGE PERIOD EXTRACTION ===\n\n{first_lines}\n")
        logger.debug(f'[JOB {job_id}] Wrote GPT input to {debug_file}')
    except Exception as e:
        logger.warning(f'[JOB {job_id}] Could not write debug file: {e}')
    
    prompt = config.COVERAGE_PERIOD_EXTRACTION_PROMPT.format(text=first_lines)
    logger.debug(f'[JOB {job_id}] Sending prompt to GPT (length: {len(prompt)} chars)')
    
    response = gpt_extract(prompt, 'coverage_period_extractor')
    logger.info(f'[JOB {job_id}] GPT response received (length: {len(response) if response else 0} chars)')
    
    result = {'type': None, 'start_date': None, 'end_date': None, 'as_of_date': None, 'explanation': '', 'raw_gpt_response': response}
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
            result['type'] = data.get('type')
            result['start_date'] = data.get('start_date')
            result['end_date'] = data.get('end_date')
            result['as_of_date'] = data.get('as_of_date')
            result['explanation'] = data.get('explanation', '')
            logger.info(f'[JOB {job_id}] GPT extraction result: type={result["type"]}, start={result["start_date"]}, end={result["end_date"]}')
            
            # Sanity check: If GPT returned null dates but text contains obvious date patterns, warn
            if not result.get('start_date') and not result.get('end_date') and not result.get('as_of_date'):
                # Check for common date patterns in the text
                date_hints = []
                if re.search(r'\d{1,2}/\d{1,2}/\d{4}', first_lines):
                    date_hints.append('MM/DD/YYYY format')
                if re.search(r'[A-Za-z]+\s+\d{1,2},?\s+\d{4}\s+(?:to|through)\s+[A-Za-z]+\s+\d{1,2},?\s+\d{4}', first_lines, re.IGNORECASE):
                    date_hints.append('"Month DD, YYYY to Month DD, YYYY" pattern')
                if re.search(r'(?:from|period|beginning).*\d{4}', first_lines, re.IGNORECASE):
                    date_hints.append('date-related phrases with year')
                
                if date_hints:
                    warning_msg = f'GPT returned null dates but text contains: {", ".join(date_hints)}'
                    logger.warning(f'[JOB {job_id}] {warning_msg}')
                    logger.warning(f'[JOB {job_id}] GPT may have hallucinated. Consider reviewing: {debug_file}')
                    result['explanation'] += f' [WARNING: {warning_msg}]'
        except Exception as e:
            logger.info(f'[JOB {job_id}] Failed to parse GPT response: {e}')
            logger.debug(f'[JOB {job_id}] Raw response: {response[:500]}...')
            result['explanation'] = f'Failed to parse GPT response: {e}'
    
    # Regex fallback: Try to extract date ranges directly if GPT failed completely
    if not result.get('start_date') and not result.get('end_date') and not result.get('as_of_date'):
        logger.info(f'[JOB {job_id}] GPT extraction returned no dates, trying regex fallback for coverage period')
        import datetime as _dt
        
        # Look for date range patterns like "January 1, 2023 to December 31, 2023"
        date_range_pattern = r'([A-Za-z]+\s+\d{1,2},?\s+\d{4})\s+(?:to|through|-)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})'
        matches = list(re.finditer(date_range_pattern, first_lines, re.IGNORECASE))
        
        if matches:
            # Use the first match found
            match = matches[0]
            start_str = match.group(1)
            end_str = match.group(2)
            
            try:
                # Parse dates (handle both "January 1, 2023" and "January 1 2023")
                start_str_clean = start_str.replace(',', '')
                end_str_clean = end_str.replace(',', '')
                start_date = _dt.datetime.strptime(start_str_clean, '%B %d %Y').strftime('%Y-%m-%d')
                end_date = _dt.datetime.strptime(end_str_clean, '%B %d %Y').strftime('%Y-%m-%d')
                
                result['start_date'] = start_date
                result['end_date'] = end_date
                result['type'] = 'Type 2'  # Assume Type 2 for date ranges
                result['explanation'] = 'Extracted via regex fallback (date range pattern)'
                logger.info(f'[JOB {job_id}] Regex fallback found coverage period: {start_date} to {end_date}')
            except Exception as parse_error:
                logger.warning(f'[JOB {job_id}] Failed to parse regex-matched dates: {parse_error}')
    
    # Deduction fallback: Try temporal rule-based deduction if GPT failed or incomplete
    # Consider GPT extraction incomplete if:
    # 1. No type returned, OR
    # 2. Type is "Type 2" but no coverage dates (start_date and end_date both missing), OR  
    # 3. Type is "Type 1" but no as_of_date, OR
    # 4. end_date is missing (for both Type 1 and Type 2)
    try:
        is_type2_missing_coverage = (result.get('type') == 'Type 2' and 
                                      not result.get('start_date') and not result.get('end_date'))
        is_type1_missing_date = (result.get('type') == 'Type 1' and 
                                 not result.get('as_of_date') and not result.get('end_date'))
        missing_end_date = not result.get('end_date') and not result.get('as_of_date')
        
        need_deduction = (not result.get('type') or 
                         is_type2_missing_coverage or 
                         is_type1_missing_date or
                         missing_end_date)
        
        logger.info(f"[JOB {job_id}] Deduction check: type={result.get('type')}, start={result.get('start_date')}, end={result.get('end_date')}, as_of={result.get('as_of_date')}, need_deduction={need_deduction}")
    except Exception as e:
        logger.info(f"[JOB {job_id}] Error checking deduction need: {e}")
        need_deduction = True
    
    if need_deduction:
        logger.info(f"[JOB {job_id}] GPT extraction incomplete, attempting date deduction fallback...")
        deduced = deduce_dates_from_candidates(txt_lines, section_results, job_id=job_id)
        if deduced:
            result = deduced
            result['raw_gpt_response'] = response  # Preserve GPT response for debugging
            logger.info(f"[JOB {job_id}] Deduction fallback successful: {result}")
        else:
            logger.warning(f"[JOB {job_id}] Deduction fallback failed, trying regex heuristics...")

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

    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info(f'[JOB {job_id}] Coverage period extraction result: {result}')
    return result

__all__ = ["extract_coverage_period"]

if __name__ == '__main__':
    extract_coverage_period()
