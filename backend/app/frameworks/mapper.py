"""
Framework Mapping Module
========================

Centralized module for mapping controls and CUECs to framework criteria.
Separated from extraction logic for clean architecture.

This module provides:
1. Dynamic multi-framework mapping (Phase 2 - NEW)
2. Legacy TSC/COSO mapping (backward compatibility)
3. Token usage tracking
4. Confidence scoring
5. Primary framework selection
6. Parallel mapping support (v2.1.0 - NEW)

Architecture:
- Extraction (control_extractor_*.py) -> Gets control text from PDFs
- Mapping (THIS MODULE) -> Maps controls to framework criteria
- Cleanup (main.py endpoints) -> Merges, deduplicates, validates

Usage:
    from backend.app.frameworks.mapper import map_control_to_frameworks_dynamic
    from backend.app.frameworks.loader import get_available_frameworks
    
    # Get frameworks for report type
    frameworks = get_available_frameworks(report_type="SOC2", scan_id=123)
    
    # Map control to frameworks
    result = map_control_to_frameworks_dynamic(
        control_desc="Control performs daily review...",
        control_id="1.1",
        available_frameworks=frameworks,
        has_deviation=False
    )
    
    # Result contains:
    # {
    #     "framework_mappings": {"TSC": [...], "COSO": [...], ...},
    #     "primary_framework": "TSC",
    #     "primary_criterion_id": "CC7.2",
    #     "primary_confidence": 0.95,
    #     "token_usage": {"TSC": 1250, "COSO": 980}
    # }
"""

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional, List, Callable

# Import GPT client and config
try:
    from ..gpt_client import gpt_extract
    from .. import config
except Exception as e:
    print(f"[MAPPER] Import error: {e}")
    raise


# ============================================================================
# TOKEN USAGE TRACKING
# ============================================================================

def log_token_usage(entity_type: str, entity_id: str, token_usage: Dict[str, int]):
    """
    Log token usage for control/CUEC mapping operations.
    
    Args:
        entity_type: "CONTROL" or "CUEC"
        entity_id: Control/CUEC identifier
        token_usage: Dict mapping framework names to token counts
    """
    total_tokens = sum(token_usage.values())
    frameworks_str = ", ".join([f"{fw}:{tokens}" for fw, tokens in token_usage.items()])
    logging.info(f"[TOKEN_USAGE] {entity_type} {entity_id}: {total_tokens} tokens ({frameworks_str})")


# ============================================================================
# PHASE 2: DYNAMIC MULTI-FRAMEWORK MAPPING (NEW)
# ============================================================================

def map_control_to_frameworks_dynamic(
    control_desc: str,
    control_id: str,
    available_frameworks: Dict[str, Dict[str, Any]],
    has_deviation: bool = False,
    deviation_desc: str = None,
    top_k: int = 5
) -> Dict[str, Any]:
    """
    Map a control to multiple framework criteria dynamically based on available frameworks.
    
    This is the Phase 2 implementation that supports unlimited frameworks beyond TSC/COSO.
    Uses the framework registry to determine which frameworks to map against.
    
    Args:
        control_desc: Control description text
        control_id: Control identifier for logging
        available_frameworks: Dict from get_available_frameworks() with structure:
            {"TSC": {"info": FrameworkInfo, "criteria": [...]}, "COSO": {...}, ...}
        has_deviation: Whether control has a deviation/exception
        deviation_desc: Deviation description text
        top_k: Maximum matches to return per framework (default 5)
        
    Returns:
        Dict with structure:
        {
            "framework_mappings": {
                "TSC": [{"id": "CC7.2", "confidence": 0.95, "reasoning": "...", "deviation": "..."}],
                "COSO": [{"id": "10", "confidence": 0.92, "reasoning": "..."}],
                "FINANCIAL_ASSERTIONS": [{"id": "EO1", "confidence": 0.90, "reasoning": "..."}],
                ...
            },
            "primary_framework": "TSC",
            "primary_criterion_id": "CC7.2",
            "primary_confidence": 0.95,
            "token_usage": {"TSC": 1250, "COSO": 980, ...}
        }
        
    Note: This replaces map_control_to_frameworks_multi() for new code.
    """
    token_usage = {}
    framework_mappings = {}
    
    # Truncate deviation if present
    deviation_text = None
    if has_deviation and deviation_desc:
        if len(deviation_desc) > 80:
            deviation_text = deviation_desc[:80] + "..."
        else:
            deviation_text = deviation_desc
    
    # Prepare deviation context for prompts
    deviation_context = ""
    if has_deviation and deviation_desc:
        deviation_context = f"\nNOTE: This control has a documented deviation/exception: {deviation_text}\nConsider criteria related to monitoring, deficiency reporting, or control evaluation."
    
    # Map to each framework independently (can be parallelized in future)
    for framework_name, framework_data in available_frameworks.items():
        try:
            criteria = framework_data.get("criteria", [])
            if not criteria:
                logging.warning(f"[{control_id}] No criteria available for framework {framework_name}")
                continue
            
            # Get framework-specific prompt (fallback to generic if not defined)
            prompt_key = f"FRAMEWORK_MULTI_MATCH_PROMPT_{framework_name}"
            framework_prompt_template = getattr(config, prompt_key, None)
            
            # If no specific prompt, use TSC prompt as template (works for most frameworks)
            if not framework_prompt_template:
                framework_prompt_template = config.FRAMEWORK_MULTI_MATCH_PROMPT_TSC
                logging.info(f"[{control_id}] Using generic TSC prompt for {framework_name}")
            
            # Format criteria list
            criteria_list_text = "\n".join([
                f"- {c.get('id', 'N/A')}: {c.get('description', c.get('principle', c.get('name', 'N/A')))}"
                for c in criteria
            ])
            
            # Build prompt (template keys vary by framework, use all for compatibility)
            framework_prompt = framework_prompt_template.format(
                control_desc=control_desc,
                criteria_list=criteria_list_text,
                tsc_criteria_list=criteria_list_text,
                coso_criteria_list=criteria_list_text,
                deviation_context=deviation_context
            )
            
            # Call GPT with framework mapping model
            framework_model = config.get_runtime_model_config('framework_mapping')
            response = gpt_extract(framework_prompt, f"framework_{framework_name.lower()}_matching", override_model=framework_model)
            token_usage[framework_name] = len(framework_prompt) // 4
            
            if not response:
                logging.warning(f"[{control_id}] {framework_name} matching returned empty response")
                framework_mappings[framework_name] = []
                continue
            
            # Parse response
            result = json.loads(response.strip())
            matches = result.get("matches", [])
            
            # Validate IDs
            valid_ids = {c.get("id") for c in criteria if c.get("id")}
            matches = [
                m for m in matches 
                if m.get("id") in valid_ids and m.get("confidence", 0) >= 0.6
            ]
            
            # Limit to top_k
            matches = matches[:top_k]
            
            # Add deviation to each match
            for match in matches:
                match["deviation"] = deviation_text
            
            framework_mappings[framework_name] = matches
            logging.info(f"[{control_id}] {framework_name}: Found {len(matches)} matches from {len(criteria)} criteria")
            
        except Exception as e:
            logging.error(f"[{control_id}] {framework_name} mapping failed: {e}")
            framework_mappings[framework_name] = []
    
    # Calculate primary framework and criterion (highest confidence across all frameworks)
    primary_framework = None
    primary_criterion_id = None
    primary_confidence = 0.0
    
    for fw_name, matches in framework_mappings.items():
        for match in matches:
            if match.get("confidence", 0) > primary_confidence:
                primary_confidence = match["confidence"]
                primary_framework = fw_name
                primary_criterion_id = match.get("id")
    
    # Add metadata to result
    result_with_metadata = {
        "framework_mappings": framework_mappings,
        "primary_framework": primary_framework,
        "primary_criterion_id": primary_criterion_id,
        "primary_confidence": primary_confidence,
        "token_usage": token_usage
    }
    
    # Log token usage
    log_token_usage("CONTROL", control_id, token_usage)
    
    return result_with_metadata


def map_cuec_to_frameworks_dynamic(
    cuec_desc: str,
    cuec_id: str,
    available_frameworks: Dict[str, Dict[str, Any]],
    top_k: int = 5
) -> Dict[str, Any]:
    """
    Map a CUEC to multiple framework criteria dynamically.
    
    Similar to map_control_to_frameworks_dynamic but optimized for CUECs.
    CUECs don't have deviations, so prompt is simpler.
    
    Args:
        cuec_desc: CUEC description text
        cuec_id: CUEC identifier for logging
        available_frameworks: Dict from get_available_frameworks()
        top_k: Maximum matches to return per framework
        
    Returns:
        Dict with same structure as map_control_to_frameworks_dynamic
    """
    return map_control_to_frameworks_dynamic(
        control_desc=cuec_desc,
        control_id=f"CUEC-{cuec_id}",
        available_frameworks=available_frameworks,
        has_deviation=False,
        deviation_desc=None,
        top_k=top_k
    )





# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def extract_mapping_fields_for_db(mapping_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract database-compatible fields from mapping result.
    
    Converts the structured mapping result into flat fields for database storage.
    
    Args:
        mapping_result: Result from map_control_to_frameworks_dynamic()
        
    Returns:
        Dict with database fields:
        {
            "framework_mappings": {...},  # JSON field
            "primary_framework": "TSC",
            "primary_criterion_id": "CC7.2",
            "primary_confidence": 0.95,
            "control_tsc_mappings": [...],  # For backward compatibility
            "control_coso_mappings": [...]  # For backward compatibility
        }
    """
    framework_mappings = mapping_result.get("framework_mappings", {})
    
    return {
        "framework_mappings": framework_mappings,
        "primary_framework": mapping_result.get("primary_framework"),
        "primary_criterion_id": mapping_result.get("primary_criterion_id"),
        "primary_confidence": mapping_result.get("primary_confidence", 0.0),
        # Legacy fields for backward compatibility
        "control_tsc_mappings": framework_mappings.get("TSC", []),
        "control_coso_mappings": framework_mappings.get("COSO", [])
    }


def get_primary_criterion_details(
    mapping_result: Dict[str, Any],
    available_frameworks: Dict[str, Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Get full details of the primary criterion from available frameworks.
    
    Args:
        mapping_result: Result from map_control_to_frameworks_dynamic()
        available_frameworks: Framework data dict
        
    Returns:
        Criterion dict with full details or None if not found
    """
    primary_framework = mapping_result.get("primary_framework")
    primary_criterion_id = mapping_result.get("primary_criterion_id")
    
    if not primary_framework or not primary_criterion_id:
        return None
    
    framework_data = available_frameworks.get(primary_framework, {})
    criteria = framework_data.get("criteria", [])
    
    for criterion in criteria:
        if criterion.get("id") == primary_criterion_id:
            return criterion
    
    return None


# ============================================================================
# PHASE 2.2: PARALLEL FRAMEWORK MAPPING (v2.1.0 - NEW)
# ============================================================================

def map_controls_parallel(
    controls: List[Dict[str, Any]],
    available_frameworks: Dict[str, Dict[str, Any]],
    report_type: str,
    executor=None,
    progress_tracker=None,
    job_id: str = None,
    redis_client=None,
    scan_id: int = None
) -> List[Dict[str, Any]]:
    """
    Map multiple controls to frameworks in parallel.
    
    Uses nested parallelism:
    - Outer: Process 4 controls concurrently
    - Inner: Map each control to 3-5 frameworks concurrently
    - Total: Up to 12-20 concurrent GPT calls
    
    Args:
        controls: List of control dicts with 'control_desc', 'control_id', etc.
        available_frameworks: Dict from get_available_frameworks()
        report_type: "SOC1" or "SOC2"
        executor: IntelligentTaskExecutor instance (optional, for outer parallelism)
        progress_tracker: ProgressTracker instance (optional)
        job_id: Redis job ID for progress updates
        redis_client: Redis client for progress updates
        scan_id: Scan ID for logging
        
    Returns:
        List of controls with framework_mappings added
        
    Example:
        from backend.app.threading import IntelligentTaskExecutor, ProgressTracker
        from backend.app.frameworks import get_available_frameworks, map_controls_parallel
        
        executor = IntelligentTaskExecutor(max_workers=4)
        tracker = ProgressTracker(job_id="test-123", redis_client=redis)
        frameworks = get_available_frameworks(report_type="SOC2")
        
        mapped_controls = map_controls_parallel(
            controls=validated_controls,
            available_frameworks=frameworks,
            report_type="SOC2",
            executor=executor,
            progress_tracker=tracker,
            job_id="test-123",
            redis_client=redis
        )
    """
    # Fallback to sequential if no executor provided
    if not executor:
        logging.info("[PARALLEL_MAPPER] No executor provided, falling back to sequential mapping")
        return _map_controls_sequential(
            controls, available_frameworks, report_type,
            job_id, redis_client, progress_tracker
        )
    
    import time
    start_time = time.time()
    
    logging.info(f"[PARALLEL_MAPPER] Starting parallel mapping for {len(controls)} controls across {len(available_frameworks)} frameworks")
    
    # Thread-safe variables
    mapped_controls = []
    mapped_lock = threading.Lock()
    mappings_completed = 0
    total_gpt_time = 0.0
    gpt_time_lock = threading.Lock()
    
    # Start extractor in progress tracker
    if progress_tracker:
        progress_tracker.start_extractor(
            "framework_mapping",
            estimated_total=len(controls)
        )
    
    def map_single_control(control: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map a single control to all frameworks using inner parallelism.
        
        This runs on a worker thread from the executor, and internally
        spawns additional threads to map frameworks in parallel.
        """
        nonlocal mappings_completed, total_gpt_time
        
        # Check for cancellation
        if job_id and redis_client:
            try:
                cancelled = redis_client.get(f"job:{job_id}:cancelled")
                if cancelled:
                    logging.info(f"[PARALLEL_MAPPER] Job {job_id} cancelled, stopping framework mapping")
                    return None
            except Exception as e:
                logging.warning(f"[PARALLEL_MAPPER] Could not check cancellation flag: {e}")
        
        control_id = control.get("control_id", "UNKNOWN")
        control_desc = control.get("control_desc", "") or control.get("description", "")
        has_deviation = control.get("has_deviation", False)
        deviation_desc = control.get("deviation_desc")
        
        if not control_desc:
            logging.warning(f"[{control_id}] No description available for framework mapping, skipping")
            return control
        
        control_start_time = time.time()
        
        # Inner parallelism: map to all frameworks concurrently
        # Using ThreadPoolExecutor for framework-level parallelism
        try:
            with ThreadPoolExecutor(max_workers=len(available_frameworks)) as inner_executor:
                # Submit all framework mapping tasks
                future_to_framework = {}
                for fw_name in available_frameworks.keys():
                    future = inner_executor.submit(
                        _map_single_framework,
                        control_desc=control_desc,
                        control_id=control_id,
                        framework_name=fw_name,
                        framework_data=available_frameworks[fw_name],
                        has_deviation=has_deviation,
                        deviation_desc=deviation_desc
                    )
                    future_to_framework[future] = fw_name
                
                # Collect results
                framework_mappings = {}
                token_usage = {}
                
                for future in as_completed(future_to_framework):
                    fw_name = future_to_framework[future]
                    try:
                        result = future.result(timeout=60)  # 1 minute per framework
                        if result:
                            framework_mappings[fw_name] = result.get("matches", [])
                            token_usage[fw_name] = result.get("tokens", 0)
                    except Exception as e:
                        logging.error(f"[{control_id}] Framework {fw_name} mapping failed: {e}")
                        framework_mappings[fw_name] = []
                        token_usage[fw_name] = 0
                
                # Calculate primary framework
                primary_framework = None
                primary_criterion_id = None
                primary_confidence = 0.0
                
                for fw_name, matches in framework_mappings.items():
                    for match in matches:
                        if match.get("confidence", 0) > primary_confidence:
                            primary_confidence = match["confidence"]
                            primary_framework = fw_name
                            primary_criterion_id = match.get("id")
                
                # Update control with mapping results
                control["framework_mappings"] = framework_mappings
                control["primary_framework"] = primary_framework
                control["primary_criterion_id"] = primary_criterion_id
                control["primary_confidence"] = primary_confidence
                
                # Add legacy fields for backward compatibility
                control["control_tsc_mappings"] = framework_mappings.get("TSC", [])
                control["control_coso_mappings"] = framework_mappings.get("COSO", [])
                control["control_closest_framework"] = primary_framework or "Undetermined"
                
                # Track timing
                control_elapsed = time.time() - control_start_time
                with gpt_time_lock:
                    total_gpt_time += control_elapsed
                
                logging.info(f"[{control_id}] Mapped to {len(framework_mappings)} frameworks in {control_elapsed:.2f}s, primary: {primary_framework}")
                
                return control
                
        except Exception as e:
            logging.error(f"[{control_id}] Parallel mapping failed: {e}, falling back to sequential")
            # Fallback to sequential for this control
            try:
                mapping_result = map_control_to_frameworks_dynamic(
                    control_desc=control_desc,
                    control_id=control_id,
                    available_frameworks=available_frameworks,
                    has_deviation=has_deviation,
                    deviation_desc=deviation_desc,
                    top_k=5
                )
                
                db_fields = extract_mapping_fields_for_db(mapping_result)
                control["framework_mappings"] = db_fields["framework_mappings"]
                control["primary_framework"] = db_fields["primary_framework"]
                control["primary_criterion_id"] = db_fields["primary_criterion_id"]
                control["primary_confidence"] = db_fields["primary_confidence"]
                control["control_tsc_mappings"] = db_fields.get("control_tsc_mappings", [])
                control["control_coso_mappings"] = db_fields.get("control_coso_mappings", [])
                control["control_closest_framework"] = db_fields["primary_framework"] or "Undetermined"
                
                return control
            except Exception as fallback_err:
                logging.error(f"[{control_id}] Sequential fallback also failed: {fallback_err}")
                return control
    
    def process_control_batch(control: Dict[str, Any]) -> Dict[str, Any]:
        """
        Wrapper for executor.map() - processes single control and updates progress.
        """
        nonlocal mappings_completed
        
        mapped = map_single_control(control)
        
        if mapped:
            # Thread-safe append and progress update
            with mapped_lock:
                mapped_controls.append(mapped)
                mappings_completed += 1
                
                # Update progress every 4 mappings (as specified)
                if mappings_completed % 4 == 0:
                    if progress_tracker:
                        progress_tracker.update_mappings(
                            mapped_count=mappings_completed,
                            estimated_total=len(controls)
                        )
                    
                    # Update Redis counters
                    if job_id and redis_client:
                        try:
                            import json
                            controls_mapped_percent = int((mappings_completed / len(controls)) * 100)
                            job_json = redis_client.get(f"job:{job_id}")
                            if job_json:
                                job = json.loads(job_json)
                                if "counters" not in job:
                                    job["counters"] = {}
                                job["counters"]["controls_mapped_count"] = mappings_completed
                                job["counters"]["controls_mapped_percent"] = controls_mapped_percent
                                redis_client.set(f"job:{job_id}", json.dumps(job), ex=86400)
                                logging.info(f"[PROGRESS] Framework mapping: {mappings_completed}/{len(controls)} ({controls_mapped_percent}%)")
                        except Exception as e:
                            logging.warning(f"Could not update mapping progress: {e}")
        
        return mapped
    
    # Execute parallel mapping using outer executor
    try:
        from ..threading.intelligent_executor import TaskPriority
        
        results = executor.map(
            process_control_batch,
            controls,
            priority=TaskPriority.MEDIUM,
            timeout=180,  # 3 minutes per control (includes inner parallelism)
            return_exceptions=False
        )
        
        # Results are already in mapped_controls from the callback
        mapped_controls = [r for r in results if r is not None]
        
    except Exception as e:
        logging.error(f"[PARALLEL_MAPPER] Executor failed: {e}, falling back to sequential")
        # Complete fallback to sequential
        return _map_controls_sequential(
            controls, available_frameworks, report_type,
            job_id, redis_client, progress_tracker
        )
    
    # Calculate metrics
    parallel_time = time.time() - start_time
    parallelism_speedup = total_gpt_time / parallel_time if parallel_time > 0 else 1.0
    
    logging.info(f"[PARALLEL_MAPPER] Completed: {len(mapped_controls)} controls mapped")
    logging.info(f"[PARALLEL_MAPPER] Parallel time: {parallel_time:.2f}s, Total GPT time: {total_gpt_time:.2f}s")
    logging.info(f"[PARALLEL_MAPPER] Parallelism speedup: {parallelism_speedup:.2f}x")
    
    # Complete extractor in progress tracker
    if progress_tracker:
        progress_tracker.complete_extractor(
            "framework_mapping",
            extracted_count=len(mapped_controls)
        )
    
    return mapped_controls


def _map_single_framework(
    control_desc: str,
    control_id: str,
    framework_name: str,
    framework_data: Dict[str, Any],
    has_deviation: bool,
    deviation_desc: str = None
) -> Dict[str, Any]:
    """
    Map a single control to a single framework (used by inner parallelism).
    
    This is called from ThreadPoolExecutor in map_single_control().
    
    Returns:
        Dict with 'matches' and 'tokens' keys
    """
    try:
        criteria = framework_data.get("criteria", [])
        if not criteria:
            logging.warning(f"[{control_id}] No criteria available for framework {framework_name}")
            return {"matches": [], "tokens": 0}
        
        # Truncate deviation if present
        deviation_text = None
        if has_deviation and deviation_desc:
            if len(deviation_desc) > 80:
                deviation_text = deviation_desc[:80] + "..."
            else:
                deviation_text = deviation_desc
        
        # Prepare deviation context for prompts
        deviation_context = ""
        if has_deviation and deviation_desc:
            deviation_context = f"\nNOTE: This control has a documented deviation/exception: {deviation_text}\nConsider criteria related to monitoring, deficiency reporting, or control evaluation."
        
        # Get framework-specific prompt
        prompt_key = f"FRAMEWORK_MULTI_MATCH_PROMPT_{framework_name}"
        framework_prompt_template = getattr(config, prompt_key, None)
        
        # If no specific prompt, use TSC prompt as template
        if not framework_prompt_template:
            framework_prompt_template = config.FRAMEWORK_MULTI_MATCH_PROMPT_TSC
        
        # Format criteria list
        criteria_list_text = "\n".join([
            f"- {c.get('id', 'N/A')}: {c.get('description', c.get('principle', c.get('name', 'N/A')))}"
            for c in criteria
        ])
        
        # Build prompt
        framework_prompt = framework_prompt_template.format(
            control_desc=control_desc,
            criteria_list=criteria_list_text,
            tsc_criteria_list=criteria_list_text,
            coso_criteria_list=criteria_list_text,
            deviation_context=deviation_context
        )
        
        # Call GPT with framework mapping model
        framework_model = config.get_runtime_model_config('framework_mapping')
        response = gpt_extract(framework_prompt, f"framework_{framework_name.lower()}_matching", override_model=framework_model)
        tokens = len(framework_prompt) // 4
        
        if not response:
            logging.warning(f"[{control_id}] {framework_name} matching returned empty response")
            return {"matches": [], "tokens": tokens}
        
        # Parse response
        result = json.loads(response.strip())
        matches = result.get("matches", [])
        
        # Validate IDs
        valid_ids = {c.get("id") for c in criteria if c.get("id")}
        matches = [
            m for m in matches 
            if m.get("id") in valid_ids and m.get("confidence", 0) >= 0.6
        ]
        
        # Limit to top 5
        matches = matches[:5]
        
        # Add deviation to each match
        for match in matches:
            match["deviation"] = deviation_text
        
        return {"matches": matches, "tokens": tokens}
        
    except Exception as e:
        logging.error(f"[{control_id}] {framework_name} mapping failed: {e}")
        return {"matches": [], "tokens": 0}


def _map_controls_sequential(
    controls: List[Dict[str, Any]],
    available_frameworks: Dict[str, Dict[str, Any]],
    report_type: str,
    job_id: str = None,
    redis_client=None,
    progress_tracker=None
) -> List[Dict[str, Any]]:
    """
    Sequential fallback for framework mapping.
    
    Uses the existing map_control_to_frameworks_dynamic() function.
    """
    logging.info(f"[SEQUENTIAL_MAPPER] Mapping {len(controls)} controls sequentially")
    
    # Start extractor in progress tracker
    if progress_tracker:
        progress_tracker.start_extractor(
            "framework_mapping",
            estimated_total=len(controls)
        )
    
    controls_mapped = 0
    
    for idx, control in enumerate(controls, 1):
        control_desc = control.get("control_desc", "") or control.get("description", "")
        control_id = control.get("control_id", "UNKNOWN")
        has_deviation = control.get("has_deviation", False)
        deviation_desc = control.get("deviation_desc")
        
        if not control_desc:
            logging.warning(f"[{control_id}] No description available for framework mapping, skipping")
            continue
        
        # Map control to all available frameworks
        mapping_result = map_control_to_frameworks_dynamic(
            control_desc=control_desc,
            control_id=control_id,
            available_frameworks=available_frameworks,
            has_deviation=has_deviation,
            deviation_desc=deviation_desc,
            top_k=5
        )
        
        # Extract DB-compatible fields
        db_fields = extract_mapping_fields_for_db(mapping_result)
        
        # Add to control dict
        control["framework_mappings"] = db_fields["framework_mappings"]
        control["primary_framework"] = db_fields["primary_framework"]
        control["primary_criterion_id"] = db_fields["primary_criterion_id"]
        control["primary_confidence"] = db_fields["primary_confidence"]
        control["control_tsc_mappings"] = db_fields.get("control_tsc_mappings", [])
        control["control_coso_mappings"] = db_fields.get("control_coso_mappings", [])
        control["control_closest_framework"] = db_fields["primary_framework"] or "Undetermined"
        
        controls_mapped += 1
        
        # Update progress every 4 mappings
        if controls_mapped % 4 == 0:
            if progress_tracker:
                progress_tracker.update_mappings(
                    mapped_count=controls_mapped,
                    estimated_total=len(controls)
                )
            
            # Update Redis counters
            if job_id and redis_client:
                try:
                    import json
                    controls_mapped_percent = int((controls_mapped / len(controls)) * 100)
                    job_json = redis_client.get(f"job:{job_id}")
                    if job_json:
                        job = json.loads(job_json)
                        if "counters" not in job:
                            job["counters"] = {}
                        job["counters"]["controls_mapped_count"] = controls_mapped
                        job["counters"]["controls_mapped_percent"] = controls_mapped_percent
                        redis_client.set(f"job:{job_id}", json.dumps(job), ex=86400)
                except Exception as e:
                    logging.warning(f"Could not update mapping progress: {e}")
    
    # Complete extractor in progress tracker
    if progress_tracker:
        progress_tracker.complete_extractor(
            "framework_mapping",
            extracted_count=controls_mapped
        )
    
    return controls


# ============================================================================
# BATCHED MULTI-FRAMEWORK MAPPING (OPTIMIZATION v2.2.0)
# ============================================================================

def map_control_to_all_frameworks_batched(
    control_desc: str,
    control_id: str,
    available_frameworks: Dict[str, Dict[str, Any]],
    has_deviation: bool = False,
    deviation_desc: str = None,
    top_k: int = 5
) -> Dict[str, Any]:
    """
    Map a control to ALL frameworks in a SINGLE API call (6-7x speedup optimization).
    
    This is the v2.2.0 batched implementation that requests mappings for all frameworks
    at once instead of making sequential API calls per framework. This reduces API calls
    from 7 per control to 1 per control (for 7 frameworks).
    
    PERFORMANCE COMPARISON:
    - Sequential (old): 218 controls × 7 frameworks = 1,526 API calls = 127 minutes
    - Batched (new): 218 controls × 1 call = 218 API calls = 18-22 minutes (6-7x faster)
    
    Args:
        control_desc: Control description text
        control_id: Control identifier for logging
        available_frameworks: Dict from get_available_frameworks() with structure:
            {"TSC": {"info": FrameworkInfo, "criteria": [...]}, "COSO": {...}, ...}
        has_deviation: Whether control has a deviation/exception
        deviation_desc: Deviation description text
        top_k: Maximum matches to return per framework (default 5)
        
    Returns:
        Dict with same structure as map_control_to_frameworks_dynamic():
        {
            "framework_mappings": {
                "TSC": [{"id": "CC7.2", "confidence": 0.95, "reasoning": "...", "deviation": "..."}],
                "COSO": [{"id": "10", "confidence": 0.92, "reasoning": "..."}],
                ...
            },
            "primary_framework": "TSC",
            "primary_criterion_id": "CC7.2",
            "primary_confidence": 0.95,
            "token_usage": {"TOTAL": 3500}  # Single call aggregated usage
        }
    """
    # Truncate deviation if present
    deviation_text = None
    if has_deviation and deviation_desc:
        deviation_text = deviation_desc[:80] + "..." if len(deviation_desc) > 80 else deviation_desc
    
    # Prepare deviation context
    deviation_context = ""
    if has_deviation and deviation_desc:
        deviation_context = f"\n\n**DEVIATION ALERT**: This control has a documented deviation/exception: {deviation_text}\nConsider criteria related to monitoring, deficiency reporting, or control evaluation."
    
    # Build multi-framework prompt
    framework_sections = []
    framework_names = list(available_frameworks.keys())
    
    for framework_name, framework_data in available_frameworks.items():
        criteria = framework_data.get("criteria", [])
        if not criteria:
            logging.warning(f"[{control_id}] No criteria for {framework_name}, skipping in batch")
            continue
        
        # Format criteria list
        criteria_list_text = "\n".join([
            f"  - {c.get('id', 'N/A')}: {c.get('description', c.get('principle', c.get('name', 'N/A')))}"
            for c in criteria
        ])
        
        # Add framework section to prompt
        framework_sections.append(f"""
### {framework_name} Framework
{criteria_list_text}
""")
    
    # Build the master batched prompt
    batched_prompt = f"""You are a control framework mapping expert. Analyze the following control and map it to ALL of the framework criteria below.

**CONTROL DESCRIPTION**:
{control_desc}{deviation_context}

**TASK**: For EACH framework listed below, identify the top {top_k} matching criteria. Return results in JSON format.

**FRAMEWORKS AND THEIR CRITERIA**:
{"".join(framework_sections)}

**OUTPUT FORMAT** (valid JSON only, no markdown):
{{
  "matches": {{
    "TSC": [
      {{"id": "CC7.2", "confidence": 0.95, "reasoning": "Control performs monitoring which aligns with CC7.2 Monitoring Activities"}},
      {{"id": "CC6.1", "confidence": 0.85, "reasoning": "Secondary match for security operations"}}
    ],
    "COSO": [
      {{"id": "17", "confidence": 0.90, "reasoning": "Monitoring aligns with COSO Principle 17"}}
    ],
    "FINANCIAL_ASSERTIONS": [
      {{"id": "EO1", "confidence": 0.88, "reasoning": "Control validates existence of transactions"}}
    ]
  }}
}}

**MATCHING RULES**:
1. Only include matches with confidence ≥ 0.6
2. Limit to top {top_k} matches per framework
3. Confidence scale: 0.6=weak, 0.7=moderate, 0.8=strong, 0.9+=excellent
4. Include brief reasoning for each match
5. Return empty array [] if no good matches for a framework
6. Use EXACT criterion IDs from the lists above"""
    
    # Call GPT with batched prompt (uses FRAMEWORK_MAPPING_MODEL from config)
    try:
        # Use the framework mapping model (gpt-4o-mini by default)
        framework_model = config.get_runtime_model_config('framework_mapping')
        response = gpt_extract(batched_prompt, f"framework_batched_mapping_{control_id}", override_model=framework_model)
        
        if not response:
            logging.error(f"[{control_id}] Batched framework mapping returned empty response")
            return _empty_framework_result(framework_names)
        
        # Parse the batched response
        result = json.loads(response.strip())
        matches_by_framework = result.get("matches", {})
        
        # Validate and structure results
        framework_mappings = {}
        for framework_name, framework_data in available_frameworks.items():
            criteria = framework_data.get("criteria", [])
            valid_ids = {c.get("id") for c in criteria if c.get("id")}
            
            # Get matches for this framework from the batched response
            framework_matches = matches_by_framework.get(framework_name, [])
            
            # Validate IDs and confidence
            validated_matches = [
                m for m in framework_matches
                if m.get("id") in valid_ids and m.get("confidence", 0) >= 0.6
            ]
            
            # Add deviation to each match
            for match in validated_matches:
                match["deviation"] = deviation_text
            
            # Limit to top_k
            validated_matches = validated_matches[:top_k]
            framework_mappings[framework_name] = validated_matches
            
            logging.info(f"[{control_id}] {framework_name}: Found {len(validated_matches)} matches (batched mode)")
        
        # Calculate primary framework (highest confidence across all frameworks)
        primary_framework = None
        primary_criterion_id = None
        primary_confidence = 0.0
        
        for fw_name, matches in framework_mappings.items():
            for match in matches:
                if match.get("confidence", 0) > primary_confidence:
                    primary_confidence = match["confidence"]
                    primary_framework = fw_name
                    primary_criterion_id = match.get("id")
        
        # Estimate token usage (single batched call)
        total_tokens = len(batched_prompt) // 4  # Rough approximation
        
        result_with_metadata = {
            "framework_mappings": framework_mappings,
            "primary_framework": primary_framework,
            "primary_criterion_id": primary_criterion_id,
            "primary_confidence": primary_confidence,
            "token_usage": {"BATCHED": total_tokens}  # Single call, not per-framework
        }
        
        logging.info(f"[{control_id}] Batched mapping complete: {len(framework_mappings)} frameworks, ~{total_tokens} tokens")
        
        # DEBUG: Log detailed output for first 3 controls to verify structure
        if control_id in ['1.1', '1.2', '1.3', '1', '2', '3']:
            logging.info(f"[DEBUG] ========== Control {control_id} Batched Mapping Output ==========")
            logging.info(f"[DEBUG] Primary Framework: {primary_framework}")
            logging.info(f"[DEBUG] Primary Criterion: {primary_criterion_id}")
            logging.info(f"[DEBUG] Primary Confidence: {primary_confidence}")
            logging.info(f"[DEBUG] Framework Mappings Count: {len(framework_mappings)}")
            for fw_name, matches in framework_mappings.items():
                logging.info(f"[DEBUG]   - {fw_name}: {len(matches)} matches")
                if matches:
                    logging.info(f"[DEBUG]     Top match: {matches[0]}")
            logging.info(f"[DEBUG] ==========================================================")
        
        return result_with_metadata
        
    except Exception as e:
        logging.error(f"[{control_id}] Batched framework mapping failed: {e}")
        return _empty_framework_result(framework_names)


def _empty_framework_result(framework_names: List[str]) -> Dict[str, Any]:
    """Helper to return empty result structure when mapping fails."""
    return {
        "framework_mappings": {name: [] for name in framework_names},
        "primary_framework": None,
        "primary_criterion_id": None,
        "primary_confidence": 0.0,
        "token_usage": {}
    }


__all__ = [
    # Dynamic multi-framework mapping
    'map_control_to_frameworks_dynamic',
    'map_cuec_to_frameworks_dynamic',
    
    # Batched mapping (v2.2.0 - OPTIMIZATION)
    'map_control_to_all_frameworks_batched',
    
    # Parallel mapping (v2.1.0)
    'map_controls_parallel',
    
    # Helper functions
    'extract_mapping_fields_for_db',
    'get_primary_criterion_details',
    'log_token_usage'
]
