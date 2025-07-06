from .extractors.auditor import extract_auditor_from_report
from .extractors.company import extract_company_from_report
from .extractors.control_extractor import extract_controls
from .extractors.cuec_extractor import extract_cuecs
from .extractors.subservice_orgs import extract_subservice_orgs
from .extractors.product import extract_product_from_report
from .extractors.report_date import extract_report_date
from .extractors.coverage_period import extract_coverage_period
import logging
import traceback

def analyze_pdf_file(pdf_path, output_json_path='data/json/section_results.json', progress_callback=None, checklist_callback=None):

    logger = logging.getLogger(__name__)

    # Always resolve data paths relative to the project root
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    def data_path(rel_path):
        return os.path.join(PROJECT_ROOT, rel_path)

    def update_progress(percent, status=None):
        if progress_callback:
            progress_callback(percent, status)

    def update_checklist(statuses):
        if checklist_callback:
            checklist_callback(statuses)

    logger.debug(f"Starting analyze_pdf_file for {pdf_path}")
    if not os.path.isfile(pdf_path):
        logger.error(f"File {pdf_path} not found.")
        raise FileNotFoundError(f"File {pdf_path} not found.")

    # Patch all output/input paths to use root-level data directory
    global OUTPUT_TEXT_FILE
    global SECTION_JSON_PATH
    global AUDITOR_JSON_PATH
    global COMPANY_JSON_PATH
    global PDF_TXT_PATH
    OUTPUT_TEXT_FILE = data_path('data/output/output.txt')
    SECTION_JSON_PATH = data_path('data/json/section_results.json')
    AUDITOR_JSON_PATH = data_path('data/json/auditor_result.json')
    COMPANY_JSON_PATH = data_path('data/json/company_result.json')
    PDF_TXT_PATH = data_path('data/output/output.txt')

    try:
        # Always (re)generate section_results.json before running extractors
        update_progress(10, "Extracting text from PDF...")
        extract_text_from_pdf(pdf_path, OUTPUT_TEXT_FILE)
        logger.debug(f"Extracted text to {OUTPUT_TEXT_FILE}")
        update_progress(20, "Analyzing sections...")
        with open(OUTPUT_TEXT_FILE, 'r', encoding='utf-8') as f:
            text = f.read()
        section_results = find_section_candidates(text)
        logger.debug(f"Section candidates found: {len(section_results)}")
        # Add text snippets and line numbers, but preserve all other fields
        for section in section_results:
            if section.get('confidence', 0) > 0 and section.get('clean_heading') is not None:
                heading = section['clean_heading']
                offset = section.get('offset', None)
                if offset in (None, -1):
                    offset = text.find(heading)
                section['offset'] = offset if offset is not None and offset >= 0 else 0
                section['line'] = offset_to_line(text, section['offset']) if section['offset'] is not None and section['offset'] >= 0 else 0
                section['snippet'] = get_text_snippet(text, section['offset']) if section['offset'] is not None and section['offset'] >= 0 else ''
            else:
                if section.get('offset') is None:
                    section['offset'] = 0
                if section.get('line') is None:
                    section['line'] = 0
                if section.get('snippet') is None:
                    section['snippet'] = ''
        # Always write section_results.json before running extractors
        try:
            os.makedirs(os.path.dirname(data_path(output_json_path)), exist_ok=True)
            with open(data_path(output_json_path), 'w', encoding='utf-8') as jf:
                json.dump(section_results, jf, indent=2)
            logger.debug(f"Section results saved to {output_json_path}")
        except Exception as e:
            logger.error(f"Failed to write {output_json_path}: {e}\n{traceback.format_exc()}")
            update_progress(100, f"Failed to write {output_json_path}.")
            return {"error": f"Failed to write {output_json_path}: {e}"}

        # --- Enhanced checklist: file upload, text extraction, section extraction, then extractors ---
        checklist = [
            {"name": "file_uploaded", "status": "pending"},
            {"name": "text_extracted", "status": "pending"},
            {"name": "sections_extracted", "status": "pending"},
            {"name": "company", "status": "pending"},
            {"name": "auditor", "status": "pending"},
            {"name": "controls", "status": "pending"},
            {"name": "cuecs", "status": "pending"},
            {"name": "subservice_orgs", "status": "pending"},
            {"name": "product", "status": "pending"},
            {"name": "report_date", "status": "pending"},
            {"name": "coverage_period", "status": "pending"},
        ]
        # 0: file_uploaded
        checklist[0]["status"] = "done"
        update_checklist(checklist)
        # 1: text_extracted
        checklist[1]["status"] = "done"
        update_checklist(checklist)
        # 2: sections_extracted
        checklist[2]["status"] = "done"
        update_checklist(checklist)
        results = {}
        results['sections'] = section_results
        # Check for section_results.json existence before running extractors
        if not os.path.isfile(data_path(output_json_path)):
            logger.error(f"Required file {output_json_path} not found before running extractors.")
            update_progress(100, "Required file missing before extractors.")
            return {"error": f"Required file {output_json_path} not found before running extractors."}
        # --- Run company and auditor sequentially (prerequisites) ---
        prereq_steps = [
            (3, "company", extract_company_from_report, "Running company extractor...", 30),
            (4, "auditor", extract_auditor_from_report, "Running auditor extractor...", 40),
        ]
        parallel_steps = [
            (5, "controls", extract_controls, "Running controls extractor...", 50),
            (6, "cuecs", extract_cuecs, "Running CUECs extractor...", 60),
            (7, "subservice_orgs", extract_subservice_orgs, "Running subservice orgs extractor...", 70),
            (8, "product", extract_product_from_report, "Running product extractor...", 80),
            (9, "report_date", extract_report_date, "Running report date extractor...", 90),
            (10, "coverage_period", extract_coverage_period, "Running coverage period extractor...", 95),
        ]
        # Run prerequisites sequentially
        for idx, key, func, status, pct in prereq_steps:
            try:
                update_progress(pct, status)
                logger.debug(f"{status}")
                results[key] = func()
                logger.debug(f"{key}: {results[key]}")
                checklist[idx]["status"] = "done"
            except Exception as e:
                logger.error(f"{key} extractor failed: {e}\n{traceback.format_exc()}")
                partial_path = None
                if key == 'auditor':
                    partial_path = data_path('data/json/auditor_result.json')
                elif key == 'company':
                    partial_path = data_path('data/json/company_result.json')
                if partial_path and os.path.isfile(partial_path):
                    try:
                        with open(partial_path, 'r', encoding='utf-8') as pf:
                            results[key] = json.load(pf)
                        checklist[idx]["status"] = "partial"
                    except Exception as e2:
                        logger.error(f"Failed to load partial result for {key}: {e2}")
                        results[key] = None
            # Update checklist in Redis after each sequential extractor
            update_checklist(checklist)
        # --- Run remaining extractors in parallel threads ---
        from concurrent.futures import ThreadPoolExecutor, as_completed
        def run_extractor(idx, key, func, status, pct):
            try:
                update_progress(pct, status)
                logger.debug(f"{status}")
                res = func()
                logger.debug(f"{key}: {res}")
                # If result is None but JSON file exists, try to load it
                if res is None:
                    partial_path = None
                    if key == 'controls':
                        partial_path = data_path('data/json/control_result.json')
                    elif key == 'cuecs':
                        partial_path = data_path('data/json/cuec_result.json')
                    elif key == 'subservice_orgs':
                        partial_path = data_path('data/json/subservice_orgs_result.json')
                    elif key == 'product':
                        partial_path = data_path('data/json/product_result.json')
                    elif key == 'report_date':
                        partial_path = data_path('data/json/report_date_result.json')
                    elif key == 'coverage_period':
                        partial_path = data_path('data/json/coverage_period_result.json')
                    if partial_path and os.path.isfile(partial_path):
                        try:
                            with open(partial_path, 'r', encoding='utf-8') as pf:
                                res = json.load(pf)
                            checklist[idx]["status"] = "partial"
                            update_checklist(checklist)
                            return key, res
                        except Exception as e2:
                            logger.error(f"Failed to load partial result for {key}: {e2}")
                # If there are bad_chunks, mark as done_with_warnings
                if key in ('controls', 'cuecs'):
                    bad_chunk_count = 0
                    if res and isinstance(res, dict):
                        bad_chunk_count = res.get('bad_chunk_count', 0)
                    if bad_chunk_count > 0:
                        checklist[idx]["status"] = "done_with_warnings"
                        update_checklist(checklist)
                        return key, res
                checklist[idx]["status"] = "done"
                update_checklist(checklist)
                return key, res
            except Exception as e:
                logger.error(f"{key} extractor failed: {e}\n{traceback.format_exc()}")
                partial_path = None
                if key == 'controls':
                    partial_path = data_path('data/json/control_result.json')
                elif key == 'cuecs':
                    partial_path = data_path('data/json/cuec_result.json')
                elif key == 'subservice_orgs':
                    partial_path = data_path('data/json/subservice_orgs_result.json')
                elif key == 'product':
                    partial_path = data_path('data/json/product_result.json')
                elif key == 'report_date':
                    partial_path = data_path('data/json/report_date_result.json')
                elif key == 'coverage_period':
                    partial_path = data_path('data/json/coverage_period_result.json')
                if partial_path and os.path.isfile(partial_path):
                    try:
                        with open(partial_path, 'r', encoding='utf-8') as pf:
                            res = json.load(pf)
                        checklist[idx]["status"] = "partial"
                        update_checklist(checklist)
                        return key, res
                    except Exception as e2:
                        logger.error(f"Failed to load partial result for {key}: {e2}")
                checklist[idx]["status"] = "error"
                update_checklist(checklist)
                return key, None
        # Map parallel steps to their indices in the checklist
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(run_extractor, idx, key, func, status, pct)
                       for (idx, key, func, status, pct) in parallel_steps]
            for future in as_completed(futures):
                key, res = future.result()
                results[key] = res
            update_checklist(checklist)
        update_progress(100, "Analysis complete.")
        logger.debug(f"Final results: {results}")
        return results
    except Exception as e:
        logger.error(f"analyze_pdf_file failed: {e}\n{traceback.format_exc()}")
        update_progress(100, "Analysis failed.")
        return {"error": str(e)}

import argparse
import json
import os
from .pdf_handler import extract_text_from_pdf, find_section_candidates
from .config import SOC2_REPORTS_DIR, OUTPUT_TEXT_FILE

def get_text_snippet(text, offset, context=200):
    start = max(0, offset - context)
    end = min(len(text), offset + context)
    return text[start:end]

def offset_to_line(text, offset):
    return text[:offset].count('\n') + 1

def main():
    parser = argparse.ArgumentParser(description="Extract text from a SOC 2 PDF report and analyze sections.")
    parser.add_argument('--file', type=str, help='PDF filename in soc2_reports to analyze')
    parser.add_argument('--json', type=str, default='data/json/section_results.json', help='Output JSON file for section results')
    args = parser.parse_args()

    if args.file:
        pdf_path = os.path.join(SOC2_REPORTS_DIR, args.file)
        if not os.path.isfile(pdf_path):
            print(f"File {args.file} not found in soc2_reports.")
            return
    else:
        pdf_files = [f for f in os.listdir(SOC2_REPORTS_DIR) if f.lower().endswith('.pdf')]
        if not pdf_files:
            print("No PDF files found in soc2_reports.")
            return
        pdf_path = os.path.join(SOC2_REPORTS_DIR, pdf_files[0])

    extract_text_from_pdf(pdf_path, OUTPUT_TEXT_FILE)
    print(f"Extracted text from {pdf_path} to {OUTPUT_TEXT_FILE}")

    # Call robust GPT section analysis after extraction
    with open(OUTPUT_TEXT_FILE, 'r', encoding='utf-8') as f:
        text = f.read()
    total_chars = len(text)
    print(f"Total character count: {total_chars}")
    section_results = find_section_candidates(text)  # changed function call
    print("\nSection positions and confidence:")
    print(json.dumps(section_results, indent=2))

    # Add text snippets and line numbers, but preserve all other fields
    for section in section_results:
        # Only update/add offset, line, snippet; preserve all other fields
        if section.get('confidence', 0) > 0 and section.get('clean_heading') is not None:
            heading = section['clean_heading']
            offset = section.get('offset', None)
            if offset in (None, -1):
                offset = text.find(heading)
            section['offset'] = offset if offset is not None and offset >= 0 else 0
            section['line'] = offset_to_line(text, section['offset']) if section['offset'] is not None and section['offset'] >= 0 else 0
            section['snippet'] = get_text_snippet(text, section['offset']) if section['offset'] is not None and section['offset'] >= 0 else ''
        else:
            if section.get('offset') is None:
                section['offset'] = 0
            if section.get('line') is None:
                section['line'] = 0
            if section.get('snippet') is None:
                section['snippet'] = ''
    # Print details to console
    print("\nSection details:")
    for section in section_results:
        print(f"Topic: {section.get('topic')} | Offset: {section.get('offset')} | Line: {section.get('line')} | Confidence: {section.get('confidence')}%\nSnippet:\n{section.get('snippet')}\n{'-'*60}")
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as jf:
            json.dump(section_results, jf, indent=2)
        print(f"Section results with snippets saved to {args.json}")
    else:
        print("No JSON output file specified.")

if __name__ == "__main__":
    main()

# Expose analyze_pdf_file for import
__all__ = ["analyze_pdf_file"]
