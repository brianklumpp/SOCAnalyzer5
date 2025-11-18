# control_extractor_v4.py

"""
AWARE-CHUNK + CHAIN-OF-THOUGHT (CoT) Control Extractor
========================================================

Architecture:
1. AWARE CHUNKING - Intelligent text segmentation with overlap and metadata
2. CHAIN-OF-THOUGHT - Multi-step reasoning embedded in prompt
3. CONTINUATION HANDLING - Merge controls split across chunks
4. CONFIDENCE FILTERING - Discard low-confidence extractions
5. POST-MERGE VALIDATION - Schema and overlap validation

This replaces the "fire-and-forget" overlapping chunk logic with a hybrid
approach that maintains context awareness and applies reasoning steps.
"""

import os
import json
import logging
import time
import re
from typing import Dict, Any, List, Optional, Tuple
from ..gpt_client import gpt_extract

try:
    from .. import config
except Exception as import_err:
    print(f"[CONTROL_EXTRACTOR_V4] Import error: {import_err}")
    raise

# Configure logging
log_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'logs', 'control_extractor_v4.log')
logging.basicConfig(
    filename=log_path,
    filemode='w',
    level=logging.INFO,
    format='%(asctime)s [CONTROL_EXTRACTOR_V4] %(message)s',
)

# ============================================================================
# NEW PROMPT (v4) - Imported from config.py
# ============================================================================
# The CONTROL_EXTRACTION_PROMPT_V4 is now defined in config.py

# ============================================================================
# AWARE CHUNKING - Text Segmentation with Metadata
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
    full_text = '\n'.join(section_lines)
    
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
# CHAIN-OF-THOUGHT EXTRACTION
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
        # Format prompt with chunk text (using prompt from config)
        prompt = config.CONTROL_EXTRACTION_PROMPT_V4.format(
            start_line=start_line,
            text=text
        )
        
        # Call GPT
        response = gpt_extract(prompt, "control_extractor_v4")
        
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
            logging.info(f"[CHUNK {chunk_id}] Extracted control: {control.get('control_id', 'N/A')}, confidence: {control.get('control_confidence', 0):.2f}, continuation: {control.get('continuation', False)}, TSC mappings: {len(control['control_tsc_mappings'])}, COSO mappings: {len(control['control_coso_mappings'])}, Closest framework: {control['control_closest_framework']}")
        
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
            
            if "control_test_results" in control and not isinstance(control["control_test_results"], list):
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
# CONTINUATION HANDLING - Merge Split Controls
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
# CONFIDENCE FILTERING
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
# 5-FACTOR CONFIDENCE CALCULATION
# ============================================================================

def _calculate_multi_factor_confidence(
    control: Dict[str, Any],
    weights: Dict[str, float],
    gpt_confidence: float,
    pattern_confidence: float
) -> Dict[str, Any]:
    """
    Calculate confidence using 5-factor scoring system.
    
    Factors:
    1. GPT Confidence (default 25%): Base extraction quality
    2. Pattern Confidence (default 20%): ID pattern recognition
    3. Structure Score (default 20%): Completeness of fields
    4. Framework Score (default 20%): Quality of TSC/COSO mappings
    5. Deviation Score (default 15%): Deviation flag consistency
    
    Args:
        control: Control dictionary
        weights: Weight configuration dict
        gpt_confidence: GPT extraction confidence
        pattern_confidence: Pattern library score
        
    Returns:
        Dictionary with all scores and final confidence
    """
    from datetime import datetime
    
    # Factor 3: Structure Score (0.0-1.0)
    # Checks presence of key fields: control_test, control_test_results, control_desc
    structure_fields_present = 0
    structure_fields_total = 3
    
    if control.get("control_test") or control.get("control_tests"):
        structure_fields_present += 1
    if control.get("control_test_results"):
        structure_fields_present += 1
    if control.get("control_desc"):
        structure_fields_present += 1
    
    structure_score = structure_fields_present / structure_fields_total if structure_fields_total > 0 else 0.0
    
    # Factor 4: Framework Score (0.0-1.0)
    # Average confidence from TSC and COSO mappings
    framework_confidences = []
    
    # Check TSC mappings
    if control.get("control_tsc_mappings"):
        for mapping in control["control_tsc_mappings"]:
            if isinstance(mapping, dict) and "confidence" in mapping:
                framework_confidences.append(mapping["confidence"])
    
    # Check COSO mappings
    if control.get("control_coso_mappings"):
        for mapping in control["control_coso_mappings"]:
            if isinstance(mapping, dict) and "confidence" in mapping:
                framework_confidences.append(mapping["confidence"])
    
    framework_score = sum(framework_confidences) / len(framework_confidences) if framework_confidences else 0.5
    
    # Factor 5: Deviation Score (0.0-1.0)
    # Checks consistency between has_deviation flag and deviation_desc content
    has_deviation = control.get("has_deviation", False)
    deviation_desc = control.get("deviation_desc", "")
    
    # Consistent if: (has_deviation=True AND deviation_desc exists) OR (has_deviation=False AND no deviation_desc)
    if has_deviation and deviation_desc:
        deviation_score = 1.0  # Consistent: flag set and description provided
    elif not has_deviation and not deviation_desc:
        deviation_score = 1.0  # Consistent: no flag and no description
    else:
        deviation_score = 0.3  # Inconsistent: flag doesn't match description
    
    # Calculate weighted final confidence
    final_confidence = (
        weights["gpt_weight"] * gpt_confidence +
        weights["pattern_weight"] * pattern_confidence +
        weights["structure_weight"] * structure_score +
        weights["framework_weight"] * framework_score +
        weights["deviation_weight"] * deviation_score
    )
    
    # Prepare detailed metadata
    factor_scores = {
        "gpt_confidence": round(gpt_confidence, 3),
        "pattern_confidence": round(pattern_confidence, 3),
        "structure_score": round(structure_score, 3),
        "framework_score": round(framework_score, 3),
        "deviation_score": round(deviation_score, 3)
    }
    
    weighted_contributions = {
        "gpt_contribution": round(weights["gpt_weight"] * gpt_confidence, 3),
        "pattern_contribution": round(weights["pattern_weight"] * pattern_confidence, 3),
        "structure_contribution": round(weights["structure_weight"] * structure_score, 3),
        "framework_contribution": round(weights["framework_weight"] * framework_score, 3),
        "deviation_contribution": round(weights["deviation_weight"] * deviation_score, 3)
    }
    
    return {
        "factor_scores": factor_scores,
        "weighted_contributions": weighted_contributions,
        "weights_used": weights.copy(),
        "final_confidence": round(final_confidence, 3),
        "calculated_at": datetime.utcnow().isoformat(),
        "method": "5-factor"
    }

# ============================================================================
# POST-MERGE VALIDATION
# ============================================================================

def validate_controls(
    controls: List[Dict[str, Any]], 
    organization: str = None,
    pattern_library = None,
    db_session = None
) -> List[Dict[str, Any]]:
    """
    Validate and clean controls post-merge.
    
    Checks:
    1. Required fields present
    2. Line ranges don't overlap
    3. Schema compliance
    4. Pattern-based confidence scoring (if pattern_library provided)
    
    Args:
        controls: List of controls to validate
        organization: Organization name for pattern scoring
        pattern_library: ControlPatternLibrary instance (optional)
        
    Returns:
        List of validated controls
    """
    validated = []
    
    # Required fields
    required_fields = ["control_desc"]
    
    for i, control in enumerate(controls):
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
        
        # TYPE VALIDATION FIX: Ensure framework mappings are always lists (fix type misalignment)
        for mapping_field in ["control_tsc_mappings", "control_coso_mappings"]:
            if mapping_field in control:
                value = control[mapping_field]
                if isinstance(value, str):
                    # Try to parse JSON string
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, list):
                            control[mapping_field] = parsed
                            logging.info(f"Control {i+1}: Parsed {mapping_field} from JSON string to list")
                        else:
                            logging.warning(f"Control {i+1}: {mapping_field} parsed but not a list, setting to empty list")
                            control[mapping_field] = []
                    except (json.JSONDecodeError, TypeError) as e:
                        logging.warning(f"Control {i+1}: Failed to parse {mapping_field} JSON string: {e}, setting to empty list")
                        control[mapping_field] = []
                elif not isinstance(value, list):
                    logging.warning(f"Control {i+1}: {mapping_field} is not a list or string, setting to empty list")
                    control[mapping_field] = []
        
        # DATA FLOW FIX: Convert arrays to TEXT for database insertion
        # Database expects TEXT fields, but extraction produces arrays
        if "control_tests" in control and isinstance(control["control_tests"], list):
            control["control_test"] = "\n".join(str(t) for t in control["control_tests"] if t)
        elif "control_test" not in control:
            control["control_test"] = ""
        
        if "control_test_results" in control and isinstance(control.get("control_test_results"), list):
            control["control_test_results"] = "\n".join(str(r) for r in control["control_test_results"] if r)
        elif "control_test_results" not in control:
            control["control_test_results"] = ""
        
        # DATA FLOW FIX: Extract page and line references
        # Import page number extraction function
        try:
            from ..pdf_handler import get_page_for_line
            # Extract page number from === PAGE X === markers if source_start_line is available
            if "source_start_line" in control and "text_lines" in control:
                page_num = get_page_for_line(control["text_lines"], control["source_start_line"])
                control["control_page_ref"] = page_num
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
        
        # Load confidence weights from database
        weights = {"gpt_weight": 0.25, "pattern_weight": 0.20, "structure_weight": 0.20, "framework_weight": 0.20, "deviation_weight": 0.15}
        if db_session and organization:
            try:
                from ..models import ConfidenceWeights
                from sqlalchemy import select
                # Try to get organization-specific weights
                result = db_session.execute(
                    select(ConfidenceWeights).where(ConfidenceWeights.organization == organization)
                )
                weight_config = result.scalar_one_or_none()
                
                # Fall back to global default if no org-specific weights
                if not weight_config:
                    result = db_session.execute(
                        select(ConfidenceWeights).where(ConfidenceWeights.organization == None)
                    )
                    weight_config = result.scalar_one_or_none()
                
                if weight_config:
                    weights = {
                        "gpt_weight": weight_config.gpt_weight,
                        "pattern_weight": weight_config.pattern_weight,
                        "structure_weight": weight_config.structure_weight,
                        "framework_weight": weight_config.framework_weight,
                        "deviation_weight": weight_config.deviation_weight
                    }
            except Exception as e:
                logging.warning(f"Failed to load confidence weights: {e}. Using defaults.")
        
        # Calculate 5-factor confidence score
        gpt_conf = control.get("control_confidence", 0.5)
        pattern_score = 0.5  # Default
        
        if pattern_library and organization:
            try:
                pattern_score = pattern_library.score_control_id(
                    control.get("control_id"),
                    organization
                )
            except Exception as e:
                logging.warning(f"Pattern scoring failed for control {i}: {e}")
        
        # Calculate multi-factor confidence
        confidence_result = _calculate_multi_factor_confidence(
            control, weights, gpt_conf, pattern_score
        )
        
        # Store results
        control["pattern_confidence"] = pattern_score
        control["final_confidence"] = confidence_result["final_confidence"]
        control["verification_metadata"] = confidence_result
        
        # Enhanced justification with all factor scores
        original_just = control.get("control_gpt_conf_justification", "")
        factor_summary = " | ".join([
            f"GPT: {confidence_result['factor_scores']['gpt_confidence']:.2f}",
            f"Pattern: {confidence_result['factor_scores']['pattern_confidence']:.2f}",
            f"Structure: {confidence_result['factor_scores']['structure_score']:.2f}",
            f"Framework: {confidence_result['factor_scores']['framework_score']:.2f}",
            f"Deviation: {confidence_result['factor_scores']['deviation_score']:.2f}",
            f"Final: {confidence_result['final_confidence']:.2f}"
        ])
        control["control_gpt_conf_justification"] = f"{original_just} | {factor_summary}"
        
        # Ensure closest framework fields
        if "control_closest_framework" not in control:
            control["control_closest_framework"] = "Undetermined"
        if "control_closest_framework_justification" not in control:
            control["control_closest_framework_justification"] = ""
        
        # Apply multi-match framework mapping if enabled
        if getattr(config, 'ENABLE_MULTI_MATCH_MAPPING', False):
            try:
                # Rate limiting: sleep every 5 controls to prevent CPU spike during extraction
                if i > 0 and i % 5 == 0:
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            import time as time_module
                            time_module.sleep(0.05)
                    except:
                        import time as time_module
                        time_module.sleep(0.05)
                
                tsc_matches, coso_matches = map_control_to_frameworks_multi(
                    control_desc=control.get("control_desc", ""),
                    control_id=control.get("control_id", f"Control_{i}"),
                    has_deviation=control.get("has_deviation", False),
                    deviation_desc=control.get("deviation_desc", ""),
                    tsc_criteria=config.TSC_CRITERIA,
                    coso_criteria=config.COSO_2013_CRITERIA,
                    top_k=3
                )
                
                # Store arrays
                control["control_tsc_mappings"] = tsc_matches
                control["control_coso_mappings"] = coso_matches
                
                # Populate legacy columns with highest confidence match (backward compatibility)
                if tsc_matches:
                    top_tsc = tsc_matches[0]
                    control["control_tsc_id"] = top_tsc.get("id")
                    control["control_tsc_similarity"] = top_tsc.get("confidence")
                    control["control_tsc_confidence_pct"] = int(round(top_tsc.get("confidence", 0) * 100))
                
                if coso_matches:
                    top_coso = coso_matches[0]
                    control["control_coso_id"] = top_coso.get("id")
                    control["control_coso_similarity"] = top_coso.get("confidence")
                    control["control_coso_confidence_pct"] = int(round(top_coso.get("confidence", 0) * 100))
                
                # Determine closest framework
                if tsc_matches and coso_matches:
                    if tsc_matches[0].get("confidence", 0) > coso_matches[0].get("confidence", 0):
                        control["control_closest_framework"] = "TSC"
                    elif coso_matches[0].get("confidence", 0) > tsc_matches[0].get("confidence", 0):
                        control["control_closest_framework"] = "COSO"
                    else:
                        control["control_closest_framework"] = "Equal"
                elif tsc_matches:
                    control["control_closest_framework"] = "TSC"
                elif coso_matches:
                    control["control_closest_framework"] = "COSO"
                
            except Exception as e:
                logging.error(f"Failed to apply multi-match mapping for control {i}: {e}")
                # Ensure empty arrays on failure
                control["control_tsc_mappings"] = []
                control["control_coso_mappings"] = []
        
        validated.append(control)
    
    # Check for overlapping line ranges
    validated.sort(key=lambda c: c.get("source_start_line", 0))
    
    for i in range(len(validated) - 1):
        curr_end = validated[i].get("end_line", 0)
        next_start = validated[i+1].get("source_start_line", 0)
        
        if curr_end > next_start:
            logging.warning(f"Overlapping line ranges: Control {i+1} ends at {curr_end}, Control {i+2} starts at {next_start}")
    
    logging.info(f"Validated {len(validated)} controls")
    return validated

# ============================================================================
# MULTI-MATCH FRAMEWORK MAPPING - Adaptive Token Management
# ============================================================================

def log_token_usage(entity_type: str, entity_id: str, pass_results: Dict[str, int]) -> None:
    """
    Log token usage for framework mapping operations.
    
    Args:
        entity_type: "CONTROL" or "CUEC"
        entity_id: Control or CUEC identifier
        pass_results: Dict with keys like "pass1", "pass2", "pass3" mapping to token counts
    """
    token_log_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'logs', 'framework_mapping_tokens.log')
    
    try:
        os.makedirs(os.path.dirname(token_log_path), exist_ok=True)
        
        total_tokens = sum(pass_results.values())
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
        pass_details = " | ".join([f"Pass {k.replace('pass', '')}: {v} tokens" for k, v in sorted(pass_results.items())])
        log_line = f"{timestamp} | {entity_type} | {entity_id} | {pass_details} | Total: {total_tokens} tokens\n"
        
        with open(token_log_path, 'a', encoding='utf-8') as f:
            f.write(log_line)
    except Exception as e:
        logging.warning(f"Failed to log token usage: {e}")


def map_control_to_frameworks_multi(
    control_desc: str,
    control_id: str,
    has_deviation: bool,
    deviation_desc: str,
    tsc_criteria: List[Dict[str, Any]],
    coso_criteria: List[Dict[str, Any]],
    top_k: int = 5
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Map a control to multiple TSC and COSO framework criteria using three-pass GPT strategy.
    
    Three-pass approach:
    1. TSC matching - select top 3-5 TSC criteria from full list with semantic keyword matching
    2. COSO matching - select top 3-5 COSO principles from full list with semantic keyword matching
    3. Cross-validation - validate TSC/COSO alignment consistency and adjust confidence scores
    
    Args:
        control_desc: Control description text
        control_id: Control identifier for logging
        has_deviation: Whether control has a deviation/exception
        deviation_desc: Deviation description text (truncated to 80 chars)
        tsc_criteria: Full list of TSC criteria dicts with keys: id, description, domain
        coso_criteria: Full list of COSO criteria dicts with keys: id, component, principle, description
        top_k: Maximum matches to return per framework (default 5, increased from 3)
        
    Returns:
        Tuple of (tsc_matches, coso_matches) where each is a list of dicts:
        [{"id": "CC7.2", "confidence": 0.95, "reasoning": "...", "deviation": "..." or None}]
    """
    from .. import config
    
    token_usage = {}
    
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
    
    # ========== PASS 1: TSC Matching (Full Criteria List with Semantic Matching) ==========
    try:
        # Format ALL TSC criteria for prompt with full descriptions (no truncation)
        tsc_list_text = "\n".join([
            f"- {c['id']}: {c.get('description', '')}"
            for c in tsc_criteria
        ])
        
        tsc_prompt = config.FRAMEWORK_MULTI_MATCH_PROMPT_TSC.format(
            control_desc=control_desc,
            tsc_criteria_list=tsc_list_text,
            deviation_context=deviation_context
        )
        
        response_pass1 = gpt_extract(tsc_prompt, "framework_tsc_matching")
        token_usage["pass1"] = len(tsc_prompt) // 4
        
        if not response_pass1:
            logging.warning(f"[{control_id}] Pass 1 (TSC matching) returned empty response")
            tsc_matches = []
        else:
            tsc_result = json.loads(response_pass1.strip())
            tsc_matches = tsc_result.get("matches", [])
            
            # Validate IDs and filter by confidence (raised threshold to 0.6)
            valid_tsc_ids = {c["id"] for c in tsc_criteria}
            tsc_matches = [
                m for m in tsc_matches 
                if m.get("id") in valid_tsc_ids and m.get("confidence", 0) >= 0.6
            ]
            
            # Limit to top_k (now 5)
            tsc_matches = tsc_matches[:top_k]
            
            # Add deviation to each match
            for match in tsc_matches:
                match["deviation"] = deviation_text
            
            logging.info(f"[{control_id}] Pass 1: Found {len(tsc_matches)} TSC matches from {len(tsc_criteria)} criteria")
        
    except Exception as e:
        logging.error(f"[{control_id}] Pass 1 (TSC matching) failed: {e}")
        tsc_matches = []
    
    # ========== PASS 2: COSO Matching (Full List with Semantic Matching) ==========
    try:
        # Format ALL COSO criteria for prompt with full descriptions (no truncation)
        coso_list_text = "\n".join([
            f"- {c['id']}: {c.get('principle', '')} - {c.get('description', '')}"
            for c in coso_criteria
        ])
        
        coso_prompt = config.FRAMEWORK_MULTI_MATCH_PROMPT_COSO.format(
            control_desc=control_desc,
            coso_criteria_list=coso_list_text,
            deviation_context=deviation_context
        )
        
        response_pass2 = gpt_extract(coso_prompt, "framework_coso_matching")
        token_usage["pass2"] = len(coso_prompt) // 4
        
        if not response_pass2:
            logging.warning(f"[{control_id}] Pass 2 (COSO matching) returned empty response")
            coso_matches = []
        else:
            coso_result = json.loads(response_pass2.strip())
            coso_matches = coso_result.get("matches", [])
            
            # Validate IDs and filter by confidence (raised threshold to 0.6)
            valid_coso_ids = {c["id"] for c in coso_criteria}
            coso_matches = [
                m for m in coso_matches 
                if m.get("id") in valid_coso_ids and m.get("confidence", 0) >= 0.6
            ]
            
            # Limit to top_k (now 5)
            coso_matches = coso_matches[:top_k]
            
            # Add deviation to each match
            for match in coso_matches:
                match["deviation"] = deviation_text
            
            logging.info(f"[{control_id}] Pass 2: Found {len(coso_matches)} COSO matches from {len(coso_criteria)} principles")
        
    except Exception as e:
        logging.error(f"[{control_id}] Pass 2 (COSO matching) failed: {e}")
        coso_matches = []
    
    # ========== PASS 3: Cross-Framework Validation ==========
    alignment_quality = "Undetermined"
    consistency_score = 0.5
    
    if tsc_matches and coso_matches:
        try:
            # Format matches for validation prompt
            tsc_summary = "\n".join([
                f"- {m['id']} (confidence: {m['confidence']:.2f}): {m.get('reasoning', 'N/A')}"
                for m in tsc_matches
            ])
            coso_summary = "\n".join([
                f"- {m['id']} (confidence: {m['confidence']:.2f}): {m.get('reasoning', 'N/A')}"
                for m in coso_matches
            ])
            
            validation_prompt = config.FRAMEWORK_CROSS_VALIDATION_PROMPT.format(
                control_desc=control_desc,
                tsc_matches=tsc_summary,
                coso_matches=coso_summary
            )
            
            response_pass3 = gpt_extract(validation_prompt, "framework_cross_validation")
            token_usage["pass3"] = len(validation_prompt) // 4
            
            if response_pass3:
                validation_result = json.loads(response_pass3.strip())
                alignment_quality = validation_result.get("alignment_quality", "Undetermined")
                consistency_score = validation_result.get("consistency_score", 0.5)
                adjustments = validation_result.get("confidence_adjustments", {})
                
                # Apply confidence multipliers
                tsc_multiplier = adjustments.get("tsc_confidence_multiplier", 1.0)
                coso_multiplier = adjustments.get("coso_confidence_multiplier", 1.0)
                
                for match in tsc_matches:
                    original_conf = match["confidence"]
                    match["confidence"] = min(1.0, original_conf * tsc_multiplier)
                    match["alignment_quality"] = alignment_quality
                    match["consistency_score"] = consistency_score
                
                for match in coso_matches:
                    original_conf = match["confidence"]
                    match["confidence"] = min(1.0, original_conf * coso_multiplier)
                    match["alignment_quality"] = alignment_quality
                    match["consistency_score"] = consistency_score
                
                logging.info(f"[{control_id}] Pass 3: Alignment quality={alignment_quality}, consistency={consistency_score:.2f}")
            
        except Exception as e:
            logging.error(f"[{control_id}] Pass 3 (cross-validation) failed: {e}")
    
    # Log token usage
    log_token_usage("CONTROL", control_id, token_usage)
    
    return tsc_matches, coso_matches

# ============================================================================
# MAIN EXTRACTION PIPELINE
# ============================================================================

def extract_controls_v4(
    start_at_control: Optional[int] = None,
    start_at_line: Optional[int] = None,
    organization: str = None,
    pattern_library = None,
    db_session = None
) -> Dict[str, Any]:
    """
    Main extraction pipeline using AWARE-CHUNK + CoT architecture.
    
    Pipeline:
    1. Load section boundaries
    2. Create aware chunks with metadata
    3. Extract controls with Chain-of-Thought
    4. Merge continuations
    5. Filter by confidence
    6. Validate and clean (with 5-factor confidence scoring)
    7. Return structured results
    
    Args:
        start_at_control: Resume from control sequence number
        start_at_line: Resume from line number
        organization: Organization name for pattern scoring and weights
        pattern_library: ControlPatternLibrary instance for scoring
        db_session: Database session for loading confidence weights
        
    Returns:
        Dict with extraction results and diagnostics
    """
    start_time = time.time()
    logging.info("=" * 80)
    logging.info("CONTROL EXTRACTION V4 - AWARE-CHUNK + CoT")
    logging.info("=" * 80)
    
    # Load section boundaries
    with open(config.SECTION_JSON_PATH, 'r', encoding='utf-8') as f:
        sections = json.load(f)
    
    control_section = next((s for s in sections if s["topic"] == "Control_Descriptions"), None)
    
    if not control_section:
        logging.error("Control_Descriptions section not found")
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
    
    # Step 1: Create aware chunks
    chunks = create_aware_chunks(
        text_lines,
        section_start,
        section_end,
        tokens_per_chunk=getattr(config, 'CONTROL_V4_TOKENS_PER_CHUNK', 1000),
        overlap_tokens=getattr(config, 'CONTROL_V4_OVERLAP_TOKENS', 200)
    )
    
    # Step 2: Extract controls with CoT (may return multiple controls per chunk)
    raw_controls = []
    for chunk in chunks:
        try:
            controls_from_chunk = extract_control_with_cot(chunk)
            if controls_from_chunk and isinstance(controls_from_chunk, list):
                # Extend list with all controls found in this chunk
                raw_controls.extend(controls_from_chunk)
            elif controls_from_chunk:
                logging.warning(f"[CHUNK {chunk['chunk_id']}] extract_control_with_cot returned non-list: {type(controls_from_chunk)}")
        except Exception as e:
            logging.error(f"[CHUNK {chunk['chunk_id']}] Exception during extraction: {e}", exc_info=True)
            continue
    
    logging.info(f"Extracted {len(raw_controls)} raw controls from {len(chunks)} chunks")
    
    # Step 3: Merge continuations
    merged_controls = merge_continuations(raw_controls)
    
    # Step 4: Filter by confidence
    min_confidence = getattr(config, 'CONTROL_V4_MIN_CONFIDENCE', 0.5)
    accepted_controls, rejected_controls = filter_by_confidence(merged_controls, min_confidence)
    
    # Add text_lines context to controls for page number extraction
    for control in accepted_controls:
        control["text_lines"] = text_lines
    
    # Step 5: Validate with 5-factor confidence scoring
    validated_controls = validate_controls(
        accepted_controls,
        organization=organization,
        pattern_library=pattern_library,
        db_session=db_session
    )
    
    # Step 6: Add sequence numbers
    for i, control in enumerate(validated_controls, 1):
        control["control_seq"] = i
    
    # Calculate diagnostics
    elapsed = time.time() - start_time
    continuations_detected = sum(1 for c in raw_controls if c.get("continuation", False))
    avg_confidence = sum(c.get("control_confidence", 0) for c in validated_controls) / len(validated_controls) if validated_controls else 0
    deviations = sum(1 for c in validated_controls if c.get("has_deviation", False))
    
    diagnostics = {
        "extractor_version": "v4",
        "total_chunks": len(chunks),
        "raw_controls_extracted": len(raw_controls),
        "controls_merged": len(raw_controls) - len(merged_controls),
        "continuations_detected": continuations_detected,
        "controls_after_merge": len(merged_controls),
        "controls_rejected_confidence": len(rejected_controls),
        "final_control_count": len(validated_controls),
        "avg_confidence": round(avg_confidence, 3),
        "deviations_found": deviations,
        "processing_time_seconds": round(elapsed, 2)
    }
    
    logging.info("=" * 80)
    logging.info("EXTRACTION DIAGNOSTICS")
    logging.info("=" * 80)
    for key, value in diagnostics.items():
        logging.info(f"{key}: {value}")
    
    # Save results - maintain v2 compatibility by using {"controls": [...]} format
    output = {
        "controls": validated_controls,
        "diagnostics": diagnostics,
        "rejected_controls": rejected_controls if getattr(config, 'CONTROL_V4_SAVE_REJECTED', False) else []
    }
    
    try:
        with open(config.CONTROL_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logging.info(f"Saved {len(validated_controls)} controls to {config.CONTROL_JSON_PATH}")
    except Exception as e:
        logging.error(f"Failed to save results: {e}", exc_info=True)
        raise
    
    # Return nothing (like v2) since data is saved to file
    return None

# ============================================================================
# TESTING FUNCTION
# ============================================================================

def test_extraction_on_pdfs(pdf_list: List[str]):
    """
    Test the extraction pipeline on multiple PDFs.
    
    Args:
        pdf_list: List of PDF names (Adobe, Okta, Bitwarden, Anaqua, SimpleLegal)
    """
    logging.info("=" * 80)
    logging.info("TESTING CONTROL EXTRACTION V4")
    logging.info("=" * 80)
    
    results = {}
    
    for pdf_name in pdf_list:
        logging.info(f"\nTesting: {pdf_name}")
        logging.info("-" * 80)
        
        # Set up paths for this PDF (would need configuration)
        # For now, just log
        logging.info(f"Would process: {pdf_name}")
        # result = extract_controls_v4()
        # results[pdf_name] = result["diagnostics"]
    
    logging.info("\n" + "=" * 80)
    logging.info("TESTING SUMMARY")
    logging.info("=" * 80)
    # Would print summary across all PDFs
    
    return results

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # Run extraction
    result = extract_controls_v4()
    
    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
    print(f"Total controls: {result['diagnostics']['final_control_count']}")
    print(f"Average confidence: {result['diagnostics']['avg_confidence']:.2f}")
    print(f"Deviations found: {result['diagnostics']['deviations_found']}")
    print(f"Processing time: {result['diagnostics']['processing_time_seconds']}s")
    print("=" * 80)
