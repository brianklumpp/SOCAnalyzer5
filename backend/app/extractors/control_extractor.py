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
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable
from ..gpt_client import gpt_extract
from ..utils.objective_id_normalizer import normalize_objective_id
import concurrent.futures

try:
    from .. import config
except Exception as import_err:
    print(f"[CONTROL_EXTRACTOR] Import error: {import_err}")
    raise

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


def _parse_chunk_line_map(chunk_text: str) -> List[Tuple[int, str]]:
    """
    Parse a chunk's ║N║-marked text into (line_number, line_text) pairs.

    Each original document line was prefixed with ║<line_num>║ during chunking.
    This function extracts those markers and returns a list of tuples, each
    containing the document-relative line number and the text on that line.

    Args:
        chunk_text: The raw chunk text containing ║N║ markers.

    Returns:
        List of (doc_line_number, line_text) tuples in document order.
    """
    results: List[Tuple[int, str]] = []
    # Find all ║N║ markers and capture the text between them
    marker_pattern = re.compile(r'║(\d+)║')
    markers = list(marker_pattern.finditer(chunk_text))
    if not markers:
        return results

    for i, m in enumerate(markers):
        line_num = int(m.group(1))
        text_start = m.end()
        # Text runs until the next marker (or end of string)
        text_end = markers[i + 1].start() if i + 1 < len(markers) else len(chunk_text)
        line_text = chunk_text[text_start:text_end]
        results.append((line_num, line_text))

    return results


def find_control_line_in_chunk(
    chunk_text: str,
    control_id: Optional[str],
    control_desc: Optional[str],
    chunk_start_line: int,
    gpt_start_line: Optional[int] = None,
) -> int:
    """
    Search the chunk text for the actual document line where a control appears.

    Hybrid strategy (tried in order):
      1. Text search for control_id (e.g. "EM-01-01") in ║N║-marked lines.
      2. GPT-reported start_line — validated against chunk boundaries.
      3. Text search for first ~8 words of control_desc (fallback for messy PDFs).
      4. Fallback: return chunk_start_line (current behaviour).

    GPT start_line (Strategy 2) is placed *after* control_id search because the
    ID search is deterministic and cheap, but *before* description search because
    GPT understands the semantic role of interleaved lines (control desc vs test
    procedure vs result) that a text pattern match cannot distinguish.

    Args:
        chunk_text:       The raw chunk text with ║N║ markers.
        control_id:       The GPT-extracted control identifier (may be None).
        control_desc:     The GPT-extracted control description (may be None).
        chunk_start_line: Fallback line number (chunk's start_line).
        gpt_start_line:   GPT-reported start_line from the extraction (may be None).

    Returns:
        The document-relative line number where the control starts.
    """
    line_map = _parse_chunk_line_map(chunk_text)
    if not line_map:
        return chunk_start_line

    # Determine the valid line range for this chunk (for sanity checks)
    chunk_line_min = line_map[0][0]
    chunk_line_max = line_map[-1][0]

    # --- Strategy 1: search by control_id ---
    if control_id:
        cid_clean = control_id.strip()
        # Try exact substring match first (case-insensitive)
        for line_num, line_text in line_map:
            if cid_clean.lower() in line_text.lower():
                logging.info(
                    f"[LINEREF] Strategy 1: Matched control_id '{cid_clean}' at doc line {line_num}"
                )
                return line_num

        # Try with whitespace collapsed (handles line-break splits like "EM-\n01-01")
        cid_collapsed = re.sub(r'\s+', '', cid_clean).lower()
        # Build a running window of consecutive lines to catch IDs split across lines
        for i in range(len(line_map)):
            # Combine this line with the next line (handles 2-line splits)
            combined = line_map[i][1]
            if i + 1 < len(line_map):
                combined += line_map[i + 1][1]
            combined_collapsed = re.sub(r'\s+', '', combined).lower()
            if cid_collapsed in combined_collapsed:
                logging.info(
                    f"[LINEREF] Strategy 1: Matched control_id '{cid_clean}' (collapsed) at doc line {line_map[i][0]}"
                )
                return line_map[i][0]

    # --- Strategy 2: GPT-reported start_line (validated) ---
    if gpt_start_line is not None and isinstance(gpt_start_line, int):
        if chunk_line_min <= gpt_start_line <= chunk_line_max:
            logging.info(
                f"[LINEREF] Strategy 2: Using GPT start_line {gpt_start_line} "
                f"(within chunk range {chunk_line_min}-{chunk_line_max})"
            )
            return gpt_start_line
        else:
            logging.warning(
                f"[LINEREF] Strategy 2: GPT start_line {gpt_start_line} outside chunk range "
                f"{chunk_line_min}-{chunk_line_max} — skipping"
            )

    # --- Strategy 3: search by first ~8 words of description ---
    if control_desc and control_desc.strip():
        # Strip any leftover ║N║ markers from the description GPT returned
        desc_clean = strip_line_markers(control_desc)
        words = desc_clean.split()
        if words:
            # Use first 8 words (or fewer if desc is short)
            snippet_words = words[:8]
            snippet = ' '.join(snippet_words).lower()

            for line_num, line_text in line_map:
                line_norm = ' '.join(strip_line_markers(line_text).split()).lower()
                if snippet in line_norm:
                    logging.info(
                        f"[LINEREF] Strategy 3: Matched desc snippet at doc line {line_num}"
                    )
                    return line_num

            # Try progressively shorter snippets (7, 6, 5 words) for partial matches
            for word_count in (7, 6, 5):
                if len(words) >= word_count:
                    shorter_snippet = ' '.join(words[:word_count]).lower()
                    for line_num, line_text in line_map:
                        line_norm = ' '.join(strip_line_markers(line_text).split()).lower()
                        if shorter_snippet in line_norm:
                            logging.info(
                                f"[LINEREF] Strategy 3: Matched desc snippet ({word_count} words) at doc line {line_num}"
                            )
                            return line_num

            # Last resort within strategy 3: try combining adjacent lines
            # (handles descriptions that start mid-line or span a line break)
            snippet = ' '.join(snippet_words).lower()
            for i in range(len(line_map)):
                combined_text = line_map[i][1]
                if i + 1 < len(line_map):
                    combined_text += ' ' + line_map[i + 1][1]
                combined_norm = ' '.join(strip_line_markers(combined_text).split()).lower()
                if snippet in combined_norm:
                    logging.info(
                        f"[LINEREF] Strategy 3: Matched desc snippet (cross-line) at doc line {line_map[i][0]}"
                    )
                    return line_map[i][0]

    # --- Strategy 4: fallback ---
    logging.info(
        f"[LINEREF] Strategy 4: No match found for control_id='{control_id}', "
        f"gpt_start_line={gpt_start_line}, falling back to chunk start line {chunk_start_line}"
    )
    return chunk_start_line

# ============================================================================
# CHECKPOINT MANAGEMENT - Incremental Write Support
# ============================================================================

def write_checkpoint(
    validated_controls: List[Dict[str, Any]],
    rejected_controls: List[Dict[str, Any]],
    diagnostics: Dict[str, Any],
    checkpoint_path: str,
    scan_id: Optional[str] = None,
    job_id: Optional[str] = None
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
        checkpoint_path: Path to checkpoint file
        scan_id: Optional scan ID for tracking
        job_id: Optional job ID for logging
    """
    log_prefix = f"[JOB {job_id}] " if job_id else ""
    
    if not checkpoint_path:
        logging.warning(f"{log_prefix}Checkpoint file not configured, skipping checkpoint write")
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
        temp_checkpoint = checkpoint_path + ".tmp"
        with open(temp_checkpoint, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)
        
        # Atomic rename
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)
        os.rename(temp_checkpoint, checkpoint_path)
        
        logging.info(f"{log_prefix}✓ Checkpoint saved: {len(validated_controls)} controls")
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
# CONTROL FEEDBACK LEARNING SYSTEM
# ============================================================================

def _get_control_feedback_text(
    scan_id: Optional[int] = None,
    max_examples: int = 12,
) -> str:
    """
    Query ControlFeedback for this scan (and optionally global) and format
    as a few-shot block that can be injected into the extraction prompt.
    
    Returns an empty string if no feedback exists or DB is unavailable.
    """
    try:
        from sqlalchemy import create_engine, text as sa_text
        from ..database import SYNC_DATABASE_URL
        
        engine = create_engine(SYNC_DATABASE_URL, pool_pre_ping=True)
        
        with engine.connect() as conn:
            # First try scan-specific feedback, then supplement with global
            if scan_id:
                rows = conn.execute(sa_text("""
                    SELECT action, control_id_text, control_desc_snippet,
                           original_confidence, rejection_reason, corrected_control_id
                    FROM control_feedback
                    WHERE scan_id = :scan_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                """), {"scan_id": scan_id, "limit": max_examples}).fetchall()
            else:
                rows = []
            
            # Supplement with global if < 4 scan-specific examples
            if len(rows) < 4:
                remaining = max_examples - len(rows)
                global_filter = f"AND scan_id != {scan_id}" if scan_id else ""
                global_rows = conn.execute(sa_text(f"""
                    SELECT action, control_id_text, control_desc_snippet,
                           original_confidence, rejection_reason, corrected_control_id
                    FROM control_feedback
                    WHERE 1=1 {global_filter}
                    ORDER BY created_at DESC
                    LIMIT :limit
                """), {"limit": remaining}).fetchall()
                rows.extend(global_rows)
        
        if not rows:
            return ""
        
        lines = [
            "\n### 11. Analyst Feedback (use these corrections to calibrate extraction):"
        ]
        
        for row in rows:
            action = row[0]
            cid = row[1] or "?"
            desc_snip = (row[2] or "")[:120]
            orig_conf = row[3]
            reason = row[4] or ""
            corrected_id = row[5] or ""
            
            if action == "rejected":
                reason_text = f" ({reason.replace('_', ' ')})" if reason else ""
                lines.append(
                    f"- NOT a control{reason_text}: \"{cid}\" — \"{desc_snip}\" "
                    f"[was extracted at confidence {orig_conf or '?'}]"
                )
            elif action == "converted_to_objective":
                lines.append(
                    f"- IS AN OBJECTIVE, not a control: \"{cid}\" — \"{desc_snip}\" "
                    f"[was extracted at confidence {orig_conf or '?'}]"
                )
            elif action == "id_corrected":
                lines.append(
                    f"- WRONG ID: \"{cid}\" should be \"{corrected_id}\" — \"{desc_snip}\""
                )
            elif action == "confirmed":
                lines.append(
                    f"- CORRECT control: \"{cid}\" — \"{desc_snip}\""
                )
        
        return "\n".join(lines)
    except Exception as e:
        logging.warning(f"[CONTROL_FEEDBACK] Failed to load feedback: {e}")
        return ""


# ============================================================================
# CHAIN-OF-THOUGHT EXTRACTION (from control_extractor_v4.py)
# ============================================================================

def extract_control_with_cot(chunk: Dict[str, Any], control_feedback_block: str = "") -> Optional[List[Dict[str, Any]]]:
    """
    Extract controls using Chain-of-Thought reasoning.
    
    The CoT is embedded in the prompt itself through the parsing strategy steps.
    GPT-4/5 will internally:
    1. Reason about control boundaries
    2. Classify each sentence by role
    3. Emit structured JSON with all controls found
    
    Args:
        chunk: Chunk dictionary with text and metadata
        control_feedback_block: Optional few-shot feedback text from ControlFeedback table
        
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
            text=text,
            control_feedback_block=control_feedback_block,
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
            # Hybrid line-ref: control_id text search → GPT start_line → desc text search → fallback
            gpt_start = control.get("start_line")
            if isinstance(gpt_start, int) and gpt_start > 0:
                # GPT may return chunk-relative or doc-absolute — normalise
                # If GPT returned a small number (< start_line), treat as chunk-relative
                if gpt_start < start_line:
                    gpt_start = start_line + gpt_start
            else:
                gpt_start = None
            control["source_start_line"] = find_control_line_in_chunk(
                text,
                control.get("control_id"),
                control.get("control_desc"),
                start_line,
                gpt_start_line=gpt_start,
            )
            # Adjust end_line: GPT should now return doc-absolute ║N║ marker numbers,
            # but older models may return chunk-relative offsets. Normalise both.
            if "end_line" in control and isinstance(control["end_line"], int):
                if control["end_line"] < start_line:
                    # Looks chunk-relative → convert to doc-absolute
                    control["end_line"] = start_line + control["end_line"]
                # else: already doc-absolute, keep as-is
            logging.info(f"[CHUNK {chunk_id}] Extracted control: {control.get('control_id', 'N/A')}, confidence: {control.get('control_confidence', 0):.2f}, line_ref: {control['source_start_line']}, continuation: {control.get('continuation', False)}")
        
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
            
            # CRITICAL FIX: Strip newlines and whitespace from control_id immediately after GPT extraction
            if "control_id" in control and control["control_id"]:
                control["control_id"] = str(control["control_id"]).strip().replace('\n', '').replace('\r', '').replace('\t', ' ')
            
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
    
    # Collect ALL line positions into all_line_refs (Phase A: location preservation)
    base_line = merged.get("control_line_ref")
    add_line = addition.get("control_line_ref")
    existing_all = list(merged.get("all_line_refs") or [])
    addition_all = list(addition.get("all_line_refs") or [])
    combined_lines = set(existing_all + addition_all)
    if base_line is not None:
        combined_lines.add(base_line)
    if add_line is not None:
        combined_lines.add(add_line)
    if combined_lines:
        merged["all_line_refs"] = sorted(combined_lines)
    
    # Update end_line to furthest (handle None values)
    if "end_line" in addition:
        merged_end = merged.get("end_line") or 0
        addition_end = addition["end_line"] or 0
        merged["end_line"] = max(merged_end, addition_end)
    
    # ── Merge confidence re-evaluation ──
    # Instead of averaging (which punishes complete merges), re-score based
    # on the merged content's completeness.  A control that was split across
    # chunks often has a low score on the partial chunk; averaging drags
    # down the confidence of the now-complete merged result.
    #
    # Strategy:
    #   1. Start with the MAX of the two original confidences (the chunk
    #      that already had a mostly-complete view).
    #   2. If the merge added missing components (tests, results, description
    #      expansion), give a small boost because the merged result is more
    #      complete than either piece alone.
    base_conf = merged.get("control_confidence", 0)
    add_conf = addition.get("control_confidence", 0)
    max_conf = max(base_conf, add_conf)

    # Check which components the merged result now has
    has_id = bool(merged.get("control_id"))
    has_desc = len((merged.get("control_desc") or "").strip()) >= 20
    has_tests = bool(merged.get("control_tests"))
    has_results = bool(merged.get("control_test_results"))
    component_count = sum([has_id, has_desc, has_tests, has_results])

    if component_count == 4:
        # All components present — the merged control is complete.
        # Boost up to 0.90 if the max component score allows it, but
        # never *lower* confidence below the max original score.
        merged["control_confidence"] = max(max_conf, 0.90)
        logging.info(
            f"[MERGE_RESCORE] '{merged.get('control_id', '?')}' complete after merge: "
            f"base={base_conf:.2f}, add={add_conf:.2f} → {merged['control_confidence']:.2f} (4/4 components)"
        )
    elif component_count >= 3:
        # 3 of 4 — mostly complete
        merged["control_confidence"] = max(max_conf, 0.80)
        logging.info(
            f"[MERGE_RESCORE] '{merged.get('control_id', '?')}' mostly complete after merge: "
            f"base={base_conf:.2f}, add={add_conf:.2f} → {merged['control_confidence']:.2f} ({component_count}/4 components)"
        )
    else:
        # Still incomplete — use max rather than average to avoid dragging down
        merged["control_confidence"] = max_conf
        logging.info(
            f"[MERGE_RESCORE] '{merged.get('control_id', '?')}' still partial after merge: "
            f"base={base_conf:.2f}, add={add_conf:.2f} → max={max_conf:.2f} ({component_count}/4 components)"
        )
    
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


# TSC criteria IDs that should not be extracted as controls
_TSC_ID_PATTERN = re.compile(r'^(CC|A|C|P|PI)\d+\.\d+$', re.IGNORECASE)


def filter_tsc_criteria(controls: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Post-extraction filter: auto-flag controls whose IDs match TSC criteria patterns.
    
    TSC criteria (CC1.1, CC3.2, A1.1, etc.) are objectives, not controls.
    When the extractor picks these up, they should be separated out and marked
    with a low confidence + annotation so they can be auto-converted to objectives.
    
    Args:
        controls: List of control dicts from extraction
        
    Returns:
        Tuple of (real_controls, tsc_flagged) where tsc_flagged have lowered confidence
    """
    real_controls = []
    tsc_flagged = []
    
    for control in controls:
        cid = (control.get("control_id") or "").strip()
        if _TSC_ID_PATTERN.match(cid):
            # This looks like a TSC criteria ID, not a real control
            control["_tsc_flagged"] = True
            control["_original_confidence"] = control.get("control_confidence", 0)
            control["control_confidence"] = 0.0  # Zero it — user can convert to objective
            control["control_gpt_conf_justification"] = (
                f"Auto-flagged as TSC criteria (ID pattern: {cid}). "
                f"Original confidence: {control['_original_confidence']:.2f}. "
                f"TSC criteria are objectives, not controls."
            )
            tsc_flagged.append(control)
            logging.info(
                f"[TSC_FILTER] Flagged '{cid}' as TSC criteria objective "
                f"(original confidence: {control['_original_confidence']:.2f})"
            )
        else:
            real_controls.append(control)
    
    if tsc_flagged:
        logging.info(
            f"[TSC_FILTER] {len(tsc_flagged)} controls flagged as TSC criteria, "
            f"{len(real_controls)} real controls retained"
        )
    
    return real_controls, tsc_flagged


# Auditor test procedure language patterns
_AUDITOR_TEST_PATTERNS = [
    re.compile(r'\b(?:inspected|observed|inquired|examined|reviewed|tested)\b.*\bto determine whether\b', re.IGNORECASE),
    re.compile(r'\b(?:inspected|observed|inquired|examined)\b.*\bfor a selection of\b', re.IGNORECASE),
    re.compile(r'\b(?:inspected|observed)\b.*\bevidence\b.*\bfor a selection\b', re.IGNORECASE),
    re.compile(r'\binspected.*(?:completion records|documentation|evidence|records)\b.*\bfor a selection\b', re.IGNORECASE),
]

# Generic / vague statement patterns
_GENERIC_STATEMENT_PATTERNS = [
    re.compile(r'^(?:corrective action is taken|changes are implemented|ability to make changes)', re.IGNORECASE),
    re.compile(r'^(?:the entity implements data classification|the company evaluates configurations)', re.IGNORECASE),
]


def filter_auditor_and_generic(
    controls: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Post-extraction filter: penalize controls that look like auditor test procedures
    or generic/vague statements. Learned from control_feedback rejection data:
      - 14 auditor_test_procedure rejections (avg conf 0.38)
      - 18 generic_statement rejections (avg conf 0.29)

    Instead of removing outright, these are confidence-penalized so
    they sort to the bottom and the user can decide.
    """
    clean = []
    flagged = []

    for control in controls:
        desc = (control.get("control_desc") or "").strip()

        # --- auditor test procedure check ---
        # Only flag if the description STARTS with auditor language (first 80 chars)
        # or if the MAJORITY of the text is auditor test procedures.
        # GPT sometimes concatenates test text onto a valid description —
        # we should not penalize if there's real control text at the start.
        is_auditor = False
        for p in _AUDITOR_TEST_PATTERNS:
            m = p.search(desc)
            if m:
                # If the match starts within the first 30 chars, it's primarily auditor text
                # If it starts later, the description leads with real control text
                if m.start() < 30:
                    is_auditor = True
                    break
                # Also flag if >60% of the description is after the auditor match start
                # (meaning the description is mostly test procedure text)
                elif m.start() < len(desc) * 0.4:
                    is_auditor = True
                    break

        # --- generic statement check (short + no specific actor/system) ---
        is_generic = any(p.search(desc) for p in _GENERIC_STATEMENT_PATTERNS)
        # Also flag very short descriptions (< 60 chars) that lack a named subject
        if not is_generic and len(desc) < 60 and not re.search(r'[A-Z][a-z]+(?:\s[A-Z][a-z]+)*', desc):
            # Short description with no proper noun → likely generic fragment
            is_generic = True

        if is_auditor or is_generic:
            reason = "auditor_test_procedure" if is_auditor else "generic_statement"
            orig_conf = control.get("control_confidence", 0)
            # Penalty: cap at 0.15 so they don't pollute mapping
            new_conf = min(orig_conf, 0.15)
            control["_quality_flagged"] = reason
            control["_original_confidence"] = orig_conf
            control["control_confidence"] = new_conf
            control["control_gpt_conf_justification"] = (
                f"Auto-flagged as {reason}. "
                f"Original confidence: {orig_conf:.2f} → {new_conf:.2f}. "
                f"Description: \"{desc[:80]}…\""
            )
            flagged.append(control)
            logging.info(
                f"[QUALITY_FILTER] Flagged '{control.get('control_id', '?')}' as {reason} "
                f"(conf {orig_conf:.2f} → {new_conf:.2f})"
            )
        else:
            clean.append(control)

    if flagged:
        logging.info(
            f"[QUALITY_FILTER] {len(flagged)} controls flagged "
            f"(auditor/generic), {len(clean)} retained"
        )

    return clean, flagged


def apply_short_description_penalty(
    controls: List[Dict[str, Any]],
    min_chars: int = 50,
    penalty_factor: float = 0.9,
) -> List[Dict[str, Any]]:
    """
    Post-extraction penalty: controls with very short descriptions
    (< min_chars) get a mild confidence reduction.

    Learned from scan 8 review: 5 of 6 manually-boosted controls were
    solely penalized by this function. Short descriptions with a valid
    control_id and high GPT confidence are often legitimate, complete
    controls (e.g. "Adobe restricted data at rest is encrypted." — 43 chars).
    Softened from 0.6× to 0.9× so these controls remain in the
    high-confidence bucket unless other penalties also apply.
    """
    for control in controls:
        desc = (control.get("control_desc") or "").strip()
        if len(desc) < min_chars:
            orig_conf = control.get("control_confidence", 0)
            new_conf = round(orig_conf * penalty_factor, 3)
            control["_short_desc_penalty"] = True
            control["_original_confidence"] = control.get("_original_confidence", orig_conf)
            control["control_confidence"] = new_conf
            logging.info(
                f"[SHORT_DESC_PENALTY] '{control.get('control_id', '?')}' "
                f"desc={len(desc)} chars → conf {orig_conf:.2f} × {penalty_factor} = {new_conf:.2f}"
            )
    return controls


def augment_page_refs_from_text(
    controls: List[Dict[str, Any]],
    text_lines: List[str],
) -> List[Dict[str, Any]]:
    """
    Post-extraction pass: scan the full document text for each control's ID
    to discover page references that GPT may have missed during chunk-level
    extraction.

    For each control with a non-empty control_id, we search the document text
    for occurrences of that ID (exact, case-insensitive).  For each occurrence,
    we determine its page number via the ``=== PAGE N ===`` markers in the
    extracted text and add it to ``control_page_refs``.

    This is especially important for multi-page controls that appear under
    multiple objectives — the initial chunk-level extraction may only capture
    the first occurrence.

    Returns the controls list (mutated in place) with augmented page_refs.
    """
    from ..pdf_handler import get_page_for_line as _get_page

    if not text_lines:
        logging.warning("[PAGE_REF_SEARCH] No text_lines provided — skipping augmentation")
        return controls

    # Build a set of control IDs to search for
    id_map: Dict[str, List[Dict[str, Any]]] = {}
    for ctrl in controls:
        cid = (ctrl.get("control_id") or "").strip()
        if cid:
            id_map.setdefault(cid.lower(), []).append(ctrl)

    if not id_map:
        return controls

    augmented_count = 0
    total_new_pages = 0

    for line_idx, line in enumerate(text_lines):
        line_lower = line.lower()
        for cid_lower, ctrls in id_map.items():
            if cid_lower in line_lower:
                # Determine the page for this line occurrence
                page = _get_page(text_lines, line_idx + 1)  # line_idx is 0-based; get_page expects 1-based
                if page:
                    for ctrl in ctrls:
                        existing = ctrl.get("control_page_refs") or []
                        if isinstance(existing, str):
                            existing = [int(p.strip()) for p in existing.split(",") if p.strip().isdigit()]
                        if page not in existing:
                            existing.append(page)
                            ctrl["control_page_refs"] = sorted(set(existing))
                            total_new_pages += 1

    augmented_count = sum(
        1 for ctrl in controls
        if len(ctrl.get("control_page_refs") or []) > len(ctrl.get("_original_page_refs") or ctrl.get("control_page_refs") or [])
    )

    # Snapshot originals for comparison logging
    # We take the snapshot BEFORE the first run, so use a flag
    for ctrl in controls:
        if "_page_ref_augmented" not in ctrl:
            ctrl["_page_ref_augmented"] = True

    if total_new_pages > 0:
        logging.info(
            f"[PAGE_REF_SEARCH] Augmented page_refs: {total_new_pages} new page(s) "
            f"discovered across controls"
        )
    else:
        logging.info("[PAGE_REF_SEARCH] No additional page references found (text search matched existing refs)")

    return controls


def apply_missing_id_penalty(
    controls: List[Dict[str, Any]],
    penalty_factor: float = 0.70,
) -> List[Dict[str, Any]]:
    """
    Post-extraction penalty: controls without a control_id get their
    confidence lowered so they move from high-confidence to low-confidence.

    The GPT prompt instructs 0.6-0.89 for "missing ID" yet GPT routinely
    assigns 0.85-0.95 to no-ID controls.  This enforces that guidance.

    With a 0.70 multiplier:
    - 0.95 → 0.665 (below 0.75, appears in low-confidence for review)
    - 0.80 → 0.56  (still above 0.50, remains visible)
    - 0.60 → 0.42  (low but retained)

    Controls are NOT removed — only moved to the low-confidence bucket.
    """
    penalized = 0
    for control in controls:
        cid = (control.get("control_id") or "").strip()
        if not cid:
            orig_conf = control.get("control_confidence", 0)
            new_conf = round(orig_conf * penalty_factor, 3)
            control["_missing_id_penalty"] = True
            control["_original_confidence"] = control.get("_original_confidence", orig_conf)
            control["control_confidence"] = new_conf
            penalized += 1
            logging.info(
                f"[MISSING_ID_PENALTY] No control_id → "
                f"conf {orig_conf:.2f} × {penalty_factor} = {new_conf:.2f}  "
                f"desc='{(control.get('control_desc') or '')[:60]}…'"
            )

    if penalized:
        logging.info(f"[MISSING_ID_PENALTY] Penalized {penalized} controls without IDs")
    return controls


def detect_subset_controls(
    controls: List[Dict[str, Any]],
    penalty_factor: float = 0.65,
) -> List[Dict[str, Any]]:
    """
    Post-extraction penalty: detect controls that are **chunking fragments**
    — i.e. no control_id AND their description is a true substring of another
    control's description.

    Key distinction (per domain expertise):
    - A control can legitimately appear multiple times in a SOC report under
      different control objectives.  Auditors may intentionally shorten or
      tailor the description for each objective context.  These all carry
      their own control_id and should NOT be penalized.
    - A chunking artifact is a fragment where GPT re-extracted part of a
      control from an overlapping chunk but couldn't identify the control_id.
      These have NO control_id and their text is a literal substring of the
      full control.  Only these should be penalized.

    Additional heuristic: if the no-ID fragment ends mid-sentence (no
    terminal punctuation), it's almost certainly a chunk boundary cut-off.
    If it ends cleanly, we apply a lighter penalty.

    O(n²) — fine for typical n < 200.
    """
    if len(controls) < 2:
        return controls

    import re as _re
    norm_descs = []
    for ctrl in controls:
        desc = (ctrl.get("control_desc") or "").strip()
        norm = _re.sub(r'\s+', ' ', desc.lower())
        norm_descs.append(norm)

    # Track which index is a subset of which
    penalized_map: dict = {}  # idx -> superset_idx

    for i in range(len(controls)):
        if not norm_descs[i] or len(norm_descs[i]) < 30:
            continue
        if i in penalized_map:
            continue  # already penalized

        # ONLY penalize controls without a control_id.
        # If a control has an ID, the auditor assigned it intentionally —
        # even if its text is a substring of another control with a
        # different ID, that's an intentional variant for a different
        # control objective.
        id_i = (controls[i].get("control_id") or "").strip()
        if id_i:
            continue  # has an ID → never penalize as subset

        for j in range(len(controls)):
            if i == j:
                continue
            if not norm_descs[j]:
                continue

            # Only check if i is shorter than j (true subset direction)
            if len(norm_descs[i]) >= len(norm_descs[j]):
                continue

            # Exact substring check
            if norm_descs[i] in norm_descs[j]:
                penalized_map[i] = j
                break  # found a superset, move on

    subset_count = 0
    for idx, superset_idx in penalized_map.items():
        ctrl = controls[idx]
        orig_conf = ctrl.get("control_confidence", 0)

        # Heuristic: if the fragment ends mid-sentence (no terminal
        # punctuation), it's almost certainly a chunk boundary cut-off
        # → apply full penalty.  If it ends with '.', '!', '?' it may
        # be a complete thought extracted without its ID → lighter penalty.
        raw_desc = (ctrl.get("control_desc") or "").strip()
        ends_cleanly = raw_desc and raw_desc[-1] in '.!?'
        effective_factor = penalty_factor if not ends_cleanly else min(penalty_factor + 0.15, 0.90)

        new_conf = round(orig_conf * effective_factor, 3)
        ctrl["_subset_text_penalty"] = True
        ctrl["_original_confidence"] = ctrl.get("_original_confidence", orig_conf)
        ctrl["control_confidence"] = new_conf
        subset_count += 1

        superset_id = controls[superset_idx].get("control_id") or f"ctrl@{superset_idx}"
        trunc_tag = "truncated" if not ends_cleanly else "complete-sentence"
        logging.info(
            f"[SUBSET_TEXT] no-ID '{raw_desc[:40]}…' is substring of '{superset_id}' "
            f"[{trunc_tag}] → conf {orig_conf:.2f} × {effective_factor:.2f} = {new_conf:.2f}"
        )

    if subset_count:
        logging.info(f"[SUBSET_TEXT] Penalized {subset_count} true-substring controls")
    else:
        logging.info("[SUBSET_TEXT] No true-substring overlaps detected")

    return controls


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
    logging.error(f"[VALIDATE_CONTROLS ENTRY] Called with {len(controls)} controls")
    validated = []
    
    # Required fields
    required_fields = ["control_desc"]
    
    for i, control in enumerate(controls):
        if i == 0:
            logging.error(f"[VALIDATE_CONTROLS] Processing control 0, keys: {list(control.keys())[:10]}")
        # Strip line markers from text fields
        text_fields = ['control_id', 'control_desc', 'deviation_desc', 'control_gpt_conf_justification']
        for field in text_fields:
            if field in control and control[field]:
                control[field] = strip_line_markers(str(control[field]))
        
        # Strip markers from list fields
        list_fields = ['control_tests', 'control_test_results', 'additional_references']
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
        for field in ["control_tests", "control_test_results", "additional_references"]:
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
            
            has_source = "source_start_line" in control
            has_text_lines = "text_lines" in control
            
            if i == 0:  # Debug first control only
                logging.info(f"[PAGE EXTRACTION DEBUG] Control 0: has_source_start_line={has_source}, has_text_lines={has_text_lines}")
                if has_text_lines:
                    logging.info(f"[PAGE EXTRACTION DEBUG] Control 0: text_lines length={len(control.get('text_lines', []))}")
            
            if "source_start_line" in control and "text_lines" in control:
                page_num = get_page_for_line(control["text_lines"], control["source_start_line"])
                control["control_line_ref"] = control["source_start_line"]
                # Initialize all_line_refs with this position (merge will accumulate more)
                if "all_line_refs" not in control or not control["all_line_refs"]:
                    control["all_line_refs"] = [control["source_start_line"]]
                
                # Compute pages from ALL known line positions (start, end, all_line_refs)
                all_pages = set()
                if page_num:
                    all_pages.add(page_num)
                # Also add end_line page if available
                end_line = control.get("end_line")
                if end_line and isinstance(end_line, int):
                    end_page = get_page_for_line(control["text_lines"], end_line)
                    if end_page:
                        all_pages.add(end_page)
                # Also add pages for all_line_refs entries
                for lr in (control.get("all_line_refs") or []):
                    if isinstance(lr, int) and lr > 0:
                        p = get_page_for_line(control["text_lines"], lr)
                        if p:
                            all_pages.add(p)
                control["control_page_refs"] = sorted(all_pages) if all_pages else []
                
                if i == 0:
                    logging.info(f"[PAGE EXTRACTION DEBUG] Control 0: Extracted pages={control['control_page_refs']} for line={control['source_start_line']}")
            elif "source_start_line" in control:
                control["control_line_ref"] = control["source_start_line"]
                if "all_line_refs" not in control or not control["all_line_refs"]:
                    control["all_line_refs"] = [control["source_start_line"]]
                if i == 0:
                    logging.warning(f"[PAGE EXTRACTION DEBUG] Control 0: Has source_start_line but missing text_lines")
        except Exception as e:
            logging.error(f"[PAGE EXTRACTION ERROR] Control {i}: {e}")
            import traceback
            logging.error(f"[PAGE EXTRACTION ERROR] Traceback: {traceback.format_exc()}")
        
        # Ensure boolean fields
        if "has_deviation" not in control:
            control["has_deviation"] = False
        if "continuation" not in control:
            control["continuation"] = False
        
        # Set default confidence if missing
        if "control_confidence" not in control:
            control["control_confidence"] = 0.5
            control["control_gpt_conf_justification"] = "Default confidence (no GPT score provided)"
        
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
    job_paths: Optional[Dict[str, Path]] = None,
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
        job_paths: Job-specific paths dictionary
        job_id: Job ID for logging and Redis updates
        redis_client: Redis client for progress updates
        
    Returns:
        Dict with extraction results and diagnostics
    """
    # Validate job_paths parameter
    if job_paths is None:
        raise ValueError("job_paths parameter is required")
    if job_id is None:
        raise ValueError("job_id parameter is required")
    
    log_prefix = f"[JOB {job_id}] "
    
    # Create job-specific paths
    pdf_txt_path = str(job_paths['txt_path'])
    control_json_path = str(job_paths['json_dir'] / 'control_result.json')
    checkpoint_path = str(job_paths['json_dir'] / 'control_checkpoint.json')
    
    logging.info(f"{log_prefix}Checkpoint file: {checkpoint_path}")
    
    # Apply quick test mode if enabled and max_controls not explicitly set
    if max_controls is None and getattr(config, 'QUICK_TEST_MODE_ENABLED', False):
        max_controls = getattr(config, 'QUICK_TEST_MAX_CONTROLS', 10)
        logging.info(f"{log_prefix}QUICK TEST MODE ENABLED: Limiting extraction to {max_controls} controls")
    
    start_time = time.time()
    logging.info(f"{log_prefix}" + "=" * 80)
    logging.info(f"{log_prefix}UNIFIED CONTROL EXTRACTION - Report Type: {report_type}")
    logging.info(f"{log_prefix}Assertion Mapping: {'ENABLED' if enable_assertion_mapping else 'DISABLED'}")
    logging.info(f"{log_prefix}Max Controls: {max_controls if max_controls else 'UNLIMITED (full extraction)'}")
    logging.info(f"{log_prefix}Scan ID: {scan_id or 'N/A'}")
    logging.info(f"{log_prefix}Job ID: {job_id}")
    logging.info(f"{log_prefix}" + "=" * 80)
    
    # Find control section - MUST be Control_Descriptions for proper control extraction
    # Do NOT use Description_of_System as it contains narrative, not control tables
    control_section = next(
        (s for s in sections if s["topic"] == "Control_Descriptions"),
        None
    )
    
    if not control_section:
        logging.error(f"{log_prefix}Control_Descriptions section not found in extracted sections")
        logging.error(f"{log_prefix}Available sections: {[s.get('topic') for s in sections]}")
        return {"error": "Control_Descriptions section not found"}
    
    section_start = control_section["start_line"]
    section_end = control_section["end_line"]
    
    # Handle resume logic
    if start_at_line:
        section_start = start_at_line
        logging.info(f"{log_prefix}Resuming from line {start_at_line}")
    
    logging.info(f"{log_prefix}Extracting controls from lines {section_start} to {section_end}")
    
    # Load document
    with open(pdf_txt_path, 'r', encoding='utf-8') as f:
        text_lines = f.readlines()
    
    # Validate section bounds against actual file length
    actual_line_count = len(text_lines)
    if section_end > actual_line_count:
        logging.warning(f"{log_prefix}Section end_line ({section_end}) exceeds actual file length ({actual_line_count}). Adjusting to file length.")
        section_end = actual_line_count
    
    if section_start > actual_line_count:
        logging.error(f"{log_prefix}Section start_line ({section_start}) exceeds actual file length ({actual_line_count}). Cannot proceed.")
        return {"error": f"Invalid section bounds: start_line={section_start} > file_length={actual_line_count}"}
    
    logging.info(f"{log_prefix}Validated bounds: lines {section_start}-{section_end} (file has {actual_line_count} lines)")
    
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
    
    # ── Control Feedback Learning System ──
    # Build feedback block once and reuse for all chunks
    control_feedback_block = ""
    try:
        int_scan_id = int(scan_id) if scan_id else None
        control_feedback_block = _get_control_feedback_text(scan_id=int_scan_id)
        if control_feedback_block:
            logging.info(f"{log_prefix}[CONTROL_FEEDBACK] Loaded feedback block ({len(control_feedback_block)} chars)")
        else:
            logging.info(f"{log_prefix}[CONTROL_FEEDBACK] No feedback data available")
    except Exception as fb_err:
        logging.warning(f"{log_prefix}[CONTROL_FEEDBACK] Failed to load feedback: {fb_err}")
    
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
            controls_from_chunk = extract_control_with_cot(chunk, control_feedback_block=control_feedback_block)
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
                            # Estimate total controls from section size
                            avg_controls_per_line = len(raw_controls) / max(1, lines_processed)
                            controls_total_estimate = int(avg_controls_per_line * section_total_lines)
                            
                            from ..job_state import job_hmset
                            job_hmset(job_id, {
                                'controls_count': len(raw_controls),
                                'controls_total_estimate': controls_total_estimate,
                                'controls_percent': controls_percent
                            }, redis_client)
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
    
    # Step 4b: TSC criteria auto-filter
    accepted_controls, tsc_flagged = filter_tsc_criteria(accepted_controls)
    rejected_controls.extend(tsc_flagged)  # TSC criteria go to rejected with confidence=0

    # Step 4c: Auditor test procedure / generic statement filter
    accepted_controls, quality_flagged = filter_auditor_and_generic(accepted_controls)
    rejected_controls.extend(quality_flagged)

    # Step 4d: Short-description confidence penalty (enumeration fragments)
    accepted_controls = apply_short_description_penalty(accepted_controls)

    # Step 4e: Missing control_id penalty (GPT ignores its own scoring guidance)
    accepted_controls = apply_missing_id_penalty(accepted_controls)

    # Step 4f: Subset-text detection (fragment re-extractions across chunks)
    accepted_controls = detect_subset_controls(accepted_controls)

    # NOTE: No re-filter here — penalties only lower confidence so controls
    # move from high-confidence to low-confidence bucket for user review.

    # Add text_lines context to controls for page number extraction
    for control in accepted_controls:
        control["text_lines"] = text_lines
    
    # Step 5: Validate
    validated_controls = validate_controls(accepted_controls)
    
    # Step 5b: Augment page refs by scanning document text for control ID mentions
    # Must run BEFORE text_lines are removed since it needs them for page lookup
    validated_controls = augment_page_refs_from_text(validated_controls, text_lines)
    
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
        write_checkpoint(validated_controls, rejected_controls, partial_diagnostics, checkpoint_path, scan_id, job_id)
        logging.info(f"{log_prefix}Checkpoint written: {len(validated_controls)} controls (before framework mapping)")
    
    # Step 5b: Framework mapping - SKIPPED during pipeline extraction
    # Framework mapping is now handled as a separate parallel phase in analyze.py
    # (_run_framework_mapping_task) which runs concurrently with objective extraction.
    # This avoids sequential blocking here and enables parallel execution.
    # The batch phase uses map_controls_to_frameworks_batch() with parallel workers.
    logging.info(f"{log_prefix}Skipping inline framework mapping (handled in parallel post-control phase)")
    
    # Initialize empty framework fields so controls pass validation
    for control in validated_controls:
        if "framework_mappings" not in control:
            control["framework_mappings"] = {}
            control["primary_framework"] = None
            control["primary_criterion_id"] = None
            control["primary_criterion_id_normalized"] = None
            control["primary_criterion_id_original"] = None
            control["primary_confidence"] = 0.0
    
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
        with open(control_json_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logging.info(f"{log_prefix}Saved {len(validated_controls)} controls to {control_json_path}")
        
        # Clean up checkpoint file on successful completion
        if checkpoint_path and os.path.exists(checkpoint_path):
            try:
                os.remove(checkpoint_path)
                logging.info("✓ Checkpoint file removed after successful completion")
            except Exception as e:
                logging.warning(f"Failed to remove checkpoint file: {e}")
    except Exception as e:
        logging.error(f"Failed to save results: {e}", exc_info=True)
        # Keep checkpoint file if final write fails - allows recovery
        logging.info("Checkpoint file preserved due to save failure")
        raise
    
    return output


# ============================================================================
# PARALLEL CONTROL EXTRACTION - v2.1.0 Multi-Threading
# ============================================================================

def extract_controls_parallel(
    sections: List[Dict[str, Any]],
    report_type: str,
    executor: Optional[Any] = None,
    progress_tracker: Optional[Any] = None,
    enable_assertion_mapping: bool = False,
    start_at_line: Optional[int] = None,
    max_controls: Optional[int] = None,
    scan_id: Optional[str] = None,
    job_paths: Optional[Dict[str, Path]] = None,
    job_id: Optional[str] = None,
    redis_client: Optional[Any] = None
) -> Dict[str, Any]:
    """
    PARALLEL control extraction pipeline using IntelligentTaskExecutor.
    
    Key Differences from Sequential Version:
    - Processes 4 chunks concurrently (semaphore-limited)
    - Updates progress tracker every 2 controls extracted
    - Thread-safe control aggregation
    - Adaptive throttling prevents resource spikes
    - Circuit breaker handles GPT API failures gracefully
    
    Pipeline:
    1. Load section boundaries
    2. Create aware chunks with metadata
    3. **PARALLEL** Extract controls from chunks (4 concurrent workers)
    4. Merge continuations (sequential - requires full dataset)
    5. Filter by confidence (sequential)
    6. Validate and clean (sequential)
    7. Optionally map financial assertions (sequential - or future parallel)
    8. Return structured results
    
    Args:
        sections: List of section dictionaries from section extraction
        report_type: Report type ("SOC1", "SOC2", "COMBINED")
        executor: IntelligentTaskExecutor instance (if None, falls back to sequential)
        progress_tracker: ProgressTracker instance for granular updates
        enable_assertion_mapping: Enable batch financial assertion mapping
        start_at_line: Resume from line number
        max_controls: Maximum controls to extract (for testing)
        scan_id: Scan ID for checkpoint tracking
        job_paths: Job-specific paths dictionary
        job_id: Job ID for Redis progress updates and logging
        redis_client: Redis client for progress persistence
        
    Returns:
        Dict with extraction results and diagnostics
    """
    # Fallback to sequential if executor not provided
    if not executor:
        logging.warning("[PARALLEL] No executor provided, falling back to sequential extraction")
        return extract_controls(
            sections=sections,
            report_type=report_type,
            enable_assertion_mapping=enable_assertion_mapping,
            start_at_line=start_at_line,
            max_controls=max_controls,
            scan_id=scan_id,
            job_paths=job_paths,
            job_id=job_id,
            redis_client=redis_client
        )
    
    # Validate job_paths parameter
    if job_paths is None:
        raise ValueError("job_paths parameter is required")
    if job_id is None:
        raise ValueError("job_id parameter is required")
    
    log_prefix = f"[JOB {job_id}] [PARALLEL] "
    
    # Create job-specific paths
    pdf_txt_path = str(job_paths['txt_path'])
    control_json_path = str(job_paths['json_dir'] / 'control_result.json')
    checkpoint_path = str(job_paths['json_dir'] / 'control_checkpoint_parallel.json')
    
    logging.info(f"{log_prefix}Checkpoint file: {checkpoint_path}")
    
    # Apply quick test mode if enabled
    if max_controls is None and getattr(config, 'QUICK_TEST_MODE_ENABLED', False):
        max_controls = getattr(config, 'QUICK_TEST_MAX_CONTROLS', 10)
        logging.info(f"[PARALLEL] QUICK TEST MODE: Limiting to {max_controls} controls")
    
    start_time = time.time()
    logging.info("=" * 80)
    logging.info(f"PARALLEL CONTROL EXTRACTION (v2.1.0) - Report Type: {report_type}")
    logging.info(f"Executor: {executor.__class__.__name__} (max_workers={executor.max_workers})")
    logging.info(f"Progress Tracker: {'ENABLED' if progress_tracker else 'DISABLED'}")
    logging.info(f"Assertion Mapping: {'ENABLED' if enable_assertion_mapping else 'DISABLED'}")
    logging.info(f"Max Controls: {max_controls if max_controls else 'UNLIMITED'}")
    logging.info("=" * 80)
    
    # Start progress tracking
    if progress_tracker:
        progress_tracker.start_extractor("controls", estimated_total=None, total_chunks=0)
    
    # Find control section
    control_section = next(
        (s for s in sections if s["topic"] == "Control_Descriptions"),
        None
    )
    
    if not control_section:
        logging.error("[PARALLEL] Control_Descriptions section not found")
        return {"error": "Control_Descriptions section not found"}
    
    section_start = control_section["start_line"]
    section_end = control_section["end_line"]
    
    if start_at_line:
        section_start = start_at_line
        logging.info(f"[PARALLEL] Resuming from line {start_at_line}")
    
    logging.info(f"{log_prefix}Extracting from lines {section_start} to {section_end}")
    
    # Load document
    with open(pdf_txt_path, 'r', encoding='utf-8') as f:
        text_lines = f.readlines()
    
    # Validate section bounds
    actual_line_count = len(text_lines)
    if section_end > actual_line_count:
        logging.warning(f"[PARALLEL] Adjusting section_end {section_end} → {actual_line_count}")
        section_end = actual_line_count
    
    if section_start > actual_line_count:
        logging.error(f"[PARALLEL] Invalid start_line {section_start} > {actual_line_count}")
        return {"error": f"Invalid section bounds"}
    
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
    logging.info(f"[PARALLEL] Created {len(chunks)} chunks in {chunk_time:.2f}s")
    
    # Update progress tracker with chunk count
    if progress_tracker:
        # Estimate controls based on section size (rough: 1 control per 20 lines)
        estimated_controls = max(10, (section_end - section_start) // 20)
        progress_tracker.start_extractor("controls", estimated_total=estimated_controls, total_chunks=len(chunks))
    
    # Step 2: PARALLEL chunk processing
    raw_controls = []
    raw_controls_lock = threading.Lock()
    total_gpt_time = 0
    gpt_time_lock = threading.Lock()
    control_count = 0  # Track for "every 2 controls" updates
    
    # ── Control Feedback Learning System ──
    control_feedback_block = ""
    try:
        int_scan_id = int(scan_id) if scan_id else None
        control_feedback_block = _get_control_feedback_text(scan_id=int_scan_id)
        if control_feedback_block:
            logging.info(f"[PARALLEL] [CONTROL_FEEDBACK] Loaded feedback block ({len(control_feedback_block)} chars)")
    except Exception as fb_err:
        logging.warning(f"[PARALLEL] [CONTROL_FEEDBACK] Failed to load feedback: {fb_err}")
    
    def process_chunk(chunk_data: Tuple[int, Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """
        Process a single chunk (called in parallel).
        
        Args:
            chunk_data: Tuple of (chunk_index, chunk_dict)
            
        Returns:
            List of controls extracted from chunk, or None if error
        """
        chunk_idx, chunk = chunk_data
        
        try:
            # Check cancellation flag
            if job_id and redis_client:
                cancelled = redis_client.get(f"job:{job_id}:cancelled")
                if cancelled:
                    logging.info(f"[PARALLEL] Chunk {chunk_idx}: Cancellation detected")
                    return None
            
            # Track GPT timing
            gpt_start = time.time()
            controls_from_chunk = extract_control_with_cot(chunk, control_feedback_block=control_feedback_block)
            gpt_elapsed = time.time() - gpt_start
            
            # Update global GPT time (thread-safe)
            with gpt_time_lock:
                nonlocal total_gpt_time
                total_gpt_time += gpt_elapsed
            
            chunk_control_count = len(controls_from_chunk) if controls_from_chunk and isinstance(controls_from_chunk, list) else 0
            logging.info(f"[PARALLEL] Chunk {chunk_idx}/{len(chunks)}: {chunk_control_count} controls in {gpt_elapsed:.2f}s")
            
            if controls_from_chunk and isinstance(controls_from_chunk, list):
                # Thread-safe append to raw_controls
                with raw_controls_lock:
                    nonlocal control_count
                    raw_controls.extend(controls_from_chunk)
                    control_count = len(raw_controls)
                    
                    # Update progress every 2 controls
                    if control_count % 2 == 0:
                        if progress_tracker:
                            progress_tracker.update_controls(control_count)
                        
                        # Also update Redis for legacy frontend
                        if job_id and redis_client:
                            try:
                                # Calculate progress
                                current_line = chunk.get('end_line', section_start)
                                lines_processed = current_line - section_start
                                section_total_lines = section_end - section_start
                                controls_percent = int((lines_processed / max(1, section_total_lines)) * 100)
                                
                                # Estimate total
                                avg_controls_per_line = control_count / max(1, lines_processed)
                                controls_total_estimate = int(avg_controls_per_line * section_total_lines)
                                
                                # Use thread-safe flat hash update
                                from ..job_state import job_hmset
                                job_hmset(job_id, {
                                    'controls_count': control_count,
                                    'controls_total_estimate': controls_total_estimate,
                                    'controls_percent': min(95, controls_percent)
                                }, redis_client)
                                    
                                logging.info(f"[PARALLEL] Progress: {control_count}/{controls_total_estimate} ({controls_percent}%)")
                            except Exception as prog_err:
                                logging.warning(f"[PARALLEL] Progress update failed: {prog_err}")
                    
                    # Check max_controls limit
                    if max_controls and control_count >= max_controls:
                        logging.info(f"[PARALLEL] Reached max_controls limit ({max_controls})")
                        return controls_from_chunk  # Return what we have
                
                return controls_from_chunk
            elif controls_from_chunk:
                logging.warning(f"[PARALLEL] Chunk {chunk_idx}: Non-list result: {type(controls_from_chunk)}")
                return None
            else:
                return None
                
        except Exception as e:
            logging.error(f"[PARALLEL] Chunk {chunk_idx}: Exception: {e}", exc_info=True)
            return None
    
    # Submit all chunks for parallel processing
    logging.info(f"[PARALLEL] Submitting {len(chunks)} chunks to executor")
    chunk_data = [(idx, chunk) for idx, chunk in enumerate(chunks)]
    
    try:
        # Use executor.map for parallel processing with automatic result ordering
        from ..scan_threading import TaskPriority
        results = executor.map(
            process_chunk,
            chunk_data,
            priority=TaskPriority.HIGH,
            timeout=600,  # 10 min timeout for entire operation
            return_exceptions=False
        )
        
        logging.info(f"[PARALLEL] Completed chunk processing")
        
    except Exception as e:
        logging.error(f"[PARALLEL] Executor failed: {e}", exc_info=True)
        # Fallback to sequential if parallel fails
        logging.warning("[PARALLEL] Falling back to sequential extraction")
        return extract_controls(
            sections=sections,
            report_type=report_type,
            enable_assertion_mapping=enable_assertion_mapping,
            start_at_line=start_at_line,
            max_controls=max_controls,
            scan_id=scan_id,
            job_paths=job_paths,  # FIXED: Add missing job_paths parameter
            job_id=job_id,
            redis_client=redis_client
        )
    
    parallel_time = time.time() - chunk_start_time
    avg_gpt_time = total_gpt_time / len(chunks) if chunks else 0
    
    logging.info(f"=" * 80)
    logging.info(f"PARALLEL EXTRACTION METRICS:")
    logging.info(f"  Total chunks: {len(chunks)}")
    logging.info(f"  Parallel processing time: {parallel_time:.2f}s")
    logging.info(f"  Total GPT time: {total_gpt_time:.2f}s")
    logging.info(f"  Avg GPT time/chunk: {avg_gpt_time:.2f}s")
    logging.info(f"  Parallelism speedup: {(total_gpt_time / parallel_time):.2f}x")
    logging.info(f"  Raw controls extracted: {len(raw_controls)}")
    logging.info(f"=" * 80)
    
    # Rest of pipeline is sequential (merge, validate, etc.)
    logging.info(f"[PARALLEL] Merging continuations...")
    merged_controls = merge_continuations(raw_controls)
    logging.info(f"[PARALLEL] Merged {len(raw_controls)} → {len(merged_controls)} controls")
    
    logging.info(f"[PARALLEL] Filtering by confidence...")
    high_confidence_controls, rejected_controls = filter_by_confidence(
        merged_controls,
        min_confidence=getattr(config, 'CONTROL_V4_MIN_CONFIDENCE', 0.0)
    )
    logging.info(f"[PARALLEL] Kept {len(high_confidence_controls)}, rejected {len(rejected_controls)}")
    
    # TSC criteria auto-filter
    high_confidence_controls, tsc_flagged = filter_tsc_criteria(high_confidence_controls)
    rejected_controls.extend(tsc_flagged)
    if tsc_flagged:
        logging.info(f"[PARALLEL] TSC filter: {len(tsc_flagged)} flagged, {len(high_confidence_controls)} retained")

    # Auditor test procedure / generic statement filter
    high_confidence_controls, quality_flagged = filter_auditor_and_generic(high_confidence_controls)
    rejected_controls.extend(quality_flagged)
    if quality_flagged:
        logging.info(f"[PARALLEL] Quality filter: {len(quality_flagged)} flagged, {len(high_confidence_controls)} retained")

    # Short-description confidence penalty (enumeration fragments)
    high_confidence_controls = apply_short_description_penalty(high_confidence_controls)

    # Missing control_id penalty (GPT ignores its own scoring guidance)
    high_confidence_controls = apply_missing_id_penalty(high_confidence_controls)

    # Subset-text detection (fragment re-extractions across chunks)
    high_confidence_controls = detect_subset_controls(high_confidence_controls)

    # NOTE: No re-filter here — penalties only lower confidence so controls
    # move from high-confidence to low-confidence bucket for user review.

    # Add text_lines context to controls for page number extraction
    for control in high_confidence_controls:
        control["text_lines"] = text_lines
    
    logging.info(f"[PARALLEL] Validating and cleaning...")
    validated_controls = validate_controls(high_confidence_controls)
    logging.info(f"[PARALLEL] Validated {len(validated_controls)} controls")
    
    # Augment page refs by scanning document text for control ID mentions
    validated_controls = augment_page_refs_from_text(validated_controls, text_lines)
    
    # Remove text_lines to avoid bloating the JSON output
    for control in validated_controls:
        control.pop("text_lines", None)
    
    # Optional assertion mapping (SOC1 only)
    if enable_assertion_mapping and report_type.upper() == "SOC1":
        logging.info(f"[PARALLEL] Mapping financial assertions...")
        try:
            validated_controls = batch_map_assertions(validated_controls)
            assertions_mapped = sum(1 for c in validated_controls if c.get("financial_assertions"))
            logging.info(f"[PARALLEL] Mapped assertions for {assertions_mapped} controls")
        except Exception as e:
            logging.error(f"[PARALLEL] Assertion mapping failed: {e}")
            logging.info("[PARALLEL] Continuing without assertions")
    
    # Complete progress tracking
    if progress_tracker:
        progress_tracker.complete_extractor("controls")
    
    # Calculate diagnostics
    elapsed = time.time() - start_time
    continuations_detected = sum(1 for c in raw_controls if c.get("continuation", False))
    avg_confidence = sum(c.get("control_confidence", 0) for c in validated_controls) / len(validated_controls) if validated_controls else 0
    deviations = sum(1 for c in validated_controls if c.get("has_deviation", False))
    assertions_mapped = sum(1 for c in validated_controls if c.get("financial_assertions"))
    
    diagnostics = {
        "extractor_version": "parallel_v2.1.0",
        "report_type": report_type,
        "parallel_workers": executor.max_workers,
        "assertion_mapping_enabled": enable_assertion_mapping,
        "total_chunks": len(chunks),
        "parallel_processing_time": round(parallel_time, 2),
        "parallelism_speedup": round(total_gpt_time / parallel_time, 2) if parallel_time > 0 else 1.0,
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
    logging.info("PARALLEL EXTRACTION DIAGNOSTICS")
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
        with open(control_json_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logging.info(f"{log_prefix}Saved {len(validated_controls)} controls to {control_json_path}")
        
        # Clean up checkpoint file (if checkpoint functionality is enabled)
        checkpoint_file = job_paths.get('checkpoint') if job_paths else None
        if checkpoint_file and os.path.exists(checkpoint_file):
            try:
                os.remove(checkpoint_file)
                logging.info("[PARALLEL] Checkpoint file removed")
            except Exception as e:
                logging.warning(f"[PARALLEL] Failed to remove checkpoint: {e}")
    except Exception as e:
        logging.error(f"[PARALLEL] Failed to save results: {e}", exc_info=True)
        raise
    
    return output


# ============================================================================
# FRAMEWORK MAPPING BATCH - Separate Phase with Parallel Execution
# ============================================================================

def map_controls_to_frameworks_batch(
    controls: List[Dict[str, Any]],
    available_frameworks: Dict[str, Dict[str, Any]],
    executor: Optional[Any] = None,
    progress_tracker: Optional[Any] = None,
    job_id: Optional[str] = None,
    redis_client: Optional[Any] = None,
    logger: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Map controls to frameworks in batch with parallel execution and checkpointing.
    
    This function is designed to be called separately after control extraction,
    allowing framework mapping to be a visible, resumable phase in the pipeline.
    
    Args:
        controls: List of extracted controls to map
        available_frameworks: Dict from get_available_frameworks()
        executor: IntelligentTaskExecutor for parallel mapping
        progress_tracker: ProgressTracker instance
        job_id: Job ID for Redis progress updates
        redis_client: Redis client for state updates
        logger: Logger instance
        
    Returns:
        List of controls with framework_mappings added
    """
    if not logger:
        logger = logging.getLogger(__name__)
    
    if not controls:
        logger.warning("[FRAMEWORK_MAPPING] No controls provided for mapping")
        return controls
    
    logger.info(f"[FRAMEWORK_MAPPING] Starting batch framework mapping for {len(controls)} controls")
    logger.info(f"[FRAMEWORK_MAPPING] Available frameworks: {list(available_frameworks.keys())}")
    
    # NOTE: Checkpoint feature disabled as config.CONTROL_JSON_PATH no longer exists
    # Job-based paths are now used instead. Checkpointing can be re-enabled in future update.
    checkpoint_path = None
    mapped_control_ids = set()
    
    # Checkpoint loading disabled
    # try:
    #     if checkpoint_path and os.path.exists(checkpoint_path):
    #         with open(checkpoint_path, 'r', encoding='utf-8') as f:
    #             checkpoint_data = json.load(f)
    #         mapped_control_ids = set(checkpoint_data.get('mapped_control_ids', []))
    #         logger.info(f"[FRAMEWORK_MAPPING] Resumed from checkpoint: {len(mapped_control_ids)} controls already mapped")
    # except Exception as e:
    #     logger.warning(f"[FRAMEWORK_MAPPING] Could not load checkpoint: {e}")
    
    # Get batch size from config
    batch_size = getattr(config, 'CONTROL_FRAMEWORK_MAPPING_BATCH_SIZE', 5)
    logger.info(f"[FRAMEWORK_MAPPING] Using batch size: {batch_size}")
    
    # Check if batched mode is enabled (v2.2.0 optimization)
    use_batched_mode = getattr(config, 'BATCH_ALL_FRAMEWORKS_IN_ONE_CALL', True)
    framework_model = getattr(config, 'FRAMEWORK_MAPPING_MODEL', 'gpt-4o-mini')
    logger.info(f"[FRAMEWORK_MAPPING] Batched mode: {use_batched_mode}, Model: {framework_model}")
    
    # Import framework functions
    from ..frameworks import (
        map_control_to_frameworks_dynamic,
        map_control_to_all_frameworks_batched,
        extract_mapping_fields_for_db
    )
    
    # Thread-safe counter for progress
    import threading
    progress_lock = threading.Lock()
    controls_mapped = len(mapped_control_ids)
    
    def map_single_control(control: Dict[str, Any]) -> Dict[str, Any]:
        """Map a single control to frameworks."""
        nonlocal controls_mapped
        
        control_id = control.get("control_id", "UNKNOWN")
        
        # Skip if already mapped in checkpoint
        if control_id in mapped_control_ids:
            logger.debug(f"[{control_id}] Already mapped (from checkpoint)")
            return control
        
        try:
            control_desc = control.get("control_desc", "") or control.get("description", "")
            has_deviation = control.get("has_deviation", False)
            deviation_desc = control.get("deviation_desc")
            
            if not control_desc:
                logger.warning(f"[{control_id}] No description available for framework mapping")
                # Add empty framework fields
                control["framework_mappings"] = {}
                control["primary_framework"] = None
                control["primary_criterion_id"] = None
                control["primary_criterion_id_normalized"] = None
                control["primary_criterion_id_original"] = None
                control["primary_confidence"] = 0.0
                return control
            
            # Map control to all available frameworks
            # Use batched mapper if enabled (v2.2.0 - 6-7x speedup)
            if use_batched_mode:
                mapping_result = map_control_to_all_frameworks_batched(
                    control_desc=control_desc,
                    control_id=control_id,
                    available_frameworks=available_frameworks,
                    has_deviation=has_deviation,
                    deviation_desc=deviation_desc,
                    top_k=5
                )
            else:
                # Fallback to sequential mapping (legacy mode)
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
            
            # Normalize the criterion ID
            original_criterion_id = db_fields["primary_criterion_id"]
            normalized_criterion_id = normalize_objective_id(original_criterion_id) if original_criterion_id else None
            
            # Add to control dict
            control["framework_mappings"] = db_fields["framework_mappings"]
            control["primary_framework"] = db_fields["primary_framework"]
            control["primary_criterion_id"] = original_criterion_id
            control["primary_criterion_id_normalized"] = normalized_criterion_id
            control["primary_criterion_id_original"] = original_criterion_id
            control["primary_confidence"] = db_fields["primary_confidence"]
            
            logger.info(f"[{control_id}] Mapped to {len(db_fields['framework_mappings'])} frameworks, primary: {db_fields['primary_framework']}")
            
            # Update progress counter
            with progress_lock:
                controls_mapped += 1
                
                # Update job state every 10 controls
                if job_id and redis_client and controls_mapped % 10 == 0:
                    try:
                        controls_mapped_percent = int((controls_mapped / len(controls)) * 100)
                        progress_val = 50 + int(controls_mapped_percent * 0.20)
                        from ..job_state import job_hmset
                        job_hmset(job_id, {
                            'controls_mapped_count': controls_mapped,
                            'controls_mapped_percent': controls_mapped_percent,
                            'progress': progress_val,
                            'status': f"Mapping {controls_mapped}/{len(controls)} controls to frameworks ({controls_mapped_percent}%)..."
                        }, redis_client)
                        logger.info(f"[PROGRESS] Framework mapping: {controls_mapped}/{len(controls)} ({controls_mapped_percent}%) - Overall: {progress_val}%")
                    except Exception as progress_err:
                        logger.warning(f"Could not update progress: {progress_err}")
                
                # Checkpoint writing disabled (checkpoint_path = None)
                # if checkpoint_path and controls_mapped % 10 == 0:
                #     try:
                #         mapped_control_ids.add(control_id)
                #         checkpoint_data = {
                #             'timestamp': time.time(),
                #             'mapped_control_ids': list(mapped_control_ids),
                #             'controls_mapped': controls_mapped,
                #             'total_controls': len(controls)
                #         }
                #         with open(checkpoint_path, 'w', encoding='utf-8') as f:
                #             json.dump(checkpoint_data, f, indent=2)
                #         logger.info(f"[CHECKPOINT] {controls_mapped}/{len(controls)} controls mapped")
                #     except Exception as checkpoint_err:
                #         logger.warning(f"Could not write checkpoint: {checkpoint_err}")
            
            return control
            
        except Exception as e:
            logger.error(f"[{control_id}] Framework mapping failed: {e}", exc_info=True)
            # Add empty framework fields on error - continue with warnings
            control["framework_mappings"] = {}
            control["primary_framework"] = None
            control["primary_criterion_id"] = None
            control["primary_criterion_id_normalized"] = None
            control["primary_criterion_id_original"] = None
            control["primary_confidence"] = 0.0
            return control
    
    # Execute mapping in parallel if executor provided
    if executor:
        logger.info(f"[FRAMEWORK_MAPPING] Using parallel execution with batch size {batch_size}")
        try:
            from ..scan_threading import TaskPriority
            mapped_controls = list(executor.map(
                map_single_control,
                controls,
                priority=TaskPriority.MEDIUM,
                timeout=600,
                return_exceptions=False
            ))
            
            # Filter out None values from timeouts/failures and match with original controls
            if None in mapped_controls:
                logger.warning(f"[FRAMEWORK_MAPPING] Found {mapped_controls.count(None)} failed/timed out tasks, retrying sequentially")
                for i, result in enumerate(mapped_controls):
                    if result is None:
                        logger.info(f"[FRAMEWORK_MAPPING] Retrying control {i+1}/{len(controls)}")
                        mapped_controls[i] = map_single_control(controls[i])
            
            controls = mapped_controls
        except Exception as e:
            logger.error(f"[FRAMEWORK_MAPPING] Parallel execution failed: {e}", exc_info=True)
            logger.warning("[FRAMEWORK_MAPPING] Falling back to sequential mapping")
            # Fall through to sequential mapping
            for control in controls:
                map_single_control(control)
    else:
        # Sequential mapping
        logger.info("[FRAMEWORK_MAPPING] Using sequential execution")
        for control in controls:
            map_single_control(control)
    
    # Clean up checkpoint on success
    try:
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)
            logger.info("[FRAMEWORK_MAPPING] Checkpoint file removed after successful completion")
    except Exception as e:
        logger.warning(f"[FRAMEWORK_MAPPING] Could not remove checkpoint: {e}")
    
    # Filter out any remaining None values (shouldn't happen but safety check)
    controls = [c for c in controls if c is not None]
    
    frameworks_mapped = sum(1 for c in controls if c and c.get("framework_mappings"))
    logger.info(f"[FRAMEWORK_MAPPING] Batch mapping complete: {frameworks_mapped}/{len(controls)} controls mapped")
    
    # Final progress update to 100%
    if job_id and redis_client:
        try:
            from ..job_state import job_hmset
            job_hmset(job_id, {
                'controls_mapped_count': len(controls),
                'controls_mapped_percent': 100,
                'total_controls': len(controls),
                'status': f"Framework mapping complete: {frameworks_mapped}/{len(controls)} controls mapped"
            }, redis_client)
            logger.info(f"[PROGRESS] Framework mapping final update: {frameworks_mapped}/{len(controls)} (100%)")
        except Exception as final_err:
            logger.warning(f"Could not update final progress: {final_err}")
    
    return controls
