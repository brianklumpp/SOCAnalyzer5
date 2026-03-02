# --- All imports at the top (PEP8 best practice) ---
import os
import json
import logging
import traceback
import argparse
import time  # Added missing import for watchdog timing and progress tracking
import threading  # Still needed for ThreadPoolExecutor in parallel metadata
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
from .job_state import job_hmset, job_hset, job_hget, job_hgetall


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
    logger=None,
    job_paths=None
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
        job_paths: Dict with job-specific paths (json_dir, logs_dir, temp_dir)
        
    Returns:
        Dict with keys: 'product_extraction', 'report_date_extraction', 
        'coverage_period_extraction', 'cuec_extraction', 'subservice_orgs_extraction'
        
    Example:
        from backend.app.scan_threading import IntelligentTaskExecutor, ProgressTracker
        
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
            validated_report_type, job_id, redis_client, logger, job_paths
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
                    job_hset(job_id, 'status', status_messages[extractor_name], redis_client)
            except Exception:
                pass  # Fail silently
        
        try:
            # Pass job_paths and job_id to metadata extractors
            result = extractor_func(job_paths=job_paths, job_id=job_id)
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
                
                # Update Redis job state with flat hash fields
                if job_id and redis_client:
                    try:
                        entity_updates = {}
                        if extractor_name == 'auditor_extraction' and result:
                            auditor = result.get('auditor') if isinstance(result, dict) else result
                            if auditor:
                                entity_updates['auditor'] = str(auditor)
                        
                        elif extractor_name == 'product_extraction' and result:
                            product = result.get('product') if isinstance(result, dict) else result
                            if product:
                                entity_updates['product'] = str(product)
                        
                        elif extractor_name == 'report_date_extraction' and result:
                            report_date = result.get('report_date') if isinstance(result, dict) else result
                            if report_date:
                                entity_updates['report_date'] = str(report_date)
                        
                        elif extractor_name == 'coverage_period_extraction' and result:
                            if isinstance(result, dict):
                                if result.get('start_date') and result.get('end_date'):
                                    coverage_str = f"{result['start_date']} to {result['end_date']}"
                                elif result.get('as_of_date'):
                                    coverage_str = f"As of {result['as_of_date']}"
                                elif result.get('end_date'):
                                    coverage_str = f"As of {result['end_date']}"
                                else:
                                    coverage_str = str(result)
                                entity_updates['coverage_period'] = coverage_str
                            else:
                                entity_updates['coverage_period'] = str(result)
                        
                        # Build counter updates (flat fields now)
                        if extractor_name == 'cuec_extraction' and result:
                            if isinstance(result, dict):
                                entity_updates['cuecs_count'] = len(result.get('cuecs', []))
                        
                        elif extractor_name == 'subservice_orgs_extraction' and result:
                            if isinstance(result, dict):
                                entity_updates['subservice_orgs_count'] = len(result.get('subservice_orgs', []))
                        
                        if entity_updates:
                            job_hmset(job_id, entity_updates, redis_client)
                    
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
        from .scan_threading.intelligent_executor import TaskPriority
        
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
    logger=None,
    job_paths=None
):
    """
    Sequential fallback for metadata extraction.
    
    Runs extractors one at a time in the original order.
    
    Args:
        validated_report_type: ReportType enum value
        job_id: Redis job ID for progress updates
        redis_client: Redis client for state updates
        logger: Logger instance
        job_paths: Dict with job-specific paths (json_dir, logs_dir, temp_dir)
    
    Returns:
        Dict with extraction results
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    logger.info("[SEQUENTIAL_METADATA] Running metadata extractors sequentially")
    
    results = {}
    
    # Import CUEC extraction wrapper
    def _run_cuec_extraction():
        from .extractors.cuec_extractor import extract_cuecs
        return extract_cuecs(report_type=validated_report_type.value, job_paths=job_paths, job_id=job_id)
    
    def _run_subservice_orgs_extraction():
        from .extractors.subservice_orgs import extract_subservice_orgs
        return extract_subservice_orgs(job_paths=job_paths, job_id=job_id)
    
    extractors = [
        ('product_extraction', lambda: extract_product_from_report(job_paths=job_paths, job_id=job_id)),
        ('report_date_extraction', lambda: extract_report_date(job_paths=job_paths, job_id=job_id)),
        ('coverage_period_extraction', lambda: extract_coverage_period(job_paths=job_paths, job_id=job_id)),
        ('cuec_extraction', _run_cuec_extraction),
        ('subservice_orgs_extraction', _run_subservice_orgs_extraction),
    ]
    
    for name, func in extractors:
        try:
            logger.info(f"[SEQUENTIAL_METADATA] Starting {name}")
            result = func()
            results[name] = result
            logger.info(f"[SEQUENTIAL_METADATA] {name} completed")
            
            # Update Redis job state with flat hash fields
            if job_id and redis_client and result:
                try:
                    entity_updates = {}
                    if name == 'product_extraction':
                        product = result.get('product') if isinstance(result, dict) else result
                        if product:
                            entity_updates['product'] = str(product)
                    
                    elif name == 'report_date_extraction':
                        report_date = result.get('report_date') if isinstance(result, dict) else result
                        if report_date:
                            entity_updates['report_date'] = str(report_date)
                    
                    elif name == 'coverage_period_extraction':
                        coverage = result.get('coverage_period') if isinstance(result, dict) else result
                        if coverage:
                            entity_updates['coverage_period'] = str(coverage)
                    
                    # Counter updates (flat fields)
                    if name == 'cuec_extraction' and isinstance(result, dict):
                        entity_updates['cuecs_count'] = len(result.get('cuecs', []))
                    elif name == 'subservice_orgs_extraction' and isinstance(result, dict):
                        entity_updates['subservice_orgs_count'] = len(result.get('subservice_orgs', []))
                    
                    if entity_updates:
                        job_hmset(job_id, entity_updates, redis_client)
                
                except Exception as e:
                    logger.warning(f"[SEQUENTIAL_METADATA] Could not update job state: {e}")
        
        except Exception as e:
            logger.error(f"[SEQUENTIAL_METADATA] {name} failed: {e}")
            logger.error(traceback.format_exc())
            results[name] = None
    
    return results


def analyze_pdf_file(pdf_path, output_json_path='data/json/section_results.json', report_type='SOC2', 
                      progress_callback=None, checklist_callback=None, job_id=None, 
                      executor=None, progress_tracker=None, job_paths=None, password=None):
    # Reset GPT tracking at start of analysis
    from .gpt_tracker import reset_tracking, get_usage_summary
    reset_tracking()
    logger = logging.getLogger(__name__)
    
    # Validate job_paths parameter
    if not job_paths or not isinstance(job_paths, dict):
        raise ValueError("[ANALYZE] job_paths parameter is required for job isolation")
    if not all(k in job_paths for k in ['json_dir', 'logs_dir', 'temp_dir']):
        raise ValueError("[ANALYZE] job_paths must contain json_dir, logs_dir, and temp_dir keys")
    
    logger.info(f"[JOB {job_id}] Starting analysis with isolated workspace: {job_paths['json_dir']}")
    
    # Log parallel execution status
    if executor:
        logger.info(f"[PARALLEL_EXEC] Parallel execution ENABLED (max_workers={executor.max_workers if hasattr(executor, 'max_workers') else 'unknown'})")
    else:
        logger.info("[PARALLEL_EXEC] Parallel execution DISABLED (running sequentially)")
    
    # Log PDF password status
    if password:
        logger.info(f"[JOB {job_id}] PDF password provided - will attempt decryption")
    
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
    CHECKPOINT_PATH = str(job_paths['json_dir'] / '_extraction_checkpoint.json')
    if os.path.isfile(CHECKPOINT_PATH):
        try:
            os.remove(CHECKPOINT_PATH)
            logger.info(f"Cleared checkpoint file for fresh scan")
        except Exception as e:
            logger.warning(f"Failed to clear checkpoint: {e}")
    
    # List of files to clear in job-specific directory
    files_to_clear = [
        str(job_paths['json_dir'] / 'section_results.json'),
        str(job_paths['json_dir'] / 'control_result.json'),
        str(job_paths['json_dir'] / 'cuec_result.json'),
        str(job_paths['json_dir'] / 'auditor_result.json'),
        str(job_paths['json_dir'] / 'company_result.json'),
        str(job_paths['json_dir'] / 'product_result.json'),
        str(job_paths['json_dir'] / 'report_date_result.json'),
        str(job_paths['json_dir'] / 'coverage_period_result.json'),
        str(job_paths['json_dir'] / 'subservice_orgs_result.json'),
        str(job_paths['json_dir'] / '_extraction_checkpoint.json'),
    ]
    for f in files_to_clear:
        try:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            # For JSON outputs, write an empty JSON object to avoid stale content
            if f.endswith('section_results.json'):
                # Section results will be regenerated below; start with an empty array for clarity
                with open(f, 'w', encoding='utf-8') as clearf:
                    clearf.write('[]')
            elif f.endswith('.json'):
                with open(f, 'w', encoding='utf-8') as clearf:
                    clearf.write('{}')
        except Exception:
            # Ignore if file does not exist yet or cannot be written; downstream steps will recreate as needed
            pass
    # Special-case: do NOT pre-create/overwrite combined_result.json; remove it if present to indicate not-yet-written
    try:
        _combined_path = str(job_paths['json_dir'] / 'combined_result.json')
        if os.path.isfile(_combined_path):
            os.remove(_combined_path)
    except Exception:
        pass

    # Always resolve data paths relative to the project root
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    def data_path(rel_path):
        # For job-isolated paths, use job_paths directly
        if rel_path.startswith('data/json/'):
            filename = os.path.basename(rel_path)
            return str(job_paths['json_dir'] / filename)
        elif rel_path.startswith('data/output/'):
            filename = os.path.basename(rel_path)
            return str(job_paths['temp_dir'] / filename)
        else:
            return os.path.join(PROJECT_ROOT, rel_path)

    _last_progress_pct = 0  # monotonic guard

    def update_progress(percent, status=None):
        nonlocal _last_progress_pct
        # Never let progress go backward (parallel tasks may report out of order)
        if percent < _last_progress_pct and percent < 100:
            logger.debug(f"[PROGRESS] Suppressed backward progress {percent}% (current {_last_progress_pct}%)")
            # Still update status text if provided, but keep the higher percent
            if status and progress_callback:
                progress_callback(_last_progress_pct, status)
            return
        _last_progress_pct = percent
        if progress_callback:
            progress_callback(percent, status)

    def update_checklist(statuses):
        if checklist_callback:
            checklist_callback(statuses)

    logger.debug(f"[JOB {job_id}] Starting analyze_pdf_file for {pdf_path}")
    if not os.path.isfile(pdf_path):
        logger.error(f"[JOB {job_id}] File {pdf_path} not found.")
        raise FileNotFoundError(f"File {pdf_path} not found.")

    # Set up job-specific paths
    OUTPUT_TEXT_FILE = str(job_paths['temp_dir'] / 'output.txt')
    SECTION_JSON_PATH = str(job_paths['json_dir'] / 'section_results.json')
    AUDITOR_JSON_PATH = str(job_paths['json_dir'] / 'auditor_result.json')
    COMPANY_JSON_PATH = str(job_paths['json_dir'] / 'company_result.json')
    PDF_TXT_PATH = str(job_paths['temp_dir'] / 'output.txt')

    # Helper for control extraction progress based on section end_line
    control_section = None
    try:
        with open(SECTION_JSON_PATH, 'r', encoding='utf-8') as sf:
            _secs = json.load(sf)
            control_section = next((s for s in _secs if s.get('topic') == 'Control_Descriptions'), None)
    except Exception:
        control_section = None

    def _control_progress_hook(latest_ctrl_end_line: int):
        """Update progress during control extraction (20-55% range)."""
        try:
            if progress_callback and control_section and isinstance(control_section.get('end_line'), int):
                ctrl_end = max(0, latest_ctrl_end_line)
                sec_end = max(1, control_section['end_line'])
                pct = 20 + int(35 * min(1.0, ctrl_end / float(sec_end)))
                update_progress(pct, f"Controls {ctrl_end}/{sec_end}")
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
        update_progress(1, "Checking for embedded files...")
        from .pdf_handler import extract_embedded_files, flatten_pdf
        
        temp_extract_dir = os.path.join(os.path.dirname(pdf_path), 'extracted')
        embedded_pdfs = extract_embedded_files(pdf_path, temp_extract_dir, password=password)
        
        if embedded_pdfs:
            # Use GPT to determine which PDF is the actual SOC report
            # (Some reports have cover sheet as main + embedded report, others have report as main + embedded supplements)
            import fitz
            from .gpt_client import gpt_extract
            try:
                # Extract first page text from both PDFs
                main_doc = fitz.open(pdf_path)
                main_pages = len(main_doc)
                main_first_page = main_doc[0].get_text()[:2000]  # First 2000 chars
                main_doc.close()
                
                embedded_doc = fitz.open(embedded_pdfs[0])
                embedded_pages = len(embedded_doc)
                embedded_first_page = embedded_doc[0].get_text()[:2000]
                embedded_doc.close()
                
                # Ask GPT which one is the actual report
                prompt = f"""You are analyzing two PDFs to determine which is the actual SOC 1 or SOC 2 audit report.

PDF A (Main file, {main_pages} pages):
{main_first_page}

PDF B (Embedded file, {embedded_pages} pages):
{embedded_first_page}

Which PDF appears to be the actual SOC audit report (vs a cover letter, terms of use, or supplementary document)?

Respond with ONLY the letter (A or B) and a brief reason (max 20 words).
Format: X - reason"""

                response = gpt_extract(
                    prompt=prompt,
                    extractor_name="embedded_pdf_selection"
                )
                
                choice = response.strip().upper()[0] if response else 'A'
                logger.info(f"GPT selection: {response.strip()}")
                
                if choice == 'B':
                    logger.info(f"Using embedded PDF based on GPT analysis")
                    # Store embedded PDF for serving in split view
                    try:
                        with open(embedded_pdfs[0], 'rb') as f:
                            embedded_pdf_bytes = f.read()
                        standardized_results["embedded_pdf_file"] = embedded_pdf_bytes
                        standardized_results["embedded_pdf_filename"] = os.path.basename(embedded_pdfs[0])
                        logger.info(f"Stored embedded PDF ({len(embedded_pdf_bytes)} bytes) for split view")
                    except Exception as e:
                        logger.error(f"Failed to store embedded PDF: {e}")
                    # Use the embedded PDF as the source
                    pdf_path = embedded_pdfs[0]
                else:
                    logger.info(f"Using main PDF based on GPT analysis (embedded appears to be supplementary)")
            except Exception as e:
                logger.error(f"Failed to analyze PDFs with GPT: {e}, using main PDF")
        
        # Check if PDF needs flattening (has interactive elements or protected content)
        # Try flattening first, then fall back to original if it fails
        update_progress(2, "Preprocessing PDF...")
        flattened_path = pdf_path.replace('.pdf', '_flattened.pdf')
        flatten_success = flatten_pdf(pdf_path, flattened_path, password=password)
        
        if flatten_success and os.path.exists(flattened_path):
            logger.info(f"Using flattened PDF for extraction: {flattened_path}")
            extraction_path = flattened_path
        else:
            logger.warning(f"PDF flattening failed or skipped, using original PDF")
            extraction_path = pdf_path
        
        # Always (re)generate section_results.json before running extractors
        update_progress(3, "Extracting text from PDF...")
        extract_text_from_pdf(extraction_path, OUTPUT_TEXT_FILE, password=password)
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
        update_progress(5, "Analyzing sections...")
        with open(OUTPUT_TEXT_FILE, 'r', encoding='utf-8') as f:
            text = f.read()
        section_data = find_section_candidates(text)
        
        # Extract sections list and toc_page_offset
        if isinstance(section_data, dict):
            section_results = section_data.get('sections', [])
            toc_page_offset = section_data.get('toc_page_offset', None)
        else:
            # Legacy format: section_data is already the list
            section_results = section_data
            toc_page_offset = None
        
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
        # Fix end_line indexing: pdf_handler returns 0-indexed end_line, but
        # start_line was overwritten above to 1-indexed. Convert end_line to
        # 1-indexed so the pair is consistent for extractors using
        # text_lines[start_line-1:end_line] slicing.
        for section in section_results:
            el = section.get('end_line')
            sl = section.get('start_line', 0)
            if el is not None and isinstance(el, int) and el > 0 and sl > 0:
                # Only convert if end_line appears 0-indexed (i.e. less than start_line or equal)
                # pdf_handler's second pass sets end_line = next_start_line - 1 (0-indexed)
                # After analyze.py converts start_line to 1-indexed, a correct section would have
                # end_line < start_line of the NEXT section (already 1-indexed).  We add 1 to
                # align end_line with 1-indexed convention expected by create_aware_chunks().
                section['end_line'] = el + 1
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
            {"name": "management_response_extraction", "status": "pending"}, # Index 11
            {"name": "objective_extraction", "status": "pending"}, # Index 12
            {"name": "cuec_extraction", "status": "pending"},     # Index 13
            {"name": "subservice_orgs_extraction", "status": "pending"}, # Index 14
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
        
        # Store toc_page_offset if detected during section identification
        # Always persist a value (0 when no offset detected) so the frontend
        # never has to guess with a ?? 2 fallback.
        results['toc_page_offset'] = toc_page_offset if toc_page_offset is not None else 0
        logger.info(f"Storing TOC page offset in results: {results['toc_page_offset']}")
        
        # Initialize checkpoint tracking variable early
        completed_extractors = []
        
        # Check for section_results.json existence before running extractors
        if not os.path.isfile(data_path(output_json_path)):
            logger.error(f"Required file {output_json_path} not found before running extractors.")
            update_progress(100, "Required file missing before extractors.")
            return {"error": f"Required file {output_json_path} not found before running extractors."}
        # --- Run company and auditor sequentially (prerequisites) ---
        # Wrapper for subservice_orgs to run both extraction and filtering sequentially
        def _run_subservice_orgs_extraction(job_paths=job_paths, job_id=job_id):
            """Run subservice extraction + GPT filtering, return final filtered result.

            Also write a debug dump of the direct return value to
            `data/logs/debug_subservice_postrun_dump.json` so end-to-end runs
            can be compared with isolated extractor runs.
            """
            try:
                extract_subservice_orgs(job_paths=job_paths, job_id=job_id)  # Extracts and writes raw results to JSON
            except Exception:
                # Let downstream filter attempt to load partial results if available
                pass
            try:
                res = filter_third_parties_with_gpt(job_paths=job_paths, job_id=job_id)  # Reads JSON, filters, writes back, returns result
            except Exception as e:
                # If filtering fails, attempt to load on-disk JSON as a fallback
                try:
                    fallback_p = job_paths['json_dir'] / 'subservice_orgs_result.json'
                    if fallback_p.exists():
                        with open(fallback_p, 'r', encoding='utf-8') as pf:
                            res = json.load(pf)
                    else:
                        raise
                except Exception:
                    # Re-raise original filtering error if fallback also fails
                    raise
            # Write a debug post-run dump for immediate inspection by the analyzer
            try:
                log_dir = job_paths['logs_dir']
                log_dir.mkdir(parents=True, exist_ok=True)
                dump_path = log_dir / f'{job_id}_debug_subservice_postrun_dump.json'
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
            # Load sections from job-specific path
            section_json_path = job_paths['json_dir'] / 'section_results.json'
            with open(section_json_path, 'r', encoding='utf-8') as f:
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
                    job_paths=job_paths,  # Pass job-specific paths
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
                    job_paths=job_paths,  # Pass job-specific paths
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
                available_frameworks = get_available_frameworks(report_type=validated_report_type.value, scan_default_only=True)
                logger.info(f"[FRAMEWORK_MAPPING] Loaded {len(available_frameworks)} frameworks (scan_default_only): {list(available_frameworks.keys())}")
                
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
        
        # Management response extraction function - runs after control extraction
        async def _run_management_response_extraction():
            """
            Extract management responses for deviation controls using cascading search strategies.
            
            Returns:
                Dict with extracted response count
            """
            try:
                logger.info("[MGMT_RESPONSE] Starting management response extraction for deviations")
                
                # Load controls from control_result.json
                control_json_path = data_path('data/json/control_result.json')
                if not os.path.isfile(control_json_path):
                    logger.warning("[MGMT_RESPONSE] control_result.json not found, skipping management response extraction")
                    return {"responses_extracted": 0, "error": "No controls to process"}
                
                with open(control_json_path, 'r', encoding='utf-8') as f:
                    control_data = json.load(f)
                
                controls = control_data.get('controls', [])
                if not controls:
                    logger.warning("[MGMT_RESPONSE] No controls found in control_result.json")
                    return {"responses_extracted": 0}
                
                # Check if there are any deviation controls
                deviation_controls = [c for c in controls if c.get('has_deviation')]
                if not deviation_controls:
                    logger.info("[MGMT_RESPONSE] No deviation controls found, skipping management response extraction")
                    return {"responses_extracted": 0, "message": "No deviations to process"}
                
                logger.info(f"[MGMT_RESPONSE] Found {len(deviation_controls)} deviation controls")
                
                # Load extracted text with page markers
                txt_path = data_path('data/json/extracted_text.txt')
                if not os.path.isfile(txt_path):
                    logger.warning("[MGMT_RESPONSE] extracted_text.txt not found, cannot extract management responses")
                    return {"responses_extracted": 0, "error": "No extracted text available"}
                
                with open(txt_path, 'r', encoding='utf-8') as f:
                    txt_lines = f.readlines()
                
                # Count total pages
                total_pages = 0
                for line in txt_lines:
                    if line.strip().startswith('=== PAGE '):
                        try:
                            page_num = int(line.strip().split()[2])
                            total_pages = max(total_pages, page_num)
                        except (IndexError, ValueError):
                            continue
                
                logger.info(f"[MGMT_RESPONSE] Document has {total_pages} pages")
                
                # Get Redis client for caching
                from .extractors.management_response_extractor import extract_management_responses_for_scan
                
                # Extract management responses
                response_results = await extract_management_responses_for_scan(
                    controls=controls,
                    txt_lines=txt_lines,
                    total_pages=total_pages,
                    scan_id=job_id,
                    redis_client=redis_client
                )
                
                # Update controls with management response data
                controls_updated = 0
                for control in controls:
                    control_id = control.get('control_id')
                    if control_id in response_results:
                        response_data = response_results[control_id]
                        control['management_response_text'] = response_data['text']
                        control['management_response_page_refs'] = response_data['page_refs']
                        control['management_response_line_ref'] = response_data.get('line_ref')
                        control['management_response_confidence'] = response_data['confidence']
                        control['response_detection_method'] = response_data['method']
                        controls_updated += 1
                
                # Save updated controls back to control_result.json
                control_data['controls'] = controls
                with open(control_json_path, 'w', encoding='utf-8') as f:
                    json.dump(control_data, f, indent=2, ensure_ascii=False)
                
                logger.info(f"[MGMT_RESPONSE] Successfully extracted management responses for {controls_updated}/{len(deviation_controls)} deviation controls")
                
                return {"responses_extracted": controls_updated, "deviations_total": len(deviation_controls)}
                
            except Exception as e:
                logger.error(f"[MGMT_RESPONSE] Management response extraction failed: {e}", exc_info=True)
                # Continue with warnings - don't fail the entire scan
                return {"responses_extracted": 0, "error": str(e)}
        
        # Wrapper for CUEC extraction - routes based on report_type with progress updates
        def _run_cuec_extraction(job_paths=job_paths, job_id=job_id):
            """
            Run unified CUEC extraction with report type parameter and real-time progress updates.
            Supports SOC1, SOC2, and COMBINED report types.
            """
            from .extractors.cuec_extractor import extract_cuecs
            logger.info(f"Running unified CUEC extractor (report_type={validated_report_type.value})")
            # Pass job_id and redis_client for real-time progress updates
            return extract_cuecs(
                report_type=validated_report_type.value,
                job_paths=job_paths,
                job_id=job_id,
                redis_client=redis_client
            )
        
        # Logo fetching function - runs after company is identified
        def _run_logo_fetching():
            """Fetch company logo after company has been identified."""
            logger.error(f"[LOGO_DEBUG] _run_logo_fetching called! job_paths exists: {job_paths is not None}")
            try:
                logger.error(f"[LOGO_DEBUG] About to call data_path...")
                company_json_path = data_path('data/json/company_result.json')
                logger.error(f"[LOGO_DEBUG] data_path returned: {company_json_path}")
                logger.error(f"[LOGO_DEBUG] Checking if file exists...")
                file_exists = os.path.isfile(company_json_path)
                logger.error(f"[LOGO_DEBUG] File exists: {file_exists}")
                if not file_exists:
                    logger.warning("[LOGO] company_result.json not found, skipping logo fetch")
                    return {"success": False, "reason": "Company not yet identified"}
                
                # Wait for file to be fully written/closed (race condition fix)
                import time
                logger.error(f"[LOGO_DEBUG] Waiting 0.5s for file to be fully written...")
                time.sleep(0.5)
                
                logger.error(f"[LOGO_DEBUG] Opening file...")
                try:
                    with open(company_json_path, 'r', encoding='utf-8') as f:
                        company_data = json.load(f)
                    logger.error(f"[LOGO_DEBUG] File loaded successfully!")
                    logger.error(f"[LOGO_DEBUG] File data: {company_data}")
                except Exception as file_ex:
                    logger.error(f"[LOGO_DEBUG] FILE OPERATION FAILED: {type(file_ex).__name__}: {file_ex}")
                    raise
                
                logger.error(f"[LOGO_DEBUG] Extracting company name and domain...")
                company_name = company_data.get('company', 'Unknown')
                company_domain = company_data.get('company_domain') or company_data.get('domain')
                logger.error(f"[LOGO_DEBUG] company_name={company_name}, company_domain={company_domain}")
                
                if not company_domain:
                    logger.error(f"[LOGO] No domain found for {company_name}, skipping logo fetch")
                    return {"success": False, "reason": "No domain available"}
                
                logger.error(f"[LOGO] Fetching logo for {company_name} (domain: {company_domain})")
                
                # Fetch logo directly from external APIs (Clearbit with Google fallback)
                # Note: Database caching requires async session, so fetching directly for now
                import requests
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                
                CLEARBIT_LOGO_API = "https://logo.clearbit.com/{domain}"
                GOOGLE_FAVICON_API = "https://www.google.com/s2/favicons?domain={domain}&sz=128"
                REQUEST_TIMEOUT = 5  # seconds
                
                logo_url = None
                
                # Try Clearbit API first
                try:
                    clearbit_url = CLEARBIT_LOGO_API.format(domain=company_domain)
                    response = requests.head(clearbit_url, timeout=REQUEST_TIMEOUT, allow_redirects=True, verify=False)
                    if response.status_code == 200:
                        logo_url = clearbit_url
                        logger.error(f"[LOGO] ✓ Logo fetched from Clearbit: {logo_url}")
                except Exception as e:
                    logger.error(f"[LOGO] Clearbit API failed: {str(e)}")
                
                # Fallback to Google Favicon API
                if not logo_url:
                    try:
                        google_url = GOOGLE_FAVICON_API.format(domain=company_domain)
                        response = requests.head(google_url, timeout=REQUEST_TIMEOUT, allow_redirects=True, verify=False)
                        if response.status_code == 200:
                            logo_url = google_url
                            logger.error(f"[LOGO] ✓ Logo fetched from Google Favicon: {logo_url}")
                    except Exception as e:
                        logger.error(f"[LOGO] Google Favicon API failed: {str(e)}")
                
                if logo_url:
                    logger.error(f"[LOGO] SUCCESS! Returning logo_url: {logo_url}")
                    return {"success": True, "logo_url": logo_url, "domain": company_domain}
                else:
                    logger.error(f"[LOGO] No logo available for {company_domain}")
                    return {"success": False, "reason": "Logo not available from external services"}
                    
            except Exception as e:
                logger.error(f"[LOGO] Logo fetch failed: {e}")
                return {"success": False, "reason": str(e)}
        
        prereq_steps = [
            (3, "company_extraction", extract_company_from_report, "Running company extractor...", 8),
            (4, "logo_fetching", _run_logo_fetching, "Fetching company logo...", 10),
        ]
        # Control extraction step (has internal parallelism, progress hook covers 20-55%)
        parallel_steps = [
            (9, "control_extraction", _run_control_extraction, "Running controls extractor...", 20),
        ]
        # Management response extraction step - runs in parallel pool after control extraction
        management_response_step = [
            (11, "management_response_extraction", _run_management_response_extraction, "Extracting management responses for deviations...", 58),
        ]
        
        # Objective extraction step - runs after management response extraction
        # Extracts control objectives and maps them to controls
        async def _run_objective_extraction():
            """Extract control objectives and create control-objective mappings."""
            try:
                from .extractors.objective_extractor import extract_objectives, map_controls_to_objectives
                from .database import get_db_session
                
                logger.info("Extracting control objectives from report")
                
                # Get extracted text from job path
                txt_path = job_paths['extracted_text']
                with open(txt_path, 'r', encoding='utf-8') as f:
                    extracted_text = f.read()

                sections = []
                try:
                    section_json_path = job_paths['json_dir'] / 'section_results.json'
                    if section_json_path.exists():
                        with open(section_json_path, 'r', encoding='utf-8') as sf:
                            sections = json.load(sf)
                except Exception as e:
                    logger.warning(f"Objective extraction: failed to load sections: {e}")
                
                # Get database session
                db_session = next(get_db_session())
                
                try:
                    # Extract objectives
                    _result = extract_objectives(
                        extracted_text=extracted_text,
                        scan_id=None,  # Will be set when saving to database
                        db_session=db_session,
                        sections=sections,
                        job_id=job_id,
                        redis_client=redis_client
                    )
                    objectives = _result[0] if isinstance(_result, tuple) else _result
                    
                    logger.info(f"Extracted {len(objectives)} control objectives")
                    
                    # Map objectives to controls (if scan_id available)
                    # Note: This requires controls to be saved to database first
                    # In practice, this will happen during data insertion phase
                    
                    return {"success": True, "objectives_count": len(objectives)}
                    
                finally:
                    db_session.close()
                    
            except Exception as e:
                logger.error(f"Objective extraction failed: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
        
        objective_extraction_step = [
            (11.5, "objective_extraction", _run_objective_extraction, "Extracting control objectives...", 60),
        ]
        
        # Post-control extraction steps (CUEC only — subservice_orgs moved to parallel pool)
        post_control_parallel_steps = [
            (12, "cuec_extraction", _run_cuec_extraction, "Running CUECs extractor...", 78),
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
                    cur_status = job_hget(job_id, 'status', redis_client) if job_id else None
                    cur_paused = job_hget(job_id, 'paused', redis_client) if job_id else False
                    if cur_status == 'Paused' and not cur_paused:
                        logger.error(f"[PAUSE_CLEANUP] Removing stale 'Paused' status from job {job_id}")
                        job_hset(job_id, 'status', 'Starting', redis_client)
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
                    cur_status = job_hget(job_id, 'status', redis_client)
                    has_paused_flag = job_hget(job_id, 'paused', redis_client)
                    
                    if cur_status is None:
                        logger.error(f"[PAUSE_CHECK] No job data found in Redis for {job_id}")
                        return
                    
                    is_job_paused = cur_status == "Paused"
                    
                    # VERBOSE LOGGING - Log job state details
                    logger.error(f"[PAUSE_CHECK] job_id={job_id}, queue_paused={is_queue_paused}, status='{cur_status}', paused_flag={has_paused_flag}")
                    
                    # Only trigger if BOTH status is "Paused" AND paused flag is True
                    # This prevents false positives from stale status
                    if is_queue_paused or (is_job_paused and has_paused_flag):
                        logger.warning(f"[PAUSE] Scan paused (queue:{is_queue_paused}, job:{is_job_paused}, flag:{has_paused_flag})")
                        raise RuntimeError("Scan paused by user")
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
                
                # Merge existing with new data (new overwrites old)
                merged_data = {**existing_data, **standardized_partial}
                
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
        logger.error(f"[DEBUG_PREREQ] ABOUT TO RUN PREREQ LOOP, prereq_steps has {len(prereq_steps)} items")
        for idx, key, func, status, pct in prereq_steps:
            logger.error(f"[DEBUG_PREREQ] ENTERING PREREQ LOOP for {key}")
            # Check for pause before each step
            _check_pause()
            
            try:
                update_progress(pct, status)
                logger.info(f"[PREREQ] Starting: {status}")  # Changed to INFO for visibility
                # Pass job_paths and job_id to extractors that need them
                if key in ('company_extraction', 'auditor_extraction', 'product_extraction', 'report_date_extraction', 'coverage_period_extraction'):
                    results[key] = func(job_paths=job_paths, job_id=job_id)
                else:
                    results[key] = func()
                logger.info(f"[PREREQ] {key} completed: {results[key]}")  # Changed to INFO
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
            
            # **CRITICAL FIX**: Update identified_entities in Redis for company AND logo
            logger.info(f"[REDIS_UPDATE_CHECK] key={key}, job_id={job_id is not None}, redis_client={redis_client is not None}, results_has_key={key in results}, results_key_value={results.get(key) is not None}")
            if job_id and redis_client and results.get(key):
                try:
                    entity_updates = {}
                    if key == 'company_extraction' and isinstance(results[key], dict):
                        company_name = results[key].get('company', 'Unknown')
                        company_domain = results[key].get('company_domain')
                        entity_updates = {'company': company_name}
                        if company_domain:
                            entity_updates['company_domain'] = company_domain
                        logger.info(f"[PROGRESS] Company identified: {company_name}")
                    elif key == 'logo_fetching' and isinstance(results[key], dict):
                        # Logo fetching now returns actual logo URL
                        if results[key].get('success') and results[key].get('logo_url'):
                            logo_url = results[key]['logo_url']
                            entity_updates = {'company_logo_url': logo_url}
                            logger.info(f"[PROGRESS] Company logo fetched: {logo_url}")
                        else:
                            reason = results[key].get('reason', 'Unknown')
                            logger.info(f"[PROGRESS] Logo fetch failed: {reason}")
                    elif key == 'auditor_extraction':
                        auditor_name = results[key].get('auditor') if isinstance(results[key], dict) else results[key]
                        if auditor_name:
                            entity_updates = {'auditor': str(auditor_name)}
                            logger.info(f"[PROGRESS] Auditor identified: {auditor_name}")
                    elif key == 'product_extraction':
                        product = results[key].get('product') if isinstance(results[key], dict) else results[key]
                        if product:
                            entity_updates = {'product': str(product)}
                            logger.info(f"[PROGRESS] Product identified: {product}")
                    elif key == 'report_date_extraction':
                        report_date = results[key].get('report_date') if isinstance(results[key], dict) else results[key]
                        if report_date:
                            entity_updates = {'report_date': str(report_date)}
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
                            entity_updates = {'coverage_period': coverage_str}
                            logger.info(f"[PROGRESS] Coverage period identified: {coverage_str}")
                    
                    if entity_updates:
                        job_hmset(job_id, entity_updates, redis_client)
                except Exception as entity_err:
                    logger.warning(f"Could not update identified_entities: {entity_err}")
            
            # Update checklist in Redis after each sequential extractor
            update_checklist(checklist)
        
        # Run metadata extractors in parallel using the OLD superior implementation
        # DEPENDENCY: Auditor extraction requires company extraction to be completed first
        # (needs company name for exclusion logic). Company + logo MUST run before this point.
        if config.ENABLE_PARALLEL_METADATA_EXTRACTION and executor and progress_tracker:
            logger.info("[PARALLEL_EXEC] Running metadata extractors (auditor, product, report_date, coverage_period) in PARALLEL mode")
            logger.info("[PARALLEL_EXEC] Dependencies satisfied: company extraction ✓, logo fetching ✓")
            
            # Call the superior run_metadata_extractors_parallel function with correct parameters
            metadata_results = run_metadata_extractors_parallel(
                validated_report_type=validated_report_type,
                executor=executor,
                progress_tracker=progress_tracker,
                job_id=job_id,
                redis_client=redis_client,
                logger=logger,
                job_paths=job_paths
            )
            
            # STEP 4: Detect partial failures
            successful = [k for k, v in metadata_results.items() if v is not None]
            failed = [k for k, v in metadata_results.items() if v is None]
            
            if failed:
                logger.warning(f"[PARALLEL_EXEC] Partial metadata failure: {len(failed)}/{len(metadata_results)} extractors failed: {failed}")
                if job_id and redis_client:
                    try:
                        job_hmset(job_id, {
                            'extraction_partial': True,
                            'extraction_failures': failed
                        }, redis_client)
                    except Exception as e:
                        logger.warning(f"[PARALLEL_EXEC] Could not update partial failure status: {e}")
            else:
                logger.info(f"[PARALLEL_EXEC] All {len(metadata_results)} metadata extractors completed successfully")
            
            # Merge results
            for key, res in metadata_results.items():
                results[key] = res
                # Update checklist for these extractors
                for item in checklist:
                    if item.get('name') == key:
                        item['status'] = 'done' if res is not None else 'error'
                        break
            
            # STEP 3: Track completed extractors (checkpoint will be saved later in normal flow)
            for key in successful:
                if key not in completed_extractors:
                    completed_extractors.append(key)
            
            logger.info(f"[PARALLEL_EXEC] Parallel metadata extraction complete: {len(successful)} successful, {len(failed)} failed")
            logger.info(f"[PARALLEL_EXEC] Completed extractors tracked: {completed_extractors}")
            update_checklist(checklist)
        
        # --- Run remaining extractors in parallel threads ---
        extractor_results = {}
        def run_extractor(idx, key, func, status, pct):
            # Check for pause before starting extractor
            _check_pause()
            
            try:
                update_progress(pct, status)
                logger.debug(f"{status}")
                # Nested wrapper functions (_run_*) are closures with access to job_paths/job_id
                # Direct extractor functions need parameters passed explicitly
                if key in ('product_extraction', 'report_date_extraction', 'coverage_period_extraction', 'auditor_extraction', 'company_extraction'):
                    res = func(job_paths=job_paths, job_id=job_id)
                else:
                    # Wrapper functions and other extractors don't need parameters (closures)
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
                        job_hmset(job_id, {
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
                    
                    # Update Redis counters after control extraction completes
                    if k == 'control_extraction' and job_id and redis_client:
                        try:
                            controls_count = 0
                            if isinstance(res, dict) and isinstance(res.get('controls'), list):
                                controls_count = len(res['controls'])
                            elif isinstance(res, list):
                                controls_count = len(res)
                            job_hmset(job_id, {
                                'controls_count': controls_count,
                                'controls_percent': 100,
                            }, redis_client)
                            logger.info(f"[COUNTERS] Control extraction complete: {controls_count} controls")
                        except Exception as counter_err:
                            logger.warning(f"[COUNTERS] Failed to update control count: {counter_err}")
                    
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
            
            # ======================================================================
            # PERFORMANCE: Run framework mapping + management response + objective
            # extraction + subservice orgs concurrently where possible
            # ======================================================================
            # Framework mapping reads/writes control_result.json
            # Objective extraction reads extracted text + sections, writes to DB
            # Management response reads control_result.json (read-only for deviations)
            # Subservice orgs reads extracted text + sections only (no control dependency)
            # These can safely overlap (framework mapping only modifies framework_mapping
            # fields, while objective extraction writes to a different table, and
            # subservice orgs operates on independent data)
            # ======================================================================
            
            import concurrent.futures as _cf
            import threading as _threading
            
            _parallel_tasks = {}
            _parallel_executor = _cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="post_control")
            _checkpoint_lock = _threading.Lock()  # Protect completed_extractors + save_checkpoint
            
            # Task 1: Framework mapping
            if 'control_extraction' in extractor_results and 'control_framework_mapping' not in completed_extractors:
                def _run_framework_mapping_task():
                    logger.info("Starting control framework mapping (parallel)")
                    try:
                        checklist[10]["status"] = "running"
                        update_checklist(checklist)
                        
                        if job_id and redis_client:
                            try:
                                control_json_path = data_path('data/json/control_result.json')
                                if os.path.isfile(control_json_path):
                                    with open(control_json_path, 'r', encoding='utf-8') as f:
                                        control_data = json.load(f)
                                    total_controls = len(control_data.get('controls', []))
                                    job_hmset(job_id, {
                                        'status': f'Mapping 0/{total_controls} controls to frameworks...',
                                        'controls_mapped_count': 0,
                                        'controls_mapped_percent': 0,
                                        'total_controls': total_controls
                                    }, redis_client)
                            except Exception as init_err:
                                logger.warning(f"Could not initialize framework mapping state: {init_err}")
                        
                        mapping_result = _run_control_framework_mapping()
                        
                        # Reload control_result.json to get mapped controls
                        try:
                            control_json_path = data_path('data/json/control_result.json')
                            if os.path.isfile(control_json_path):
                                with open(control_json_path, 'r', encoding='utf-8') as f:
                                    updated_control_data = json.load(f)
                                extractor_results['control_extraction'] = updated_control_data
                                results['control_extraction'] = updated_control_data
                                logger.info("[FRAMEWORK_MAPPING] Reloaded control_result.json with framework mappings")
                        except Exception as reload_err:
                            logger.error(f"Failed to reload control_result.json after framework mapping: {reload_err}")
                        
                        checklist[10]["status"] = "done"
                        update_checklist(checklist)
                        with _checkpoint_lock:
                            completed_extractors.append('control_framework_mapping')
                            save_checkpoint(completed_extractors)
                        logger.info("Control framework mapping completed successfully")
                        return mapping_result
                    except Exception as e:
                        logger.error(f"Control framework mapping failed: {e}\n{traceback.format_exc()}")
                        checklist[10]["status"] = "error"
                        update_checklist(checklist)
                        return None
                
                _parallel_tasks['framework_mapping'] = _parallel_executor.submit(_run_framework_mapping_task)
            
            # Task 2: Management response extraction
            if 'management_response_extraction' not in completed_extractors:
                def _run_mgmt_response_task():
                    logger.info("[MGMT_RESPONSE] Running management response extraction (parallel)")
                    try:
                        import asyncio
                        mgmt_response_result = asyncio.run(_run_management_response_extraction())
                        logger.info(f"[MGMT_RESPONSE] Extraction complete: {mgmt_response_result}")
                        checklist[11]["status"] = "done"
                        update_checklist(checklist)
                        with _checkpoint_lock:
                            completed_extractors.append('management_response_extraction')
                            save_checkpoint(completed_extractors)
                        return mgmt_response_result
                    except Exception as e:
                        logger.error(f"Management response extraction failed: {e}\n{traceback.format_exc()}")
                        checklist[11]["status"] = "error"
                        update_checklist(checklist)
                        return None
                
                _parallel_tasks['mgmt_response'] = _parallel_executor.submit(_run_mgmt_response_task)
            
            # Task 3: Objective extraction (runs in parallel with framework mapping)
            # NOTE: The initial GPT extraction of objectives doesn't need framework mapping.
            # Only the final map_controls_to_objectives() step needs controls in DB,
            # which happens later during data insertion.
            _objective_extraction_future = None
            if 'objective_extraction' not in completed_extractors:
                def _run_objective_extraction_task():
                    logger.info("[OBJECTIVE] Running control objective extraction (parallel)")
                    update_progress(60, "Extracting control objectives...")
                    # Note: monotonic guard prevents this from going backward
                    
                    for item in checklist:
                        if item.get('name') == 'objective_extraction':
                            item['status'] = 'running'
                            break
                    update_checklist(checklist)
                    
                    try:
                        from .extractors.objective_extractor import extract_objectives
                        from sqlalchemy import create_engine
                        from sqlalchemy.orm import sessionmaker
                        
                        sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
                        sync_engine = create_engine(sync_db_url, echo=False)
                        SessionLocal = sessionmaker(bind=sync_engine)
                        objective_db_session = SessionLocal()
                        
                        try:
                            txt_path = None
                            candidate_paths = []
                            if job_paths and isinstance(job_paths, dict) and job_paths.get('temp_dir'):
                                candidate_paths.append(job_paths['temp_dir'] / 'output.txt')
                            candidate_paths.append(data_path('data/output/output.txt'))
                            
                            for candidate in candidate_paths:
                                if os.path.isfile(candidate):
                                    txt_path = candidate
                                    break
                            
                            if txt_path:
                                with open(txt_path, 'r', encoding='utf-8') as f:
                                    extracted_text = f.read()
                                
                                sections = []
                                try:
                                    section_json_path = job_paths['json_dir'] / 'section_results.json'
                                    if section_json_path.exists():
                                        with open(section_json_path, 'r', encoding='utf-8') as sf:
                                            sections = json.load(sf)
                                except Exception as e:
                                    logger.warning(f"[OBJECTIVE] Failed to load sections: {e}")
                                
                                _result = extract_objectives(
                                    extracted_text=extracted_text,
                                    scan_id=None,
                                    db_session=objective_db_session,
                                    sections=sections,
                                    job_id=job_id,
                                    redis_client=redis_client
                                )
                                objectives = _result[0] if isinstance(_result, tuple) else _result
                                
                                logger.info(f"[OBJECTIVE] Extracted {len(objectives)} control objectives")
                                results['objectives'] = objectives
                                results['objectives_extracted'] = len(objectives)
                                
                                for item in checklist:
                                    if item.get('name') == 'objective_extraction':
                                        item['status'] = 'done'
                                        break
                                update_checklist(checklist)
                            else:
                                logger.warning("[OBJECTIVE] Extracted text not found, skipping")
                                results['objectives_extracted'] = 0
                                for item in checklist:
                                    if item.get('name') == 'objective_extraction':
                                        item['status'] = 'error'
                                        break
                                update_checklist(checklist)
                        finally:
                            objective_db_session.close()
                        
                        with _checkpoint_lock:
                            completed_extractors.append('objective_extraction')
                            save_checkpoint(completed_extractors)
                        return True
                        
                    except Exception as obj_err:
                        logger.error(f"[OBJECTIVE] Objective extraction failed: {obj_err}", exc_info=True)
                        results['objectives_extracted'] = 0
                        results['objective_extraction_error'] = str(obj_err)
                        for item in checklist:
                            if item.get('name') == 'objective_extraction':
                                item['status'] = 'error'
                                item['error'] = str(obj_err)[:100]
                                break
                        update_checklist(checklist)
                        with _checkpoint_lock:
                            completed_extractors.append('objective_extraction')
                            save_checkpoint(completed_extractors)
                        return False
                
                _parallel_tasks['objective_extraction'] = _parallel_executor.submit(_run_objective_extraction_task)
            
            # Task 4: Subservice orgs extraction (independent of controls — needs only extracted text/sections)
            if 'subservice_orgs_extraction' not in completed_extractors:
                def _run_subservice_orgs_task():
                    logger.info("[SUBSERVICE_ORGS] Running subservice orgs extraction (parallel)")
                    update_progress(65, "Running subservice orgs extractor...")
                    try:
                        for item in checklist:
                            if item.get('name') == 'subservice_orgs_extraction':
                                item['status'] = 'running'
                                break
                        update_checklist(checklist)
                        
                        result = _run_subservice_orgs_extraction()
                        
                        extractor_results['subservice_orgs_extraction'] = result
                        
                        # Update Redis counter
                        if job_id and redis_client and result:
                            try:
                                count = 0
                                if isinstance(result, dict):
                                    count = len(result.get('subservice_orgs', []))
                                elif isinstance(result, list):
                                    count = len(result)
                                job_hset(job_id, 'subservice_orgs_count', count, redis_client)
                                logger.info(f"[COUNTERS] Subservice orgs extraction complete: {count} orgs")
                            except Exception as counter_err:
                                logger.warning(f"[COUNTERS] Failed to update subservice orgs count: {counter_err}")
                        
                        for item in checklist:
                            if item.get('name') == 'subservice_orgs_extraction':
                                item['status'] = 'done'
                                break
                        update_checklist(checklist)
                        
                        with _checkpoint_lock:
                            completed_extractors.append('subservice_orgs_extraction')
                            save_checkpoint(completed_extractors)
                        
                        logger.info("[SUBSERVICE_ORGS] Subservice orgs extraction completed successfully")
                        return result
                    except Exception as e:
                        logger.error(f"[SUBSERVICE_ORGS] Subservice orgs extraction failed: {e}", exc_info=True)
                        for item in checklist:
                            if item.get('name') == 'subservice_orgs_extraction':
                                item['status'] = 'error'
                                break
                        update_checklist(checklist)
                        return None
                
                _parallel_tasks['subservice_orgs'] = _parallel_executor.submit(_run_subservice_orgs_task)
            
            # Wait for all parallel tasks to complete
            logger.info(f"[PARALLEL_POST_CONTROL] Waiting for {len(_parallel_tasks)} parallel tasks: {list(_parallel_tasks.keys())}")
            for task_name, future in _parallel_tasks.items():
                try:
                    result = future.result(timeout=3600)  # 1 hour max per task
                    logger.info(f"[PARALLEL_POST_CONTROL] {task_name} completed: {result}")
                except Exception as e:
                    logger.error(f"[PARALLEL_POST_CONTROL] {task_name} failed: {e}")
            
            _parallel_executor.shutdown(wait=False)
            logger.info("[PARALLEL_POST_CONTROL] All post-control tasks completed")
            
            # NOTE: Auto-merge of objectives happens post-save in main.py
            # scan_id (DB row ID) is not available here — it's assigned after analyze_pdf_file returns
            
            # Run remaining post-control steps (CUEC — subservice_orgs already in parallel pool above)
            logger.info("[PARALLEL_EXEC] Running remaining post-control extractors")
            
            # Filter post-control steps to skip already completed
            remaining_post_control_steps = [(idx, key, func, status, pct) for (idx, key, func, status, pct) in post_control_parallel_steps 
                                           if key not in completed_extractors]
            
            for idx, key, func, status, pct in remaining_post_control_steps:
                logger.info(f"Starting post-control extractor '{key}'")
                try:
                    k, res = run_extractor(idx, key, func, status, pct)
                    extractor_results[k] = res
                    logger.info(f"Extractor '{k}' completed successfully")
                    
                    # Update Redis counters immediately after each post-control extractor
                    if job_id and redis_client and res:
                        try:
                            if k == 'cuec_extraction':
                                count = 0
                                if isinstance(res, dict):
                                    count = len(res.get('cuecs', []))
                                elif isinstance(res, list):
                                    count = len(res)
                                job_hset(job_id, 'cuecs_count', count, redis_client)
                                logger.info(f"[COUNTERS] CUEC extraction complete: {count} CUECs")
                            elif k == 'subservice_orgs_extraction':
                                count = 0
                                if isinstance(res, dict):
                                    count = len(res.get('subservice_orgs', []))
                                elif isinstance(res, list):
                                    count = len(res)
                                job_hset(job_id, 'subservice_orgs_count', count, redis_client)
                                logger.info(f"[COUNTERS] Subservice orgs extraction complete: {count} orgs")
                        except Exception as counter_err:
                            logger.warning(f"[COUNTERS] Failed to update counter for {k}: {counter_err}")
                    
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
                                    entity_updates = {'product': str(product)}
                                    logger.info(f"[PROGRESS] Product identified: {product}")
                            elif key == 'report_date_extraction':
                                report_date = extractor_results[key].get('report_date') if isinstance(extractor_results[key], dict) else extractor_results[key]
                                if report_date:
                                    entity_updates = {'report_date': str(report_date)}
                                    logger.info(f"[PROGRESS] Report date identified: {report_date}")
                            elif key == 'coverage_period_extraction':
                                coverage = extractor_results[key].get('coverage_period') if isinstance(extractor_results[key], dict) else extractor_results[key]
                                if coverage:
                                    entity_updates = {'coverage_period': str(coverage)}
                                    logger.info(f"[PROGRESS] Coverage period identified: {coverage}")
                            elif key == 'subservice_orgs_extraction':
                                # Extract subservice orgs count
                                res = extractor_results[key]
                                count = 0
                                if isinstance(res, dict):
                                    count = len(res.get('subservice_orgs', []))
                                elif isinstance(res, list):
                                    count = len(res)
                                counter_updates = {'subservice_orgs_count': count}
                                logger.info(f"[PROGRESS] Found {count} subservice organizations")
                            elif key == 'cuec_extraction':
                                # Extract CUECs count
                                res = extractor_results[key]
                                count = 0
                                if isinstance(res, dict):
                                    count = len(res.get('cuecs', []))
                                elif isinstance(res, list):
                                    count = len(res)
                                counter_updates = {'cuecs_count': count}
                                logger.info(f"[PROGRESS] Found {count} CUECs")
                            
                            # Apply all updates in one call
                            all_updates = {}
                            all_updates.update(entity_updates)
                            all_updates.update(counter_updates)
                            if all_updates:
                                job_hmset(job_id, all_updates, redis_client)
                        except Exception as entity_err:
                            logger.warning(f"Could not update progress for {key}: {entity_err}")
                    
                    # Merge extractor results into main results dict
                    results.update(extractor_results)
        
        # Post-extraction progress updates (for both parallel and sequential modes)
        # Update final entity counts and progress state
        if job_id and redis_client:
            try:
                final_updates = {}
                for key, result in extractor_results.items():
                    if result and key not in ['control_extraction']:
                        if key == 'product_extraction':
                            product = result.get('product') if isinstance(result, dict) else result
                            if product:
                                final_updates['product'] = str(product)
                        elif key == 'report_date_extraction':
                            report_date = result.get('report_date') if isinstance(result, dict) else result
                            if report_date:
                                final_updates['report_date'] = str(report_date)
                        elif key == 'coverage_period_extraction':
                            coverage = result.get('coverage_period') if isinstance(result, dict) else result
                            if coverage:
                                final_updates['coverage_period'] = str(coverage)
                        elif key == 'subservice_orgs_extraction':
                            count = 0
                            if isinstance(result, dict):
                                count = len(result.get('subservice_orgs', []))
                            elif isinstance(result, list):
                                count = len(result)
                            final_updates['subservice_orgs_count'] = count
                        elif key == 'cuec_extraction':
                            count = 0
                            if isinstance(result, dict):
                                count = len(result.get('cuecs', []))
                            elif isinstance(result, list):
                                count = len(result)
                            final_updates['cuecs_count'] = count
                
                if final_updates:
                    job_hmset(job_id, final_updates, redis_client)
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
        try:
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
        except (PermissionError, OSError):
            # Skip logging if we can't write to the file
            pass
        
        update_progress(85, "Extraction Complete - Finalizing...")
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

def get_text_snippet(text, offset, context=200):
    """Extract a snippet of text around the given offset"""
    start = max(0, offset - context)
    end = min(len(text), offset + context)
    return text[start:end]

def offset_to_line(text, offset):
    """Convert character offset to line number"""
    return text[:offset].count('\n') + 1

# Legacy standalone test code removed - use production pipeline with job-specific paths
if __name__ == "__main__":
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
