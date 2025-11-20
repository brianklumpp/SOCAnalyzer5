# --- All imports at the top (PEP8 best practice) ---
import os
import json
import logging
import traceback
import argparse
import time  # Added missing import for watchdog timing and progress tracking
# ThreadPoolExecutor removed - now using sequential processing for stability
from .extractors.auditor import extract_auditor_from_report
from .extractors.company import extract_company_from_report
from .extractors.control_integration import extract_controls  # V2/V4 unified interface
# CUEC extractor routing (SOC1, SOC2, Combined)
# Import will be done dynamically based on report_type
from .extractors.subservice_orgs import extract_subservice_orgs, filter_third_parties_with_gpt
from .extractors.product import extract_product_from_report
from .extractors.report_date import extract_report_date
from .extractors.coverage_period import extract_coverage_period
from .pdf_handler import extract_text_from_pdf, find_section_candidates
from . import config
from .models import ReportType
import glob


def validate_report_type(report_type_str):
    """
    Validate and convert report_type string to ReportType enum.
    
    Args:
        report_type_str: String value ('SOC1', 'SOC2', 'COMBINED', or None for default)
        
    Returns:
        ReportType enum value
        
    Raises:
        ValueError: If report_type_str is invalid
    """
    if report_type_str is None or report_type_str == '':
        return ReportType.SOC2  # Default to SOC2 for backward compatibility
    
    # Normalize input
    report_type_upper = str(report_type_str).strip().upper()
    
    # Try to match to enum
    try:
        return ReportType[report_type_upper]
    except KeyError:
        valid_types = ', '.join([t.value for t in ReportType])
        raise ValueError(f"Invalid report_type '{report_type_str}'. Must be one of: {valid_types}")


def analyze_pdf_file(pdf_path, output_json_path='data/json/section_results.json', report_type='SOC2', 
                      progress_callback=None, checklist_callback=None):
    # Reset GPT tracking at start of analysis
    from .gpt_tracker import reset_tracking, get_usage_summary
    reset_tracking()
    logger = logging.getLogger(__name__)
    
    # Track start time for elapsed_seconds
    import time
    analysis_start_time = time.time()
    
    # Validate and normalize report_type
    try:
        validated_report_type = validate_report_type(report_type)
        logger.info(f"Analysis starting for report type: {validated_report_type.value}")
    except ValueError as e:
        logger.error(f"Invalid report_type: {e}")
        raise

    # --- Reset logs and JSON outputs at the start of each run ---
    # List of files to clear
    files_to_clear = [
        str(config.JSON_DIR / 'section_results.json'),
        str(config.JSON_DIR / 'control_result.json'),
        str(config.JSON_DIR / 'cuec_result.json'),
        str(config.JSON_DIR / 'auditor_result.json'),
        str(config.JSON_DIR / 'company_result.json'),
        str(config.JSON_DIR / 'product_result.json'),
        str(config.JSON_DIR / 'report_date_result.json'),
        str(config.JSON_DIR / 'coverage_period_result.json'),
        str(config.JSON_DIR / 'subservice_orgs_result.json'),
        str(config.LOGS_DIR / 'control_gpt.log'),
        str(config.LOGS_DIR / 'cuec_extractor.log'),
        str(config.LOGS_DIR / 'backend_errors.log'),
        str(config.LOGS_DIR / 'section_gpt_responses.log'),
    # control_extractor.log (v1) removed; v2 logs to control_extractor_v2.log
        str(config.LOGS_DIR / 'subservice_orgs_extractor.log'),
        str(config.LOGS_DIR / 'product_extractor.log'),
        str(config.LOGS_DIR / 'auditor_extractor.log'),
        str(config.LOGS_DIR / 'company_extractor.log'),
        str(config.LOGS_DIR / 'coverage_period_extractor.log'),
        str(config.LOGS_DIR / 'report_date_extractor.log'),
    ]
    for f in files_to_clear:
        try:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            # For JSON outputs, write an empty JSON object to avoid stale content
            if f.replace('\\', '/').endswith('/data/json/section_results.json'):
                # Section results will be regenerated below; start with an empty array for clarity
                with open(f, 'w', encoding='utf-8') as clearf:
                    clearf.write('[]')
            elif '/data/json/' in f.replace('\\', '/') and f.lower().endswith('.json'):
                with open(f, 'w', encoding='utf-8') as clearf:
                    clearf.write('{}')
            else:
                # Logs and other files: truncate
                with open(f, 'w', encoding='utf-8') as clearf:
                    clearf.truncate(0)
        except Exception:
            # Ignore if file does not exist yet or cannot be written; downstream steps will recreate as needed
            pass
    # Special-case: do NOT pre-create/overwrite combined_result.json; remove it if present to indicate not-yet-written
    try:
        _combined_path = str(config.JSON_DIR / 'combined_result.json')
        if os.path.isfile(_combined_path):
            os.remove(_combined_path)
    except Exception:
        pass

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

    # Helper for control extraction progress based on section end_line
    control_section = None
    try:
        with open(SECTION_JSON_PATH, 'r', encoding='utf-8') as sf:
            _secs = json.load(sf)
            control_section = next((s for s in _secs if s.get('topic') == 'Control_Descriptions'), None)
    except Exception:
        control_section = None

    def _control_progress_hook(latest_ctrl_end_line: int):
        try:
            if progress_callback and control_section and isinstance(control_section.get('end_line'), int):
                ctrl_end = max(0, latest_ctrl_end_line)
                sec_end = max(1, control_section['end_line'])
                pct = 50 + int(45 * min(1.0, ctrl_end / float(sec_end)))
                progress_callback(pct, f"Controls {ctrl_end}/{sec_end}")
        except Exception:
            pass

    # Install progress hook for control extractor (v2 only - v4 doesn't support hooks yet)
    control_version = getattr(config, 'CONTROL_EXTRACTOR_VERSION', 'v4')
    if control_version == 'v2':
        try:
            from .extractors.control_extractor_v2 import set_progress_hook as _set_ctrl_hook
            _set_ctrl_hook(_control_progress_hook)
        except Exception:
            pass

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
                section['start_line'] = offset_to_line(text, section['offset']) if section['offset'] is not None and section['offset'] >= 0 else 0
                # Remove old 'line' field if present
                if 'line' in section:
                    del section['line']
                section['snippet'] = get_text_snippet(text, section['offset']) if section['offset'] is not None and section['offset'] >= 0 else ''
                # Set 'end_line' if not present and possible (e.g., from next section or known logic)
                # (Leave as-is if already set)
            else:
                if section.get('offset') is None:
                    section['offset'] = 0
                if section.get('start_line') is None:
                    section['start_line'] = 0
                if 'line' in section:
                    del section['line']
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
            {"name": "company_extraction", "status": "pending"},
            {"name": "auditor_extraction", "status": "pending"},
            {"name": "control_extraction", "status": "pending"},
            {"name": "cuec_extraction", "status": "pending"},
            {"name": "subservice_orgs_extraction", "status": "pending"},
            {"name": "product_extraction", "status": "pending"},
            {"name": "report_date_extraction", "status": "pending"},
            {"name": "coverage_period_extraction", "status": "pending"},
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
        # Wrapper for subservice_orgs to run both extraction and filtering sequentially
        def _run_subservice_orgs_extraction():
            """Run subservice extraction + GPT filtering, return final filtered result.

            Also write a debug dump of the direct return value to
            `data/logs/debug_subservice_postrun_dump.json` so end-to-end runs
            can be compared with isolated extractor runs.
            """
            try:
                extract_subservice_orgs()  # Extracts and writes raw results to JSON
            except Exception:
                # Let downstream filter attempt to load partial results if available
                pass
            try:
                res = filter_third_parties_with_gpt()  # Reads JSON, filters, writes back, returns result
            except Exception as e:
                # If filtering fails, attempt to load on-disk JSON as a fallback
                try:
                    proj = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    fallback_p = os.path.join(proj, 'data', 'json', 'subservice_orgs_result.json')
                    if os.path.isfile(fallback_p):
                        with open(fallback_p, 'r', encoding='utf-8') as pf:
                            res = json.load(pf)
                    else:
                        raise
                except Exception:
                    # Re-raise original filtering error if fallback also fails
                    raise
            # Write a debug post-run dump for immediate inspection by the analyzer
            try:
                proj = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                log_dir = os.path.join(proj, 'data', 'logs')
                os.makedirs(log_dir, exist_ok=True)
                dump_path = os.path.join(log_dir, 'debug_subservice_postrun_dump.json')
                with open(dump_path, 'w', encoding='utf-8') as df:
                    json.dump({'type': str(type(res)), 'value': res}, df, indent=2, ensure_ascii=False)
            except Exception:
                # Non-fatal: don't let debug write break extraction
                pass
            return res
        
        # Wrapper for control extraction - routes based on report_type
        def _run_control_extraction():
            """
            Run control extraction using report_type routing:
            - SOC1 → control_extractor_v4_soc1.py
            - SOC2 → control_extractor_v4.py (default)
            - COMBINED → control_extractor_combined.py
            """
            # Determine extractor version based on report_type
            if report_type == 'SOC1':
                version = 'v4_soc1'
                logger.info(f"Routing to SOC 1 control extractor (report_type={report_type})")
            elif report_type == 'COMBINED':
                version = 'combined'
                logger.info(f"Routing to Combined control extractor (report_type={report_type})")
            else:
                # Default: SOC 2
                version = getattr(config, 'CONTROL_EXTRACTOR_VERSION', 'v4')
                logger.info(f"Routing to SOC 2 control extractor (version={version}, report_type={report_type})")
            
            extract_controls(version=version)
            # All extractors write to config.CONTROL_JSON_PATH
            with open(config.CONTROL_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("controls", [])
        
        # Wrapper for CUEC extraction - routes based on report_type
        def _run_cuec_extraction():
            """
            Run CUEC extraction using report_type routing:
            - SOC1 → cuec_extractor_soc1.py (financial reporting keywords)
            - SOC2 → cuec_extractor.py (default)
            - COMBINED → cuec_extractor.py (default to SOC 2 logic)
            """
            if report_type == 'SOC1':
                from .extractors.cuec_extractor_soc1 import extract_cuecs as extract_cuecs_soc1
                logger.info(f"Routing to SOC 1 CUEC extractor (report_type={report_type})")
                return extract_cuecs_soc1()
            else:
                # Default: SOC 2 CUEC extractor
                from .extractors.cuec_extractor import extract_cuecs
                logger.info(f"Routing to SOC 2 CUEC extractor (report_type={report_type})")
                return extract_cuecs()
        
        prereq_steps = [
            (3, "company_extraction", extract_company_from_report, "Running company extractor...", 30),
            (4, "auditor_extraction", extract_auditor_from_report, "Running auditor extractor...", 40),
        ]
        parallel_steps = [
            (5, "control_extraction", _run_control_extraction, "Running controls extractor...", 50),
            (6, "cuec_extraction", _run_cuec_extraction, "Running CUECs extractor...", 60),
            (7, "subservice_orgs_extraction", _run_subservice_orgs_extraction, "Running subservice orgs extractor...", 70),
            (8, "product_extraction", extract_product_from_report, "Running product extractor...", 80),
            (9, "report_date_extraction", extract_report_date, "Running report date extractor...", 90),
            (10, "coverage_period_extraction", extract_coverage_period, "Running coverage period extractor...", 95),
        ]

        # Watchdog: if controls extractor runs too long without increasing result size, mark as partial and continue
        CONTROL_WATCHDOG_ENABLED = getattr(config, 'CONTROL_WATCHDOG_ENABLED', True)
        CONTROL_WATCHDOG_MAX_MINUTES = getattr(config, 'CONTROL_WATCHDOG_MAX_MINUTES', 25)
        _ctrl_last_count = 0
        _ctrl_last_time = time.time()
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
                # Attempt to load any partial JSON result if present to avoid stale data in memory
                partial_path = None
                if key == 'auditor_extraction':
                    partial_path = data_path('data/json/auditor_result.json')
                elif key == 'company_extraction':
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
        # Predefine flatten map for building standardized results (also used for partial writes)
        flatten_map = {
            'control_extraction': ('controls', 'controls'),
            'cuec_extraction': ('cuecs', 'cuecs'),
            # The subservice extractor writes a top-level 'subservice_orgs' list
            # so use that as the inner key here to ensure the analyzer treats
            # it as a list and runs enhancement/deduplication consistently.
            'subservice_orgs_extraction': ('subservice_orgs', 'subservice_orgs'),
            'product_extraction': ('product', 'product'),
            'auditor_extraction': ('auditor', 'auditor'),
            'company_extraction': ('company', 'company'),
            'report_date_extraction': ('report_date', 'report_date'),
            'coverage_period_extraction': ('coverage_period', 'coverage_period'),
        }

        def _write_partial_combined(current_results: dict):
            try:
                standardized_partial = {}
                for ext_key, (short_key, inner_key) in flatten_map.items():
                    val = current_results.get(ext_key)
                    if val is None:
                        continue
                    if isinstance(val, dict) and inner_key in val:
                        if short_key == 'controls' and isinstance(val[inner_key], list):
                            standardized_partial[short_key] = [dict(c) for c in val[inner_key]]
                        else:
                            standardized_partial[short_key] = val[inner_key]
                    else:
                        standardized_partial[short_key] = val
                if standardized_partial:
                    standardized_partial['sections'] = results.get('sections', [])
                    combined_result_path = data_path('data/json/combined_result.json')
                    with open(combined_result_path, 'w', encoding='utf-8') as f:
                        json.dump(standardized_partial, f, indent=2, ensure_ascii=False)
            except Exception as _p_err:
                logger.error(f"Failed partial combined write: {_p_err}")

        # --- Run remaining extractors in parallel threads ---
        extractor_results = {}
        def run_extractor(idx, key, func, status, pct):
            try:
                update_progress(pct, status)
                logger.debug(f"{status}")
                res = func()
                logger.debug(f"{key}: {res}")
                # If controls extractor returned a list or dict with controls, update watchdog metrics
                if key == 'control_extraction':
                    try:
                        if isinstance(res, dict) and isinstance(res.get('controls'), list):
                            current_count = len(res['controls'])
                        elif isinstance(res, list):
                            current_count = len(res)
                        else:
                            current_count = 0
                        if current_count > _ctrl_last_count:
                            _ctrl_last_count = current_count
                            _ctrl_last_time = time.time()
                    except Exception:
                        pass
                # If result is None but JSON file exists, try to load it
                if res is None:
                    partial_path = None
                    if key == 'control_extraction':
                        partial_path = data_path('data/json/control_result.json')
                    elif key == 'cuec_extraction':
                        partial_path = data_path('data/json/cuec_result.json')
                    elif key == 'subservice_orgs_extraction':
                        partial_path = data_path('data/json/subservice_orgs_result.json')
                    elif key == 'product_extraction':
                        partial_path = data_path('data/json/product_result.json')
                    elif key == 'report_date_extraction':
                        partial_path = data_path('data/json/report_date_result.json')
                    elif key == 'coverage_period_extraction':
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
                if key in ('control_extraction', 'cuec_extraction'):
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
                # Attempt to load any partial JSON result if present
                partial_path = None
                if key == 'control_extraction':
                    partial_path = data_path('data/json/control_result.json')
                elif key == 'cuec_extraction':
                    partial_path = data_path('data/json/cuec_result.json')
                elif key == 'subservice_orgs_extraction':
                    partial_path = data_path('data/json/subservice_orgs_result.json')
                elif key == 'product_extraction':
                    partial_path = data_path('data/json/product_result.json')
                elif key == 'report_date_extraction':
                    partial_path = data_path('data/json/report_date_result.json')
                elif key == 'coverage_period_extraction':
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
                return key, None
        
        # === CHECKPOINT SYSTEM ===
        CHECKPOINT_PATH = data_path('data/json/_extraction_checkpoint.json')
        def save_checkpoint(completed_extractors):
            """Save current extraction progress to checkpoint file."""
            try:
                checkpoint_data = {
                    'timestamp': time.time(),
                    'completed': completed_extractors,
                    'checklist': checklist
                }
                with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as cf:
                    json.dump(checkpoint_data, cf, indent=2)
                logger.info(f"Checkpoint saved: {len(completed_extractors)} extractors completed")
            except Exception as e:
                logger.error(f"Failed to save checkpoint: {e}")
        
        def load_checkpoint():
            """Load checkpoint and return list of completed extractors."""
            try:
                if os.path.isfile(CHECKPOINT_PATH):
                    with open(CHECKPOINT_PATH, 'r', encoding='utf-8') as cf:
                        data = json.load(cf)
                    completed = data.get('completed', [])
                    saved_checklist = data.get('checklist', [])
                    logger.info(f"Checkpoint loaded: {len(completed)} extractors previously completed")
                    return completed, saved_checklist
            except Exception as e:
                logger.error(f"Failed to load checkpoint: {e}")
            return [], []
        
        # Load checkpoint to resume from previous run
        completed_extractors, saved_checklist = load_checkpoint()
        if saved_checklist:
            # Restore checklist state from checkpoint
            checklist = saved_checklist
            update_checklist(checklist)
        
        # Filter parallel steps to skip already completed extractors
        if completed_extractors:
            logger.info(f"Resuming from checkpoint, skipping: {completed_extractors}")
            parallel_steps = [(idx, key, func, status, pct) for (idx, key, func, status, pct) in parallel_steps 
                             if key not in completed_extractors]
        
        # SEQUENTIAL PROCESSING: Run extractors one at a time for maximum stability
        # No threading, no race conditions, no DNS threading issues
        logger.info("Running extractors SEQUENTIALLY (no parallel workers)")
        for idx, key, func, status, pct in parallel_steps:
            logger.info(f"Starting extractor '{key}' (sequential mode)")
            try:
                k, res = run_extractor(idx, key, func, status, pct)
                extractor_results[k] = res
                logger.info(f"Extractor '{k}' completed successfully")
                
                # Add to checkpoint after each completion
                if k not in completed_extractors:
                    completed_extractors.append(k)
                    save_checkpoint(completed_extractors)
                    
            except Exception as e:
                logger.error(f"Extractor '{key}' raised exception: {e}\n{traceback.format_exc()}")
                extractor_results[key] = None
                # Mark as failed in checklist but continue with remaining extractors
                for item in checklist:
                    if item.get('name') == key:
                        item['status'] = 'error'
                        break
                update_checklist(checklist)
                
            finally:
                # Write partial combined_result.json after each extractor
                _write_partial_combined(extractor_results)
            
        # --- Always load extractor outputs from JSON files if present ---
        extractor_json_map = {
            'control_extraction': 'data/json/control_result.json',
            'cuec_extraction': 'data/json/cuec_result.json',
            'subservice_orgs_extraction': 'data/json/subservice_orgs_result.json',
            'product_extraction': 'data/json/product_result.json',
            'auditor_extraction': 'data/json/auditor_result.json',
            'company_extraction': 'data/json/company_result.json',
            'report_date_extraction': 'data/json/report_date_result.json',
            'coverage_period_extraction': 'data/json/coverage_period_result.json',
        }
        for ext_key, json_path in extractor_json_map.items():
            fpath = data_path(json_path)
            if os.path.isfile(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as pf:
                        extractor_results[ext_key] = json.load(pf)
                except Exception as e:
                    logger.error(f"Failed to load {json_path} for {ext_key}: {e}")
        # --- FLATTEN AND ENFORCE: Only short keys in final result ---
        standardized_results = {}
        # Debug: persist the raw extractor result for subservice orgs to help
        # diagnose cases where the analyzer ends up with a dict instead of
        # the expected list. This file is inspected when troubleshooting.
        try:
            debug_so = extractor_results.get('subservice_orgs_extraction')
            debug_path = str(config.LOGS_DIR / 'debug_subservice_extraction_result.json')
            with open(debug_path, 'w', encoding='utf-8') as df:
                json.dump(debug_so, df, indent=2, ensure_ascii=False)
        except Exception:
            pass
        for ext_key, (short_key, inner_key) in flatten_map.items():
            val = extractor_results.get(ext_key)
            if val is not None:
                if isinstance(val, dict) and inner_key in val:
                    if short_key == 'controls' and isinstance(val[inner_key], list):
                        standardized_results[short_key] = [dict(c) for c in val[inner_key]]
                    else:
                        standardized_results[short_key] = val[inner_key]
                else:
                    standardized_results[short_key] = val
        # Persist bad_chunks from cuec and controls into standardized_results so they are stored with the scan
        try:
            if isinstance(extractor_results.get('cuec_extraction'), dict):
                cuec_res = extractor_results['cuec_extraction']
                if isinstance(cuec_res.get('bad_chunks'), list) and len(cuec_res['bad_chunks']) > 0:
                    standardized_results.setdefault('cuecs', {})  # ensure key exists
                    if isinstance(standardized_results['cuecs'], list):
                        # keep list of cuecs as-is; add a sibling metadata container
                        standardized_results.setdefault('cuecs_meta', {})
                        standardized_results['cuecs_meta']['bad_chunks'] = cuec_res['bad_chunks']
                        standardized_results['cuecs_meta']['bad_chunk_count'] = cuec_res.get('bad_chunk_count', len(cuec_res['bad_chunks']))
                    elif isinstance(standardized_results['cuecs'], dict):
                        standardized_results['cuecs']['bad_chunks'] = cuec_res['bad_chunks']
                        standardized_results['cuecs']['bad_chunk_count'] = cuec_res.get('bad_chunk_count', len(cuec_res['bad_chunks']))
            if isinstance(extractor_results.get('control_extraction'), dict):
                ctrl_res = extractor_results['control_extraction']
                if isinstance(ctrl_res.get('bad_chunks'), list) and len(ctrl_res['bad_chunks']) > 0:
                    standardized_results.setdefault('controls', {})
                    if isinstance(standardized_results['controls'], list):
                        standardized_results.setdefault('controls_meta', {})
                        standardized_results['controls_meta']['bad_chunks'] = ctrl_res['bad_chunks']
                        standardized_results['controls_meta']['bad_chunk_count'] = ctrl_res.get('bad_chunk_count', len(ctrl_res['bad_chunks']))
                    elif isinstance(standardized_results['controls'], dict):
                        standardized_results['controls']['bad_chunks'] = ctrl_res['bad_chunks']
                        standardized_results['controls']['bad_chunk_count'] = ctrl_res.get('bad_chunk_count', len(ctrl_res['bad_chunks']))
            if isinstance(extractor_results.get('subservice_orgs_extraction'), dict):
                so_res = extractor_results['subservice_orgs_extraction']
                if isinstance(so_res.get('bad_chunks'), list) and len(so_res['bad_chunks']) > 0:
                    standardized_results.setdefault('subservice_orgs', {})
                    if isinstance(standardized_results['subservice_orgs'], list):
                        standardized_results.setdefault('subservice_orgs_meta', {})
                        standardized_results['subservice_orgs_meta']['bad_chunks'] = so_res['bad_chunks']
                        standardized_results['subservice_orgs_meta']['bad_chunk_count'] = so_res.get('bad_chunk_count', len(so_res['bad_chunks']))
                    elif isinstance(standardized_results['subservice_orgs'], dict):
                        standardized_results['subservice_orgs']['bad_chunks'] = so_res['bad_chunks']
                        standardized_results['subservice_orgs']['bad_chunk_count'] = so_res.get('bad_chunk_count', len(so_res['bad_chunks']))
        except Exception:
            pass
        # Always include sections
        standardized_results['sections'] = results.get('sections', [])
        # --- VALIDATION AND LOGGING ---
        log_path = str(config.LOGS_DIR / 'backend_errors.log')
        with open(log_path, 'a', encoding='utf-8') as logf:
            logf.write('\n[STANDARDIZED RESULT VALIDATION]\n')
            for key in flatten_map.values():
                short_key = key[0]
                val = standardized_results.get(short_key, None)
                if val is None:
                    logf.write(f"Missing key: {short_key}\n")
                else:
                    if isinstance(val, list):
                        logf.write(f"{short_key}: list, len={len(val)}\n")
                    elif isinstance(val, dict):
                        logf.write(f"{short_key}: dict, keys={list(val.keys())}\n")
                    else:
                        logf.write(f"{short_key}: type={type(val)}\n")
            logf.write(f"Full standardized results keys: {list(standardized_results.keys())}\n")
        update_progress(100, "Analysis complete.")
        logger.debug(f"Final standardized results: {standardized_results}")

        # Ensure subservice orgs deduplication/enhancement is applied to the
        # standardized results even when the extractor ran previously or when
        # results were loaded from disk. This guarantees canonicalization and
        # confidence adjustments are consistently executed as part of the
        # regular workflow.
        try:
            if isinstance(standardized_results.get('subservice_orgs'), list) and len(standardized_results.get('subservice_orgs')) > 0:
                logger.info("Applying subservice orgs enhancement/dedup to standardized results...")
                try:
                    from .extractors.subservice_orgs_dedup import enhance_subservice_orgs
                    standardized_results['subservice_orgs'] = enhance_subservice_orgs(standardized_results['subservice_orgs'])
                    logger.info("Subservice orgs enhancement complete; reduced to %d entries", len(standardized_results['subservice_orgs']))
                except Exception as e:
                    logger.exception("Failed to run subservice orgs enhancement: %s", e)
        except Exception:
            logger.exception("Unexpected error while attempting to enhance subservice orgs")

        # Add extracted text from output.txt to results
        try:
            with open(OUTPUT_TEXT_FILE, 'r', encoding='utf-8') as f:
                extracted_text = f.read()
            standardized_results["extracted_text"] = extracted_text
            logger.debug(f"Added extracted text to results ({len(extracted_text)} characters)")
        except Exception as e:
            logger.error(f"Failed to read extracted text from {OUTPUT_TEXT_FILE}: {e}")
            standardized_results["extracted_text"] = None
        
        # Add GPT usage summary to results
        gpt_summary = get_usage_summary()
        standardized_results.update(gpt_summary)
        logger.debug(f"Added GPT usage summary: {gpt_summary['total_calls']} calls, ${gpt_summary['gpt_cost']}")
        
        # Add report type to results
        standardized_results["report_type"] = validated_report_type.value
        logger.debug(f"Added report type: {validated_report_type.value}")
        
        # Add elapsed time to results
        elapsed_seconds = time.time() - analysis_start_time
        standardized_results["elapsed_seconds"] = elapsed_seconds
        logger.debug(f"Analysis completed in {elapsed_seconds:.1f} seconds")
        
        # Add PDF filename and file bytes to results for database storage
        try:
            standardized_results["pdf_filename"] = os.path.basename(pdf_path)
            logger.debug(f"Added PDF filename: {standardized_results['pdf_filename']}")
            
            # Read PDF file as binary and store as bytes
            with open(pdf_path, 'rb') as pdf_file:
                pdf_bytes = pdf_file.read()
            standardized_results["pdf_file"] = pdf_bytes
            logger.debug(f"Added PDF file ({len(pdf_bytes)} bytes)")
        except Exception as e:
            logger.error(f"Failed to read PDF file {pdf_path}: {e}")
            standardized_results["pdf_filename"] = None
            standardized_results["pdf_file"] = None
        
        # --- Write combined extraction result to a file for troubleshooting ---
        try:
            combined_result_path = data_path('data/json/combined_result.json')
            # Don't write pdf_file bytes to JSON (not JSON-serializable)
            results_for_json = {k: v for k, v in standardized_results.items() if k != 'pdf_file'}
            with open(combined_result_path, 'w', encoding='utf-8') as f:
                json.dump(results_for_json, f, indent=2, ensure_ascii=False)
            logger.info(f"Combined extraction result written to {combined_result_path}")
        except Exception as e:
            logger.error(f"Failed to write combined_result.json: {e}\n{traceback.format_exc()}")
        return standardized_results
    except Exception as e:
        logger.error(f"analyze_pdf_file failed: {e}\n{traceback.format_exc()}")
        update_progress(100, "Analysis failed.")
        return {"error": str(e)}

import argparse
import json
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
        if section.get('confidence', 0) > 0 and section.get('clean_heading') is not None:
            heading = section['clean_heading']
            offset = section.get('offset', None)
            if offset in (None, -1):
                offset = text.find(heading)
            section['offset'] = offset if offset is not None and offset >= 0 else 0
            section['start_line'] = offset_to_line(text, section['offset']) if section['offset'] is not None and section['offset'] >= 0 else 0
            # Remove old 'line' field if present
            if 'line' in section:
                del section['line']
            section['snippet'] = get_text_snippet(text, section['offset']) if section['offset'] is not None and section['offset'] >= 0 else ''
            # Set 'end_line' if not present and possible (e.g., from next section or known logic)
            # (Leave as-is if already set)
        else:
            if section.get('offset') is None:
                section['offset'] = 0
            if section.get('start_line') is None:
                section['start_line'] = 0
            if 'line' in section:
                del section['line']
            if section.get('snippet') is None:
                section['snippet'] = ''
    # Print details to console
    print("\nSection details:")
    for section in section_results:
        print(f"Topic: {section.get('topic')} | Offset: {section.get('offset')} | Line: {section.get('start_line')} | Confidence: {section.get('confidence')}%\nSnippet:\n{section.get('snippet')}\n{'-'*60}")
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
