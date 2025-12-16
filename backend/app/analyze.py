# --- All imports at the top (PEP8 best practice) ---
import os
import json
import logging
import traceback
import argparse
import time  # Added missing import for watchdog timing and progress tracking
import threading  # For thread-safe job state management
# ThreadPoolExecutor removed - now using sequential processing for stability
from .extractors.auditor import extract_auditor_from_report
from .extractors.company import extract_company_from_report
from .extractors.control_extractor import extract_controls  # Unified control extractor
# CUEC extractor routing (SOC1, SOC2, Combined)
# Import will be done dynamically based on report_type
from .extractors.subservice_orgs import extract_subservice_orgs, filter_third_parties_with_gpt
from .extractors.product import extract_product_from_report
from .extractors.report_date import extract_report_date
from .extractors.coverage_period import extract_coverage_period
from .pdf_handler import extract_text_from_pdf, find_section_candidates
from . import config
from .models import ReportType

# Thread-safe job state management for multi-threading support
_job_locks = {}  # Dictionary of job_id -> Lock
_job_locks_lock = threading.Lock()  # Lock for managing the locks dictionary


def _deep_merge(base_dict, update_dict):
    """
    Recursively merge update_dict into base_dict, preserving existing keys.
    
    Args:
        base_dict: Base dictionary to merge into
        update_dict: Dictionary with updates to apply
        
    Returns:
        Merged dictionary
    """
    if not isinstance(base_dict, dict) or not isinstance(update_dict, dict):
        return update_dict
    
    result = base_dict.copy()
    for key, value in update_dict.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _update_job_state(job_id, updates_dict, redis_client):
    """
    Thread-safe update of Redis job state with deep merge support.
    
    Args:
        job_id: Job identifier
        updates_dict: Dictionary of updates to merge into existing state
        redis_client: Sync Redis client instance
    """
    
    # Get or create per-job lock
    with _job_locks_lock:
        if job_id not in _job_locks:
            _job_locks[job_id] = threading.Lock()
        job_lock = _job_locks[job_id]
    
    # Perform atomic get-modify-set with per-job lock
    with job_lock:
        try:
            job_json = redis_client.get(f"job:{job_id}")
            if not job_json:
                logging.warning(f"[_update_job_state] Job {job_id} not found in Redis, update skipped")
                return
            
            current_state = json.loads(job_json)
            merged_state = _deep_merge(current_state, updates_dict)
            redis_client.set(f"job:{job_id}", json.dumps(merged_state), ex=86400)
            
        except Exception as e:
            logging.error(f"[_update_job_state] Failed to update job {job_id}: {e}")


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


def run_metadata_extractors_parallel(
    validated_report_type,
    executor=None,
    progress_tracker=None,
    job_id=None,
    redis_client=None,
    logger=None
):
    """
    Run metadata extractors in parallel using IntelligentTaskExecutor.
    
    Runs 4 extractors concurrently:
    1. Auditor extraction
    2. Product extraction
    3. Report date extraction
    4. Coverage period extraction
    
    Args:
        validated_report_type: ReportType enum value
        executor: IntelligentTaskExecutor instance (optional)
        progress_tracker: ProgressTracker instance (optional)
        job_id: Redis job ID for progress updates
        redis_client: Redis client for state updates
        logger: Logger instance
        
    Returns:
        Dict with keys: 'product_extraction', 'report_date_extraction', 
        'coverage_period_extraction', 'cuec_extraction', 'subservice_orgs_extraction'
        
    Example:
        from backend.app.threading import IntelligentTaskExecutor, ProgressTracker
        
        executor = IntelligentTaskExecutor(max_workers=5)
        tracker = ProgressTracker(job_id="test-123", redis_client=redis)
        
        results = run_metadata_extractors_parallel(
            validated_report_type=ReportType.SOC2,
            executor=executor,
            progress_tracker=tracker,
            job_id="test-123",
            redis_client=redis,
            logger=logging.getLogger(__name__)
        )
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Fallback to sequential if no executor provided
    if not executor:
        logger.info("[PARALLEL_METADATA] No executor provided, falling back to sequential")
        return _run_metadata_extractors_sequential(
            validated_report_type, job_id, redis_client, logger
        )
    
    import time
    start_time = time.time()
    
    logger.info("[PARALLEL_METADATA] Starting parallel metadata extraction (5 extractors)")
    
    # Thread-safe result storage
    results = {}
    results_lock = threading.Lock()
    extractors_completed = 0
    
    # Start metadata phase in progress tracker
    if progress_tracker:
        progress_tracker.start_phase("metadata")
    
    def run_single_extractor(extractor_name, extractor_func):
        """
        Wrapper to run a single metadata extractor.
        
        Args:
            extractor_name: Name for logging (e.g., 'product_extraction')
            extractor_func: Callable that returns extraction result
            
        Returns:
            Tuple of (extractor_name, result)
        """
        nonlocal extractors_completed
        
        # Check for cancellation
        if job_id and redis_client:
            try:
                cancelled = redis_client.get(f"job:{job_id}:cancelled")
                if cancelled:
                    logger.info(f"[PARALLEL_METADATA] Job {job_id} cancelled, stopping {extractor_name}")
                    return extractor_name, None
            except Exception as e:
                logger.warning(f"[PARALLEL_METADATA] Could not check cancellation flag: {e}")
        
        logger.info(f"[PARALLEL_METADATA] Starting {extractor_name}")
        extractor_start = time.time()
        
        # Update status for metadata extractors
        if job_id and redis_client:
            try:
                status_messages = {
                    'auditor_extraction': 'Extracting auditor information...',
                    'product_extraction': 'Extracting product information...',
                    'report_date_extraction': 'Extracting report date...',
                    'coverage_period_extraction': 'Extracting coverage period...'
                }
                if extractor_name in status_messages:
                    job_json = redis_client.get(f"job:{job_id}")
                    if job_json:
                        job_data = json.loads(job_json)
                        job_data["status"] = status_messages[extractor_name]
                        redis_client.set(f"job:{job_id}", json.dumps(job_data), ex=86400)
            except Exception:
                pass  # Fail silently
        
        try:
            result = extractor_func()
            elapsed = time.time() - extractor_start
            logger.info(f"[PARALLEL_METADATA] {extractor_name} completed in {elapsed:.2f}s")
            
            # Update progress tracker with entity detection
            if progress_tracker:
                if extractor_name == 'product_extraction' and result:
                    product = result.get('product') if isinstance(result, dict) else result
                    if product:
                        progress_tracker.update_entity('product', str(product))
                
                elif extractor_name == 'report_date_extraction' and result:
                    report_date = result.get('report_date') if isinstance(result, dict) else result
                    if report_date:
                        progress_tracker.update_entity('report_date', str(report_date))
                
                elif extractor_name == 'coverage_period_extraction' and result:
                    coverage = result.get('coverage_period') if isinstance(result, dict) else result
                    if coverage:
                        progress_tracker.update_entity('coverage_period', str(coverage))
                
                elif extractor_name == 'cuec_extraction' and result:
                    if isinstance(result, dict):
                        cuec_count = len(result.get('cuecs', []))
                        progress_tracker.update_cuecs(extracted_count=cuec_count)
                
                elif extractor_name == 'subservice_orgs_extraction' and result:
                    if isinstance(result, dict):
                        orgs_count = len(result.get('subservice_orgs', []))
                        progress_tracker.update_subservice_orgs(extracted_count=orgs_count)
            
            # Thread-safe result storage and progress update
            with results_lock:
                results[extractor_name] = result
                extractors_completed += 1
                
                # Update Redis job state with entity detection
                if job_id and redis_client:
                    try:
                        job_json = redis_client.get(f"job:{job_id}")
                        if job_json:
                            job = json.loads(job_json)
                            
                            # Update identified_entities
                            if 'identified_entities' not in job:
                                job['identified_entities'] = {}
                            
                            if extractor_name == 'product_extraction' and result:
                                product = result.get('product') if isinstance(result, dict) else result
                                if product:
                                    job['identified_entities']['product'] = str(product)
                            
                            elif extractor_name == 'report_date_extraction' and result:
                                report_date = result.get('report_date') if isinstance(result, dict) else result
                                if report_date:
                                    job['identified_entities']['report_date'] = str(report_date)
                            
                            elif extractor_name == 'coverage_period_extraction' and result:
                                # Result is dict with {type, start_date, end_date, as_of_date, explanation}
                                if isinstance(result, dict):
                                    if result.get('start_date') and result.get('end_date'):
                                        coverage_str = f"{result['start_date']} to {result['end_date']}"
                                    elif result.get('as_of_date'):
                                        coverage_str = f"As of {result['as_of_date']}"
                                    elif result.get('end_date'):
                                        coverage_str = f"As of {result['end_date']}"
                                    else:
                                        coverage_str = str(result)
                                    job['identified_entities']['coverage_period'] = coverage_str
                                else:
                                    job['identified_entities']['coverage_period'] = str(result)
                            
                            # Update counters
                            if 'counters' not in job:
                                job['counters'] = {}
                            
                            if extractor_name == 'cuec_extraction' and result:
                                if isinstance(result, dict):
                                    cuec_count = len(result.get('cuecs', []))
                                    job['counters']['cuecs_count'] = cuec_count
                            
                            elif extractor_name == 'subservice_orgs_extraction' and result:
                                if isinstance(result, dict):
                                    orgs_count = len(result.get('subservice_orgs', []))
                                    job['counters']['subservice_orgs_count'] = orgs_count
                            
                            redis_client.set(f"job:{job_id}", json.dumps(job), ex=86400)
                    
                    except Exception as e:
                        logger.warning(f"[PARALLEL_METADATA] Could not update job state: {e}")
            
            return extractor_name, result
            
        except Exception as e:
            logger.error(f"[PARALLEL_METADATA] {extractor_name} failed: {e}")
            logger.error(traceback.format_exc())
            return extractor_name, None
    
    # Define extractor tasks
    def _run_cuec_extraction():
        """Wrapper for CUEC extraction with report type parameter."""
        from .extractors.cuec_extractor import extract_cuecs
        logger.info(f"Running unified CUEC extractor (report_type={validated_report_type.value})")
        return extract_cuecs(report_type=validated_report_type.value)
    
    extractor_tasks = [
        ('auditor_extraction', extract_auditor_from_report),
        ('product_extraction', extract_product_from_report),
        ('report_date_extraction', extract_report_date),
        ('coverage_period_extraction', extract_coverage_period),
    ]
    
    # Execute in parallel using executor
    try:
        from .threading.intelligent_executor import TaskPriority
        
        # Create list of (name, func) tuples for executor.map
        task_list = [(name, func) for name, func in extractor_tasks]
        
        # Use executor.map with LOW priority (metadata is less critical than controls)
        futures = []
        for name, func in task_list:
            future = executor.submit(
                run_single_extractor,
                name,
                func,
                priority=TaskPriority.LOW
            )
            futures.append(future)
        
        # Wait for all to complete
        for future in futures:
            try:
                future.result()  # Blocks until complete
            except Exception as e:
                logger.error(f"[PARALLEL_METADATA] Extractor task raised exception: {e}")
        
    except Exception as e:
        logger.error(f"[PARALLEL_METADATA] Executor failed: {e}, falling back to sequential")
        # Complete fallback to sequential
        return _run_metadata_extractors_sequential(
            validated_report_type, job_id, redis_client, logger
        )
    
    # Calculate metrics
    parallel_time = time.time() - start_time
    
    logger.info(f"[PARALLEL_METADATA] Completed: {extractors_completed}/5 extractors in {parallel_time:.2f}s")
    
    # Complete metadata phase in progress tracker
    if progress_tracker:
        progress_tracker.complete_phase("metadata")
    
    return results


def _run_metadata_extractors_sequential(
    validated_report_type,
    job_id=None,
    redis_client=None,
    logger=None
):
    """
    Sequential fallback for metadata extraction.
    
    Runs extractors one at a time in the original order.
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    logger.info("[SEQUENTIAL_METADATA] Running metadata extractors sequentially")
    
    results = {}
    
    # Import CUEC extraction wrapper
    def _run_cuec_extraction():
        from .extractors.cuec_extractor import extract_cuecs
        return extract_cuecs(report_type=validated_report_type.value)
    
    def _run_subservice_orgs_extraction():
        return extract_subservice_orgs()
    
    extractors = [
        ('product_extraction', extract_product_from_report),
        ('report_date_extraction', extract_report_date),
        ('coverage_period_extraction', extract_coverage_period),
        ('cuec_extraction', _run_cuec_extraction),
        ('subservice_orgs_extraction', _run_subservice_orgs_extraction),
    ]
    
    for name, func in extractors:
        try:
            logger.info(f"[SEQUENTIAL_METADATA] Starting {name}")
            result = func()
            results[name] = result
            logger.info(f"[SEQUENTIAL_METADATA] {name} completed")
            
            # Update Redis job state
            if job_id and redis_client and result:
                try:
                    job_json = redis_client.get(f"job:{job_id}")
                    if job_json:
                        job = json.loads(job_json)
                        
                        if 'identified_entities' not in job:
                            job['identified_entities'] = {}
                        
                        if name == 'product_extraction':
                            product = result.get('product') if isinstance(result, dict) else result
                            if product:
                                job['identified_entities']['product'] = str(product)
                        
                        elif name == 'report_date_extraction':
                            report_date = result.get('report_date') if isinstance(result, dict) else result
                            if report_date:
                                job['identified_entities']['report_date'] = str(report_date)
                        
                        elif name == 'coverage_period_extraction':
                            coverage = result.get('coverage_period') if isinstance(result, dict) else result
                            if coverage:
                                job['identified_entities']['coverage_period'] = str(coverage)
                        
                        if 'counters' not in job:
                            job['counters'] = {}
                        
                        if name == 'cuec_extraction' and isinstance(result, dict):
                            cuec_count = len(result.get('cuecs', []))
                            job['counters']['cuecs_count'] = cuec_count
                        
                        elif name == 'subservice_orgs_extraction' and isinstance(result, dict):
                            orgs_count = len(result.get('subservice_orgs', []))
                            job['counters']['subservice_orgs_count'] = orgs_count
                        
                        redis_client.set(f"job:{job_id}", json.dumps(job), ex=86400)
                
                except Exception as e:
                    logger.warning(f"[SEQUENTIAL_METADATA] Could not update job state: {e}")
        
        except Exception as e:
            logger.error(f"[SEQUENTIAL_METADATA] {name} failed: {e}")
            logger.error(traceback.format_exc())
            results[name] = None
    
    return results


def analyze_pdf_file(pdf_path, output_json_path='data/json/section_results.json', report_type='SOC2', 
                      progress_callback=None, checklist_callback=None, job_id=None, 
                      executor=None, progress_tracker=None):
    # Reset GPT tracking at start of analysis
    from .gpt_tracker import reset_tracking, get_usage_summary
    reset_tracking()
    logger = logging.getLogger(__name__)
    
    # Log parallel execution status
    if executor:
        logger.info(f"[PARALLEL_EXEC] Parallel execution ENABLED (max_workers={executor.max_workers if hasattr(executor, 'max_workers') else 'unknown'})")
    else:
        logger.info("[PARALLEL_EXEC] Parallel execution DISABLED (running sequentially)")
    
    # Track start time for elapsed_seconds
    import time
    analysis_start_time = time.time()
    
    # Validate and normalize report_type
    logger.error(f"[DEBUG] analyze_pdf_file called with report_type={report_type}, type={type(report_type)}")
    try:
        validated_report_type = validate_report_type(report_type)
        logger.error(f"[DEBUG] After validation: validated_report_type={validated_report_type}, value={validated_report_type.value}")
        logger.info(f"Analysis starting for report type: {validated_report_type.value}")
    except ValueError as e:
        logger.error(f"Invalid report_type: {e}")
        raise

    # --- Reset logs and JSON outputs at the start of each run ---
    # Clear checkpoint file for fresh scan state (unless resuming)
    CHECKPOINT_PATH = str(config.JSON_DIR / '_extraction_checkpoint.json')
    if os.path.isfile(CHECKPOINT_PATH):
        try:
            os.remove(CHECKPOINT_PATH)
            logger.info(f"Cleared checkpoint file for fresh scan")
        except Exception as e:
            logger.warning(f"Failed to clear checkpoint: {e}")
    
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
        str(config.JSON_DIR / '_extraction_checkpoint.json'),
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
        # Check for embedded PDFs first (common with protected/agreement PDFs)
        update_progress(3, "Checking for embedded files...")
        from .pdf_handler import extract_embedded_files, flatten_pdf
        
        temp_extract_dir = os.path.join(os.path.dirname(pdf_path), 'extracted')
        embedded_pdfs = extract_embedded_files(pdf_path, temp_extract_dir)
        
        if embedded_pdfs:
            logger.info(f"Found {len(embedded_pdfs)} embedded PDF(s), using first one: {embedded_pdfs[0]}")
            # Use the first embedded PDF as the source
            pdf_path = embedded_pdfs[0]
            # Note: We'll clean this up later
        
        # Check if PDF needs flattening (has interactive elements or protected content)
        # Try flattening first, then fall back to original if it fails
        update_progress(5, "Preprocessing PDF...")
        flattened_path = pdf_path.replace('.pdf', '_flattened.pdf')
        flatten_success = flatten_pdf(pdf_path, flattened_path)
        
        if flatten_success and os.path.exists(flattened_path):
            logger.info(f"Using flattened PDF for extraction: {flattened_path}")
            extraction_path = flattened_path
        else:
            logger.warning(f"PDF flattening failed or skipped, using original PDF")
            extraction_path = pdf_path
        
        # Always (re)generate section_results.json before running extractors
        update_progress(10, "Extracting text from PDF...")
        extract_text_from_pdf(extraction_path, OUTPUT_TEXT_FILE)
        logger.debug(f"Extracted text to {OUTPUT_TEXT_FILE}")
        
        # Clean up flattened PDF after extraction
        if flatten_success and os.path.exists(flattened_path):
            try:
                os.remove(flattened_path)
                logger.debug(f"Cleaned up flattened PDF: {flattened_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up flattened PDF: {e}")
        
        # Clean up extracted embedded files
        if embedded_pdfs and os.path.exists(temp_extract_dir):
            try:
                import shutil
                shutil.rmtree(temp_extract_dir)
                logger.debug(f"Cleaned up extracted files directory: {temp_extract_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up extracted files: {e}")
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
            {"name": "file_uploaded", "status": "pending"},       # Index 0
            {"name": "text_extracted", "status": "pending"},      # Index 1
            {"name": "sections_extracted", "status": "pending"},  # Index 2
            {"name": "company_extraction", "status": "pending"},  # Index 3
            {"name": "logo_fetching", "status": "pending"},       # Index 4
            {"name": "auditor_extraction", "status": "pending"},  # Index 5
            {"name": "product_extraction", "status": "pending"},  # Index 6
            {"name": "report_date_extraction", "status": "pending"}, # Index 7
            {"name": "coverage_period_extraction", "status": "pending"}, # Index 8
            {"name": "control_extraction", "status": "pending"},  # Index 9
            {"name": "control_framework_mapping", "status": "pending"}, # Index 10
            {"name": "cuec_extraction", "status": "pending"},     # Index 11
            {"name": "subservice_orgs_extraction", "status": "pending"}, # Index 12
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
        
        # Wrapper for control extraction - uses unified extractor
        def _run_control_extraction():
            """
            Run unified control extraction for all report types.
            
            Uses unified control_extractor.py which:
            - Uses SOC2 prompt for ALL report types (proven, reliable)
            - Optionally maps financial assertions via batch GPT (SOC1 only, if enabled)
            - Gracefully degrades if assertion mapping fails
            - Supports parallel extraction if executor and progress_tracker are available
            """
            # Load sections for extractor
            with open(config.SECTION_JSON_PATH, 'r', encoding='utf-8') as f:
                sections = json.load(f)
            
            # Check if parallel extraction is enabled and infrastructure is available
            if config.ENABLE_PARALLEL_EXTRACTION and executor and progress_tracker:
                from .extractors.control_extractor import extract_controls_parallel
                
                logger.info(f"[PARALLEL_EXEC] Using parallel control extractor (report_type={validated_report_type.value})")
                
                result = extract_controls_parallel(
                    sections=sections,
                    report_type=validated_report_type.value,
                    executor=executor,
                    progress_tracker=progress_tracker,
                    enable_assertion_mapping=config.ENABLE_ASSERTION_MAPPING,
                    max_controls=None,  # None = use config.QUICK_TEST_MODE_ENABLED if set
                    scan_id=None,  # Checkpoint will still work, just without scan_id tracking
                    job_id=job_id,  # Pass job_id for real-time progress updates
                    redis_client=redis_client  # Pass Redis client for job state updates
                )
            else:
                from .extractors.control_extractor import extract_controls as extract_controls_unified
                
                logger.info(f"Using unified control extractor (report_type={validated_report_type.value})")
                
                # Fall back to sequential extraction
                result = extract_controls_unified(
                    sections=sections,
                    report_type=validated_report_type.value,
                    enable_assertion_mapping=config.ENABLE_ASSERTION_MAPPING,
                    max_controls=None,  # None = use config.QUICK_TEST_MODE_ENABLED if set
                    scan_id=None,  # Checkpoint will still work, just without scan_id tracking
                    job_id=job_id,  # Pass job_id for real-time progress updates
                    redis_client=redis_client  # Pass Redis client for job state updates
                )
            
            # Return full result dict (not just controls list) to preserve framework_mappings and all metadata
            return result
        
        # Control framework mapping function - runs after control extraction
        def _run_control_framework_mapping():
            """
            Map extracted controls to frameworks with parallel execution and checkpointing.
            
            Returns:
                Dict with mapped controls count
            """
            try:
                logger.info("[FRAMEWORK_MAPPING] Starting control framework mapping")
                
                # Load controls from control_result.json
                control_json_path = data_path('data/json/control_result.json')
                if not os.path.isfile(control_json_path):
                    logger.warning("[FRAMEWORK_MAPPING] control_result.json not found, skipping framework mapping")
                    return {"controls_mapped": 0, "error": "No controls to map"}
                
                with open(control_json_path, 'r', encoding='utf-8') as f:
                    control_data = json.load(f)
                
                controls = control_data.get('controls', [])
                if not controls:
                    logger.warning("[FRAMEWORK_MAPPING] No controls found in control_result.json")
                    return {"controls_mapped": 0}
                
                logger.info(f"[FRAMEWORK_MAPPING] Loaded {len(controls)} controls for framework mapping")
                
                # Call the batch framework mapping function from control_extractor
                from .extractors.control_extractor import map_controls_to_frameworks_batch
                from .frameworks import get_available_frameworks
                
                # Get available frameworks for report type
                available_frameworks = get_available_frameworks(report_type=validated_report_type.value)
                logger.info(f"[FRAMEWORK_MAPPING] Loaded {len(available_frameworks)} frameworks: {list(available_frameworks.keys())}")
                
                # Map controls with parallel execution
                mapped_controls = map_controls_to_frameworks_batch(
                    controls=controls,
                    available_frameworks=available_frameworks,
                    executor=executor,
                    progress_tracker=progress_tracker,
                    job_id=job_id,
                    redis_client=redis_client,
                    logger=logger
                )
                
                # Save mapped controls back to control_result.json
                control_data['controls'] = mapped_controls
                with open(control_json_path, 'w', encoding='utf-8') as f:
                    json.dump(control_data, f, indent=2, ensure_ascii=False)
                
                logger.info(f"[FRAMEWORK_MAPPING] Successfully mapped {len(mapped_controls)} controls to frameworks")
                
                return {"controls_mapped": len(mapped_controls)}
                
            except Exception as e:
                logger.error(f"[FRAMEWORK_MAPPING] Framework mapping failed: {e}", exc_info=True)
                # Continue with warnings - don't fail the entire scan
                return {"controls_mapped": 0, "error": str(e)}
        
        # Wrapper for CUEC extraction - routes based on report_type with progress updates
        def _run_cuec_extraction():
            """
            Run unified CUEC extraction with report type parameter and real-time progress updates.
            Supports SOC1, SOC2, and COMBINED report types.
            """
            from .extractors.cuec_extractor import extract_cuecs
            logger.info(f"Running unified CUEC extractor (report_type={validated_report_type.value})")
            # Pass job_id and redis_client for real-time progress updates
            return extract_cuecs(
                report_type=validated_report_type.value,
                job_id=job_id,
                redis_client=redis_client
            )
        
        # Logo fetching function - runs after company is identified
        def _run_logo_fetching():
            """Fetch company logo after company has been identified."""
            try:
                company_json_path = data_path('data/json/company_result.json')
                if not os.path.isfile(company_json_path):
                    logger.warning("[LOGO] company_result.json not found, skipping logo fetch")
                    return {"success": False, "reason": "Company not yet identified"}
                
                with open(company_json_path, 'r', encoding='utf-8') as f:
                    company_data = json.load(f)
                
                company_name = company_data.get('company', 'Unknown')
                # FIX: Read 'company_domain' field instead of 'domain'
                company_domain = company_data.get('company_domain') or company_data.get('domain')
                
                if not company_domain:
                    logger.info(f"[LOGO] No domain found for {company_name}, skipping logo fetch")
                    return {"success": False, "reason": "No domain available"}
                
                logger.info(f"[LOGO] Fetching logo for {company_name} (domain: {company_domain})")
                
                from .logo_service import fetch_and_cache_logo
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker
                from .models import Scan
                
                if not config.db_path:
                    logger.warning("[LOGO] No database path configured")
                    return {"success": False, "reason": "No database configured"}
                
                engine = create_engine(config.db_path)
                SessionLocal = sessionmaker(bind=engine)
                db = SessionLocal()
                try:
                    # Get company_id from the most recent scan
                    scan = db.query(Scan).filter(Scan.job_id == job_id).first()
                    if scan and scan.company_id:
                        success, logo_url = fetch_and_cache_logo(scan.company_id, company_domain, db)
                        if success and logo_url:
                            logger.info(f"[LOGO] ✓ Logo cached: {logo_url}")
                            return {"success": True, "logo_url": logo_url}
                        else:
                            logger.info(f"[LOGO] No logo found for {company_domain}")
                            return {"success": False, "reason": "Logo not found"}
                    else:
                        logger.warning("[LOGO] Could not find scan or company_id")
                        return {"success": False, "reason": "Scan not found"}
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"[LOGO] Logo fetch failed: {e}", exc_info=True)
                return {"success": False, "reason": str(e)}
        
        prereq_steps = [
            (3, "company_extraction", extract_company_from_report, "Running company extractor...", 30),
            (4, "logo_fetching", _run_logo_fetching, "Fetching company logo...", 32),
        ]
        # Metadata extractors that run in parallel after company and logo (NOTE: metadata_parallel_steps is documentation - run_metadata_extractors_parallel has actual list)
        metadata_parallel_steps = [
            (5, "auditor_extraction", extract_auditor_from_report, "Running auditor extractor...", 34),
            (6, "product_extraction", extract_product_from_report, "Running product extractor...", 36),
            (7, "report_date_extraction", extract_report_date, "Running report date extractor...", 38),
            (8, "coverage_period_extraction", extract_coverage_period, "Running coverage period extractor...", 40),
        ]
        # Control extraction step (has internal parallelism)
        parallel_steps = [
            (9, "control_extraction", _run_control_extraction, "Running controls extractor...", 50),
        ]
        # Post-control extraction steps that run in parallel
        post_control_parallel_steps = [
            (11, "cuec_extraction", _run_cuec_extraction, "Running CUECs extractor...", 70),
            (12, "subservice_orgs_extraction", _run_subservice_orgs_extraction, "Running subservice orgs extractor...", 80),
        ]

        # Watchdog: if controls extractor runs too long without increasing result size, mark as partial and continue
        CONTROL_WATCHDOG_ENABLED = getattr(config, 'CONTROL_WATCHDOG_ENABLED', True)
        CONTROL_WATCHDOG_MAX_MINUTES = getattr(config, 'CONTROL_WATCHDOG_MAX_MINUTES', 25)
        _ctrl_last_count = 0
        _ctrl_last_time = time.time()
        # Create Redis client for job state updates
        redis_client = None
        if job_id:
            try:
                import redis as sync_redis
                from . import config as cfg
                redis_url = getattr(cfg, 'REDIS_URL', 'redis://localhost:6379/0')
                redis_client = sync_redis.from_url(redis_url, decode_responses=True)
                
                # Clean up any stale pause states from previous runs
                try:
                    job_json = redis_client.get(f"job:{job_id}")
                    if job_json:
                        job_data = json.loads(job_json)
                        if job_data.get("status") == "Paused" and not job_data.get("paused"):
                            # Status is Paused but paused flag is not set - likely stale
                            logger.error(f"[PAUSE_CLEANUP] Removing stale 'Paused' status from job {job_id}")
                            job_data["status"] = "Starting"
                            redis_client.set(f"job:{job_id}", json.dumps(job_data), ex=60*60*24)
                except Exception as cleanup_err:
                    logger.debug(f"Pause cleanup error: {cleanup_err}")
                    
            except Exception as redis_err:
                logger.warning(f"Could not create Redis client: {redis_err}")
        
        # Helper function to check if scan should be paused
        def _check_pause():
            """Check if scan queue is paused and raise exception if so."""
            if job_id and redis_client:
                try:
                    # Check both queue pause and individual job pause
                    is_queue_paused = redis_client.exists("scan_queue:paused") > 0
                    job_json = redis_client.get(f"job:{job_id}")
                    
                    # VERBOSE LOGGING - Log full state for debugging
                    logger.error(f"[PAUSE_CHECK] job_id={job_id}, queue_paused={is_queue_paused}, job_exists={bool(job_json)}")
                    
                    if job_json:
                        job_data = json.loads(job_json)
                        is_job_paused = job_data.get("status") == "Paused"
                        has_paused_flag = job_data.get("paused", False)
                        
                        # VERBOSE LOGGING - Log job state details
                        logger.error(f"[PAUSE_CHECK] status='{job_data.get('status')}', paused_flag={has_paused_flag}, is_job_paused={is_job_paused}")
                        
                        # Only trigger if BOTH status is "Paused" AND paused flag is True
                        # This prevents false positives from stale status
                        if is_queue_paused or (is_job_paused and has_paused_flag):
                            logger.warning(f"[PAUSE] Scan paused (queue:{is_queue_paused}, job:{is_job_paused}, flag:{has_paused_flag})")
                            raise RuntimeError("Scan paused by user")
                    else:
                        logger.error(f"[PAUSE_CHECK] No job data found in Redis for {job_id}")
                except json.JSONDecodeError as jde:
                    logger.error(f"[PAUSE_CHECK] JSON decode error: {jde}")
                except RuntimeError:
                    raise
                except Exception as pause_err:
                    logger.error(f"[PAUSE_CHECK] Pause check error: {pause_err}")
        
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
            # Company extraction returns a dict with company name, domain, etc.
            # We want to preserve the entire dict, not just the 'company' string field
            'company_extraction': ('company', None),  # None means use the whole result
            'report_date_extraction': ('report_date', 'report_date'),
            'coverage_period_extraction': ('coverage_period', 'coverage_period'),
        }

        def _write_partial_combined(current_results: dict):
            """Write partial combined results with file locking and merge support."""
            import tempfile
            try:
                # Import file locking with platform fallback
                try:
                    import fcntl
                    has_fcntl = True
                except ImportError:
                    has_fcntl = False
                    logger.debug("fcntl not available (Windows), skipping file lock")
                
                combined_result_path = data_path('data/json/combined_result.json')
                
                # Prepare standardized partial results
                standardized_partial = {}
                for ext_key, (short_key, inner_key) in flatten_map.items():
                    val = current_results.get(ext_key)
                    if val is None:
                        continue
                    # If inner_key is None, use the entire value (for company extraction dict)
                    if inner_key is None:
                        standardized_partial[short_key] = val
                    elif isinstance(val, dict) and inner_key in val:
                        if short_key == 'controls' and isinstance(val[inner_key], list):
                            standardized_partial[short_key] = [dict(c) for c in val[inner_key]]
                        else:
                            standardized_partial[short_key] = val[inner_key]
                    else:
                        standardized_partial[short_key] = val
                
                if not standardized_partial:
                    return
                
                standardized_partial['sections'] = results.get('sections', [])
                
                # Read existing file and merge if present
                existing_data = {}
                if os.path.isfile(combined_result_path):
                    try:
                        with open(combined_result_path, 'r', encoding='utf-8') as f:
                            if has_fcntl:
                                fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
                            existing_data = json.load(f)
                            if has_fcntl:
                                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    except Exception as read_err:
                        logger.warning(f"Could not read existing combined_result.json: {read_err}")
                
                # Deep merge existing with new data
                merged_data = _deep_merge(existing_data, standardized_partial)
                
                # Write atomically with exclusive lock
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', 
                                                  dir=os.path.dirname(combined_result_path),
                                                  delete=False, suffix='.json') as temp_f:
                    temp_path = temp_f.name
                    if has_fcntl:
                        fcntl.flock(temp_f.fileno(), fcntl.LOCK_EX)
                    json.dump(merged_data, temp_f, indent=2, ensure_ascii=False)
                    if has_fcntl:
                        fcntl.flock(temp_f.fileno(), fcntl.LOCK_UN)
                
                # Atomic rename
                os.replace(temp_path, combined_result_path)
                logger.debug(f"Updated combined_result.json with {len(standardized_partial)} entities")
                
            except Exception as _p_err:
                logger.error(f"Failed partial combined write: {_p_err}")
        
        # Run prerequisites sequentially
        for idx, key, func, status, pct in prereq_steps:
            # Check for pause before each step
            _check_pause()
            
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
            
            # Update identified_entities in job state for all metadata
            if job_id and redis_client and results.get(key):
                try:
                    entity_updates = {}
                    if key == 'company_extraction' and isinstance(results[key], dict):
                        company_name = results[key].get('company', 'Unknown')
                        entity_updates = {'identified_entities': {'company': company_name}}
                        logger.info(f"[PROGRESS] Company identified: {company_name}")
                    elif key == 'logo_fetching' and isinstance(results[key], dict):
                        if results[key].get('success'):
                            logo_url = results[key].get('logo_url')
                            if logo_url:
                                # Update both identified_entities (for API) and top-level logo_url (for queue card)
                                entity_updates = {
                                    'identified_entities': {'company_logo_url': logo_url},
                                    'logo_url': logo_url  # Add to top-level for frontend queue card display
                                }
                                logger.info(f"[PROGRESS] Logo fetched successfully: {logo_url}")
                            else:
                                logger.info(f"[PROGRESS] Logo fetched successfully")
                        else:
                            logger.info(f"[PROGRESS] Logo fetch: {results[key].get('reason', 'Unknown')}")
                    elif key == 'auditor_extraction':
                        auditor_name = results[key].get('auditor') if isinstance(results[key], dict) else results[key]
                        if auditor_name:
                            entity_updates = {'identified_entities': {'auditor': str(auditor_name)}}
                            logger.info(f"[PROGRESS] Auditor identified: {auditor_name}")
                    elif key == 'product_extraction':
                        product = results[key].get('product') if isinstance(results[key], dict) else results[key]
                        if product:
                            entity_updates = {'identified_entities': {'product': str(product)}}
                            logger.info(f"[PROGRESS] Product identified: {product}")
                    elif key == 'report_date_extraction':
                        report_date = results[key].get('report_date') if isinstance(results[key], dict) else results[key]
                        if report_date:
                            entity_updates = {'identified_entities': {'report_date': str(report_date)}}
                            logger.info(f"[PROGRESS] Report date identified: {report_date}")
                    elif key == 'coverage_period_extraction':
                        coverage = results[key].get('coverage_period') if isinstance(results[key], dict) else results[key]
                        if coverage:
                            # Format coverage_period for frontend display
                            if isinstance(coverage, dict):
                                if coverage.get('start_date') and coverage.get('end_date'):
                                    coverage_str = f"{coverage['start_date']} to {coverage['end_date']}"
                                elif coverage.get('as_of_date'):
                                    coverage_str = f"As of {coverage['as_of_date']}"
                                elif coverage.get('end_date'):
                                    coverage_str = f"As of {coverage['end_date']}"
                                else:
                                    coverage_str = str(coverage)
                            else:
                                coverage_str = str(coverage)
                            entity_updates = {'identified_entities': {'coverage_period': coverage_str}}
                            logger.info(f"[PROGRESS] Coverage period identified: {coverage_str}")
                    
                    if entity_updates:
                        _update_job_state(job_id, entity_updates, redis_client)
                except Exception as entity_err:
                    logger.warning(f"Could not update identified_entities: {entity_err}")
            
            # Update job state after each prerequisite extractor
            # NOTE: combined_result.json will be written once at the end after all extractors complete
            if job_id and redis_client:
                try:
                    _update_job_state(job_id, {}, redis_client)
                except Exception as update_err:
                    logger.warning(f"Could not update job state: {update_err}")
            
            # Update checklist in Redis after each sequential extractor
            update_checklist(checklist)
        
        # Run metadata extractors in parallel using the OLD superior implementation
        if config.ENABLE_PARALLEL_METADATA_EXTRACTION and executor and progress_tracker:
            logger.info("[PARALLEL_EXEC] Running metadata extractors (product, report_date, coverage_period, cuec, subservice_orgs) in PARALLEL mode")
            
            # Call the superior run_metadata_extractors_parallel function with correct parameters
            metadata_results = run_metadata_extractors_parallel(
                validated_report_type=validated_report_type,
                executor=executor,
                progress_tracker=progress_tracker,
                job_id=job_id,
                redis_client=redis_client,
                logger=logger
            )
            
            # Merge results
            for key, res in metadata_results.items():
                results[key] = res
                # Update checklist for these extractors
                for item in checklist:
                    if item.get('name') == key:
                        item['status'] = 'done' if res is not None else 'error'
                        break
            
            logger.info(f"[PARALLEL_EXEC] Parallel metadata extraction complete: {len(metadata_results)} extractors finished")
            update_checklist(checklist)
        
        # --- Run remaining extractors in parallel threads ---
        extractor_results = {}
        def run_extractor(idx, key, func, status, pct):
            # Check for pause before starting extractor
            _check_pause()
            
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
                
                # Set extraction_partial flag in job state
                if job_id and redis_client:
                    try:
                        error_msg = str(e)[:100]  # Truncate error message
                        _update_job_state(job_id, {
                            'extraction_partial': True,
                            'status': f'Partial: {key} failed - {error_msg}'
                        }, redis_client)
                        logger.warning(f"[PROGRESS] Warning: {key} partially completed")
                    except Exception as flag_err:
                        logger.warning(f"Could not set extraction_partial flag: {flag_err}")
                
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
        
        # EXTRACTION PROCESSING: Run extractors sequentially OR in parallel if enabled
        # Check if parallel metadata extraction is enabled
        if config.ENABLE_PARALLEL_METADATA_EXTRACTION and executor and progress_tracker:
            logger.info("[PARALLEL_EXEC] Running metadata extractors in PARALLEL mode")
            
            # Separate control/cuec/subservice extractors from metadata extractors
            # Control extraction wrapper already handles parallel vs sequential internally
            # Metadata extractors: product, report_date, coverage_period, cuec, subservice_orgs
            control_steps = []
            metadata_steps = []
            
            for idx, key, func, status, pct in parallel_steps:
                if key == 'control_extraction':
                    control_steps.append((idx, key, func, status, pct))
                else:
                    metadata_steps.append((idx, key, func, status, pct))
            
            # Run control extraction first (it has internal parallel logic)
            for idx, key, func, status, pct in control_steps:
                logger.info(f"Starting extractor '{key}'")
                try:
                    k, res = run_extractor(idx, key, func, status, pct)
                    extractor_results[k] = res
                    logger.info(f"Extractor '{k}' completed successfully")
                    
                    if k not in completed_extractors:
                        completed_extractors.append(k)
                        save_checkpoint(completed_extractors)
                except Exception as e:
                    logger.error(f"Extractor '{key}' raised exception: {e}\n{traceback.format_exc()}")
                    extractor_results[key] = None
                    for item in checklist:
                        if item.get('name') == key:
                            item['status'] = 'error'
                            break
                    update_checklist(checklist)
            
            # Run control framework mapping after control extraction
            if 'control_extraction' in extractor_results and 'control_framework_mapping' not in completed_extractors:
                logger.info("Starting control framework mapping")
                try:
                    checklist[10]["status"] = "running"  # Index 10 is control_framework_mapping
                    update_checklist(checklist)
                    
                    # Initialize framework mapping state in Redis with total control count
                    if job_id and redis_client:
                        try:
                            control_json_path = data_path('data/json/control_result.json')
                            if os.path.isfile(control_json_path):
                                with open(control_json_path, 'r', encoding='utf-8') as f:
                                    control_data = json.load(f)
                                total_controls = len(control_data.get('controls', []))
                                _update_job_state(job_id, {
                                    'status': f'Mapping 0/{total_controls} controls to frameworks...',
                                    'counters': {
                                        'controls_mapped_count': 0,
                                        'controls_mapped_percent': 0,
                                        'total_controls': total_controls
                                    }
                                }, redis_client)
                                logger.info(f"[FRAMEWORK_MAPPING] Initialized state: 0/{total_controls} controls")
                        except Exception as init_err:
                            logger.warning(f"Could not initialize framework mapping state: {init_err}")
                    
                    update_progress(50, "Mapping controls to frameworks...")
                    
                    mapping_result = _run_control_framework_mapping()
                    extractor_results['control_framework_mapping'] = mapping_result
                    
                    checklist[10]["status"] = "done"
                    update_checklist(checklist)
                    logger.info("Control framework mapping completed successfully")
                    
                    completed_extractors.append('control_framework_mapping')
                    save_checkpoint(completed_extractors)
                except Exception as e:
                    logger.error(f"Control framework mapping failed: {e}\n{traceback.format_exc()}")
                    checklist[10]["status"] = "error"
                    update_checklist(checklist)
                    # Continue with warnings
            
            # Run post-control parallel steps (CUEC + subservice_orgs)
            logger.info("[PARALLEL_EXEC] Running post-control extractors in PARALLEL")
            
            # Filter post-control steps to skip already completed
            remaining_post_control_steps = [(idx, key, func, status, pct) for (idx, key, func, status, pct) in post_control_parallel_steps 
                                           if key not in completed_extractors]
            
            for idx, key, func, status, pct in remaining_post_control_steps:
                logger.info(f"Starting post-control extractor '{key}'")
                try:
                    k, res = run_extractor(idx, key, func, status, pct)
                    extractor_results[k] = res
                    logger.info(f"Extractor '{k}' completed successfully")
                    
                    if k not in completed_extractors:
                        completed_extractors.append(k)
                        save_checkpoint(completed_extractors)
                except Exception as e:
                    logger.error(f"Extractor '{key}' raised exception: {e}\n{traceback.format_exc()}")
                    extractor_results[key] = None
                    for item in checklist:
                        if item.get('name') == key:
                            item['status'] = 'error'
                            break
                    update_checklist(checklist)
        else:
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
                    # Update identified_entities for product, dates, etc. AND counters for subservice orgs/CUECs
                    if job_id and redis_client and key in extractor_results and extractor_results[key]:
                        try:
                            entity_updates = {}
                            counter_updates = {}
                            
                            if key == 'product_extraction':
                                product = extractor_results[key].get('product') if isinstance(extractor_results[key], dict) else extractor_results[key]
                                if product:
                                    entity_updates = {'identified_entities': {'product': str(product)}}
                                    logger.info(f"[PROGRESS] Product identified: {product}")
                            elif key == 'report_date_extraction':
                                report_date = extractor_results[key].get('report_date') if isinstance(extractor_results[key], dict) else extractor_results[key]
                                if report_date:
                                    entity_updates = {'identified_entities': {'report_date': str(report_date)}}
                                    logger.info(f"[PROGRESS] Report date identified: {report_date}")
                            elif key == 'coverage_period_extraction':
                                coverage = extractor_results[key].get('coverage_period') if isinstance(extractor_results[key], dict) else extractor_results[key]
                                if coverage:
                                    entity_updates = {'identified_entities': {'coverage_period': str(coverage)}}
                                    logger.info(f"[PROGRESS] Coverage period identified: {coverage}")
                            elif key == 'subservice_orgs_extraction':
                                # Extract subservice orgs count
                                res = extractor_results[key]
                                count = 0
                                if isinstance(res, dict):
                                    count = len(res.get('subservice_orgs', []))
                                elif isinstance(res, list):
                                    count = len(res)
                                counter_updates = {'counters': {'subservice_orgs_count': count}}
                                logger.info(f"[PROGRESS] Found {count} subservice organizations")
                            elif key == 'cuec_extraction':
                                # Extract CUECs count
                                res = extractor_results[key]
                                count = 0
                                if isinstance(res, dict):
                                    count = len(res.get('cuecs', []))
                                elif isinstance(res, list):
                                    count = len(res)
                                counter_updates = {'counters': {'cuecs_count': count}}
                                logger.info(f"[PROGRESS] Found {count} CUECs")
                            
                            # Apply entity updates
                            if entity_updates:
                                _update_job_state(job_id, entity_updates, redis_client)
                            # Apply counter updates
                            if counter_updates:
                                _update_job_state(job_id, counter_updates, redis_client)
                        except Exception as entity_err:
                            logger.warning(f"Could not update progress for {key}: {entity_err}")
                    
                    # Update job state after each extractor
                    # NOTE: combined_result.json will be written once at the end after all extractors complete
                    results.update(extractor_results)  # Merge extractor results into main results dict
                    if job_id and redis_client:
                        try:
                            _update_job_state(job_id, {}, redis_client)
                        except Exception as update_err:
                            logger.warning(f"Could not update job state: {update_err}")
        
        # Post-extraction progress updates (for both parallel and sequential modes)
        # Update final entity counts and progress state
        if job_id and redis_client:
            try:
                for key, result in extractor_results.items():
                    if result and key not in ['control_extraction']:  # Control extraction already tracked internally
                        entity_updates = {}
                        counter_updates = {}
                        
                        if key == 'product_extraction':
                            product = result.get('product') if isinstance(result, dict) else result
                            if product:
                                entity_updates = {'identified_entities': {'product': str(product)}}
                        elif key == 'report_date_extraction':
                            report_date = result.get('report_date') if isinstance(result, dict) else result
                            if report_date:
                                entity_updates = {'identified_entities': {'report_date': str(report_date)}}
                        elif key == 'coverage_period_extraction':
                            coverage = result.get('coverage_period') if isinstance(result, dict) else result
                            if coverage:
                                entity_updates = {'identified_entities': {'coverage_period': str(coverage)}}
                        elif key == 'subservice_orgs_extraction':
                            count = 0
                            if isinstance(result, dict):
                                count = len(result.get('subservice_orgs', []))
                            elif isinstance(result, list):
                                count = len(result)
                            counter_updates = {'counters': {'subservice_orgs_count': count}}
                        elif key == 'cuec_extraction':
                            count = 0
                            if isinstance(result, dict):
                                count = len(result.get('cuecs', []))
                            elif isinstance(result, list):
                                count = len(result)
                            counter_updates = {'counters': {'cuecs_count': count}}
                        
                        if entity_updates:
                            _update_job_state(job_id, entity_updates, redis_client)
                        if counter_updates:
                            _update_job_state(job_id, counter_updates, redis_client)
            except Exception as final_update_err:
                logger.warning(f"Could not perform final progress updates: {final_update_err}")
        
        # Write combined_result.json ONCE after ALL extractors complete (including framework mapping)
        # This ensures framework_mappings and all other fields are included
        results.update(extractor_results)
        _write_partial_combined(results)
            
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
            # Try in-memory results first (from parallel extraction), then fall back to file-loaded extractor_results
            val = results.get(ext_key)
            if val is None:
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
        update_progress(100, "Scan Complete")
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
