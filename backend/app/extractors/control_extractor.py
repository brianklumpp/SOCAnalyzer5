# control_extractor.py

"""
UNIFIED Control Extractor for SOC1 and SOC2 Reports
====================================================

This unified extractor replaces the separate control_extractor_v4.py (SOC2) and
control_extractor_v4_soc1.py (SOC1) with a single codebase that:

1. Uses SOC2's proven CONTROL_EXTRACTION_PROMPT_V4 for ALL report types
2. Applies same chunking, merging, validation logic for consistency
3. Optionally maps financial assertions via batch GPT call (disabled by default)
4. Gracefully degrades if assertion mapping fails (continues without assertions)

Architecture:
1. AWARE CHUNKING - Intelligent text segmentation with overlap and metadata
2. CHAIN-OF-THOUGHT - Multi-step reasoning embedded in prompt
3. CONTINUATION HANDLING - Merge controls split across chunks
4. CONFIDENCE FILTERING - Discard low-confidence extractions
5. POST-MERGE VALIDATION - Schema and overlap validation
6. OPTIONAL ASSERTION MAPPING - Batch financial assertion mapping (SOC1 only, opt-in)

Key Improvements over previous extractors:
- Single codebase eliminates prompt bugs (like SOC1 using wrong prompt)
- Removes keyword-based assertion mapping that created false negatives
- Batch assertion mapping reduces GPT calls and improves accuracy
- Graceful degradation ensures extraction completes even if assertions fail
"""

import os
import json
import logging
import time
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from ..gpt_client import gpt_extract

try:
    from .. import config
except Exception as import_err:
    print(f"[CONTROL_EXTRACTOR] Import error: {import_err}")
    raise

# Checkpoint file for incremental writes
CHECKPOINT_FILE = None  # Will be set dynamically based on config.CONTROL_JSON_PATH

# Configure logging
log_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'logs', 'control_extractor.log')
logging.basicConfig(
    filename=log_path,
    filemode='w',
    level=logging.INFO,
    format='%(asctime)s [CONTROL_EXTRACTOR] %(message)s',
)

# ============================================================================
# LINE MARKER UTILITIES
# ============================================================================

def strip_line_markers(text: str) -> str:
    """
    Remove line markers like ║123║ from text.
    
    Args:
        text: Text containing line markers
        
    Returns:
        Text with markers removed
    """
    if not text:
        return text
    return re.sub(r'║\d+║\s*', '', text)

def validate_markers_stripped(text: str) -> bool:
    """
    Validate that all line markers have been removed from text.
    
    Args:
        text: Text to validate
        
    Returns:
        True if no markers found, False otherwise
    """
    if not text:
        return True
    return '║' not in text

# ============================================================================
# CHECKPOINT MANAGEMENT - Incremental Write Support
# ============================================================================

def write_checkpoint(
    validated_controls: List[Dict[str, Any]],
    rejected_controls: List[Dict[str, Any]],
    diagnostics: Dict[str, Any],
    scan_id: Optional[str] = None
) -> None:
    """
    Write current extraction state to checkpoint file for incremental progress tracking.
    
    This allows:
    - Real-time visibility into extraction progress
    - Recovery from crashes without losing work
    - Monitoring partial results during long-running extractions
    
    Args:
        validated_controls: List of validated controls extracted so far
        rejected_controls: List of rejected controls
        diagnostics: Current diagnostic information
        scan_id: Optional scan ID for tracking
    """
    if not CHECKPOINT_FILE:
        logging.warning("Checkpoint file not configured, skipping checkpoint write")
        return
    
    try:
        checkpoint_data = {
            "scan_id": scan_id,
            "timestamp": datetime.now().isoformat(),
            "status": "in_progress",
            "controls": validated_controls,
            "rejected_controls": rejected_controls,
            "diagnostics": diagnostics,
            "control_count": len(validated_controls)
        }
        
        # Write to temp file first, then rename for atomic write
        temp_checkpoint = CHECKPOINT_FILE + ".tmp"
        with open(temp_checkpoint, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)
        
        # Atomic rename
        if os.path.exists(CHECKPOINT_FILE):
            os.remove(CHECKPOINT_FILE)
        os.rename(temp_checkpoint, CHECKPOINT_FILE)
        
        logging.info(f"✓ Checkpoint saved: {len(validated_controls)} controls")
    except Exception as e:
        logging.error(f"Failed to write checkpoint: {e}", exc_info=True)
        # Non-fatal - continue extraction even if checkpoint fails

# ============================================================================
# AWARE CHUNKING - Text Segmentation with Metadata (from control_extractor_v4.py)
# ============================================================================

def create_aware_chunks(
    text_lines: List[str],
    start_line: int,
    end_line: int,
    tokens_per_chunk: int = 1000,
    overlap_tokens: int = 200
) -> List[Dict[str, Any]]:
    """
    Create intelligent chunks with metadata for continuation handling.
    
    Args:
        text_lines: Full document as list of lines
        start_line: Starting line number (1-indexed)
        end_line: Ending line number (1-indexed)
        tokens_per_chunk: Approximate tokens per chunk (~4 chars = 1 token)
        overlap_tokens: Overlap between chunks
        
    Returns:
        List of chunk dictionaries with metadata
    """
    chars_per_chunk = tokens_per_chunk * 4
    overlap_chars = overlap_tokens * 4
    
    # Extract relevant section
    section_lines = text_lines[start_line-1:end_line]
    
    # Add line markers to help GPT recognize multi-line patterns
    marked_lines = []
    for i, line in enumerate(section_lines):
        line_num = start_line + i
        marked_lines.append(f'║{line_num}║ {line}')
    
    # Use ''.join() since readlines() preserves newlines - '\n'.join() would double them
    full_text = ''.join(marked_lines)
    
    chunks = []
    chunk_id = 1
    position = 0
    total_chunks_estimate = max(1, len(full_text) // chars_per_chunk)
    
    while position < len(full_text):
        # Extract chunk with overlap from previous
        chunk_start = max(0, position - overlap_chars)
        chunk_end = min(len(full_text), position + chars_per_chunk)
        chunk_text = full_text[chunk_start:chunk_end]
        
        # Calculate line numbers
        chars_before = len(full_text[:chunk_start])
        chars_after = len(full_text[:chunk_end])
        chunk_start_line = start_line + full_text[:chunk_start].count('\n')
        chunk_end_line = start_line + full_text[:chunk_end].count('\n')
        
        # Add continuation hints
        prefix = f"[Chunk {chunk_id}/{total_chunks_estimate}. If this chunk ends mid-control, set continuation=true in JSON.]\n\n"
        suffix = "\n\n[If you detect incomplete control content at the end, add 'continuation': true to the JSON output.]"
        
        chunk_with_hints = prefix + chunk_text + suffix
        
        chunks.append({
            "chunk_id": chunk_id,
            "text": chunk_with_hints,
            "start_line": chunk_start_line,
            "end_line": chunk_end_line,
            "position_start": chunk_start,
            "position_end": chunk_end,
            "has_overlap": chunk_id > 1
        })
        
        logging.info(f"Created chunk {chunk_id}: lines {chunk_start_line}-{chunk_end_line}, {len(chunk_text)} chars")
        
        chunk_id += 1
        
        # Move position forward by effective chunk size (chunk size minus overlap)
        # This creates overlapping chunks: next chunk starts (overlap_chars) before current chunk ends
        effective_advance = chars_per_chunk - overlap_chars
        position += effective_advance
        
        # Break if we've reached the end
        if position >= len(full_text):
            break
    
    # Update total chunks count
    total_chunks = len(chunks)
    for chunk in chunks:
        # Update the prefix with actual total
        chunk["text"] = chunk["text"].replace(
            f"Chunk {chunk['chunk_id']}/{total_chunks_estimate}",
            f"Chunk {chunk['chunk_id']}/{total_chunks}"
        )
    
    logging.info(f"Created {total_chunks} aware chunks from lines {start_line}-{end_line}")
    return chunks

# ============================================================================
# CHAIN-OF-THOUGHT EXTRACTION (from control_extractor_v4.py)
# ============================================================================

def extract_control_with_cot(chunk: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Extract controls using Chain-of-Thought reasoning.
    
    The CoT is embedded in the prompt itself through the parsing strategy steps.
    GPT-4/5 will internally:
    1. Reason about control boundaries
    2. Classify each sentence by role
    3. Emit structured JSON with all controls found
    
    Args:
        chunk: Chunk dictionary with text and metadata
        
    Returns:
        List of extracted control dicts or None
    """
    chunk_id = chunk["chunk_id"]
    start_line = chunk["start_line"]
    text = chunk["text"]
    
    logging.info(f"[CHUNK {chunk_id}] Extracting controls starting at line {start_line}")
    
    try:
        # Format prompt with chunk text (ALWAYS use SOC2 prompt for all report types)
        prompt = config.CONTROL_EXTRACTION_PROMPT_V4.format(
            start_line=start_line,
            text=text
        )
        
        # Call GPT
        response = gpt_extract(prompt, "control_extractor")
        
        if not response:
            logging.warning(f"[CHUNK {chunk_id}] Empty GPT response")
            return None
        
        # Parse JSON response (returns list of controls)
        controls = parse_control_json(response, chunk_id)
        
        if not controls:
            logging.warning(f"[CHUNK {chunk_id}] Failed to parse control JSON")
            return None
        
        # Add chunk metadata and adjust line numbers
        for control in controls:
            control["chunk_id"] = chunk_id
            control["source_start_line"] = start_line
            # Adjust end_line if GPT provided relative line number
            if "end_line" in control and isinstance(control["end_line"], int):
                control["end_line"] = start_line + control["end_line"]
            # Ensure TSC/COSO mapping fields are present and lists
            for field in ["control_tsc_mappings", "control_coso_mappings"]:
                if field not in control or not isinstance(control[field], list):
                    control[field] = []
            # Ensure closest framework fields
            if "control_closest_framework" not in control:
                control["control_closest_framework"] = "Undetermined"
            if "control_closest_framework_justification" not in control:
                control["control_closest_framework_justification"] = ""
            logging.info(f"[CHUNK {chunk_id}] Extracted control: {control.get('control_id', 'N/A')}, confidence: {control.get('control_confidence', 0):.2f}, continuation: {control.get('continuation', False)}")
        
        logging.info(f"[CHUNK {chunk_id}] Extracted {len(controls)} control(s)")
        return controls
        
    except Exception as e:
        logging.error(f"[CHUNK {chunk_id}] Extraction error: {e}")
        return None

def parse_control_json(response: str, chunk_id: int) -> Optional[List[Dict[str, Any]]]:
    """
    Parse GPT JSON response into list of control dictionaries.
    
    Args:
        response: Raw GPT response (may contain single control or array)
        chunk_id: Chunk identifier for logging
        
    Returns:
        List of control dicts or None
    """
    try:
        # Try direct JSON parse
        parsed = json.loads(response.strip())
        
        # Validate response type
        if not isinstance(parsed, dict):
            logging.warning(f"[CHUNK {chunk_id}] Response is not a dict: {type(parsed)}")
            return None
        
        # Handle both old format (single control) and new format (array)
        if "controls" in parsed:
            # New format: {"controls": [...]}
            controls = parsed["controls"]
            if not isinstance(controls, list):
                controls = [controls]
        else:
            # Old format (backwards compatibility): single control object
            controls = [parsed]
        
        # Validate and normalize each control
        validated_controls = []
        for control in controls:
            if not isinstance(control, dict):
                logging.warning(f"[CHUNK {chunk_id}] Control is not a dict: {type(control)}")
                continue
            
            # Ensure lists for test arrays
            if "control_tests" in control and not isinstance(control["control_tests"], list):
                control["control_tests"] = [control["control_tests"]] if control["control_tests"] else []
            
            if "control_test_results" in control and not isinstance(control.get("control_test_results"), list):
                control["control_test_results"] = [control["control_test_results"]] if control["control_test_results"] else []
            
            validated_controls.append(control)
        
        return validated_controls if validated_controls else None
        
    except json.JSONDecodeError as e:
        logging.warning(f"[CHUNK {chunk_id}] JSON parse error: {e}")
        
        # Strategy 1: Handle "Extra data" error - GPT added text after valid JSON
        if "Extra data" in str(e):
            try:
                # Use the decoder to parse as much as possible
                decoder = json.JSONDecoder()
                parsed, end_idx = decoder.raw_decode(response.strip())
                logging.info(f"[CHUNK {chunk_id}] Recovered from 'Extra data' error")
                if "controls" in parsed:
                    return parsed["controls"] if isinstance(parsed["controls"], list) else [parsed["controls"]]
                else:
                    return [parsed]
            except Exception as ex:
                logging.warning(f"[CHUNK {chunk_id}] Recovery failed: {ex}")
        
        # Strategy 2: Try to extract JSON from markdown code blocks
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                logging.info(f"[CHUNK {chunk_id}] Extracted JSON from markdown")
                if "controls" in parsed:
                    return parsed["controls"] if isinstance(parsed["controls"], list) else [parsed["controls"]]
                else:
                    return [parsed]
            except:
                pass
        
        # Strategy 3: Find first complete JSON object (non-greedy, balanced braces)
        brace_count = 0
        start_idx = response.find('{')
        if start_idx >= 0:
            for i in range(start_idx, len(response)):
                if response[i] == '{':
                    brace_count += 1
                elif response[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        # Found complete JSON object
                        try:
                            parsed = json.loads(response[start_idx:i+1])
                            logging.info(f"[CHUNK {chunk_id}] Extracted balanced JSON")
                            if "controls" in parsed:
                                return parsed["controls"] if isinstance(parsed["controls"], list) else [parsed["controls"]]
                            else:
                                return [parsed]
                        except:
                            break
        
        logging.error(f"[CHUNK {chunk_id}] Could not extract valid JSON")
        return None

# ============================================================================
# CONTINUATION HANDLING - Merge Split Controls (from control_extractor_v4.py)
# ============================================================================

def merge_continuations(controls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge controls that were split across chunks.
    
    Merge criteria:
    1. Previous control has continuation=true
    2. Consecutive control_ids match
    3. Line ranges are adjacent or overlapping
    
    Args:
        controls: List of extracted controls in chunk order
        
    Returns:
        List of merged controls
    """
    if not controls:
        return []
    
    merged = []
    current = None
    merge_count = 0
    
    for control in controls:
        if current is None:
            # First control
            current = control.copy()
            continue
        
        # Check if should merge with current
        should_merge = False
        merge_reason = ""
        
        # Criterion 1: Previous has continuation flag
        if current.get("continuation", False):
            should_merge = True
            merge_reason = "continuation flag"
        
        # Criterion 2: Matching control IDs
        elif (current.get("control_id") and control.get("control_id") and
              current["control_id"] == control["control_id"]):
            should_merge = True
            merge_reason = "matching control_id"
        
        # Criterion 3: Adjacent line ranges
        elif ("end_line" in current and "source_start_line" in control and
              abs(current["end_line"] - control["source_start_line"]) <= 5):
            # Allow small gap (headers, whitespace)
            if current.get("control_id") == control.get("control_id"):
                should_merge = True
                merge_reason = "adjacent lines with matching ID"
        
        if should_merge:
            # Merge current with new control
            logging.info(f"Merging control {control.get('control_id', 'N/A')} ({merge_reason})")
            current = merge_two_controls(current, control)
            merge_count += 1
        else:
            # Save current and start new
            merged.append(current)
            current = control.copy()
    
    # Add final control
    if current:
        merged.append(current)
    
    logging.info(f"Merged {merge_count} continuations: {len(controls)} -> {len(merged)} controls")
    return merged

def merge_two_controls(base: Dict[str, Any], addition: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge two control dictionaries.
    
    Args:
        base: Base control to merge into
        addition: Control to merge from
        
    Returns:
        Merged control dictionary
    """
    merged = base.copy()
    
    # Concatenate text fields (handle None values)
    for field in ["control_desc", "deviation_desc"]:
        if field in addition and addition[field]:
            base_text = (merged.get(field) or "").strip()
            add_text = (addition[field] or "").strip()
            if add_text and add_text not in base_text:
                merged[field] = (base_text + " " + add_text).strip()
    
    # Preserve has_deviation flag - set to True if either control has it
    if merged.get("has_deviation") or addition.get("has_deviation"):
        merged["has_deviation"] = True
    
    # Merge list fields (deduplicate)
    for field in ["control_tests", "control_test_results", "additional_references"]:
        base_list = merged.get(field, [])
        add_list = addition.get(field, [])
        
        if not isinstance(base_list, list):
            base_list = [base_list] if base_list else []
        if not isinstance(add_list, list):
            add_list = [add_list] if add_list else []
        
        # Merge and deduplicate
        combined = base_list + [item for item in add_list if item not in base_list]
        if combined:
            merged[field] = combined
    
    # Merge page references arrays (deduplicate and sort)
    base_pages = merged.get("control_page_refs", [])
    add_pages = addition.get("control_page_refs", [])
    if not isinstance(base_pages, list):
        base_pages = [base_pages] if base_pages else []
    if not isinstance(add_pages, list):
        add_pages = [add_pages] if add_pages else []
    # Combine, deduplicate, and sort page numbers
    combined_pages = sorted(list(set(base_pages + add_pages)))
    if combined_pages:
        merged["control_page_refs"] = combined_pages
    
    # Update end_line to furthest (handle None values)
    if "end_line" in addition:
        merged_end = merged.get("end_line") or 0
        addition_end = addition["end_line"] or 0
        merged["end_line"] = max(merged_end, addition_end)
    
    # Average confidence
    if "control_confidence" in addition and "control_confidence" in merged:
        merged["control_confidence"] = (merged["control_confidence"] + addition["control_confidence"]) / 2
    
    # Prefer non-null control_id
    if not merged.get("control_id") and addition.get("control_id"):
        merged["control_id"] = addition["control_id"]
    
    # Remove continuation flag after merge
    merged["continuation"] = False
    
    # Update justification
    base_just = merged.get("control_gpt_conf_justification", "")
    add_just = addition.get("control_gpt_conf_justification", "")
    if add_just and add_just not in base_just:
        merged["control_gpt_conf_justification"] = f"{base_just}; Merged: {add_just}"
    
    return merged

# ============================================================================
# CONFIDENCE FILTERING (from control_extractor_v4.py)
# ============================================================================

def filter_by_confidence(controls: List[Dict[str, Any]], min_confidence: float = 0.5) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Filter controls by confidence threshold.
    
    Args:
        controls: List of controls
        min_confidence: Minimum confidence threshold
        
    Returns:
        Tuple of (accepted_controls, rejected_controls)
    """
    accepted = []
    rejected = []
    
    for control in controls:
        confidence = control.get("control_confidence", 0)
        
        if confidence >= min_confidence:
            accepted.append(control)
        else:
            rejected.append(control)
            logging.info(f"Filtered out low confidence control: {control.get('control_id', 'N/A')} (confidence: {confidence:.2f})")
    
    logging.info(f"Confidence filtering: {len(accepted)} accepted, {len(rejected)} rejected (threshold: {min_confidence})")
    
    return accepted, rejected

# ============================================================================
# POST-MERGE VALIDATION (simplified from control_extractor_v4.py)
# ============================================================================

def validate_controls(
    controls: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Validate and clean controls post-merge.
    
    Checks:
    1. Required fields present
    2. Schema compliance
    3. Type normalization
    
    NOTE: This is simplified version without pattern analysis or multi-factor confidence.
    Those features can be added later if needed.
    
    Args:
        controls: List of controls to validate
        
    Returns:
        List of validated controls
    """
    validated = []
    
    # Required fields
    required_fields = ["control_desc"]
    
    for i, control in enumerate(controls):
        # Strip line markers from text fields
        text_fields = ['control_id', 'control_desc', 'deviation_desc', 'control_gpt_conf_justification', 'control_closest_framework_justification']
        for field in text_fields:
            if field in control and control[field]:
                control[field] = strip_line_markers(str(control[field]))
        
        # Strip markers from list fields
        list_fields = ['control_tests', 'control_test_results', 'additional_references', 'control_tsc_mappings', 'control_coso_mappings']
        for field in list_fields:
            if field in control and isinstance(control[field], list):
                control[field] = [strip_line_markers(str(item)) if item else item for item in control[field]]
        
        # Validate markers were stripped
        for field in text_fields:
            if field in control and control[field] and not validate_markers_stripped(str(control[field])):
                logging.warning(f"Control {i+1} field '{field}' still contains line markers after stripping")
        
        # Check required fields
        missing = [field for field in required_fields if not control.get(field)]
        if missing:
            logging.warning(f"Control {i+1} missing required fields: {missing}")
            continue
        
        # Normalize lists
        for field in ["control_tests", "control_test_results", "additional_references", "control_tsc_mappings", "control_coso_mappings"]:
            if field in control:
                if not isinstance(control[field], list):
                    control[field] = [control[field]] if control[field] else []
        
        # Convert arrays to TEXT for database insertion
        if "control_tests" in control and isinstance(control["control_tests"], list):
            control["control_test"] = "\n".join(str(t) for t in control["control_tests"] if t)
        elif "control_test" not in control:
            control["control_test"] = ""
        
        if "control_test_results" in control and isinstance(control.get("control_test_results"), list):
            control["control_test_results"] = "\n".join(str(r) for r in control["control_test_results"] if r)
        elif "control_test_results" not in control:
            control["control_test_results"] = ""
        
        # Extract page and line references
        try:
            from ..pdf_handler import get_page_for_line
            if "source_start_line" in control and "text_lines" in control:
                page_num = get_page_for_line(control["text_lines"], control["source_start_line"])
                control["control_page_refs"] = [page_num] if page_num else []
                control["control_line_ref"] = control["source_start_line"]
            elif "source_start_line" in control:
                control["control_line_ref"] = control["source_start_line"]
        except Exception as e:
            logging.warning(f"Failed to extract page/line refs for control {i}: {e}")
        
        # Ensure boolean fields
        if "has_deviation" not in control:
            control["has_deviation"] = False
        if "continuation" not in control:
            control["continuation"] = False
        
        # Set default confidence if missing
        if "control_confidence" not in control:
            control["control_confidence"] = 0.5
            control["control_gpt_conf_justification"] = "Default confidence (no GPT score provided)"
        
        # Ensure closest framework fields
        if "control_closest_framework" not in control:
            control["control_closest_framework"] = "Undetermined"
        if "control_closest_framework_justification" not in control:
            control["control_closest_framework_justification"] = ""
        
        validated.append(control)
    
    logging.info(f"Validated {len(validated)} controls")
    return validated

# ============================================================================
# BATCH FINANCIAL ASSERTION MAPPING (NEW - SOC1 only, opt-in)
# ============================================================================

def estimate_token_count(text: str) -> int:
    """Estimate token count (~4 chars per token)"""
    return len(text) // 4

def batch_map_financial_assertions(
    controls: List[Dict[str, Any]],
    max_batch_tokens: int = 20000
) -> List[Dict[str, Any]]:
    """
    Map financial assertions to controls using batch GPT processing.
    
    This function sends full control JSON to GPT in dynamically-sized batches
    to minimize API calls while staying under token limits. If mapping fails,
    gracefully degrades by returning controls without assertion data.
    
    Args:
        controls: List of control dictionaries
        max_batch_tokens: Maximum tokens per batch (~20K = safe for GPT-4)
        
    Returns:
        List of controls with financial_assertions and assertion_reasoning added
    """
    if not controls:
        return controls
    
    logging.info(f"Starting batch financial assertion mapping for {len(controls)} controls")
    
    try:
        # Dynamically batch controls by token count
        batches = []
        current_batch = []
        current_tokens = 0
        
        for control in controls:
            # Estimate tokens for this control (full JSON)
            control_json = json.dumps({
                "control_id": control.get("control_id", "N/A"),
                "control_desc": control.get("control_desc", ""),
                "control_tests": control.get("control_tests", []),
                "control_test_results": control.get("control_test_results", [])
            }, ensure_ascii=False)
            control_tokens = estimate_token_count(control_json)
            
            # Check if adding this control exceeds batch limit
            if current_tokens + control_tokens > max_batch_tokens and current_batch:
                # Start new batch
                batches.append(current_batch)
                current_batch = [control]
                current_tokens = control_tokens
            else:
                # Add to current batch
                current_batch.append(control)
                current_tokens += control_tokens
        
        # Add final batch
        if current_batch:
            batches.append(current_batch)
        
        logging.info(f"Created {len(batches)} batches for assertion mapping")
        
        # Process each batch
        mapped_controls = []
        for batch_idx, batch in enumerate(batches, 1):
            logging.info(f"Processing batch {batch_idx}/{len(batches)} ({len(batch)} controls)")
            
            try:
                # Format batch prompt with full control JSON
                controls_json = json.dumps([
                    {
                        "control_id": c.get("control_id", "N/A"),
                        "control_desc": c.get("control_desc", ""),
                        "control_tests": c.get("control_tests", []),
                        "control_test_results": c.get("control_test_results", []),
                        "has_deviation": c.get("has_deviation", False),
                        "deviation_desc": c.get("deviation_desc", "")
                    }
                    for c in batch
                ], ensure_ascii=False, indent=2)
                
                prompt = config.FINANCIAL_ASSERTION_BATCH_MAPPING_PROMPT.format(
                    controls_json=controls_json,
                    num_controls=len(batch)
                )
                
                # Call GPT for batch assertion mapping
                response = gpt_extract(prompt, "financial_assertion_batch_mapper")
                
                if not response:
                    logging.warning(f"Batch {batch_idx}: Empty GPT response, skipping assertion mapping")
                    mapped_controls.extend(batch)
                    continue
                
                # Parse response
                result = json.loads(response.strip())
                assertions_by_id = result.get("assertions", [])
                
                # Map assertions back to controls
                for control in batch:
                    control_id = control.get("control_id", "N/A")
                    # Find matching assertion data
                    assertion_data = next(
                        (a for a in assertions_by_id if a.get("control_id") == control_id),
                        None
                    )
                    
                    if assertion_data:
                        control["financial_assertions"] = assertion_data.get("financial_assertions", [])
                        control["assertion_reasoning"] = assertion_data.get("assertion_reasoning", "")
                        logging.info(f"Mapped assertions for {control_id}: {control['financial_assertions']}")
                    else:
                        logging.warning(f"No assertion mapping found for {control_id}")
                        control["financial_assertions"] = []
                        control["assertion_reasoning"] = "Assertion mapping failed"
                    
                    mapped_controls.append(control)
                
            except Exception as batch_error:
                logging.error(f"Batch {batch_idx} assertion mapping failed: {batch_error}")
                # Graceful degradation: return controls without assertions
                for control in batch:
                    control["financial_assertions"] = []
                    control["assertion_reasoning"] = f"Batch mapping error: {str(batch_error)[:100]}"
                    mapped_controls.append(control)
        
        logging.info(f"Completed batch assertion mapping: {len(mapped_controls)} controls processed")
        return mapped_controls
        
    except Exception as e:
        logging.error(f"Financial assertion mapping failed: {e}")
        # Graceful degradation: return original controls without assertions
        logging.warning("Gracefully degrading: returning controls without financial assertion data")
        for control in controls:
            control["financial_assertions"] = []
            control["assertion_reasoning"] = f"Mapping failed: {str(e)[:100]}"
        return controls

# ============================================================================
# MAIN EXTRACTION PIPELINE - UNIFIED
# ============================================================================

def extract_controls(
    sections: List[Dict[str, Any]],
    report_type: str,
    enable_assertion_mapping: bool = False,
    start_at_line: Optional[int] = None,
    max_controls: Optional[int] = None,
    scan_id: Optional[str] = None,
    job_id: Optional[str] = None,
    redis_client: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Unified control extraction pipeline for SOC1 and SOC2 reports.
    
    Pipeline:
    1. Load section boundaries
    2. Create aware chunks with metadata
    3. Extract controls with Chain-of-Thought (SOC2 prompt for all types)
    4. Merge continuations
    5. Filter by confidence
    6. Validate and clean
    7. Optionally map financial assertions (SOC1 only, if enabled)
    8. Return structured results
    
    Features:
    - Incremental checkpointing every 10 controls for progress visibility
    - Atomic checkpoint writes for crash recovery
    - Framework mapping as batch post-processing
    - Quick test mode support (QUICK_TEST_MODE_ENABLED in config)
    
    Args:
        sections: List of section dictionaries from section extraction
        report_type: Report type ("SOC1", "SOC2", "COMBINED")
        enable_assertion_mapping: Enable batch financial assertion mapping (default False)
        start_at_line: Resume from line number (optional)
        max_controls: Maximum number of controls to extract (for quick testing, default None = all)
                     If None and QUICK_TEST_MODE_ENABLED is True, uses QUICK_TEST_MAX_CONTROLS from config
        scan_id: Optional scan ID for checkpoint tracking
        
    Returns:
        Dict with extraction results and diagnostics
    """
    # Initialize checkpoint file path
    global CHECKPOINT_FILE
    if config.CONTROL_JSON_PATH:
        CHECKPOINT_FILE = str(config.CONTROL_JSON_PATH).replace('.json', '_checkpoint.json')
        logging.info(f"Checkpoint file: {CHECKPOINT_FILE}")
    
    # Apply quick test mode if enabled and max_controls not explicitly set
    if max_controls is None and getattr(config, 'QUICK_TEST_MODE_ENABLED', False):
        max_controls = getattr(config, 'QUICK_TEST_MAX_CONTROLS', 10)
        logging.info(f"QUICK TEST MODE ENABLED: Limiting extraction to {max_controls} controls")
    
    start_time = time.time()
    logging.info("=" * 80)
    logging.info(f"UNIFIED CONTROL EXTRACTION - Report Type: {report_type}")
    logging.info(f"Assertion Mapping: {'ENABLED' if enable_assertion_mapping else 'DISABLED'}")
    logging.info(f"Max Controls: {max_controls if max_controls else 'UNLIMITED (full extraction)'}")
    logging.info(f"Scan ID: {scan_id or 'N/A'}")
    logging.info("=" * 80)
    
    # Find control section - MUST be Control_Descriptions for proper control extraction
    # Do NOT use Description_of_System as it contains narrative, not control tables
    control_section = next(
        (s for s in sections if s["topic"] == "Control_Descriptions"),
        None
    )
    
    if not control_section:
        logging.error("Control_Descriptions section not found in extracted sections")
        logging.error(f"Available sections: {[s.get('topic') for s in sections]}")
        return {"error": "Control_Descriptions section not found"}
    
    section_start = control_section["start_line"]
    section_end = control_section["end_line"]
    
    # Handle resume logic
    if start_at_line:
        section_start = start_at_line
        logging.info(f"Resuming from line {start_at_line}")
    
    logging.info(f"Extracting controls from lines {section_start} to {section_end}")
    
    # Load document
    with open(config.PDF_TXT_PATH, 'r', encoding='utf-8') as f:
        text_lines = f.readlines()
    
    # Validate section bounds against actual file length
    actual_line_count = len(text_lines)
    if section_end > actual_line_count:
        logging.warning(f"Section end_line ({section_end}) exceeds actual file length ({actual_line_count}). Adjusting to file length.")
        section_end = actual_line_count
    
    if section_start > actual_line_count:
        logging.error(f"Section start_line ({section_start}) exceeds actual file length ({actual_line_count}). Cannot proceed.")
        return {"error": f"Invalid section bounds: start_line={section_start} > file_length={actual_line_count}"}
    
    logging.info(f"Validated bounds: lines {section_start}-{section_end} (file has {actual_line_count} lines)")
    
    # Step 1: Create aware chunks
    chunk_start_time = time.time()
    chunks = create_aware_chunks(
        text_lines,
        section_start,
        section_end,
        tokens_per_chunk=getattr(config, 'CONTROL_V4_TOKENS_PER_CHUNK', 1000),
        overlap_tokens=getattr(config, 'CONTROL_V4_OVERLAP_TOKENS', 200)
    )
    chunk_time = time.time() - chunk_start_time
    logging.info(f"Chunking completed in {chunk_time:.2f}s")
    
    # Performance tracking
    total_tokens_without_markers = 0
    total_tokens_with_markers = 0
    total_gpt_time = 0
    
    # Step 2: Extract controls with CoT (uses SOC2 prompt for all report types)
    raw_controls = []
    last_progress_update = 0  # Track when we last updated progress
    section_total_lines = section_end - section_start
    
    for chunk in chunks:
        # Early exit if we've reached max_controls limit (for quick testing)
        if max_controls and len(raw_controls) >= max_controls:
            logging.info(f"[QUICK TEST MODE] Reached max_controls limit ({max_controls}), stopping extraction early")
            logging.info(f"[QUICK TEST MODE] Processed {chunk['chunk_id']} of {len(chunks)} chunks")
            break
            
        try:
            # Track token impact of line markers
            chunk_text = chunk['text']
            # Estimate tokens without markers (strip prefix/suffix first)
            prefix_len = chunk_text.find('\n\n') + 2 if '\n\n' in chunk_text else 0
            suffix_start = chunk_text.rfind('\n\n[If you detect') if '\n\n[If you detect' in chunk_text else len(chunk_text)
            core_text = chunk_text[prefix_len:suffix_start]
            text_without_markers = strip_line_markers(core_text)
            
            tokens_without = len(text_without_markers) // 4
            tokens_with = len(core_text) // 4
            total_tokens_without_markers += tokens_without
            total_tokens_with_markers += tokens_with
            
            marker_overhead = ((tokens_with - tokens_without) / tokens_without * 100) if tokens_without > 0 else 0
            logging.info(f"[CHUNK {chunk['chunk_id']}] Tokens: {tokens_without} → {tokens_with} (+{marker_overhead:.1f}% marker overhead)")
            
            # Track GPT response time
            gpt_start = time.time()
            controls_from_chunk = extract_control_with_cot(chunk)
            gpt_elapsed = time.time() - gpt_start
            total_gpt_time += gpt_elapsed
            logging.info(f"[CHUNK {chunk['chunk_id']}] GPT response time: {gpt_elapsed:.2f}s, found {len(controls_from_chunk) if controls_from_chunk else 0} controls")
            
            if controls_from_chunk and isinstance(controls_from_chunk, list):
                raw_controls.extend(controls_from_chunk)
                
                # Update progress every 10 controls or 5% progress
                if job_id and redis_client and len(raw_controls) % 10 == 0:
                    try:
                        # Calculate progress based on chunks processed
                        current_line = chunk.get('end_line', section_start)
                        lines_processed = current_line - section_start
                        controls_percent = int((lines_processed / max(1, section_total_lines)) * 100)
                        
                        # Only update if progress increased by 5% or more
                        if controls_percent >= last_progress_update + 5:
                            # Import needed for updates
                            import json
                            
                            # Estimate total controls from section size
                            avg_controls_per_line = len(raw_controls) / max(1, lines_processed)
                            controls_total_estimate = int(avg_controls_per_line * section_total_lines)
                            
                            # Update job state
                            job_json = redis_client.get(f"job:{job_id}")
                            if job_json:
                                job = json.loads(job_json)
                                if "counters" not in job:
                                    job["counters"] = {}
                                job["counters"]["controls_count"] = len(raw_controls)
                                job["counters"]["controls_total_estimate"] = controls_total_estimate
                                job["counters"]["controls_percent"] = controls_percent
                                redis_client.set(f"job:{job_id}", json.dumps(job), ex=86400)
                                logging.info(f"[PROGRESS] Updated controls: {len(raw_controls)}/{controls_total_estimate} ({controls_percent}%)")
                                last_progress_update = controls_percent
                    except Exception as prog_err:
                        logging.warning(f"Could not update control progress: {prog_err}")
                
            elif controls_from_chunk:
                logging.warning(f"[CHUNK {chunk['chunk_id']}] extract_control_with_cot returned non-list: {type(controls_from_chunk)}")
        except Exception as e:
            logging.error(f"[CHUNK {chunk['chunk_id']}] Exception during extraction: {e}", exc_info=True)
            continue
    
    # Log aggregate performance metrics
    avg_marker_overhead = ((total_tokens_with_markers - total_tokens_without_markers) / total_tokens_without_markers * 100) if total_tokens_without_markers > 0 else 0
    avg_gpt_time = total_gpt_time / len(chunks) if chunks else 0
    logging.info(f"=" * 80)
    logging.info(f"PERFORMANCE METRICS:")
    logging.info(f"  Total chunks: {len(chunks)}")
    logging.info(f"  Chunking time: {chunk_time:.2f}s")
    logging.info(f"  Total GPT time: {total_gpt_time:.2f}s (avg {avg_gpt_time:.2f}s/chunk)")
    logging.info(f"  Token overhead from markers: +{avg_marker_overhead:.1f}%")
    logging.info(f"  Tokens without markers: {total_tokens_without_markers}")
    logging.info(f"  Tokens with markers: {total_tokens_with_markers}")
    logging.info(f"=" * 80)
    
    logging.info(f"Extracted {len(raw_controls)} raw controls from {len(chunks)} chunks")
    
    # Step 3: Merge continuations
    merged_controls = merge_continuations(raw_controls)
    
    # Step 4: Filter by confidence
    min_confidence = getattr(config, 'CONTROL_V4_MIN_CONFIDENCE', 0.5)
    accepted_controls, rejected_controls = filter_by_confidence(merged_controls, min_confidence)
    
    # Add text_lines context to controls for page number extraction
    for control in accepted_controls:
        control["text_lines"] = text_lines
    
    # Step 5: Validate
    validated_controls = validate_controls(accepted_controls)
    
    # Remove text_lines to avoid bloating the JSON output
    for control in validated_controls:
        control.pop("text_lines", None)
    
    # Write checkpoint after initial validation (before framework mapping)
    checkpoint_interval = 10  # Write checkpoint every 10 controls
    if len(validated_controls) >= checkpoint_interval:
        partial_diagnostics = {
            "status": "pre_framework_mapping",
            "controls_validated": len(validated_controls),
            "total_raw_controls": len(raw_controls),
            "elapsed_seconds": round(time.time() - start_time, 2)
        }
        write_checkpoint(validated_controls, rejected_controls, partial_diagnostics, scan_id)
        logging.info(f"Checkpoint written: {len(validated_controls)} controls (before framework mapping)")
    
    # Step 5b: Framework mapping - Map controls to appropriate frameworks based on report type
    try:
        from ..frameworks import get_available_frameworks, map_control_to_frameworks_dynamic, extract_mapping_fields_for_db
        
        logging.info(f"Framework mapping: Loading frameworks for report_type={report_type}")
        available_frameworks = get_available_frameworks(report_type=report_type)
        logging.info(f"Framework mapping: Found {len(available_frameworks)} frameworks: {list(available_frameworks.keys())}")
        
        controls_mapped = 0  # Track mapping progress
        
        for idx, control in enumerate(validated_controls, 1):
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
            
            # Add legacy fields for backward compatibility
            control["control_tsc_mappings"] = db_fields.get("control_tsc_mappings", [])
            control["control_coso_mappings"] = db_fields.get("control_coso_mappings", [])
            
            # Determine closest framework (legacy field)
            control["control_closest_framework"] = db_fields["primary_framework"] or "Undetermined"
            
            logging.info(f"[{control_id}] Mapped to {len(db_fields['framework_mappings'])} frameworks, primary: {db_fields['primary_framework']}")
            
            controls_mapped += 1
            
            # Update job state every 10 controls with mapping progress
            if job_id and redis_client and controls_mapped % 10 == 0:
                try:
                    import json
                    controls_mapped_percent = int((controls_mapped / len(validated_controls)) * 100)
                    job_json = redis_client.get(f"job:{job_id}")
                    if job_json:
                        job = json.loads(job_json)
                        if "counters" not in job:
                            job["counters"] = {}
                        job["counters"]["controls_mapped_count"] = controls_mapped
                        job["counters"]["controls_mapped_percent"] = controls_mapped_percent
                        redis_client.set(f"job:{job_id}", json.dumps(job), ex=86400)
                        logging.info(f"[PROGRESS] Framework mapping: {controls_mapped}/{len(validated_controls)} ({controls_mapped_percent}%)")
                except Exception as map_prog_err:
                    logging.warning(f"Could not update mapping progress: {map_prog_err}")
            
            # Write checkpoint every 10 controls during framework mapping
            if idx % checkpoint_interval == 0:
                partial_diagnostics = {
                    "status": "framework_mapping",
                    "controls_mapped": idx,
                    "total_controls": len(validated_controls),
                    "elapsed_seconds": round(time.time() - start_time, 2)
                }
                write_checkpoint(validated_controls, rejected_controls, partial_diagnostics, scan_id)
                logging.info(f"Checkpoint written: {idx}/{len(validated_controls)} controls mapped")
        
        frameworks_mapped = sum(1 for c in validated_controls if c.get("framework_mappings"))
        logging.info(f"Framework mapping complete: {frameworks_mapped}/{len(validated_controls)} controls mapped")
        
    except Exception as e:
        logging.error(f"Framework mapping failed: {e}", exc_info=True)
        logging.warning("Continuing without framework mapping - controls will have empty framework_mappings")
        
        # Set extraction_partial flag due to framework mapping failure
        if job_id and redis_client:
            try:
                import json
                job_json = redis_client.get(f"job:{job_id}")
                if job_json:
                    job = json.loads(job_json)
                    job["extraction_partial"] = True
                    job["status"] = f"Partial: Framework mapping failed - {str(e)[:100]}"
                    redis_client.set(f"job:{job_id}", json.dumps(job), ex=86400)
                    logging.warning("[PROGRESS] Warning: Framework mapping partially completed")
            except Exception as flag_err:
                logging.warning(f"Could not set extraction_partial flag: {flag_err}")
        
        # Add empty framework fields so controls don't fail validation
        for control in validated_controls:
            if "framework_mappings" not in control:
                control["framework_mappings"] = {}
                control["primary_framework"] = None
                control["primary_criterion_id"] = None
                control["primary_confidence"] = 0.0
                control["control_tsc_mappings"] = []
                control["control_coso_mappings"] = []
                control["control_closest_framework"] = "Undetermined"
    
    # Step 6: Optionally map financial assertions (SOC1 only, if enabled)
    if enable_assertion_mapping and report_type == "SOC1":
        logging.info("Financial assertion mapping enabled for SOC1 report")
        max_batch_tokens = getattr(config, 'MAX_ASSERTION_BATCH_TOKENS', 20000)
        validated_controls = batch_map_financial_assertions(validated_controls, max_batch_tokens)
    elif enable_assertion_mapping:
        logging.info(f"Financial assertion mapping requested but report type is {report_type} (not SOC1), skipping")
    
    # Step 7: Add sequence numbers
    for i, control in enumerate(validated_controls, 1):
        control["control_seq"] = i
    
    # Calculate diagnostics
    elapsed = time.time() - start_time
    continuations_detected = sum(1 for c in raw_controls if c.get("continuation", False))
    avg_confidence = sum(c.get("control_confidence", 0) for c in validated_controls) / len(validated_controls) if validated_controls else 0
    deviations = sum(1 for c in validated_controls if c.get("has_deviation", False))
    assertions_mapped = sum(1 for c in validated_controls if c.get("financial_assertions"))
    
    diagnostics = {
        "extractor_version": "unified",
        "report_type": report_type,
        "assertion_mapping_enabled": enable_assertion_mapping,
        "total_chunks": len(chunks),
        "raw_controls_extracted": len(raw_controls),
        "controls_merged": len(raw_controls) - len(merged_controls),
        "continuations_detected": continuations_detected,
        "controls_after_merge": len(merged_controls),
        "controls_rejected_confidence": len(rejected_controls),
        "final_control_count": len(validated_controls),
        "avg_confidence": round(avg_confidence, 3),
        "deviations_found": deviations,
        "controls_with_assertions": assertions_mapped,
        "processing_time_seconds": round(elapsed, 2)
    }
    
    logging.info("=" * 80)
    logging.info("EXTRACTION DIAGNOSTICS")
    logging.info("=" * 80)
    for key, value in diagnostics.items():
        logging.info(f"{key}: {value}")
    
    # Save results
    output = {
        "controls": validated_controls,
        "diagnostics": diagnostics,
        "rejected_controls": rejected_controls if getattr(config, 'CONTROL_V4_SAVE_REJECTED', False) else []
    }
    
    try:
        with open(config.CONTROL_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logging.info(f"Saved {len(validated_controls)} controls to {config.CONTROL_JSON_PATH}")
        
        # Clean up checkpoint file on successful completion
        if CHECKPOINT_FILE and os.path.exists(CHECKPOINT_FILE):
            try:
                os.remove(CHECKPOINT_FILE)
                logging.info("✓ Checkpoint file removed after successful completion")
            except Exception as e:
                logging.warning(f"Failed to remove checkpoint file: {e}")
    except Exception as e:
        logging.error(f"Failed to save results: {e}", exc_info=True)
        # Keep checkpoint file if final write fails - allows recovery
        logging.info("Checkpoint file preserved due to save failure")
        raise
    
    return output
