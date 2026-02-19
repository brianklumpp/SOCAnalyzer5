"""Control Objective Extractor

Extracts control objectives from SOC reports using multi-factor confidence scoring.
Supports varied formats: explicit headings, numbered lists, table structures, and GPT inference.

Features:
- Chunk-based extraction with token-aware overlap
- Multi-factor confidence: keyword, distance, GPT opinion, alignment, format
- Deduplication across overlapping chunks
- Many-to-many control-objective mapping
- Objective-enhanced framework mapping

Usage:
    from .objective_extractor import extract_objectives
    
    objectives = extract_objectives(
        extracted_text="...",
        scan_id=123,
        db_session=session
    )
"""

import logging
import json
import re
import hashlib
from typing import List, Dict, Any, Optional, Tuple, List as ListType
from datetime import datetime
from sqlalchemy.orm import Session
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import config
from ..gpt_client import gpt_extract
from ..models import ControlObjective, ControlObjectiveMapping, Control, MappingFeedback
from ..utils.objective_id_normalizer import normalize_objective_id
from ..services.redis_service import get_redis_client
from ..job_state import job_hmset

logger = logging.getLogger(__name__)

# GPT model configuration
# Use dedicated CONTROL_OBJECTIVES_MODEL (typically gpt-5 for high accuracy)
OBJECTIVE_MODEL = config.CONTROL_OBJECTIVES_MODEL
OBJECTIVE_PATTERN_MODEL = config.OBJECTIVE_PATTERN_LEARNER_MODEL
# Use faster/cheaper model for alignment scoring (simple matching task, 100s-1000s of calls)
OBJECTIVE_ALIGNMENT_MODEL = config.OBJECTIVE_ALIGNMENT_MODEL


def _clean_newlines_from_dict(obj):
    """Recursively strip newlines from all string values in a dict/list structure."""
    if isinstance(obj, dict):
        return {k: _clean_newlines_from_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_newlines_from_dict(item) for item in obj]
    elif isinstance(obj, str):
        # Strip newlines, carriage returns, and tabs from all strings
        return obj.replace('\n', '').replace('\r', '').replace('\t', ' ').strip()
    else:
        return obj


def _parse_json_response(response: str, context: str) -> Optional[Dict[str, Any]]:
    """Parse JSON from GPT response, handling common wrappers like code fences."""
    raw = (response or "").strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
        # CRITICAL FIX: Strip newlines from ALL string values immediately after parsing
        return _clean_newlines_from_dict(parsed)
    except json.JSONDecodeError:
        cleaned = raw

        # Strip Markdown code fences if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        # Extract JSON object from surrounding text
        if "{" in cleaned and "}" in cleaned:
            cleaned = cleaned[cleaned.find("{"):cleaned.rfind("}") + 1]

        # Remove JS-style comments if present
        cleaned = re.sub(r"//.*", "", cleaned)
        
        # JSON repair: Fix common GPT formatting errors
        # 1. Remove trailing commas before closing brackets/braces
        cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)
        # 2. Fix missing commas between array elements (risky, be conservative)
        # 3. Remove duplicate commas
        cleaned = re.sub(r",+", ",", cleaned)
        # 4. Fix unescaped newlines in strings (preserve intentional \n)
        # 5. Remove trailing/leading whitespace
        cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
            # CRITICAL FIX: Strip newlines from ALL string values immediately after parsing
            return _clean_newlines_from_dict(parsed)
        except Exception as e:
            logger.error(f"{context}: Failed to parse GPT response: {e}")
            logger.debug(f"{context}: Cleaned response was: {cleaned[:200]}...")
            return None


def count_tokens(text: str) -> int:
    """Approximate token count (4 chars ≈ 1 token)"""
    return len(text) // 4


def chunk_text_by_tokens(text: str, tokens_per_chunk: int, overlap_tokens: int) -> List[Tuple[str, int, int]]:
    """
    Split text into overlapping chunks by approximate token count.
    
    Args:
        text: Full text to chunk
        tokens_per_chunk: Target tokens per chunk
        overlap_tokens: Token overlap between chunks
        
    Returns:
        List of (chunk_text, start_char, end_char) tuples
    """
    lines = text.split('\n')
    chunks = []
    
    current_chunk_lines = []
    current_tokens = 0
    chunk_start_line = 0
    
    for i, line in enumerate(lines):
        line_tokens = count_tokens(line)
        
        # If adding this line exceeds chunk size and we have content, save chunk
        if current_tokens + line_tokens > tokens_per_chunk and current_chunk_lines:
            chunk_text = '\n'.join(current_chunk_lines)
            chunks.append((chunk_text, chunk_start_line, i))
            
            # Calculate overlap: keep last N lines for context
            overlap_line_count = 0
            overlap_token_count = 0
            for j in range(len(current_chunk_lines) - 1, -1, -1):
                line_token_count = count_tokens(current_chunk_lines[j])
                if overlap_token_count + line_token_count > overlap_tokens:
                    break
                overlap_line_count += 1
                overlap_token_count += line_token_count
            
            # Start new chunk with overlap
            if overlap_line_count > 0:
                current_chunk_lines = current_chunk_lines[-overlap_line_count:]
                current_tokens = overlap_token_count
                chunk_start_line = i - overlap_line_count
            else:
                current_chunk_lines = []
                current_tokens = 0
                chunk_start_line = i
        
        current_chunk_lines.append(line)
        current_tokens += line_tokens
    
    # Add final chunk if not empty
    if current_chunk_lines:
        chunk_text = '\n'.join(current_chunk_lines)
        chunks.append((chunk_text, chunk_start_line, len(lines)))
    
    return chunks


def calculate_distance_from_keywords(text: str, line_number: int) -> int:
    """
    Calculate minimum line distance from objective section keywords.
    
    Args:
        text: Full extracted text
        line_number: Line number of the objective
        
    Returns:
        Minimum distance in lines from any objective keyword
    """
    lines = text.split('\n')
    keyword_lines = []
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in config.OBJECTIVE_SECTION_KEYWORDS):
            keyword_lines.append(i)
    
    if not keyword_lines:
        return config.OBJECTIVE_MAX_DISTANCE_FROM_KEYWORDS
    
    # Find minimum distance
    min_distance = min(abs(line_number - kw_line) for kw_line in keyword_lines)
    return min(min_distance, config.OBJECTIVE_MAX_DISTANCE_FROM_KEYWORDS)


def find_objective_line_in_chunk(
    chunk_text: str,
    objective_id: Optional[str],
    objective_text: Optional[str],
    gpt_line_ref: Optional[int],
) -> Optional[int]:
    """
    Find the chunk-relative line number where an objective actually appears.

    GPT is unreliable at counting lines in plain text, so this function searches
    the chunk text for the objective_id or description to find the real position.

    Strategy (tried in order):
      1. Search for objective_id (e.g. "CC1.1") in chunk lines.
      2. Search for the first ~6 words of objective_text.
      3. Return GPT's line_ref (may be inaccurate but better than nothing).

    Args:
        chunk_text:      The plain-text chunk sent to GPT.
        objective_id:    GPT-extracted objective identifier (e.g. "CC1.1", may be None).
        objective_text:  GPT-extracted objective text (may be None).
        gpt_line_ref:    GPT-reported chunk-relative line number (may be None).

    Returns:
        Chunk-relative line number (0-based), or None if nothing found.
    """
    chunk_lines = chunk_text.split('\n')

    # --- Strategy 1: search by objective_id ---
    if objective_id:
        oid_clean = objective_id.strip()
        # Exact match first (case-insensitive)
        for i, line in enumerate(chunk_lines):
            if oid_clean.lower() in line.lower():
                logger.info(
                    f"[OBJ_LINEREF] Strategy 1: Matched objective_id '{oid_clean}' at chunk line {i}"
                )
                return i

        # Try collapsing whitespace (handles line-break splits like "CC1.\n1")
        oid_collapsed = re.sub(r'\s+', '', oid_clean).lower()
        for i in range(len(chunk_lines)):
            combined = chunk_lines[i]
            if i + 1 < len(chunk_lines):
                combined += chunk_lines[i + 1]
            combined_collapsed = re.sub(r'\s+', '', combined).lower()
            if oid_collapsed in combined_collapsed:
                logger.info(
                    f"[OBJ_LINEREF] Strategy 1: Matched objective_id '{oid_clean}' (collapsed) at chunk line {i}"
                )
                return i

    # --- Strategy 2: search by first ~6 words of objective_text ---
    if objective_text and objective_text.strip():
        words = objective_text.strip().split()
        if words:
            for word_count in (6, 5, 4):
                if len(words) >= word_count:
                    snippet = ' '.join(words[:word_count]).lower()
                    for i, line in enumerate(chunk_lines):
                        line_norm = ' '.join(line.split()).lower()
                        if snippet in line_norm:
                            logger.info(
                                f"[OBJ_LINEREF] Strategy 2: Matched desc snippet ({word_count} words) at chunk line {i}"
                            )
                            return i

            # Cross-line search for description
            snippet = ' '.join(words[:6]).lower() if len(words) >= 6 else ' '.join(words).lower()
            for i in range(len(chunk_lines)):
                combined = chunk_lines[i]
                if i + 1 < len(chunk_lines):
                    combined += ' ' + chunk_lines[i + 1]
                combined_norm = ' '.join(combined.split()).lower()
                if snippet in combined_norm:
                    logger.info(
                        f"[OBJ_LINEREF] Strategy 2: Matched desc snippet (cross-line) at chunk line {i}"
                    )
                    return i

    # --- Strategy 3: fall back to GPT's line_ref ---
    if gpt_line_ref is not None:
        # Clamp to valid chunk range
        clamped = max(0, min(gpt_line_ref, len(chunk_lines) - 1))
        if clamped != gpt_line_ref:
            logger.warning(
                f"[OBJ_LINEREF] Strategy 3: Clamped GPT line_ref {gpt_line_ref} to {clamped} "
                f"(chunk has {len(chunk_lines)} lines)"
            )
        else:
            logger.info(
                f"[OBJ_LINEREF] Strategy 3: Using GPT line_ref {gpt_line_ref} (no text match found)"
            )
        return clamped

    logger.warning("[OBJ_LINEREF] No strategy matched, returning None")
    return None


def extract_objectives_from_chunk(chunk_text: str, chunk_index: int, scan_id: int, chunk_start_line: int = 0) -> List[Dict[str, Any]]:
    """
    Extract objectives from a single text chunk using GPT.
    
    Args:
        chunk_text: Text chunk to process
        chunk_index: Index of this chunk (for logging)
        scan_id: Scan ID for context
        chunk_start_line: Starting line number of this chunk in the original document (for line_ref adjustment)
        
    Returns:
        List of extracted objective dictionaries with line_ref adjusted to document coordinates
    """
    logger.info(f"[CHUNK_{chunk_index}] Starting extraction...")
    logger.info(f"[CHUNK_{chunk_index}] Text length: {len(chunk_text)} chars")
    logger.info(f"[CHUNK_{chunk_index}] Document start line: {chunk_start_line}")
    logger.info(f"[CHUNK_{chunk_index}] First 150 chars: {chunk_text[:150]}")
    
    prompt = config.OBJECTIVE_EXTRACTION_PROMPT.format(
        text_chunk=chunk_text,
        chunk_start_line=chunk_start_line
    )
    
    logger.info(f"[CHUNK_{chunk_index}] Calling GPT with model: {OBJECTIVE_MODEL}")
    logger.info(f"[CHUNK_{chunk_index}] Prompt length: {len(prompt)} chars")
    
    try:
        response = gpt_extract(
            prompt=prompt,
            extractor_name="objective_extractor",
            override_model=OBJECTIVE_MODEL
        )
        
        logger.info(f"[CHUNK_{chunk_index}] GPT response received, length: {len(response)} chars")
        logger.info(f"[CHUNK_{chunk_index}] Response preview: {response[:200]}")
        
        # Parse JSON response
        result = _parse_json_response(response, f"Chunk {chunk_index}")
        objectives = (result or {}).get('objectives', [])
        
        logger.info(f"[CHUNK_{chunk_index}] Parsed {len(objectives)} objectives from response")
        
        # HALLUCINATION GUARD: Discard objectives whose ID doesn't appear in chunk text.
        # GPT sometimes invents objectives from contextual clues (e.g. "trust services criteria")
        # when the actual objective ID (CC1.1, A1.2, etc.) is not present in the chunk at all.
        chunk_text_lower = chunk_text.lower()
        validated_objectives = []
        for obj in objectives:
            obj_id = (obj.get('objective_id') or '').strip()
            if obj_id:
                # Check if the objective_id appears anywhere in the chunk
                if obj_id.lower() in chunk_text_lower:
                    validated_objectives.append(obj)
                else:
                    # Also check collapsed whitespace (handles split IDs like "CC1.\n1")
                    collapsed_chunk = re.sub(r'\s+', '', chunk_text_lower)
                    collapsed_id = re.sub(r'\s+', '', obj_id.lower())
                    if collapsed_id in collapsed_chunk:
                        validated_objectives.append(obj)
                    else:
                        logger.warning(
                            f"[CHUNK_{chunk_index}] HALLUCINATION: Discarding '{obj_id}' — "
                            f"ID not found anywhere in chunk text ({len(chunk_text)} chars)"
                        )
            else:
                validated_objectives.append(obj)  # Keep objectives without ID (can't validate)
        
        if len(validated_objectives) < len(objectives):
            logger.info(
                f"[CHUNK_{chunk_index}] Hallucination guard: {len(objectives)} -> {len(validated_objectives)} objectives "
                f"(discarded {len(objectives) - len(validated_objectives)} hallucinated)"
            )
        objectives = validated_objectives
        
        # CRITICAL: Adjust line_ref from chunk-relative to document-relative coordinates
        # GPT is unreliable at line counting, so we text-search for the actual position
        for i, obj in enumerate(objectives):
            gpt_line = obj.get('line_ref')
            # Text-search for precise chunk-relative line number
            precise_line = find_objective_line_in_chunk(
                chunk_text,
                obj.get('objective_id'),
                obj.get('objective_text'),
                gpt_line,
            )
            if precise_line is not None:
                original_line_ref = gpt_line
                obj['line_ref'] = chunk_start_line + precise_line
                logger.info(
                    f"[CHUNK_{chunk_index}] Objective {i}: {obj.get('objective_id', 'NO_ID')}, "
                    f"line_ref: GPT={original_line_ref} -> text_search={precise_line} -> doc={obj['line_ref']}"
                )
            elif gpt_line is not None:
                original_line_ref = gpt_line
                obj['line_ref'] = chunk_start_line + gpt_line
                logger.info(
                    f"[CHUNK_{chunk_index}] Objective {i}: {obj.get('objective_id', 'NO_ID')}, "
                    f"line_ref adjusted (GPT only): {original_line_ref} -> {obj['line_ref']}"
                )
            else:
                logger.info(f"[CHUNK_{chunk_index}] Objective {i}: {obj.get('objective_id', 'NO_ID')}, NO LINE_REF")
        
        logger.info(f"[CHUNK_{chunk_index}] ✓ Extraction complete: {len(objectives)} objectives")
        return objectives
        
    except Exception as e:
        logger.error(f"[CHUNK_{chunk_index}] ✗ Extraction FAILED: {e}", exc_info=True)
        return []


def deduplicate_objectives(objectives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate objectives extracted from overlapping chunks.
    OPTIMIZED: Group by ID first, only use GPT for remaining fuzzy duplicates
    
    Args:
        objectives: List of objective dictionaries
        
    Returns:
        Deduplicated list with best versions preserved
    """
    if len(objectives) <= 1:
        return objectives
    
    # Filter out None values that may have been added to the list
    objectives = [obj for obj in objectives if obj is not None and isinstance(obj, dict)]
    
    if len(objectives) <= 1:
        return objectives
    
    logger.info(f"[DEDUP] Starting fast deduplication of {len(objectives)} objectives")
    
    # OPTIMIZATION 1: Group by objective_id (most duplicates have same ID)
    by_id = {}
    no_id = []
    
    for obj in objectives:
        obj_id = obj.get('objective_id')
        if obj_id:
            if obj_id not in by_id:
                by_id[obj_id] = []
            by_id[obj_id].append(obj)
        else:
            no_id.append(obj)
    
    # OPTIMIZATION 2: For each ID group, keep the one with highest confidence
    # BUT check if descriptions differ significantly (might be report error)
    deduplicated = []
    for obj_id, obj_list in by_id.items():
        if len(obj_list) == 1:
            deduplicated.append(obj_list[0])
        else:
            # Check if all descriptions are similar (likely chunk overlap duplicates)
            # Normalize whitespace before comparison — GPT returns varied spacing
            def _normalize_text(t: str) -> str:
                return ' '.join(t.strip().split()).lower()

            texts_raw = [obj.get('objective_text', '') for obj in obj_list]
            unique_texts = set(_normalize_text(t) for t in texts_raw)
            
            if len(unique_texts) == 1:
                # All identical (or whitespace-only differences) - pick best by confidence
                best = max(obj_list, key=lambda o: sum([
                    o.get('confidence_factors', {}).get('keyword_match', 0),
                    o.get('confidence_factors', {}).get('format_clarity', 0),
                    o.get('confidence_factors', {}).get('gpt_opinion', 0)
                ]))
                # Phase A: Union all line_refs and page_refs from duplicates
                all_lines = set()
                all_pages = set()
                for dup in obj_list:
                    lr = dup.get('line_ref')
                    if lr is not None:
                        all_lines.add(lr)
                    for lr2 in (dup.get('all_line_refs') or []):
                        all_lines.add(lr2)
                    for pr in (dup.get('page_refs') or []):
                        all_pages.add(pr)
                    for pr2 in (dup.get('all_page_refs') or []):
                        all_pages.add(pr2)
                if all_lines:
                    best['all_line_refs'] = sorted(all_lines)
                if all_pages:
                    best['all_page_refs'] = sorted(all_pages)
                deduplicated.append(best)
                logger.debug(f"[DEDUP] {obj_id}: merged {len(obj_list)} identical duplicates (preserved {len(all_lines)} line refs, {len(all_pages)} page refs)")
            else:
                # Different descriptions with same ID — group by normalized text,
                # keep best from EACH text variant (not all raw duplicates)
                text_groups: Dict[str, list] = {}
                for obj in obj_list:
                    norm = _normalize_text(obj.get('objective_text', ''))
                    text_groups.setdefault(norm, []).append(obj)
                
                logger.warning(
                    f"[DEDUP] {obj_id}: {len(obj_list)} objectives with {len(text_groups)} distinct descriptions — keeping best per variant"
                )
                for norm_text, group in text_groups.items():
                    best = max(group, key=lambda o: sum([
                        o.get('confidence_factors', {}).get('keyword_match', 0),
                        o.get('confidence_factors', {}).get('format_clarity', 0),
                        o.get('confidence_factors', {}).get('gpt_opinion', 0)
                    ]))
                    # Phase A: Union all line_refs and page_refs from this variant group
                    all_lines = set()
                    all_pages = set()
                    for dup in group:
                        lr = dup.get('line_ref')
                        if lr is not None:
                            all_lines.add(lr)
                        for lr2 in (dup.get('all_line_refs') or []):
                            all_lines.add(lr2)
                        for pr in (dup.get('page_refs') or []):
                            all_pages.add(pr)
                        for pr2 in (dup.get('all_page_refs') or []):
                            all_pages.add(pr2)
                    if all_lines:
                        best['all_line_refs'] = sorted(all_lines)
                    if all_pages:
                        best['all_page_refs'] = sorted(all_pages)
                    deduplicated.append(best)
                    text_preview = best.get('objective_text', '')[:80]
                    logger.info(f"  [DEDUP] {obj_id} variant ({len(group)} dupes -> 1): {text_preview}...")
    
    # OPTIMIZATION 3: For objectives without IDs, use GPT only if there are many
    if len(no_id) > 10:
        logger.info(f"[DEDUP] Using GPT for {len(no_id)} objectives without IDs")
        objectives_json = json.dumps(no_id, indent=2)
        prompt = config.OBJECTIVE_DEDUPLICATION_PROMPT.format(objective_list=objectives_json)
        
        try:
            response = gpt_extract(
                prompt=prompt,
                extractor_name="objective_deduplication",
                override_model=OBJECTIVE_MODEL
            )
            
            result = _parse_json_response(response, "Objective deduplication")
            gpt_deduplicated = (result or {}).get('deduplicated') if result else None

            if gpt_deduplicated:
                deduplicated.extend(gpt_deduplicated)
            else:
                logger.warning("[DEDUP] GPT deduplication failed, keeping all no-ID objectives")
                deduplicated.extend(no_id)
        except Exception as e:
            logger.error(f"[DEDUP] GPT deduplication failed: {e}")
            deduplicated.extend(no_id)
    else:
        # Few objectives without IDs - just keep them all
        deduplicated.extend(no_id)
    
    logger.info(f"[DEDUP] Reduced {len(objectives)} → {len(deduplicated)} objectives (saved {len(objectives) - len(deduplicated)} duplicates)")
    
    # Preserve original line_refs
    objective_line_refs = {
        obj.get('objective_id'): obj.get('line_ref')
        for obj in objectives
        if obj.get('objective_id') and obj.get('line_ref') is not None
    }
    
    for dedup_obj in deduplicated:
        obj_id = dedup_obj.get('objective_id')
        if obj_id and obj_id in objective_line_refs:
            original_line_ref = objective_line_refs[obj_id]
            dedup_line_ref = dedup_obj.get('line_ref')
            
            # Only restore if GPT changed it (GPT returns chunk-relative, we had document-relative)
            if dedup_line_ref != original_line_ref:
                logger.info(f"[DEDUP_FIX] Restoring line_ref for {obj_id}: {dedup_line_ref} -> {original_line_ref}")
                dedup_obj['line_ref'] = original_line_ref
    
    return deduplicated


def _get_control_confidence(control: Control) -> float:
    if control.final_confidence is not None:
        return float(control.final_confidence or 0.0)
    if control.control_confidence is not None:
        return float(control.control_confidence or 0.0)
    return 0.0


def _select_high_conf_controls(
    controls: List[Control],
    threshold: float,
    min_count: int
) -> List[Control]:
    if not controls:
        return []
    sorted_controls = sorted(
        controls,
        key=lambda c: (
            c.control_seq if c.control_seq is not None else 1_000_000,
            c.id
        )
    )
    # No confidence filtering - return all controls
    return sorted_controls[:max(0, min_count)] if min_count > 0 else sorted_controls


def _score_objectives_for_selection(
    objectives: List[Dict[str, Any]],
    full_text: str
) -> List[Dict[str, Any]]:
    scored = []
    lines = full_text.split('\n') if full_text else []
    for index, obj in enumerate(objectives):
        objective_text = obj.get('objective_text', '')
        line_ref = None
        if objective_text:
            search_key = objective_text[:50]
            for i, line in enumerate(lines):
                if search_key in line:
                    line_ref = i + 1
                    break

        final_confidence, confidence_calc = calculate_multi_factor_confidence(
            obj, full_text, line_ref
        )
        scored.append({
            **obj,
            "_line_ref": line_ref,
            "_final_confidence": final_confidence,
            "_confidence_calc": confidence_calc,
            "_index": index
        })
    return scored


def _select_high_conf_objectives(
    scored_objectives: List[Dict[str, Any]],
    threshold: float,
    min_count: int
) -> List[Dict[str, Any]]:
    if not scored_objectives:
        return []
    sorted_scored = sorted(
        scored_objectives,
        key=lambda obj: (
            obj.get("_line_ref") if obj.get("_line_ref") is not None else 1_000_000,
            obj.get("_index", 0)
        )
    )
    # No confidence filtering - return all objectives
    return sorted_scored[:max(0, min_count)] if min_count > 0 else sorted_scored


def _learn_objective_patterns(
    objective_samples: List[Dict[str, Any]],
    control_samples: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    prompt = config.OBJECTIVE_PATTERN_LEARNER_PROMPT.format(
        objective_samples=json.dumps(objective_samples, indent=2, ensure_ascii=False),
        control_samples=json.dumps(control_samples, indent=2, ensure_ascii=False)
    )
    try:
        response = gpt_extract(
            prompt=prompt,
            extractor_name="objective_pattern_learner",
            override_model=OBJECTIVE_PATTERN_MODEL
        )
        return _parse_json_response(response, "Objective pattern learner")
    except Exception as e:
        logger.error(f"Objective pattern learning failed: {e}")
        return None


def _identify_missing_sequences(objectives: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Identify missing objective sequences at both top-level and sub-level.
    
    Args:
        objectives: List of objective dictionaries with objective_id
        
    Returns:
        Dictionary with missing_top_level (e.g., ["CC1", "CC2"]) and 
        missing_sub_level (e.g., {"CC6": [1, 3, 4]}) ranges
    """
    if not objectives:
        return {"missing_top_level": [], "missing_sub_level": {}, "found_ranges": {}}
    
    # Parse objective IDs into (prefix, major, minor) tuples
    parsed_ids = []
    for obj in objectives:
        obj_id = obj.get("objective_id")
        if not obj_id:
            continue
        
        # Match patterns like CC6.2, A1.3, C1.1, etc.
        match = re.match(r"([A-Z]+)(\d+)\.(\d+)", obj_id)
        if match:
            prefix, major, minor = match.groups()
            parsed_ids.append((prefix, int(major), int(minor), obj_id))
    
    if not parsed_ids:
        return {"missing_top_level": [], "missing_sub_level": {}, "found_ranges": {}}
    
    # Group by prefix (e.g., CC, A, C)
    by_prefix = defaultdict(lambda: defaultdict(list))
    
    for prefix, major, minor, obj_id in parsed_ids:
        by_prefix[prefix][major].append(minor)
    
    # Identify missing sequences
    missing_top_level = []
    missing_sub_level = {}
    found_ranges = {}
    
    for prefix, major_dict in by_prefix.items():
        # Top-level: Check for gaps in major version (e.g., CC1, CC2, ..., CC9)
        major_versions = sorted(major_dict.keys())
        if len(major_versions) > 1:
            min_major = min(major_versions)
            max_major = max(major_versions)
            
            for major in range(min_major, max_major + 1):
                if major not in major_versions:
                    missing_top_level.append(f"{prefix}{major}")
            
            found_ranges[prefix] = (min_major, max_major)
        
        # Sub-level: Check for gaps in minor version (e.g., CC6.1, CC6.2, CC6.3)
        for major, minors in major_dict.items():
            if len(minors) > 1:
                sorted_minors = sorted(minors)
                min_minor = min(sorted_minors)
                max_minor = max(sorted_minors)
                
                missing_minors = []
                for minor in range(min_minor, max_minor + 1):
                    if minor not in sorted_minors:
                        missing_minors.append(minor)
                
                if missing_minors:
                    key = f"{prefix}{major}"
                    missing_sub_level[key] = missing_minors
    
    return {
        "missing_top_level": sorted(missing_top_level),
        "missing_sub_level": missing_sub_level,
        "found_ranges": found_ranges
    }


def _can_rescan_with_patterns(patterns: Optional[Dict[str, Any]]) -> bool:
    if not patterns:
        return False
    id_pattern = patterns.get("id_pattern") or {}
    text_cues = patterns.get("text_cues") or []
    return bool(text_cues) or bool(id_pattern.get("present"))


def _rescan_objectives_with_patterns(
    chunks: List[Tuple[str, int, int]],
    patterns: Dict[str, Any],
    existing_objectives: List[Dict[str, Any]],
    start_line: int = 0
) -> List[Dict[str, Any]]:
    if not chunks:
        return []

    existing_payload = json.dumps(existing_objectives, indent=2, ensure_ascii=False)
    patterns_payload = json.dumps(patterns, indent=2, ensure_ascii=False)
    rescanned = []

    for i, (chunk_text, chunk_start_line, chunk_end_line) in enumerate(chunks):
        # Calculate document-relative chunk start line
        document_chunk_start = start_line + chunk_start_line
        
        prompt = config.OBJECTIVE_PATTERN_RESCAN_PROMPT.format(
            patterns=patterns_payload,
            existing_objectives=existing_payload,
            text_chunk=chunk_text,
            chunk_start_line=document_chunk_start
        )
        try:
            response = gpt_extract(
                prompt=prompt,
                extractor_name="objective_pattern_rescan",
                override_model=OBJECTIVE_PATTERN_MODEL
            )
            result = _parse_json_response(response, f"Objective pattern rescan chunk {i}")
            objectives = (result or {}).get("objectives", [])
            
            # HALLUCINATION GUARD (same as initial extraction)
            chunk_text_lower = chunk_text.lower()
            validated = []
            for obj in objectives:
                obj_id = (obj.get('objective_id') or '').strip()
                if obj_id:
                    if obj_id.lower() in chunk_text_lower:
                        validated.append(obj)
                    else:
                        collapsed_chunk = re.sub(r'\s+', '', chunk_text_lower)
                        collapsed_id = re.sub(r'\s+', '', obj_id.lower())
                        if collapsed_id in collapsed_chunk:
                            validated.append(obj)
                        else:
                            logger.warning(
                                f"[PATTERN_RESCAN] HALLUCINATION: Discarding '{obj_id}' — "
                                f"ID not found in chunk {i} text"
                            )
                else:
                    validated.append(obj)
            objectives = validated
            
            for obj in objectives:
                # Text-search for precise line_ref (same fix as initial extraction)
                gpt_line = obj.get('line_ref')
                precise_line = find_objective_line_in_chunk(
                    chunk_text,
                    obj.get('objective_id'),
                    obj.get('objective_text'),
                    gpt_line,
                )
                if precise_line is not None:
                    obj['line_ref'] = document_chunk_start + precise_line
                    logger.info(
                        f"[PATTERN_RESCAN] Objective {obj.get('objective_id', 'NO_ID')}: "
                        f"line_ref GPT={gpt_line} -> text_search={precise_line} -> doc={obj['line_ref']}"
                    )
                elif gpt_line is not None:
                    obj['line_ref'] = document_chunk_start + gpt_line
                
                pattern_alignment = bool(obj.get("pattern_alignment"))
                obj.setdefault("extraction_method", "pattern_rescan_aligned" if pattern_alignment else "pattern_rescan")
                obj["pattern_alignment"] = pattern_alignment
            rescanned.extend(objectives)
        except Exception as e:
            logger.error(f"Objective pattern rescan failed for chunk {i}: {e}")

    return rescanned


def calculate_multi_factor_confidence(
    objective: Dict[str, Any],
    extracted_text: str,
    line_ref: Optional[int] = None,
    all_objectives: Optional[List[Dict[str, Any]]] = None
) -> Tuple[float, str, Dict[str, Any]]:
    """
    Calculate weighted multi-factor confidence score for an objective.
    
    Initial scoring uses 3 factors (alignment is NOT available yet — control mapping
    happens after scoring):
    - keyword_match (40%): TSC/COSO keyword presence in objective text
    - gpt_opinion (25%): GPT's confidence assessment (zeroed if reasoning is empty)
    - format_clarity (35%): Format clarity score (heading, numbering, table structure)
    
    NOTE: distance_confidence is DEPRECATED — it measured proximity to section headers
    like "control objective" which is not a meaningful signal. The keyword_confidence
    factor already measures TSC/COSO keyword alignment in the objective text itself.
    
    Args:
        objective: Objective dictionary with confidence_factors
        extracted_text: Full extracted text (unused, kept for API compat)
        line_ref: Line reference (unused in scoring, stored for page ref lookup)
        all_objectives: All objectives in scan for ID pattern analysis
        
    Returns:
        (final_confidence, confidence_calc, metadata) tuple
    """
    factors = objective.get('confidence_factors', {})
    weights = config.OBJECTIVE_CONFIDENCE_WEIGHTS
    
    # Extract individual factor scores (default to 0.0 if missing)
    keyword_score = factors.get('keyword_match', 0.0)
    gpt_score = factors.get('gpt_opinion', 0.0)
    format_score = factors.get('format_clarity', 0.0)
    
    # CRITICAL FIX: Zero out GPT opinion score when reasoning is empty/stub
    # GPT sometimes returns a numeric confidence without meaningful reasoning.
    # Without this guard, objectives get inflated scores from unsupported GPT opinions.
    gpt_reasoning = objective.get('reasoning', '')
    empty_reasoning_stubs = {'', 'Gap extraction:', 'Gap extraction', 'N/A', 'None'}
    if not gpt_reasoning or gpt_reasoning.strip() in empty_reasoning_stubs:
        if gpt_score > 0.0:
            logger.info(
                f"[CONFIDENCE] Zeroing GPT opinion ({gpt_score:.2f}) for "
                f"'{objective.get('objective_id', 'UNKNOWN')}' - empty/stub reasoning: "
                f"'{(gpt_reasoning or '').strip()[:50]}'"
            )
            gpt_score = 0.0
    
    # 3-factor initial scoring (no alignment — mapping hasn't happened yet)
    final_confidence = (
        keyword_score * weights['keyword'] +
        gpt_score * weights['gpt_opinion'] +
        format_score * weights['format']
    )
    
    # Build metadata for audit trail
    metadata = {
        "method": "3-factor-initial",
        "calculated_at": datetime.utcnow().isoformat(),
        "factor_scores": {
            "keyword_confidence": keyword_score,
            "gpt_confidence": gpt_score,
            "format_confidence": format_score
        },
        "weighted_contributions": {
            "keyword_contribution": keyword_score * weights['keyword'],
            "gpt_contribution": gpt_score * weights['gpt_opinion'],
            "format_contribution": format_score * weights['format']
        },
        "weights_used": weights.copy(),
        "adjustments": []
    }
    
    # Enhanced ID penalty logic with pattern detection
    objective_id_raw = objective.get('objective_id', '')
    objective_id = objective_id_raw.strip() if objective_id_raw else ''
    id_penalties = _calculate_id_penalties(objective_id, all_objectives)
    
    for penalty_type, penalty_value, reason in id_penalties:
        final_confidence = max(0.0, final_confidence * (1.0 - penalty_value))
        metadata["adjustments"].append({
            "type": penalty_type,
            "penalty_multiplier": penalty_value,
            "reason": reason,
            "applied_at": datetime.utcnow().isoformat()
        })
    
    # Create human-readable breakdown
    confidence_calc = (
        f"keyword={keyword_score:.2f}*{weights['keyword']:.2f} + "
        f"gpt={gpt_score:.2f}*{weights['gpt_opinion']:.2f} + "
        f"format={format_score:.2f}*{weights['format']:.2f}"
    )
    
    for _, penalty_value, reason in id_penalties:
        confidence_calc += f" * {1.0-penalty_value:.2f} ({reason})"
    
    confidence_calc += f" = {final_confidence:.3f}"
    
    return final_confidence, confidence_calc, metadata


def _calculate_id_penalties(
    objective_id: str,
    all_objectives: Optional[List[Dict[str, Any]]]
) -> List[Tuple[str, float, str]]:
    """
    Calculate ID-related penalties for confidence scoring.
    
    Returns list of (penalty_type, penalty_value, reason) tuples where penalty_value
    is the multiplier reduction (0.5 = 50% reduction).
    
    Rules:
    1. 50% penalty if missing ID when majority (50%+) have IDs
    2. 50% penalty if ID format differs from dominant pattern family
       - TSC patterns (CC., C., A., P., PI., Conf.) are grouped as one "TSC" family
       - Uses plurality threshold (40%+) instead of supermajority for mixed-ID reports
    """
    penalties = []
    
    if not all_objectives or len(all_objectives) < 4:
        # Need at least 4 objectives for pattern analysis
        return penalties
    
    # Collect all objective IDs (handle both dict and model objects)
    all_ids = []
    for obj in all_objectives:
        obj_id = obj.get('objective_id', '') if isinstance(obj, dict) else getattr(obj, 'objective_id', '')
        obj_id_str = str(obj_id) if obj_id else ''
        if obj_id_str and obj_id_str.strip():
            all_ids.append(obj_id_str.strip())
    
    total_count = len(all_objectives)
    with_id_count = len(all_ids)
    
    # Rule 1: Missing ID when majority have IDs (lowered from 80% to 50%)
    if not objective_id:
        if with_id_count >= total_count * 0.50:
            penalties.append((
                "missing_id_majority",
                config.OBJECTIVE_ID_MISSING_PENALTY,
                f"Missing ID when {with_id_count}/{total_count} ({with_id_count/total_count:.0%}) have IDs"
            ))
        return penalties  # No need for pattern check if ID is missing
    
    # Rule 2: ID format outlier detection with TSC family grouping
    if with_id_count >= 4:  # Need enough IDs for pattern analysis
        pattern_counts = _analyze_id_patterns(all_ids)
        
        if pattern_counts:
            # Group TSC patterns into one family for comparison
            TSC_PATTERNS = {'CC.', 'C.', 'A.', 'P.', 'PI.', 'Conf.'}
            family_counts = {}
            for pattern, count in pattern_counts.items():
                family = 'TSC' if pattern in TSC_PATTERNS else pattern
                family_counts[family] = family_counts.get(family, 0) + count
            
            total_patterns = sum(family_counts.values())
            dominant_family = max(family_counts.keys(), key=lambda k: family_counts[k])
            dominant_count = family_counts[dominant_family]
            
            # Use plurality threshold (40%) instead of supermajority (80%)
            # This catches mixed-ID reports where one family still clearly dominates
            PLURALITY_THRESHOLD = 0.40
            if dominant_count >= total_patterns * PLURALITY_THRESHOLD:
                # Check if current ID matches dominant family
                current_pattern = _extract_id_pattern(objective_id)
                current_family = 'TSC' if current_pattern in TSC_PATTERNS else current_pattern
                
                if current_family != dominant_family:
                    # Scale penalty by dominance: 40% dominance = 25% penalty, 80%+ = 50% penalty
                    dominance_ratio = dominant_count / total_patterns
                    scaled_penalty = config.OBJECTIVE_ID_OUTLIER_PENALTY * min(1.0, dominance_ratio / 0.80)
                    
                    penalties.append((
                        "id_pattern_outlier",
                        scaled_penalty,
                        f"ID family '{current_family}' differs from dominant '{dominant_family}' "
                        f"({dominant_count}/{total_patterns} = {dominance_ratio:.0%}, "
                        f"penalty={scaled_penalty:.0%})"
                    ))
    
    return penalties


def _analyze_id_patterns(objective_ids: List[str]) -> Dict[str, int]:
    """
    Analyze objective ID patterns and return counts.
    
    Patterns identified:
    - "CC." - TSC Common Criteria (CC1.1, CC2.3)
    - "C." - Confidentiality (C1.1)
    - "A." - Availability (A1.1)
    - "P." - Privacy (P1.1, P2.1)
    - "PI." - Processing Integrity (PI1.1)
    - "Conf." - Confidentiality alt (Conf1.1)
    - "ALPHA-NUM-NUM" - Dash-separated (SO-1-2, IAM-01-03)
    - "ALPHA.NUM.NUM" - Dot-separated (IM.1.2)
    - "ALPHANUM" - Concatenated (OBJ001, CTL23)
    """
    pattern_counts = {}
    
    for obj_id in objective_ids:
        pattern = _extract_id_pattern(obj_id)
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
    
    return pattern_counts


def _extract_id_pattern(objective_id: str) -> str:
    """Extract the structural pattern from an objective ID."""
    if not objective_id:
        return "none"
    
    # Normalize: uppercase, strip spaces
    normalized = objective_id.upper().replace(" ", "")
    
    # Check for known TSC patterns
    if re.match(r'^CC\d+\.\d+', normalized):
        return "CC."
    if re.match(r'^C\d+\.\d+', normalized):
        return "C."
    if re.match(r'^A\d+\.\d+', normalized):
        return "A."
    if re.match(r'^P\d+\.\d+', normalized):
        return "P."
    if re.match(r'^PI\d+\.\d+', normalized):
        return "PI."
    if re.match(r'^CONF\d+\.\d+', normalized):
        return "Conf."
    
    # Check for common custom patterns
    if re.match(r'^[A-Z]+-\d+-\d+', normalized):
        return "ALPHA-NUM-NUM"  # SO-1-2, IAM-01-03
    if re.match(r'^[A-Z]+\.\d+\.\d+', normalized):
        return "ALPHA.NUM.NUM"  # IM.1.2
    if re.match(r'^[A-Z]+\d+$', normalized):
        return "ALPHANUM"  # OBJ001, CTL23
    
    # Unknown pattern
    return "custom"


def find_page_refs(objective_text: str, extracted_text: str) -> List[int]:
    """
    Find page references for an objective by searching extracted text.
    
    Args:
        objective_text: Objective text to search for
        extracted_text: Full extracted text with page markers
        
    Returns:
        List of page numbers where objective appears
    """
    # Look for page markers like "=== PAGE 12 ==="
    page_pattern = r'=== PAGE (\d+) ==='
    pages = []
    
    # Normalize text for searching - collapse whitespace
    def normalize_text(text):
        return re.sub(r'\s+', ' ', text).strip().lower()
    
    # Split extracted text into chunks by page markers
    page_sections = re.split(page_pattern, extracted_text)
    
    # Extract page numbers (every other element after split)
    page_numbers = []
    for i in range(1, len(page_sections), 2):
        try:
            page_numbers.append(int(page_sections[i]))
        except (ValueError, IndexError):
            pass
    
    # Try progressively shorter search keys
    for key_length in [100, 60, 40, 25]:
        if len(objective_text) < key_length:
            continue
            
        search_key = normalize_text(objective_text[:key_length])
        
        # Search each page section
        for idx, section in enumerate(page_sections[::2]):  # Even indices are text sections
            if normalize_text(section).find(search_key) != -1:
                # Found it! Get the page number for this section
                page_idx = idx // 2
                if page_idx < len(page_numbers):
                    pages.append(page_numbers[page_idx])
                    return pages  # Return first match
    
    # If no match, try with just the first 20 chars as last resort
    if len(objective_text) >= 20:
        search_key = normalize_text(objective_text[:20])
        for idx, section in enumerate(page_sections[::2]):
            if normalize_text(section).find(search_key) != -1:
                page_idx = idx // 2
                if page_idx < len(page_numbers):
                    pages.append(page_numbers[page_idx])
                    return pages
    
    return pages


def _is_likely_control_not_objective(text: str, control_ids: set) -> tuple:
    """
    Determine if extracted text is actually a control, not an objective.
    
    This filter prevents controls from being misclassified as objectives by detecting
    control-specific patterns (action verbs, procedures, granular details).
    
    Args:
        text: Extracted objective text to validate
        control_ids: Set of known control IDs from the scan (uppercase)
        
    Returns:
        Tuple of (is_control: bool, reason: str)
        - is_control: True if text appears to be a control
        - reason: Human-readable explanation for classification
    """
    if not text or not isinstance(text, str):
        return (False, "No text provided")
    
    text_lower = text.lower()
    
    # Check 1: Contains control action verbs (HOW, not WHAT)
    control_verbs = [
        'reviews', 'review', 'verifies', 'verify', 'tests', 'test', 
        'inspects', 'inspect', 'validates', 'validate', 'monitors', 'monitor',
        'checks', 'check', 'confirms', 'confirm', 'assesses', 'assess',
        'examines', 'examine', 'evaluates', 'evaluate', 'performs', 'perform',
        'conducts', 'conduct', 'executes', 'execute', 'implements', 'implement'
    ]
    
    # Count verb matches (need multiple or strong match)
    verb_matches = [verb for verb in control_verbs if f" {verb} " in f" {text_lower} "]
    if len(verb_matches) >= 2:
        return (True, f"Contains multiple control action verbs: {', '.join(verb_matches[:3])}")
    
    # Check 2: Too granular/specific (mentions specific tools, frequencies, procedures)
    granular_indicators = [
        'quarterly', 'annually', 'daily', 'weekly', 'monthly', 'biannually',
        'aws cloudtrail', 'cloudwatch', 'jira', 'servicenow', 'splunk',
        'logs are', 'alerts are', 'tickets are', 'reports are',
        'documented and approved', 'reviewed and approved',
        'within 24 hours', 'within 48 hours', 'on a periodic basis'
    ]
    
    granular_matches = [ind for ind in granular_indicators if ind in text_lower]
    if granular_matches:
        return (True, f"Too granular/specific for objective: '{granular_matches[0]}'")
    
    # Check 3: Describes procedures/methods (HOW not WHAT)
    procedure_indicators = [
        'process includes', 'procedure for', 'steps to', 'method of',
        'following steps', 'following process', 'workflow includes',
        'mechanism for', 'process is', 'procedure is'
    ]
    
    procedure_matches = [ind for ind in procedure_indicators if ind in text_lower]
    if procedure_matches:
        return (True, f"Describes procedure/method: '{procedure_matches[0]}'")
    
    # Check 4: Matches known control ID from controls table
    # Extract potential IDs (alphanumeric tokens with dashes/dots)
    import re
    potential_ids = re.findall(r'\b[A-Z]{1,4}[-.]?\d{1,3}(?:[-.]\d{1,3})?\b', text.upper())
    
    for potential_id in potential_ids:
        # Normalize: remove trailing punctuation
        clean_id = potential_id.strip('.:,')
        if clean_id in control_ids:
            return (True, f"Matches control ID from database: {clean_id}")
    
    # Check 5: Very short and specific (likely a control activity, not objective goal)
    if len(text) < 50 and any(verb in text_lower for verb in control_verbs):
        return (True, "Very short statement with control verb (likely specific activity)")
    
    # Not a control - likely a legitimate objective
    return (False, "")


def extract_objectives(
    extracted_text: str,
    scan_id: int,
    db_session: Session,
    sections: List[Dict[str, Any]],  # NOW REQUIRED - no Optional
    job_id: Optional[str] = None,
    redis_client: Optional[Any] = None
) -> List[ControlObjective]:
    """
    Extract control objectives from SOC report text.
    
    Args:
        extracted_text: Full extracted text from PDF
        scan_id: Scan ID for database association
        db_session: SQLAlchemy session
        sections: REQUIRED - Section boundaries from section_results.json
        job_id: Redis job ID for progress updates
        redis_client: Redis client for progress tracking
        
    Returns:
        List of ControlObjective model instances
        
    Raises:
        ValueError: If sections is missing or Control_Descriptions section not found
    """
    if not config.ENABLE_OBJECTIVE_EXTRACTION:
        logger.info("Objective extraction disabled in config")
        return []
    
    logger.info(f"="*80)
    logger.info(f"[OBJECTIVE_EXTRACTION] Starting for scan_id={scan_id}")
    logger.info(f"[OBJECTIVE_EXTRACTION] Text length: {len(extracted_text)} chars")
    logger.info(f"[OBJECTIVE_EXTRACTION] Sections provided: {len(sections)}")
    logger.info(f"[OBJECTIVE_EXTRACTION] Section topics: {[s.get('topic') for s in sections]}")
    logger.info(f"[OBJECTIVE_EXTRACTION] Job ID: {job_id}")
    logger.info(f"[OBJECTIVE_EXTRACTION] Redis client: {'Yes' if redis_client else 'No'}")
    logger.info(f"="*80)

    # STRICT ENFORCEMENT: Fail fast if Control_Descriptions section not provided
    if not sections:
        raise ValueError(
            "Section boundaries (sections parameter) are REQUIRED for objective extraction. "
            "Cannot proceed without Control_Descriptions section definition."
        )
    
    control_section = next((s for s in sections if s.get("topic") == "Control_Descriptions"), None)
    if not control_section:
        raise ValueError(
            "Control_Descriptions section not found in sections data. "
            "Objective extraction MUST be limited to Control_Descriptions section only. "
            "Available sections: " + ", ".join([s.get("topic", "unknown") for s in sections])
        )
    
    start_line = control_section.get("start_line")
    end_line = control_section.get("end_line")
    
    if not (isinstance(start_line, int) and isinstance(end_line, int) and end_line >= start_line):
        raise ValueError(
            f"Invalid Control_Descriptions section boundaries: start_line={start_line}, end_line={end_line}. "
            "Both must be integers and end_line must be >= start_line."
        )
    
    # Filter text to ONLY Control_Descriptions section BEFORE chunking
    full_text = extracted_text or ""
    lines = full_text.split("\n")
    filtered_text = "\n".join(lines[start_line - 1:end_line])
    
    logger.info(f"[SECTION_FILTER] Total document lines: {len(lines)}")
    logger.info(f"[SECTION_FILTER] Control_Descriptions boundaries: lines {start_line}-{end_line}")
    logger.info(f"[SECTION_FILTER] Filtered text length: {len(filtered_text)} chars")
    logger.info(f"[SECTION_FILTER] Excluded {start_line - 1} lines before section")
    logger.info(f"[SECTION_FILTER] Excluded {len(lines) - end_line} lines after section")
    logger.info(f"[SECTION_FILTER] First 200 chars of filtered text: {filtered_text[:200]}")

    # If no objective keywords are found, continue but log for visibility
    keyword_haystack = filtered_text.lower()
    objective_keywords = set(config.OBJECTIVE_SECTION_KEYWORDS + config.OBJECTIVE_PATTERN_KEYWORDS)
    if not any(keyword in keyword_haystack for keyword in objective_keywords):
        logger.info("[OBJECTIVES] No objective keywords found in selected text; proceeding with extraction")
    
    # Update progress
    if job_id and redis_client:
        try:
            job_hmset(job_id, {
                "status": "running",
                "progress_status": "Extracting control objectives...",
                "processed_chunks": 0,
                "total_chunks": 0,
                "objectives_found": 0,
                "updated_at": datetime.utcnow().isoformat(),
            }, redis_client)
        except Exception as e:
            logger.warning(f"Failed to update job progress: {e}")
    
    # Step 1: Chunk text by tokens with overlap
    logger.info(f"[CHUNKING] Starting tokenization...")
    logger.info(f"[CHUNKING] Tokens per chunk: {config.OBJECTIVE_TOKENS_PER_CHUNK}")
    logger.info(f"[CHUNKING] Overlap tokens: {config.OBJECTIVE_CHUNK_OVERLAP_TOKENS}")
    chunks = chunk_text_by_tokens(
        filtered_text,
        config.OBJECTIVE_TOKENS_PER_CHUNK,
        config.OBJECTIVE_CHUNK_OVERLAP_TOKENS
    )
    logger.info(f"[CHUNKING] Created {len(chunks)} chunks")
    for i, (chunk_text, chunk_start, chunk_end) in enumerate(chunks[:3]):  # Log first 3
        logger.info(f"[CHUNKING] Chunk {i}: lines {chunk_start}-{chunk_end}, {len(chunk_text)} chars")
    if len(chunks) > 3:
        logger.info(f"[CHUNKING] ... and {len(chunks) - 3} more chunks")

    if job_id and redis_client:
        try:
            job_hmset(job_id, {
                "total_chunks": len(chunks),
                "updated_at": datetime.utcnow().isoformat(),
            }, redis_client)
        except Exception as e:
            logger.warning(f"Failed to update chunk count: {e}")
    
    # Step 2: Extract objectives from each chunk (parallel or sequential)
    logger.info(f"[EXTRACTION] Starting GPT extraction phase...")
    logger.info(f"[EXTRACTION] Parallel enabled: {config.ENABLE_PARALLEL_OBJECTIVE_EXTRACTION}")
    logger.info(f"[EXTRACTION] Number of chunks: {len(chunks)}")
    all_objectives = []
    total_found = 0
    
    if config.ENABLE_PARALLEL_OBJECTIVE_EXTRACTION and len(chunks) > 1:
        logger.info(f"[EXTRACTION] Using PARALLEL mode with {config.OBJECTIVE_WORKER_THREADS} workers")
        
        with ThreadPoolExecutor(max_workers=config.OBJECTIVE_WORKER_THREADS) as executor:
            # Submit all chunks for processing
            future_to_chunk = {}
            for i, (chunk_text, chunk_start_line, chunk_end_line) in enumerate(chunks):
                # CRITICAL: Adjust chunk line numbers from filtered-text-relative to document-relative
                document_chunk_start = start_line + chunk_start_line
                
                future = executor.submit(
                    extract_objectives_from_chunk,
                    chunk_text,
                    i,
                    scan_id,
                    document_chunk_start
                )
                future_to_chunk[future] = (i, document_chunk_start)
            
            # Collect results as they complete
            for future in as_completed(future_to_chunk):
                chunk_idx, doc_start = future_to_chunk[future]
                try:
                    chunk_objectives = future.result()
                    all_objectives.extend(chunk_objectives)
                    total_found += len(chunk_objectives)
                    
                    logger.info(f"[OBJECTIVES] Chunk {chunk_idx+1}/{len(chunks)} extracted {len(chunk_objectives)} objectives (total: {total_found})")
                    
                    if job_id and redis_client:
                        try:
                            job_hmset(job_id, {
                                "processed_chunks": chunk_idx + 1,
                                "total_chunks": len(chunks),
                                "objectives_found": total_found,
                                "updated_at": datetime.utcnow().isoformat(),
                            }, redis_client)
                        except Exception as e:
                            logger.warning(f"Failed to update chunk progress: {e}")
                except Exception as e:
                    logger.error(f"[OBJECTIVES] Chunk {chunk_idx} extraction failed: {e}", exc_info=True)
                    
    else:
        # Sequential fallback (original code path)
        logger.info(f"[EXTRACTION] Using SEQUENTIAL mode for {len(chunks)} chunks")
        for i, (chunk_text, chunk_start_line, chunk_end_line) in enumerate(chunks):
            logger.info(f"[EXTRACTION] Processing chunk {i+1}/{len(chunks)}...")
            # CRITICAL: Adjust chunk line numbers from filtered-text-relative to document-relative
            # chunk_start_line is relative to filtered_text (starts at 0)
            # We need to add start_line to get document coordinates
            document_chunk_start = start_line + chunk_start_line
            
            logger.info(f"[DEBUG] Chunk {i}: chunk_start_line={chunk_start_line}, start_line={start_line}, document_chunk_start={document_chunk_start}")
            
            chunk_objectives = extract_objectives_from_chunk(chunk_text, i, scan_id, document_chunk_start)
            all_objectives.extend(chunk_objectives)
            total_found += len(chunk_objectives)

            if job_id and redis_client:
                try:
                    job_hmset(job_id, {
                        "processed_chunks": i + 1,
                        "total_chunks": len(chunks),
                        "objectives_found": total_found,
                        "updated_at": datetime.utcnow().isoformat(),
                    }, redis_client)
                except Exception as e:
                    logger.warning(f"Failed to update chunk progress: {e}")
    
    logger.info(f"Extracted {len(all_objectives)} total objectives (before deduplication)")
    
    # Step 3: Deduplicate across chunks
    if len(all_objectives) > 0:
        logger.info(f"[DEDUP] Starting deduplication of {len(all_objectives)} objectives")
        try:
            deduplicated_objectives = deduplicate_objectives(all_objectives)
            logger.info(f"[DEDUP] Deduplication returned: {type(deduplicated_objectives)}, length={len(deduplicated_objectives) if deduplicated_objectives else 0}")
            if not deduplicated_objectives:
                logger.error("[DEDUP] ⚠️ CRITICAL: Deduplication produced ZERO objectives from {len(all_objectives)} inputs!")
                logger.error(f"[DEDUP] Sample input objectives: {[obj.get('objective_id', 'NO_ID') for obj in all_objectives[:10]]}")
                logger.warning("[DEDUP] Using raw extracted list as fallback")
                deduplicated_objectives = all_objectives
        except Exception as e:
            logger.error(f"[DEDUP] ⚠️ CRITICAL: Deduplication crashed with exception: {e}", exc_info=True)
            logger.error(f"[DEDUP] Input count: {len(all_objectives)}")
            logger.error(f"[DEDUP] Using raw extracted list as fallback")
            deduplicated_objectives = all_objectives
    else:
        logger.warning(f"[DEDUP] ⚠️ No objectives extracted from {len(chunks)} chunks - this may indicate extraction failure")
        deduplicated_objectives = []
    
    logger.info(f"[DEDUP] Final count: {len(deduplicated_objectives)} unique objectives")

    # Step 3.25: Filter out controls misclassified as objectives
    if deduplicated_objectives:
        logger.info(f"[CONTROL_FILTER] Filtering controls misclassified as objectives...")
        
        # Load control IDs from database for comparison
        controls = db_session.query(Control).filter_by(scan_id=scan_id).all()
        control_ids = {str(c.control_id).strip().upper() for c in controls if c.control_id}
        logger.info(f"[CONTROL_FILTER] Loaded {len(control_ids)} control IDs for comparison")
        
        filtered_objectives = []
        rejected_controls = []
        
        for obj in deduplicated_objectives:
            objective_text = obj.get('objective_text', '')
            is_control, reason = _is_likely_control_not_objective(objective_text, control_ids)
            
            if is_control:
                logger.info(
                    f"[CONTROL_FILTER] ✗ Rejected control misclassified as objective: {reason}"
                )
                logger.debug(f"[CONTROL_FILTER]   Text: {objective_text[:120]}...")
                rejected_controls.append({
                    'text': objective_text[:100],
                    'reason': reason
                })
            else:
                filtered_objectives.append(obj)
        
        logger.info(
            f"[CONTROL_FILTER] ✓ Filtered out {len(rejected_controls)} controls, "
            f"kept {len(filtered_objectives)} legitimate objectives"
        )
        
        if rejected_controls:
            logger.info(
                f"[CONTROL_FILTER] Top rejection reasons: "
                f"{', '.join(set([r['reason'].split(':')[0] for r in rejected_controls[:5]]))}"
            )
        
        deduplicated_objectives = filtered_objectives

    # Step 3.5: Pattern learning + rescan (after initial objectives)
    if scan_id is not None and deduplicated_objectives:
        try:
            scored_for_selection = _score_objectives_for_selection(deduplicated_objectives, full_text)
            high_conf_objectives = _select_high_conf_objectives(
                scored_for_selection,
                config.HIGH_CONFIDENCE_THRESHOLD,
                config.OBJECTIVE_PATTERN_MIN_OBJECTIVES
            )

            controls = db_session.query(Control).filter_by(scan_id=scan_id).all()
            high_conf_controls = _select_high_conf_controls(
                controls,
                config.HIGH_CONFIDENCE_THRESHOLD,
                config.OBJECTIVE_PATTERN_MIN_CONTROLS
            )

            if len(high_conf_objectives) >= config.OBJECTIVE_PATTERN_MIN_OBJECTIVES and len(high_conf_controls) >= config.OBJECTIVE_PATTERN_MIN_CONTROLS:
                objective_samples = [
                    {
                        "objective_id": obj.get("objective_id"),
                        "objective_text": obj.get("objective_text"),
                        "final_confidence": obj.get("_final_confidence")
                    }
                    for obj in high_conf_objectives
                ]
                control_samples = [
                    {
                        "control_id": ctrl.control_id,
                        "control_desc": ctrl.control_desc,
                        "final_confidence": _get_control_confidence(ctrl)
                    }
                    for ctrl in high_conf_controls
                ]

                patterns = _learn_objective_patterns(objective_samples, control_samples)
                
                # Add sequence validation to identify missing objectives
                sequence_gaps = _identify_missing_sequences(deduplicated_objectives)
                if sequence_gaps.get("missing_top_level") or sequence_gaps.get("missing_sub_level"):
                    logger.info(
                        f"Sequence validation found gaps: "
                        f"Top-level: {sequence_gaps.get('missing_top_level', [])} | "
                        f"Sub-level: {sequence_gaps.get('missing_sub_level', {})}"
                    )
                    # Add gap information to patterns for targeted rescan
                    patterns["sequence_gaps"] = sequence_gaps
                
                if _can_rescan_with_patterns(patterns):
                    existing_objectives_payload = [
                        {
                            "objective_id": obj.get("objective_id"),
                            "objective_text": obj.get("objective_text")
                        }
                        for obj in deduplicated_objectives
                    ]
                    rescanned_objectives = _rescan_objectives_with_patterns(
                        chunks,
                        patterns,
                        existing_objectives_payload,
                        start_line  # Pass start_line for document-relative adjustment
                    )

                    if rescanned_objectives:
                        combined_objectives = deduplicated_objectives + rescanned_objectives
                        deduplicated_objectives = deduplicate_objectives(combined_objectives)
                        logger.info(
                            f"Pattern rescan added {len(rescanned_objectives)} objectives; now {len(deduplicated_objectives)} total"
                        )
        except Exception as e:
            logger.error(f"Objective pattern learning/rescan failed: {e}")
    
    # Step 4: Calculate multi-factor confidence and create model instances
    objective_models = []
    
    # Get full document lines with page markers for get_page_for_line()
    full_doc_lines = extracted_text.split('\n') if extracted_text else []
    
    # Filter out None values before processing
    deduplicated_objectives = [obj for obj in deduplicated_objectives if obj is not None and isinstance(obj, dict)]
    
    for idx, obj in enumerate(deduplicated_objectives):
        obj_id_display = (obj.get('objective_id') or 'NO_ID')[:20]
        logger.info(f"[MODEL_CREATE] Processing objective {idx+1}/{len(deduplicated_objectives)}: {obj_id_display}")
        
        objective_text = obj.get('objective_text') or ''
        obj_id = obj.get('objective_id', '')
        
        # Skip objectives with no text — DB has NOT NULL constraint on objective_text
        if not objective_text.strip():
            logger.warning(f"[MODEL_CREATE] Skipping objective {obj_id_display}: objective_text is empty/null")
            continue
        
        # Use line_ref from GPT extraction if available (already document-relative)
        # This is the most accurate since GPT extracted it from the chunk
        line_ref = obj.get('line_ref')
        
        if line_ref is not None:
            logger.debug(f"Using GPT-provided line_ref={line_ref} for objective {obj_id}")
        else:
            # Fallback: search for the objective in the text
            logger.warning(f"Objective {obj_id} has no line_ref from GPT, attempting text search in section starting at line {start_line}")
            lines = full_text.split('\n')
            
            # Try multiple search strategies
            # Strategy 1: Look for objective_id first (most reliable)
            if obj_id and obj_id.strip():
                search_id = obj_id.strip()
                for i, line in enumerate(lines):
                    # More flexible matching - remove extra whitespace
                    normalized_line = ' '.join(line.split())
                    if search_id in normalized_line:
                        # i is section-relative (0-indexed), convert to document-relative (1-indexed)
                        line_ref = start_line + i
                        logger.info(f"✓ Found objective {obj_id} at document line {line_ref} via ID match")
                        break
            
            # Strategy 2: Search for first 50 chars of text (if ID search failed)
            if line_ref is None and len(objective_text) >= 50:
                search_text = objective_text[:50].strip()
                for i, line in enumerate(lines):
                    normalized_line = ' '.join(line.split())
                    if search_text in normalized_line:
                        line_ref = start_line + i
                        logger.info(f"✓ Found objective {obj_id} at document line {line_ref} via text match")
                        break
            
            # Strategy 3: Search for objective_text in multiple shorter chunks (more flexible)
            if line_ref is None and len(objective_text) >= 30:
                # Try first 30 chars
                search_text = objective_text[:30].strip()
                for i, line in enumerate(lines):
                    normalized_line = ' '.join(line.split())
                    if search_text in normalized_line:
                        line_ref = start_line + i
                        logger.info(f"✓ Found objective {obj_id} at document line {line_ref} via short text match")
                        break
            
            if line_ref is None:
                logger.error(f"✗ Could not find line_ref for objective '{obj_id}' - page_refs will be empty. Text preview: {objective_text[:80]}...")
        
        # Calculate confidence
        logger.debug(f"[MODEL_CREATE] Calculating confidence for {obj_id}")
        final_confidence, confidence_calc, metadata = calculate_multi_factor_confidence(
            obj, full_text, line_ref, all_objectives=deduplicated_objectives
        )
        logger.debug(f"[MODEL_CREATE] Confidence calculated for {obj_id}: {final_confidence:.3f}")

        if obj.get("pattern_alignment"):
            # Only apply pattern alignment boost if GPT reasoning is non-empty
            # This prevents inflated scores for objectives without meaningful validation
            obj_reasoning = obj.get('reasoning', '')
            _empty_stubs = {'', 'Gap extraction:', 'Gap extraction', 'N/A', 'None'}
            if obj_reasoning and obj_reasoning.strip() not in _empty_stubs:
                final_confidence = min(1.0, final_confidence + config.OBJECTIVE_PATTERN_ALIGNMENT_BOOST)
                confidence_calc = (
                    f"{confidence_calc} + pattern_boost={config.OBJECTIVE_PATTERN_ALIGNMENT_BOOST:.2f}"
                )
            else:
                # Halve the boost when reasoning is missing (pattern match alone isn't sufficient)
                reduced_boost = config.OBJECTIVE_PATTERN_ALIGNMENT_BOOST * 0.5
                final_confidence = min(1.0, final_confidence + reduced_boost)
                confidence_calc = (
                    f"{confidence_calc} + pattern_boost_reduced={reduced_boost:.2f} (no GPT reasoning)"
                )
                logger.info(
                    f"[CONFIDENCE] Reduced pattern boost for '{obj_id}' "
                    f"({config.OBJECTIVE_PATTERN_ALIGNMENT_BOOST:.2f} → {reduced_boost:.2f}) - empty GPT reasoning"
                )
        
        # Find page refs using get_page_for_line (EXACT SAME METHOD AS CONTROLS)
        # Controls use: get_page_for_line(control["text_lines"], control["source_start_line"])
        # We replicate exactly: get_page_for_line(full_doc_lines, line_ref)
        logger.debug(f"[MODEL_CREATE] Finding page refs for {obj_id} at line {line_ref}")
        page_refs = []
        if line_ref is not None and full_doc_lines:
            try:
                from ..pdf_handler import get_page_for_line
                # CRITICAL: Pass as list of lines (not split again) and use 1-based line_ref
                # This matches exactly how controls do it
                page_num = get_page_for_line(full_doc_lines, line_ref)
                if page_num:
                    page_refs = [page_num]
                    logger.debug(f"Objective '{obj_id}': line_ref={line_ref}, page={page_num}")
                else:
                    logger.warning(f"Objective '{obj_id}': get_page_for_line returned None for line_ref={line_ref}")
            except Exception as e:
                logger.error(f"Error extracting page refs for objective {obj_id} at line {line_ref}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        logger.debug(f"[MODEL_CREATE] Page refs found for {obj_id}: {page_refs}")
        
        # Extract confidence factors
        factors = obj.get('confidence_factors', {})
        
        # Get objective ID and normalize it
        original_objective_id = obj.get('objective_id')
        # Strip whitespace/newlines from original_objective_id before storing
        if original_objective_id:
            original_objective_id = original_objective_id.strip()
        normalized_objective_id = normalize_objective_id(original_objective_id) if original_objective_id else None
        
        # Create model instance
        objective_model = ControlObjective(
            scan_id=scan_id,
            objective_id=normalized_objective_id,  # FIXED: Use normalized version to prevent \n in database
            objective_id_normalized=normalized_objective_id,
            objective_id_original=original_objective_id,
            objective_text=objective_text,
            keyword_confidence=factors.get('keyword_match', 0.0),
            distance_confidence=0.0,  # DEPRECATED: was section-header proximity, not meaningful
            gpt_confidence=factors.get('gpt_opinion', 0.0),
            alignment_confidence=0.0,  # Calculated after control mapping
            format_confidence=factors.get('format_clarity', 0.0),
            final_confidence=final_confidence,
            confidence_calc=confidence_calc,
            confidence_metadata=metadata,  # NEW: Audit trail with factor breakdown
            gpt_reasoning=obj.get('reasoning', ''),
            page_refs=page_refs,
            line_ref=line_ref,
            all_line_refs=[line_ref] if line_ref is not None else [],  # Phase A: preserve all locations
            all_page_refs=list(page_refs) if page_refs else [],  # Phase A: preserve all page locations
            source_context=objective_text[:500] if objective_text else '',  # First 500 chars as context
            extraction_method=obj.get('extraction_method', 'gpt_inferred'),
            section_heading=obj.get('section_heading'),
            status='pending',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        logger.info(f"[DEBUG] Created model for {original_objective_id}: line_ref={line_ref}, page_refs={page_refs}, final_confidence={final_confidence}")
        
        objective_models.append(objective_model)
    
    # <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 7 -->
    # Step 4.5: Post-extraction validation - GPT-based semantic validation + boundary enforcement
    logger.info(f"[VALIDATION] Starting validation of {len(objective_models)} objectives...")
    logger.info(f"[VALIDATION] Section boundaries: lines {start_line}-{end_line}")
    logger.info(f"[VALIDATION] Using GPT-based semantic validation (supports 1000s of formats)")
    
    # Batch validation function for parallel processing
    def _validate_objectives_batch(objectives: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Validate multiple objectives in single GPT call for performance.
        
        Args:
            objectives: List of {objective_id, objective_text} dicts
            
        Returns:
            Dict mapping objective_id to {is_valid, confidence_adjustment, reasoning}
        """
        if not objectives:
            return {}
            
        prompt = f"""Validate these {len(objectives)} control objectives. Determine if each is a legitimate control objective (not metadata, headers, or noise).

Objectives to validate:
{json.dumps([{"id": obj["objective_id"], "text": (obj["objective_text"] or "")[:300]} for obj in objectives], indent=2)}

Return JSON with key "validations" containing array of results:
{{
  "validations": [
    {{"objective_id": "CC1.1", "valid": true, "confidence": 0.9, "reasoning": "Clear security objective"}},
    {{"objective_id": "HEADER", "valid": false, "confidence": 0.1, "reasoning": "Not a control objective"}}
  ]
}}"""
        
        try:
            response = gpt_extract(
                prompt=prompt,
                extractor_name="objective_batch_validator",
                override_model=OBJECTIVE_MODEL
            )
            
            # gpt_extract returns a raw string — parse it to dict first
            parsed = _parse_json_response(response, "batch_validation")
            if not parsed or not isinstance(parsed, dict):
                logger.warning(f"[BATCH_VALIDATION] Failed to parse response as JSON, falling back")
                return {}
            
            validations = parsed.get("validations", [])
            result_map = {}
            
            for v in validations:
                obj_id = v.get("objective_id", "UNKNOWN")
                is_valid = v.get("valid", True)
                gpt_confidence = v.get("confidence", 0.5)
                reasoning = v.get("reasoning", "Batch validation")[:100]
                
                # Map to same return format as single validation
                confidence_adj = 0.0 if is_valid else 0.0
                result_map[obj_id] = {
                    "is_valid": is_valid,
                    "confidence_adjustment": confidence_adj,
                    "reasoning": reasoning
                }
            
            logger.info(f"[BATCH_VALIDATION] Validated {len(validations)} objectives in single call")
            return result_map
            
        except Exception as e:
            logger.warning(f"[BATCH_VALIDATION] API error: {e}. Falling back to individual validation.")
            # Return empty dict to trigger fallback
            return {}
    
    # GPT-based validation function (with optional caching)
    def _validate_objective_with_gpt(objective_id: str, objective_text: str) -> tuple:
        """
        Validate objective using GPT semantic analysis.
        
        Returns: (is_valid, confidence_adjustment, reasoning)
        - is_valid: True if objective passes validation
        - confidence_adjustment: 0.0 (no change) or -0.15 (API error penalty)
        - reasoning: Explanation from GPT or error message
        
        Fallback: On API error, accept objective with 0.15 confidence penalty
        """
        # Check cache if enabled
        if config.ENABLE_OBJECTIVE_VALIDATION_CACHE:
            if not objective_text:
                logger.debug(f"[VALIDATION] Skipping GPT validation for {objective_id}: no objective_text")
                return False, -0.3, "No objective text provided"
            try:
                redis_client = get_redis_client(config.REDIS_URL)
                text_hash = hashlib.md5(objective_text.encode()).hexdigest()
                cache_key = f"obj_validation:{text_hash}"
                cached = redis_client.get(cache_key)
                if cached:
                    result = json.loads(cached)
                    if result and isinstance(result, dict) and "is_valid" in result:
                        logger.debug(f"[VALIDATION] Cache hit for: {objective_id}")
                        return result["is_valid"], result.get("confidence_adj", 0.0), result.get("reasoning", "cached")
            except Exception as e:
                logger.warning(f"[VALIDATION] Cache check failed: {e}")
        
        prompt = config.OBJECTIVE_VALIDATION_PROMPT.format(
            objective_id=objective_id or "UNKNOWN",
            objective_text=objective_text[:500]  # Limit context to avoid token overflow
        )
        
        try:
            response = gpt_extract(
                prompt=prompt,
                extractor_name="objective_validator",
                override_model=OBJECTIVE_MODEL
            )
            
            result = _parse_json_response(response, "Validation")
            if result:
                is_valid = result.get('valid', False)
                gpt_confidence = result.get('confidence', 0.5)
                reasoning = result.get('reasoning', 'GPT validation completed')[:100]
                
                # If GPT says invalid, reject
                if not is_valid:
                    cache_result = (False, 0.0, reasoning)
                else:
                    # If GPT says valid, no confidence adjustment needed
                    cache_result = (True, 0.0, reasoning)
                
                # Cache result if enabled
                if config.ENABLE_OBJECTIVE_VALIDATION_CACHE:
                    try:
                        redis_client.setex(
                            cache_key,
                            60 * 60 * 24 * 30,  # 30 days TTL
                            json.dumps({
                                "is_valid": cache_result[0],
                                "confidence_adj": cache_result[1],
                                "reasoning": cache_result[2]
                            })
                        )
                    except Exception as e:
                        logger.warning(f"[VALIDATION] Cache write failed: {e}")
                
                return cache_result
        except Exception as e:
            logger.warning(f"[GPT_VALIDATION] API error for '{objective_id}': {e}. Accepting with 0.15 penalty.")
            # Fallback: Accept objective but reduce confidence by 0.15
            return (True, -0.15, f"API error (accepted with penalty): {str(e)[:50]}")
        
        # Default fallback if parsing fails
        logger.warning(f"[GPT_VALIDATION] Parse failed for '{objective_id}'. Accepting with 0.15 penalty.")
        return (True, -0.15, "Validation parse failed, accepted with penalty")
    
    # Track validation timing for performance monitoring
    import time
    validation_start_time = time.time()
    
    # CRITICAL: Save count before validation for diagnostic logging
    objective_models_before_validation = len(objective_models)
    logger.info(f"[VALIDATION] Starting validation of {objective_models_before_validation} objectives")
    
    # No more regex pattern validation - using GPT instead
    valid_objectives = []
    boundary_violations = []
    gpt_rejections = []
    gpt_penalties = []
    
    # Try batch validation first if enabled
    validation_results = {}
    if config.ENABLE_BATCH_OBJECTIVE_VALIDATION and len(objective_models) > 0:
        logger.info(f"[VALIDATION] Batch validating {len(objective_models)} objectives")
        objectives_batch = [
            {
                "objective_id": obj.objective_id or "UNKNOWN",
                "objective_text": obj.objective_text
            }
            for obj in objective_models
        ]
        try:
            validation_results = _validate_objectives_batch(objectives_batch)
            logger.info(f"[VALIDATION] Batch validation returned {len(validation_results)} results")
            
            # Log summary of batch validation decisions
            valid_count = sum(1 for r in validation_results.values() if r.get('is_valid'))
            invalid_count = len(validation_results) - valid_count
            logger.info(f"[VALIDATION] Batch results: {valid_count} valid, {invalid_count} invalid")
            
            # Log first few rejections for debugging
            rejections = [(k, v) for k, v in validation_results.items() if not v.get('is_valid')]
            if rejections:
                logger.warning(f"[VALIDATION] First 5 rejections:")
                for obj_id, result in rejections[:5]:
                    logger.warning(f"  - {obj_id}: {result.get('reasoning', 'No reason given')[:150]}")
        except Exception as batch_err:
            logger.error(f"[VALIDATION] Batch validation failed: {batch_err}", exc_info=True)
            logger.error(f"[VALIDATION] Falling back to individual validation")
            validation_results = {}  # Clear partial results, will use individual validation
    
    for idx, obj_model in enumerate(objective_models):
        line_ref = obj_model.line_ref
        objective_id = obj_model.objective_id or "UNKNOWN"
        objective_text = obj_model.objective_text
        
        logger.debug(f"[VALIDATION] Processing {idx+1}/{len(objective_models)}: '{objective_id}'")
        
        # Report progress every 10 objectives
        if job_id and redis_client and idx > 0 and idx % 10 == 0:
            try:
                objectives_percent = int((idx / len(objective_models)) * 100)
                job_hmset(job_id, {
                    "objectives_count": idx,
                    "objectives_percent": objectives_percent,
                }, redis_client)
            except Exception as e:
                logger.warning(f"[OBJECTIVE] Failed to update progress: {e}")
        
        # Validation 1: GPT-based semantic validation (batch or individual)
        if validation_results and objective_id in validation_results:
            # Use batch result
            result = validation_results[objective_id]
            is_valid = result["is_valid"]
            confidence_adjustment = result["confidence_adjustment"]
            reasoning = result["reasoning"]
        else:
            # Fallback to individual validation
            is_valid, confidence_adjustment, reasoning = _validate_objective_with_gpt(
                objective_id,
                objective_text
            )
        
        if not is_valid:
            gpt_rejections.append({
                'objective_id': objective_id,
                'line_ref': line_ref,
                'reasoning': reasoning,
                'text': (objective_text or '')[:80]
            })
            logger.warning(
                f"[GPT_VALIDATION] ✗ REJECTED: '{objective_id}' failed semantic validation. "
                f"Reason: {reasoning}. Line {line_ref}. Text: {(objective_text or '')[:60]}..."
            )
            continue  # Skip this objective
        
        # Apply confidence adjustment if GPT validation had issues (API error)
        if confidence_adjustment < 0:
            obj_model.final_confidence = max(0.0, obj_model.final_confidence + confidence_adjustment)
            gpt_penalties.append({
                'objective_id': objective_id,
                'penalty': confidence_adjustment,
                'reasoning': reasoning
            })
            logger.info(
                f"[GPT_VALIDATION] ⚠ PENALTY: '{objective_id}' accepted with confidence adjustment {confidence_adjustment:.2f}. "
                f"Reason: {reasoning}. New confidence: {obj_model.final_confidence:.2f}"
            )
        else:
            logger.debug(
                f"[GPT_VALIDATION] ✓ PASSED: '{objective_id}' validated by GPT. Reason: {reasoning}"
            )
        
        # <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 8 -->
        # Validation 2: Boundary check - FINAL AUTHORITY (overrules GPT)
        # If line_ref is available, validate it falls within Control_Descriptions section
        if line_ref is not None:
            if line_ref < start_line or line_ref > end_line:
                boundary_violations.append({
                    'objective_id': objective_id,
                    'line_ref': line_ref,
                    'text': objective_text[:80]
                })
                logger.warning(
                    f"[BOUNDARY_CHECK] ✗ VIOLATION: '{objective_id}' at line {line_ref} is OUTSIDE "
                    f"Control_Descriptions section ({start_line}-{end_line}). "
                    f"Setting confidence=0% (Low Confidence table). Text: {objective_text[:60]}..."
                )
                # CRITICAL: Set confidence to 0% (goes to Low Confidence table for manual review)
                obj_model.final_confidence = 0.0
                obj_model.gpt_reasoning = f"BOUNDARY VIOLATION: Line {line_ref} outside section bounds ({start_line}-{end_line}). {obj_model.gpt_reasoning or ''}"
                # Still add to valid_objectives so it's saved to database (as zero confidence)
                valid_objectives.append(obj_model)
            else:
                # Passed both validations
                valid_objectives.append(obj_model)
                logger.debug(
                    f"[BOUNDARY_CHECK] ✓ VALID: '{objective_id}' at line {line_ref} within section bounds"
                )
        else:
            # No line_ref - can't validate boundary, but GPT validation passed
            logger.debug(
                f"[BOUNDARY_CHECK] ⚠ No line_ref for '{objective_id}' - "
                f"cannot validate boundary (allowing based on GPT validation)"
            )
            valid_objectives.append(obj_model)
    
    # Report validation results with comprehensive statistics
    validation_duration = time.time() - validation_start_time
    
    # CRITICAL ERROR CHECK: If very few objectives passed validation
    if len(objective_models) > 0 and len(valid_objectives) < len(objective_models) * 0.5:
        logger.error(
            f"[VALIDATION] ⚠️⚠️⚠️ CRITICAL: Only {len(valid_objectives)} out of {len(objective_models)} objectives passed validation ({len(valid_objectives)/len(objective_models)*100:.1f}%)! "
            f"This is unusually low and may indicate overly aggressive validation."
        )
        logger.error(f"[VALIDATION] GPT rejected: {len(gpt_rejections)}, Boundary violations: {len(boundary_violations)}")
    
    logger.info(
        f"[VALIDATION] ✓ COMPLETED in {validation_duration:.2f}s: "
        f"{len(valid_objectives)} objectives validated "
        f"(Input: {len(objective_models)}, GPT rejected: {len(gpt_rejections)}, "
        f"Boundary violations: {len(boundary_violations)}, API penalties: {len(gpt_penalties)})"
    )
    
    if gpt_rejections:
        logger.warning(
            f"[GPT_VALIDATION] ✗ REJECTED {len(gpt_rejections)} objectives via semantic analysis"
        )
        logger.warning(
            f"[GPT_VALIDATION] Rejected IDs: {[v['objective_id'] for v in gpt_rejections[:10]]}"
        )
        logger.warning(
            f"[GPT_VALIDATION] Sample reasons: {list(set([v['reasoning'][:50] for v in gpt_rejections[:5]]))}"
        )
    
    if boundary_violations:
        logger.error(
            f"[BOUNDARY_CHECK] ✗ {len(boundary_violations)} objectives OUTSIDE section boundaries "
            f"(lines {start_line}-{end_line}) - marked as confidence=0%"
        )
        logger.error(
            f"[BOUNDARY_CHECK] Violated line numbers: {[v['line_ref'] for v in boundary_violations[:10]]}"
        )
        logger.error(
            f"[BOUNDARY_CHECK] Violated IDs: {[v['objective_id'] for v in boundary_violations[:10]]}"
        )
        logger.error(
            f"[BOUNDARY_CHECK] These objectives saved to database with 0% confidence (Low Confidence table)"
        )
    
    if gpt_penalties:
        logger.info(
            f"[GPT_VALIDATION] ⚠ {len(gpt_penalties)} objectives accepted with confidence penalties (API errors)"
        )
        logger.info(
            f"[GPT_VALIDATION] Penalized IDs: {[v['objective_id'] for v in gpt_penalties[:10]]}"
        )
    
    # Performance warning if validation is slow
    if validation_duration > 30:
        logger.warning(
            f"[PERFORMANCE] ⚠ Validation took {validation_duration:.2f}s (>30s threshold). "
            f"Consider batching optimization if this persists."
        )
    
    objective_models = valid_objectives
    
    # CRITICAL DIAGNOSTIC: Log validation results summary
    logger.info(f"[VALIDATION_SUMMARY] Started with {objective_models_before_validation} objectives")
    logger.info(f"[VALIDATION_SUMMARY] After validation: {len(objective_models)} objectives remain")
    logger.info(f"[VALIDATION_SUMMARY] Rejected by GPT: {len(gpt_rejections)}")
    logger.info(f"[VALIDATION_SUMMARY] Boundary violations (0% confidence): {len(boundary_violations)}")
    logger.info(f"[VALIDATION_SUMMARY] GPT penalties applied: {len(gpt_penalties)}")
    
    if len(objective_models) == 0 and len(gpt_rejections) > 0:
        logger.error("[VALIDATION_SUMMARY] CRITICAL: ALL objectives rejected by GPT validation!")
        logger.error(f"[VALIDATION_SUMMARY] Top rejection reasons:")
        for i, rejection in enumerate(gpt_rejections[:10]):
            logger.error(f"  {i+1}. {rejection.get('objective_id', 'UNKNOWN')}: {rejection.get('reasoning', 'No reason')[:150]}")
    
    # Report final objectives count and 100% progress
    if job_id and redis_client:
        try:
            job_hmset(job_id, {
                "objectives_count": len(objective_models),
                "objectives_percent": 100,
            }, redis_client)
            logger.info(f"[OBJECTIVE] Final progress update: {len(objective_models)} objectives, 100% complete")
        except Exception as e:
            logger.warning(f"[OBJECTIVE] Failed to update final progress: {e}")
    
    # Step 5: Save to database (only if scan_id is provided)
    logger.info(f"[DATABASE] Starting database save for {len(objective_models)} objectives (scan_id={scan_id})")
    if objective_models and scan_id is not None:
        # DB-level dedup: Check for existing objectives with the same normalized ID
        # This prevents duplicates when extract_objectives is called multiple times
        # (e.g., from concurrent threads, retry flows, or re-extractions)
        existing_objs = db_session.query(ControlObjective).filter(
            ControlObjective.scan_id == scan_id
        ).all()
        existing_norm_ids = {}
        for eo in existing_objs:
            key = (eo.objective_id_normalized or '').strip().lower()
            if key:
                existing_norm_ids[key] = eo
        
        if existing_norm_ids:
            new_models = []
            skipped = 0
            for obj_model in objective_models:
                norm_id = (obj_model.objective_id_normalized or '').strip().lower()
                if norm_id and norm_id in existing_norm_ids:
                    existing = existing_norm_ids[norm_id]
                    # Update existing if new one has higher confidence
                    if (obj_model.final_confidence or 0) > (existing.final_confidence or 0):
                        existing.final_confidence = obj_model.final_confidence
                        existing.objective_text = obj_model.objective_text
                        existing.confidence_calc = obj_model.confidence_calc
                        existing.confidence_metadata = obj_model.confidence_metadata
                        existing.gpt_reasoning = obj_model.gpt_reasoning
                        existing.updated_at = datetime.utcnow()
                        logger.info(f"[DB_DEDUP] Updated existing '{norm_id}' with higher confidence {obj_model.final_confidence:.2f}")
                    else:
                        logger.debug(f"[DB_DEDUP] Skipped duplicate '{norm_id}' (existing conf={existing.final_confidence:.2f})")
                    skipped += 1
                else:
                    new_models.append(obj_model)
                    if norm_id:
                        existing_norm_ids[norm_id] = obj_model  # Track for within-batch dedup
            
            if skipped > 0:
                logger.info(f"[DB_DEDUP] Skipped {skipped} duplicate objectives already in DB, adding {len(new_models)} new")
            objective_models = new_models
        
        if objective_models:
            logger.info(f"[DATABASE] Calling db_session.add_all() for {len(objective_models)} objectives...")
            db_session.add_all(objective_models)
            logger.info(f"[DATABASE] Calling db_session.flush() to get IDs...")
            db_session.flush()  # Flush to get IDs
            logger.info(f"[DATABASE] ✓ Flush complete, objectives have database IDs")
        else:
            logger.info(f"[DATABASE] All objectives already exist in DB, nothing new to add")
        
        # Auto-approve objectives with >= 65% confidence
        AUTO_APPROVE_THRESHOLD = 0.65
        auto_approved_count = 0
        
        logger.info(f"[AUTO_APPROVAL] Starting auto-approval check for {len(objective_models)} objectives (threshold={AUTO_APPROVE_THRESHOLD})")
        for i, obj_model in enumerate(objective_models):
            obj_id = obj_model.objective_id_normalized or obj_model.objective_id or "UNKNOWN"
            logger.info(f"[AUTO_APPROVAL] {i+1}/{len(objective_models)}: '{obj_id}' confidence={obj_model.final_confidence:.2f}")
            if obj_model.final_confidence >= AUTO_APPROVE_THRESHOLD:
                obj_model.status = 'approved'
                auto_approved_count += 1
                logger.info(f"[AUTO_APPROVAL] ✓ APPROVED '{obj_id}'")
            else:
                logger.info(f"[AUTO_APPROVAL] ✗ PENDING '{obj_id}' (below threshold)")
        
        logger.info(f"[DATABASE] Committing {len(objective_models)} objectives to database...")
        db_session.commit()
        logger.info(f"[DATABASE] ✓ COMMITTED: Saved {len(objective_models)} objectives")
        logger.info(f"[DATABASE] ✓ Auto-approved {auto_approved_count} objectives")
    elif scan_id is None:
        logger.info(f"[DATABASE] SKIP: scan_id is None, objectives not saved (preview mode)")
    else:
        logger.warning(f"[DATABASE] NO objectives to save - skipping commit")
    
    # Step 6: Control-objective mapping is DEFERRED until after gap extraction.
    # Previously this ran here, but that caused controls to map to low-confidence
    # objectives before gap extraction could find the correct high-confidence ones.
    # The mapping now runs in the gap extraction completion callback below.
    logger.info(f"[OBJECTIVE_AUTO_MAP] DEFERRED: mapping will run after gap extraction completes")
    
    # Update progress
    if job_id and redis_client:
        try:
            job_hmset(job_id, {
                "status": "completed",
                "progress_status": f"Extracted {len(objective_models)} control objectives",
                "processed_chunks": len(chunks),
                "total_chunks": len(chunks),
                "objectives_found": len(objective_models),
                "updated_at": datetime.utcnow().isoformat(),
            }, redis_client)
        except Exception as e:
            logger.warning(f"Failed to update completion status: {e}")
    
    # Automatically trigger gap extraction after objective extraction completes
    if scan_id and len(objective_models) > 0:
        try:
            logger.info(f"[OBJECTIVE_GAP_AUTO] Starting automatic gap extraction for scan_id={scan_id}")
            import threading
            from ..routers.objective_router import run_gap_extraction_sync
            
            # Extract only Control_Descriptions section for gap extraction
            gap_text = extracted_text
            control_section = next((s for s in sections if s.get('topic') == 'Control_Descriptions'), None)
            if control_section and control_section.get('start_line') and control_section.get('end_line'):
                start_line = control_section['start_line']
                end_line = control_section['end_line']
                lines = extracted_text.split('\n')
                # Extract only the Control_Descriptions section (line numbers are 1-indexed)
                gap_text = '\n'.join(lines[start_line-1:end_line])
                logger.info(f"[OBJECTIVE_GAP_AUTO] Limiting gap extraction to Control_Descriptions section: lines {start_line}-{end_line} ({len(gap_text)} chars)")
            else:
                logger.warning(f"[OBJECTIVE_GAP_AUTO] Control_Descriptions section not found, searching full document")
            
            # Run gap extraction in background thread to avoid blocking
            def _run_gap_and_map():
                try:
                    result = run_gap_extraction_sync(scan_id, gap_text)
                    logger.info(f"[OBJECTIVE_GAP_AUTO] Gap extraction completed: {result.get('status')}")
                    
                    # CRITICAL: Map controls to objectives AFTER gap extraction.
                    # This is the definitive mapping — all objective identification
                    # (initial extraction, pattern rescan, gap extraction) is complete.
                    # Use force=True to create fresh mappings with the full objective set.
                    logger.info(f"[OBJECTIVE_GAP_AUTO] Running definitive control-objective mapping for scan_id={scan_id}")
                    from sqlalchemy import create_engine
                    from sqlalchemy.orm import sessionmaker
                    from .. import config
                    
                    sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
                    sync_engine = create_engine(sync_db_url, echo=False)
                    SessionLocal = sessionmaker(bind=sync_engine)
                    map_session = SessionLocal()
                    
                    try:
                        mappings_count = map_controls_to_objectives(
                            scan_id=scan_id,
                            db_session=map_session,
                            job_id=job_id,
                            redis_client=redis_client,
                            force=True  # Fresh mapping with complete objective set
                        )
                        logger.info(f"[OBJECTIVE_GAP_AUTO] Definitive mapping created {mappings_count} mappings")
                    finally:
                        map_session.close()
                except Exception as gap_err:
                    logger.error(f"[OBJECTIVE_GAP_AUTO] Gap extraction failed: {gap_err}")
                    # Even if gap extraction fails, still run mapping with whatever
                    # objectives we have from initial extraction + pattern rescan
                    logger.info(f"[OBJECTIVE_GAP_AUTO] Running fallback mapping despite gap failure")
                    try:
                        from sqlalchemy import create_engine
                        from sqlalchemy.orm import sessionmaker
                        from .. import config
                        
                        sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
                        sync_engine = create_engine(sync_db_url, echo=False)
                        SessionLocal = sessionmaker(bind=sync_engine)
                        fallback_session = SessionLocal()
                        try:
                            mappings_count = map_controls_to_objectives(
                                scan_id=scan_id,
                                db_session=fallback_session,
                                job_id=job_id,
                                redis_client=redis_client,
                                force=True
                            )
                            logger.info(f"[OBJECTIVE_GAP_AUTO] Fallback mapping created {mappings_count} mappings")
                        finally:
                            fallback_session.close()
                    except Exception as map_err:
                        logger.error(f"[OBJECTIVE_GAP_AUTO] Fallback mapping also failed: {map_err}")
            
            threading.Thread(
                target=_run_gap_and_map,
                name=f"gap-extract-auto-{scan_id}",
                daemon=True
            ).start()
            
        except Exception as trigger_err:
            logger.warning(f"[OBJECTIVE_GAP_AUTO] Failed to trigger: {trigger_err}")
    
    return objective_models


def _proximity_score(control_line: Optional[int], objective_line: Optional[int]) -> float:
    if not control_line or not objective_line:
        return 0.0
    max_distance = config.OBJECTIVE_MAPPING_MAX_LINE_DISTANCE
    if max_distance <= 0:
        return 0.0
    distance = abs(objective_line - control_line)
    if distance >= max_distance:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (distance / max_distance)))


def _min_page_ref(page_refs: Optional[Any]) -> Optional[int]:
    if not page_refs:
        return None
    if isinstance(page_refs, (int, float)):
        try:
            return int(page_refs)
        except Exception:
            return None
    if isinstance(page_refs, str):
        try:
            return int(page_refs.strip())
        except Exception:
            return None
    if isinstance(page_refs, list):
        pages = []
        for ref in page_refs:
            try:
                pages.append(int(str(ref).strip()))
            except Exception:
                continue
        return min(pages) if pages else None
    return None


def _all_page_refs(page_refs: Optional[Any]) -> ListType[int]:
    """Parse page_refs (JSON list, int, or str) into a sorted list of all page numbers."""
    if not page_refs:
        return []
    if isinstance(page_refs, (int, float)):
        try:
            return [int(page_refs)]
        except Exception:
            return []
    if isinstance(page_refs, str):
        try:
            return [int(page_refs.strip())]
        except Exception:
            return []
    if isinstance(page_refs, list):
        pages = []
        for ref in page_refs:
            try:
                pages.append(int(str(ref).strip()))
            except Exception:
                continue
        return sorted(set(pages))
    return []


def _page_proximity_score(control_page: Optional[int], objective_page: Optional[int]) -> float:
    if control_page is None or objective_page is None:
        return 0.0
    distance = abs(control_page - objective_page)
    return max(0.0, min(1.0, 1.0 / (1.0 + distance)))


def _parse_hierarchical_id(id_string: Optional[str]) -> Tuple[str, ListType[int]]:
    """
    Parse a hierarchical ID into prefix and numeric components.
    
    Examples:
        "CC1.1.2" -> ("CC", [1, 1, 2])
        "CC 1.1" -> ("CC", [1, 1])
        "CC-1-1" -> ("CC", [1, 1])
        "A1" -> ("A", [1])
        "CC11" -> ("CC", [11])  # Single number
    
    Returns:
        Tuple of (prefix, numeric_parts)
    """
    if not id_string:
        return ("", [])
    
    # Remove extra whitespace
    id_clean = ' '.join(id_string.split())
    
    # Extract prefix (letters) and numeric part
    match = re.match(r'^([A-Za-z]+)[\s\-\.]*(.+)$', id_clean)
    if not match:
        return ("", [])
    
    prefix = match.group(1).upper()
    numeric_str = match.group(2)
    
    # Split on dots, dashes, or spaces
    parts = re.split(r'[\.\-\s]+', numeric_str)
    
    # Convert to integers
    numeric_parts = []
    for part in parts:
        if part.strip():
            try:
                numeric_parts.append(int(part.strip()))
            except ValueError:
                # Skip non-numeric parts
                continue
    
    return (prefix, numeric_parts)


def _calculate_line_proximity_score(
    control_line_ref: Optional[int],
    objective_line_ref: Optional[int],
    control_id: Optional[str] = None,
    objective_id: Optional[str] = None,
    all_objectives: Optional[List[ControlObjective]] = None
) -> Tuple[float, str]:
    """
    Calculate line proximity score with table-aware logic.
    
    Args:
        control_line_ref: Line number of control
        objective_line_ref: Line number of objective
        control_id: ID of control (for pattern matching)
        objective_id: ID of objective (for pattern matching)
        all_objectives: All objectives for pattern-based boost
    
    Returns:
        Tuple of (score, explanation_string)
    """
    if control_line_ref is None or objective_line_ref is None:
        return (0.0, "Line refs unavailable")
    
    distance = control_line_ref - objective_line_ref
    score = 0.0
    explanation = ""
    
    # Check if controls share same objective ID pattern (boost score)
    pattern_boost = 0.0
    if control_id and objective_id and all_objectives:
        # Extract pattern from objective ID (e.g., "CC1" from "CC1.1")
        obj_prefix, obj_parts = _parse_hierarchical_id(objective_id)
        if obj_prefix and obj_parts and len(obj_parts) > 0:
            # Count how many other objectives share this pattern
            pattern_count = 0
            for obj in all_objectives:
                if obj.objective_id:
                    other_prefix, other_parts = _parse_hierarchical_id(obj.objective_id)
                    if (other_prefix == obj_prefix and 
                        other_parts and len(other_parts) > 0 and
                        other_parts[0] == obj_parts[0]):  # Same first number (e.g., CC1.x)
                        pattern_count += 1
            
            # If multiple objectives share pattern, boost proximity score
            if pattern_count >= 2:
                pattern_boost = 0.05
                explanation += f" [+0.05 pattern boost: {pattern_count} objectives share {obj_prefix}{obj_parts[0]}.x pattern]"
    
    if distance > 0:
        # Normal case: objective BEFORE control (objective is heading above controls)
        if distance <= 10:
            score = 0.3
            explanation = f"{distance} lines before" + explanation
        elif distance <= 20:
            score = 0.2
            explanation = f"{distance} lines before" + explanation
        elif distance <= 30:
            score = 0.1
            explanation = f"{distance} lines before" + explanation
        else:
            score = 0.0
            explanation = f"{distance} lines before (too far)" + explanation
    elif distance < 0:
        # Objective AFTER control — rare, only in table/layout edge cases
        abs_distance = abs(distance)
        if abs_distance <= config.MAPPING_TABLE_STRUCTURE_LINE_THRESHOLD:
            score = 0.2
            explanation = f"{abs_distance} lines after (table structure)"
        elif abs_distance <= 10:
            score = 0.1
            explanation = f"{abs_distance} lines after"
        else:
            score = 0.0
            explanation = f"{abs_distance} lines after (too far)"
    else:
        # Same line
        score = 0.3
        explanation = "same line"
    
    score += pattern_boost
    return (min(score, 0.35), explanation)  # Cap at 0.35 max


def _calculate_hierarchical_id_score(
    control_id: Optional[str],
    objective_id: Optional[str]
) -> Tuple[float, str]:
    """
    Calculate ID alignment score with hierarchical matching.
    
    Handles parent-child relationships:
        CC1.1.2 → CC1.1 (parent match)
        CC1.1.2 → CC1 (grandparent match)
        CC1.1.2 → CC1.1.2 (exact match)
    
    Returns:
        Tuple of (score, explanation_string)
    """
    if not control_id or not objective_id:
        return (0.0, "Missing ID")
    
    # Parse both IDs
    ctrl_prefix, ctrl_parts = _parse_hierarchical_id(control_id)
    obj_prefix, obj_parts = _parse_hierarchical_id(objective_id)
    
    if not ctrl_prefix or not ctrl_parts or not obj_prefix or not obj_parts:
        # Fallback to simple prefix matching
        norm_control = _normalize_id_value(control_id)
        norm_objective = _normalize_id_value(objective_id)
        if norm_control.startswith(norm_objective):
            return (0.3, f"{control_id}→{objective_id} (prefix)")
        return (0.0, "No ID match")
    
    # Prefixes must match
    if ctrl_prefix != obj_prefix:
        return (0.0, f"Different prefixes ({ctrl_prefix} vs {obj_prefix})")
    
    # Check hierarchy levels
    if ctrl_parts == obj_parts:
        # Exact match
        return (0.6, f"{control_id}={objective_id} (exact)")
    elif len(obj_parts) < len(ctrl_parts):
        # Objective is parent of control (e.g., CC1.1 ← CC1.1.2)
        if ctrl_parts[:len(obj_parts)] == obj_parts:
            # Direct parent match
            levels_diff = len(ctrl_parts) - len(obj_parts)
            if levels_diff == 1:
                return (0.5, f"{control_id}→{objective_id} (parent)")
            else:
                return (0.4, f"{control_id}→{objective_id} (ancestor, {levels_diff} levels)")
    elif len(obj_parts) > len(ctrl_parts):
        # Control is parent of objective (unusual but possible)
        if obj_parts[:len(ctrl_parts)] == ctrl_parts:
            return (0.4, f"{control_id}←{objective_id} (child)")
    
    # Check if first N parts match (sibling relationship)
    min_len = min(len(ctrl_parts), len(obj_parts))
    matching_parts = 0
    for i in range(min_len):
        if ctrl_parts[i] == obj_parts[i]:
            matching_parts += 1
        else:
            break
    
    if matching_parts > 0:
        match_ratio = matching_parts / max(len(ctrl_parts), len(obj_parts))
        if match_ratio >= 0.5:
            return (0.3, f"{control_id}≈{objective_id} (partial: {matching_parts}/{min_len})")
    
    return (0.0, f"No hierarchy match")


def _calculate_objective_confidence_boost(objective_gpt_confidence: Optional[float]) -> Tuple[float, str]:
    """
    Calculate confidence boost based on objective's GPT extraction confidence.
    
    Returns:
        Tuple of (boost_score, explanation_string)
    """
    if objective_gpt_confidence is None:
        return (0.0, "No GPT confidence")
    
    if objective_gpt_confidence >= 0.8:
        return (0.1, f"GPT conf={objective_gpt_confidence:.2f} (high)")
    elif objective_gpt_confidence >= 0.6:
        return (0.05, f"GPT conf={objective_gpt_confidence:.2f} (medium)")
    else:
        return (0.0, f"GPT conf={objective_gpt_confidence:.2f} (low)")


def _normalize_id_value(value: Optional[str]) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _id_alignment_score(control_id: Optional[str], objective_id: Optional[str]) -> float:
    if not control_id or not objective_id:
        return 0.0
    norm_control = _normalize_id_value(control_id)
    norm_objective = _normalize_id_value(objective_id)
    if not norm_control or not norm_objective:
        return 0.0

    if norm_control.startswith(norm_objective):
        return 0.5

    try:
        from difflib import SequenceMatcher
        ratio = SequenceMatcher(None, norm_control, norm_objective).ratio()
        return 0.5 if ratio >= config.OBJECTIVE_MAPPING_ID_SIMILARITY_THRESHOLD else 0.0
    except Exception:
        return 0.0


def _control_page_proximity_score(control_page: Optional[int], objective_page: Optional[int]) -> float:
    """Score page proximity. Objectives typically appear BEFORE the control (like headings).
    Allowance: 0-2 pages before (strong), 3 pages before (weak), 1 page after (edge case)."""
    if control_page is None or objective_page is None:
        return 0.0

    # distance > 0 means objective is BEFORE control (normal: objective is heading above controls)
    # distance < 0 means objective is AFTER control (rare edge case)
    distance = control_page - objective_page

    if distance == 0:
        return 0.6  # Same page — strongest signal
    elif distance == 1:
        return 0.5  # Objective 1 page before control — very common
    elif distance == 2:
        return 0.3  # Objective 2 pages before — still reasonable
    elif distance == 3:
        return 0.1  # Objective 3 pages before — weak but possible
    elif distance == -1:
        return 0.1  # Objective 1 page AFTER control — rare table/layout edge case
    else:
        return 0.0  # Too far in either direction


def _select_candidate_objectives(
    objectives: List[ControlObjective],
    control_line: Optional[int],
    control_page: Optional[int]
) -> List[ControlObjective]:
    limit = max(1, config.OBJECTIVE_MAPPING_CANDIDATE_LIMIT)

    if control_page is not None:
        scored_by_page = []
        for obj in objectives:
            obj_page = _min_page_ref(obj.page_refs)
            if obj_page is None:
                continue
            if obj_page > control_page + 1:  # At most 1 page after (rare edge case)
                continue
            if obj_page < control_page - 3:  # At most 3 pages before (objective as heading)
                continue
            after_flag = 1 if obj_page > control_page else 0
            distance = abs(control_page - obj_page)
            scored_by_page.append((after_flag, distance, obj))

        if scored_by_page:
            scored_by_page.sort(key=lambda item: (item[0], item[1]))
            return [obj for _, _, obj in scored_by_page[:limit]]

    if control_line:
        scored_by_distance = [
            (abs(obj.line_ref - control_line), obj)
            for obj in objectives
            if obj.line_ref is not None
        ]
        if scored_by_distance:
            scored_by_distance.sort(key=lambda item: item[0])
            return [obj for _, obj in scored_by_distance[:limit]]

    # Fallback: top objectives by final confidence
    return sorted(
        objectives,
        key=lambda obj: obj.final_confidence or 0.0,
        reverse=True
    )[:limit]


# ============================================================================
# Phase B: Document Structure Map
# ============================================================================

def build_document_structure_map(
    controls: List[Control],
    objectives: List[ControlObjective],
) -> List[Dict[str, Any]]:
    """
    Build an interleaved document-order map of objectives and controls.
    
    SOC reports follow a consistent pattern: each objective heading is
    followed by the controls that fulfil it, then the next objective, etc.
    This function reconstructs that ordering from line-ref data so the
    mapper can exploit structural proximity (Phase C / Tier 0).
    
    Each entry carries:
        {"type": "objective"|"control", "line": int, "db_id": int,
         "text_id": str|None}
    
    Controls and objectives with multiple line positions (all_line_refs)
    emit one entry per position so that a control appearing under two
    objectives generates two structural hints.
    
    Returns entries sorted ascending by line number.
    """
    entries: List[Dict[str, Any]] = []

    for obj in objectives:
        lines = obj.all_line_refs or ([obj.line_ref] if obj.line_ref is not None else [])
        for ln in lines:
            if ln is not None:
                entries.append({
                    "type": "objective",
                    "line": int(ln),
                    "db_id": obj.id,
                    "text_id": obj.objective_id,
                })

    for ctrl in controls:
        lines = ctrl.all_line_refs or ([ctrl.control_line_ref] if ctrl.control_line_ref is not None else [])
        for ln in lines:
            if ln is not None:
                entries.append({
                    "type": "control",
                    "line": int(ln),
                    "db_id": ctrl.id,
                    "text_id": ctrl.control_id,
                })

    # Stable sort: by line number, then objectives first (they're headings).
    entries.sort(key=lambda e: (e["line"], 0 if e["type"] == "objective" else 1))

    logger.info(
        f"[STRUCTURE_MAP] Built document structure map: "
        f"{sum(1 for e in entries if e['type']=='objective')} objective entries, "
        f"{sum(1 for e in entries if e['type']=='control')} control entries"
    )
    return entries


def _find_structural_objective(
    control_db_id: int,
    structure_map: List[Dict[str, Any]],
) -> Optional[int]:
    """
    Given a control's DB id, walk backwards through the structure map to
    find the nearest preceding objective.  Returns the objective's DB id
    or None if no preceding objective exists.
    
    If the control appears at multiple positions, return the objective for
    the *first* (earliest) occurrence — the most "canonical" one.
    """
    # Collect all indices where this control appears
    ctrl_indices = [
        i for i, e in enumerate(structure_map)
        if e["type"] == "control" and e["db_id"] == control_db_id
    ]
    if not ctrl_indices:
        return None

    # Use the first (earliest-in-document) occurrence
    first_idx = ctrl_indices[0]

    # Walk backwards from that position to find the nearest objective
    for i in range(first_idx - 1, -1, -1):
        if structure_map[i]["type"] == "objective":
            return structure_map[i]["db_id"]

    return None


def _find_all_structural_objectives(
    control_db_id: int,
    structure_map: List[Dict[str, Any]],
) -> List[int]:
    """
    For controls with multiple positions (all_line_refs), find the nearest
    preceding objective for *each* occurrence.  Returns a deduplicated
    list of objective DB ids.
    """
    ctrl_indices = [
        i for i, e in enumerate(structure_map)
        if e["type"] == "control" and e["db_id"] == control_db_id
    ]
    if not ctrl_indices:
        return []

    obj_ids: List[int] = []
    seen = set()
    for ci in ctrl_indices:
        for i in range(ci - 1, -1, -1):
            if structure_map[i]["type"] == "objective":
                oid = structure_map[i]["db_id"]
                if oid not in seen:
                    seen.add(oid)
                    obj_ids.append(oid)
                break  # found the nearest for this occurrence
    return obj_ids


def map_controls_to_objectives(
    scan_id: int,
    db_session: Session,
    job_id: Optional[str] = None,
    redis_client: Optional[Any] = None,
    force: bool = False
) -> int:
    """
    Create many-to-many mappings between controls and objectives.
    Uses proximity-based automatic mapping with GPT validation.
    
    Args:
        scan_id: Scan ID to process
        db_session: SQLAlchemy session
        job_id: Redis job ID for progress updates
        redis_client: Redis client for progress tracking
        
    Returns:
        Number of mappings created
    """
    logger.info(f"Mapping controls to objectives for scan_id={scan_id}")
    
    # Update progress
    if job_id and redis_client:
        try:
            job_hmset(job_id, {
                "progress_status": "Mapping controls to objectives...",
            }, redis_client)
        except Exception as e:
            logger.warning(f"Failed to update mapping progress: {e}")
    
    # Fetch objectives and controls for this scan
    # Only map to APPROVED objectives (high-confidence, validated)
    # Low-confidence pending objectives (e.g. controls misclassified as objectives)
    # should NOT receive mappings — they clutter the coverage view
    objectives = db_session.query(ControlObjective).filter(
        ControlObjective.scan_id == scan_id,
        ControlObjective.status == 'approved'
    ).all()
    
    # Only map controls with meaningful confidence (0.50+) AND a control_id.
    # DESIGN PRINCIPLE: Low confidence = "marked for deletion" (soft-delete for audit trail).
    # Controls with low confidence (ignored, rejected, or manually downgraded) are kept in DB
    # but excluded from active mappings. Only map controls with meaningful confidence (>= 0.50).
    # Controls without a control_id are spurious extractions (test procedure text, objective
    # restatements, etc.) and should never be mapped to objectives.
    controls = (
        db_session.query(Control)
        .filter_by(scan_id=scan_id)
        .filter(Control.control_confidence >= 0.50)
        .filter(Control.control_id != None)  # noqa: E711 — SQLAlchemy IS NOT NULL
        .filter(Control.control_id != '')
        .all()
    )
    
    if not objectives or not controls:
        logger.info("No approved objectives or controls found, skipping mapping")
        return 0
    
    logger.info(f"Found {len(objectives)} approved objectives and {len(controls)} controls for mapping")
    
    # Phase B: Build document structure map for Tier 0
    structure_map = build_document_structure_map(controls, objectives)
    # Pre-build objective lookup by DB id for Tier 0
    objectives_by_db_id: Dict[int, ControlObjective] = {obj.id: obj for obj in objectives}
    
    # Phase D: Load feedback examples once for few-shot prompt injection
    feedback_text = _get_feedback_examples_text(scan_id, db_session)
    if feedback_text:
        logger.info(f"[FEEDBACK] Loaded analyst feedback for few-shot injection ({len(feedback_text)} chars)")
    
    mappings_created = 0
    mappings_updated = 0
    all_new_mappings = []  # Collect all mappings, then bulk upsert at the end
    
    control_ids = [control.id for control in controls]
    existing_mappings = db_session.query(ControlObjectiveMapping).filter(
        ControlObjectiveMapping.control_id.in_(control_ids)
    ).all()
    mappings_by_control: Dict[int, List[ControlObjectiveMapping]] = {}
    for mapping in existing_mappings:
        mappings_by_control.setdefault(mapping.control_id, []).append(mapping)

    # Thread-safe shared alignment cache to avoid redundant GPT calls
    # Key: "control_desc_hash:objective_text_hash" -> (score, reasoning)
    import threading as _threading
    _alignment_cache: Dict[str, tuple] = {}
    _alignment_cache_lock = _threading.Lock()
    
    class _ThreadSafeAlignmentCache:
        """Thread-safe wrapper for the alignment score cache."""
        def __init__(self):
            self._cache: Dict[str, tuple] = {}
            self._lock = _threading.Lock()
            self._hits = 0
            self._misses = 0
        
        def __contains__(self, key):
            with self._lock:
                found = key in self._cache
                if found:
                    self._hits += 1
                else:
                    self._misses += 1
                return found
        
        def __getitem__(self, key):
            with self._lock:
                return self._cache[key]
        
        def __setitem__(self, key, value):
            with self._lock:
                self._cache[key] = value
        
        def stats(self):
            with self._lock:
                return self._hits, self._misses, len(self._cache)
    
    alignment_cache = _ThreadSafeAlignmentCache()

    # Helper function to map single control (for parallelization)
    def map_single_control_through_tiers(control) -> Tuple[List[ControlObjectiveMapping], int]:
        """
        Map one control through the waterfall tiers.
        Returns (new_mappings_list, updates_count)
        """
        new_mappings = []
        updates_count = 0
        
        existing_for_control = mappings_by_control.get(control.id, [])

        if existing_for_control and not force:
            return (new_mappings, updates_count)

        if force and existing_for_control:
            for mapping in existing_for_control:
                db_session.delete(mapping)

        control_line = control.control_line_ref
        control_page = _min_page_ref(control.control_page_refs)
        
        # Collect ALL candidate mappings across tiers (multi-objective support)
        # Each candidate: (combined_score, obj, tier_name, justification, scores_dict)
        all_candidates = []
        # Track which objective IDs we've already scored to avoid duplicates
        scored_objective_ids = set()
        
        # ===== TIER 0: Document Structure (Phase C) =====
        # Uses the interleaved document-order map to find objectives that
        # structurally "own" this control (control appears right after
        # objective heading in the PDF).  High confidence because SOC
        # reports follow a strict objective → controls structure.
        if structure_map:
            structural_obj_ids = _find_all_structural_objectives(control.id, structure_map)
            if structural_obj_ids:
                structural_objs = [
                    (objectives_by_db_id[oid], 1.0, "structural")
                    for oid in structural_obj_ids
                    if oid in objectives_by_db_id
                ]
                if structural_objs:
                    # GPT-validate structural candidates to filter false positives
                    batch_scores = calculate_alignment_scores_batch(
                        control.control_desc or "",
                        structural_objs,
                        alignment_cache=alignment_cache,
                        feedback_text=feedback_text,
                    )
                    for obj, _, _ in structural_objs:
                        if obj.id in batch_scores:
                            gpt_score, gpt_reasoning = batch_scores[obj.id]
                            # Structure provides high base confidence (0.6 weight),
                            # GPT validation prevents false positives (0.4 weight).
                            combined_score = 0.6 + (gpt_score * 0.4)
                            if combined_score > config.OBJECTIVE_MAPPING_TIER0_MIN_SCORE and gpt_score >= config.OBJECTIVE_MAPPING_TIER0_GPT_FLOOR:
                                justification = (
                                    f"Tier 0 (Document Structure): structural=1.00 + "
                                    f"GPT={gpt_score:.2f} = {combined_score:.2f}"
                                )
                                all_candidates.append((combined_score, obj, justification, {
                                    'page_proximity_score': 0.0,
                                    'line_proximity_score': 0.0,
                                    'gpt_alignment_score': gpt_score,
                                    'id_alignment_score': 0.0,
                                }))
                                scored_objective_ids.add(obj.objective_id)
                                logger.debug(
                                    f"  Tier 0: {control.control_id} → {obj.objective_id} "
                                    f"(structural + GPT={gpt_score:.2f} = {combined_score:.2f})"
                                )
        
        # ===== TIER 1: ID Hierarchy Matching =====
        if config.ENABLE_HIERARCHICAL_ID_MATCHING:
            id_matched_objectives = []
            for obj in objectives:
                id_score, id_explanation = _calculate_hierarchical_id_score(
                    control.control_id,
                    obj.objective_id
                )
                if id_score >= 0.3:  # Any hierarchical relationship
                    id_matched_objectives.append((obj, id_score, id_explanation))
            
            if id_matched_objectives:
                logger.debug(f"Control {control.control_id}: Tier 1 - {len(id_matched_objectives)} ID-matched objectives")
                
                batch_scores = calculate_alignment_scores_batch(
                    control.control_desc or "",
                    id_matched_objectives,
                    alignment_cache=alignment_cache,
                    feedback_text=feedback_text,
                )
                
                for obj, id_score, id_explanation in id_matched_objectives:
                    if obj.id in batch_scores:
                        gpt_score, gpt_reasoning = batch_scores[obj.id]
                        combined_score = (id_score * 0.7) + (gpt_score * 0.3)
                        logger.debug(f"  → Obj {obj.objective_id}: id={id_score:.2f}, gpt={gpt_score:.2f}, combined={combined_score:.2f}")
                        
                        if combined_score > config.OBJECTIVE_MAPPING_TIER1_MIN_SCORE:
                            justification = f"Tier 1 (ID Hierarchy): ID={id_score:.2f} ({id_explanation}) + GPT={gpt_score:.2f} = {combined_score:.2f}"
                            all_candidates.append((combined_score, obj, justification, {
                                'page_proximity_score': 0.0, 'line_proximity_score': 0.0,
                                'gpt_alignment_score': gpt_score, 'id_alignment_score': id_score,
                            }))
                            scored_objective_ids.add(obj.objective_id)
        
        # ===== TIER 2: Line Proximity =====
        if control_line:
            line_nearby_objectives = []
            for obj in objectives:
                obj_line = obj.line_ref
                if obj_line:
                    signed_distance = control_line - obj_line
                    if signed_distance < -10 or signed_distance > 30:
                        continue
                    line_distance = abs(signed_distance)
                    if line_distance <= 30:
                        line_score = max(0.0, 1.0 - (line_distance / 30.0))
                        if line_score >= 0.1:
                            if obj_line > control_line:
                                line_explanation = f"{obj_line - control_line}L after"
                            elif obj_line == control_line:
                                line_explanation = "same line"
                            else:
                                line_explanation = f"{control_line - obj_line}L before"
                            line_nearby_objectives.append((obj, line_score, line_explanation))
            
            if line_nearby_objectives:
                logger.debug(f"Control {control.control_id}: Tier 2 - {len(line_nearby_objectives)} line-nearby objectives")
                
                batch_scores = calculate_alignment_scores_batch(
                    control.control_desc or "",
                    line_nearby_objectives,
                    alignment_cache=alignment_cache,
                    feedback_text=feedback_text,
                )
                
                for obj, line_score, line_explanation in line_nearby_objectives:
                    if obj.id in batch_scores:
                        gpt_score, gpt_reasoning = batch_scores[obj.id]
                        combined_score = (line_score * 0.4) + (gpt_score * 0.6)
                        logger.debug(f"  → Obj {obj.objective_id}: line={line_score:.2f}, gpt={gpt_score:.2f}, combined={combined_score:.2f}")
                        
                        if combined_score > config.OBJECTIVE_MAPPING_TIER2_MIN_SCORE:
                            justification = f"Tier 2 (Line Proximity): Line={line_score:.2f} ({line_explanation}) + GPT={gpt_score:.2f} = {combined_score:.2f}"
                            all_candidates.append((combined_score, obj, justification, {
                                'page_proximity_score': 0.0, 'line_proximity_score': line_score,
                                'gpt_alignment_score': gpt_score, 'id_alignment_score': 0.0,
                            }))
                            scored_objective_ids.add(obj.objective_id)
        
        # ===== TIER 3: Page Proximity (all-pages cross-product) =====
        # Check ALL pages of both control and objective, not just the minimum page.
        # Many controls span multiple pages (e.g. referenced on pages [54, 57, 111]);
        # using only the min page misses objectives that share a later page.
        control_pages = _all_page_refs(control.control_page_refs)
        max_page_dist = config.OBJECTIVE_MAPPING_TIER3_MAX_PAGE_DISTANCE
        if control_pages:
            page_nearby_objectives = []
            for obj in objectives:
                obj_pages = _all_page_refs(obj.page_refs)
                if not obj_pages:
                    continue
                # Find best (minimum) page distance across all page pairs
                best_distance = None
                best_ctrl_pg = None
                best_obj_pg = None
                for cp in control_pages:
                    for op in obj_pages:
                        d = abs(cp - op)
                        if best_distance is None or d < best_distance:
                            best_distance = d
                            best_ctrl_pg = cp
                            best_obj_pg = op
                if best_distance is not None and best_distance <= max_page_dist:
                    page_score = _control_page_proximity_score(best_ctrl_pg, best_obj_pg)
                    if page_score >= 0.1:
                        if best_obj_pg > best_ctrl_pg:
                            page_explanation = f"{best_obj_pg - best_ctrl_pg}pg after (pg {best_ctrl_pg}↔{best_obj_pg})"
                        elif best_obj_pg == best_ctrl_pg:
                            page_explanation = f"same page ({best_ctrl_pg})"
                        else:
                            page_explanation = f"{best_ctrl_pg - best_obj_pg}pg before (pg {best_ctrl_pg}↔{best_obj_pg})"
                        page_nearby_objectives.append((obj, page_score, page_explanation))
            
            if page_nearby_objectives:
                logger.debug(f"Control {control.control_id}: Tier 3 - {len(page_nearby_objectives)} page-nearby objectives (all-pages)")
                
                batch_scores = calculate_alignment_scores_batch(
                    control.control_desc or "",
                    page_nearby_objectives,
                    alignment_cache=alignment_cache,
                    feedback_text=feedback_text,
                )
                
                for obj, page_score, page_explanation in page_nearby_objectives:
                    if obj.id in batch_scores:
                        gpt_score, gpt_reasoning = batch_scores[obj.id]
                        combined_score = (page_score * 0.3) + (gpt_score * 0.7)
                        logger.debug(f"  → Obj {obj.objective_id}: page={page_score:.2f}, gpt={gpt_score:.2f}, combined={combined_score:.2f}")
                        
                        if combined_score > config.OBJECTIVE_MAPPING_TIER3_MIN_SCORE:
                            justification = f"Tier 3 (Page Proximity): Page={page_score:.2f} ({page_explanation}) + GPT={gpt_score:.2f} = {combined_score:.2f}"
                            all_candidates.append((combined_score, obj, justification, {
                                'page_proximity_score': page_score, 'line_proximity_score': 0.0,
                                'gpt_alignment_score': gpt_score, 'id_alignment_score': 0.0,
                            }))
                            scored_objective_ids.add(obj.objective_id)
        
        # ===== Create mappings from all candidates =====
        # Deduplicate candidates by objective_id (keep highest score per objective)
        best_by_objective: Dict[str, tuple] = {}
        for combined_score, obj, justification, scores_dict in all_candidates:
            obj_key = obj.objective_id or str(obj.id)
            if obj_key not in best_by_objective or combined_score > best_by_objective[obj_key][0]:
                best_by_objective[obj_key] = (combined_score, obj, justification, scores_dict)
        
        if best_by_objective:
            # Sort by score descending — highest is primary
            sorted_candidates = sorted(best_by_objective.values(), key=lambda x: x[0], reverse=True)
            
            for idx, (combined_score, obj, justification, scores_dict) in enumerate(sorted_candidates):
                mapping = ControlObjectiveMapping(
                    control_id=control.id,
                    objective_id=obj.id,
                    mapping_confidence=combined_score,
                    mapping_method='auto_tiered',
                    is_primary=False,
                    page_proximity_score=scores_dict['page_proximity_score'],
                    line_proximity_score=scores_dict['line_proximity_score'],
                    gpt_alignment_score=scores_dict['gpt_alignment_score'],
                    id_alignment_score=scores_dict['id_alignment_score'],
                    objective_gpt_confidence_boost=0.0,
                    mapping_justification=justification,
                    created_at=datetime.utcnow()
                )
                new_mappings.append(mapping)
                logger.debug(f"✓ mapping: {control.control_id} → {obj.objective_id} (score={combined_score:.2f}, {justification[:50]})")
            
            logger.debug(f"Control {control.control_id}: {len(sorted_candidates)} objective mapping(s) created")
        else:
            logger.debug(f"Control {control.control_id}: No mapping after all tiers - UNMAPPED")
        
        return (new_mappings, updates_count)
    
    # Parallel or sequential processing based on feature flag
    if config.ENABLE_PARALLEL_OBJECTIVE_MAPPING and len(controls) > 1:
        logger.info(f"[OBJECTIVES] Parallel mapping {len(controls)} controls with {config.OBJECTIVE_WORKER_THREADS} workers")
        
        with ThreadPoolExecutor(max_workers=config.OBJECTIVE_WORKER_THREADS) as executor:
            future_to_control = {
                executor.submit(map_single_control_through_tiers, control): control.control_id
                for control in controls
            }
            
            for future in as_completed(future_to_control):
                control_id = future_to_control[future]
                try:
                    new_mappings, updates_count = future.result()
                    all_new_mappings.extend(new_mappings)
                    mappings_updated += updates_count
                except Exception as e:
                    logger.error(f"Mapping failed for control {control_id}: {e}")
    else:
        # Sequential fallback (original code)
        logger.info(f"[OBJECTIVES] Sequential mapping {len(controls)} controls")
        
        for control in controls:
            new_mappings, updates_count = map_single_control_through_tiers(control)
            all_new_mappings.extend(new_mappings)
            mappings_updated += updates_count
    
    # Bulk upsert using PostgreSQL ON CONFLICT to prevent duplicates from race conditions
    if all_new_mappings:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        for mapping in all_new_mappings:
            stmt = pg_insert(ControlObjectiveMapping).values(
                control_id=mapping.control_id,
                objective_id=mapping.objective_id,
                mapping_confidence=mapping.mapping_confidence,
                mapping_method=mapping.mapping_method,
                is_primary=mapping.is_primary,
                page_proximity_score=mapping.page_proximity_score,
                line_proximity_score=mapping.line_proximity_score,
                gpt_alignment_score=mapping.gpt_alignment_score,
                id_alignment_score=mapping.id_alignment_score,
                objective_gpt_confidence_boost=mapping.objective_gpt_confidence_boost,
                mapping_justification=mapping.mapping_justification,
                created_at=mapping.created_at,
            ).on_conflict_do_update(
                constraint='uq_control_objective_mapping',
                set_={
                    'mapping_confidence': mapping.mapping_confidence,
                    'mapping_method': mapping.mapping_method,
                    'is_primary': mapping.is_primary,
                    'page_proximity_score': mapping.page_proximity_score,
                    'line_proximity_score': mapping.line_proximity_score,
                    'gpt_alignment_score': mapping.gpt_alignment_score,
                    'id_alignment_score': mapping.id_alignment_score,
                    'objective_gpt_confidence_boost': mapping.objective_gpt_confidence_boost,
                    'mapping_justification': mapping.mapping_justification,
                }
            )
            db_session.execute(stmt)
            mappings_created += 1
        logger.info(f"Upserted {mappings_created} control-objective mappings (duplicates merged)")

    # Commit mappings
    if mappings_created > 0 or mappings_updated > 0:
        db_session.commit()
        if mappings_created > 0:
            logger.info(f"Created {mappings_created} control-objective mappings")
        if mappings_updated > 0:
            logger.info(f"Updated {mappings_updated} control-objective mappings")
        
        # Update alignment confidence for objectives
        update_objective_alignment_confidence(scan_id, db_session)
    
    # Log alignment cache performance
    cache_hits, cache_misses, cache_size = alignment_cache.stats()
    if cache_hits > 0 or cache_misses > 0:
        hit_rate = cache_hits / (cache_hits + cache_misses) * 100 if (cache_hits + cache_misses) > 0 else 0
        logger.info(
            f"[ALIGNMENT_CACHE] Performance: {cache_hits} hits, {cache_misses} misses, "
            f"{hit_rate:.1f}% hit rate, {cache_size} entries. "
            f"Estimated {cache_hits} GPT calls saved."
        )
    
    # Update progress
    if job_id and redis_client:
        try:
            job_hmset(job_id, {
                "progress_status": f"Mapped {mappings_created} control-objective relationships",
            }, redis_client)
        except Exception as e:
            logger.warning(f"Failed to update mapping completion: {e}")
    
    return mappings_created


# ============================================================================
# Phase D: Feedback-driven few-shot prompt injection
# ============================================================================

def _get_feedback_examples_text(
    scan_id: int,
    db_session: Session,
    max_examples: int = 8,
) -> str:
    """
    Query MappingFeedback for this scan (and optionally global) and
    format as a few-shot block that can be injected into the alignment prompt.
    
    Returns an empty string if no feedback exists.
    """
    try:
        # First try scan-specific feedback
        rows = (
            db_session.query(MappingFeedback)
            .filter(MappingFeedback.scan_id == scan_id)
            .order_by(MappingFeedback.created_at.desc())
            .limit(max_examples)
            .all()
        )
        
        # If scan has < 3 examples, supplement with global feedback
        if len(rows) < 3:
            global_rows = (
                db_session.query(MappingFeedback)
                .filter(MappingFeedback.scan_id != scan_id)
                .order_by(MappingFeedback.created_at.desc())
                .limit(max_examples - len(rows))
                .all()
            )
            rows.extend(global_rows)
        
        if not rows:
            return ""
        
        lines = [
            "\n## Analyst Feedback (use these corrections to calibrate your scoring):"
        ]
        for fb in rows:
            ctrl_text = fb.control_id_text or "?"
            obj_text = fb.objective_id_text or "?"
            desc_snip = (fb.control_desc_snippet or "")[:120]
            obj_snip = (fb.objective_text_snippet or "")[:120]
            
            if fb.action == "confirmed":
                lines.append(
                    f"- CORRECT mapping: Control {ctrl_text} (\"{desc_snip}\") → "
                    f"Objective {obj_text} (\"{obj_snip}\") [confidence was {fb.original_confidence or '?'}]"
                )
            elif fb.action == "removed":
                lines.append(
                    f"- WRONG mapping (removed): Control {ctrl_text} (\"{desc_snip}\") should NOT map to "
                    f"Objective {obj_text} (\"{obj_snip}\") [auto-confidence was {fb.original_confidence or '?'}]"
                )
            elif fb.action == "added":
                lines.append(
                    f"- MISSING mapping (added manually): Control {ctrl_text} (\"{desc_snip}\") → "
                    f"Objective {obj_text} (\"{obj_snip}\")"
                )
            elif fb.action == "redirected":
                redir_text = fb.redirected_to_objective_text or "?"
                lines.append(
                    f"- REDIRECTED: Control {ctrl_text} was moved FROM Objective {obj_text} "
                    f"TO \"{redir_text[:120]}\""
                )
        
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[FEEDBACK] Failed to load feedback examples: {e}")
        return ""


def calculate_alignment_score(objective_text: str, control_desc: str) -> Tuple[float, str]:
    """
    Calculate alignment score between objective and control using GPT.
    
    Args:
        objective_text: Objective text
        control_desc: Control description
        
    Returns:
        (alignment_score, reasoning) tuple
    """
    prompt = config.OBJECTIVE_CONTROL_ALIGNMENT_PROMPT.format(
        objective_text=objective_text,
        control_desc=control_desc
    )
    
    try:
        response = gpt_extract(
            prompt=prompt,
            extractor_name="objective_alignment",
            override_model=OBJECTIVE_ALIGNMENT_MODEL
        )
        
        result = json.loads(response)
        score = result.get('alignment_score', 0.0)
        reasoning = result.get('reasoning', '')
        
        return score, reasoning
        
    except Exception as e:
        logger.error(f"Alignment calculation failed: {e}")
        return 0.0, "Alignment calculation failed"


def calculate_alignment_scores_batch(
    control_desc: str,
    objectives: List[tuple],  # List of (obj, metadata_score, metadata_explanation)
    max_batch_size: int = 15,
    max_tokens_per_batch: int = 7000,
    alignment_cache: Optional[Dict[str, tuple]] = None,
    feedback_text: str = "",
) -> Dict[int, tuple]:  # Returns {objective_id: (score, reasoning)}
    """
    Score multiple objectives against one control in a single GPT call.
    Uses dynamic token-based batching to handle large objective lists.
    
    Args:
        control_desc: The control description text
        objectives: List of (objective_obj, metadata_score, metadata_explanation) tuples
        max_batch_size: Maximum objectives per batch (default 15)
        max_tokens_per_batch: Maximum tokens per batch (default 7000)
        alignment_cache: Optional shared cache dict mapping 
                         "control_hash:objective_hash" -> (score, reasoning)
                         to avoid redundant GPT calls across controls
    
    Returns:
        Dictionary mapping objective_id to (alignment_score, reasoning)
    """
    if not objectives:
        return {}
    
    # Check cache for already-scored pairs
    control_hash = hashlib.md5((control_desc or "").encode()).hexdigest()[:12]
    cached_scores = {}
    uncached_objectives = []
    
    if alignment_cache is not None:
        for obj, meta_score, meta_explanation in objectives:
            obj_hash = hashlib.md5((obj.objective_text or "").encode()).hexdigest()[:12]
            cache_key = f"{control_hash}:{obj_hash}"
            if cache_key in alignment_cache:
                cached_scores[obj.id] = alignment_cache[cache_key]
            else:
                uncached_objectives.append((obj, meta_score, meta_explanation))
        
        if cached_scores:
            logger.debug(f"Alignment cache: {len(cached_scores)} hits, {len(uncached_objectives)} misses")
    else:
        uncached_objectives = list(objectives)
    
    # If everything was cached, return immediately
    if not uncached_objectives:
        return cached_scores
    
    # Estimate tokens (rough approximation: 1 token ≈ 4 characters)
    def estimate_tokens(text: str) -> int:
        return len(text) // 4
    
    control_tokens = estimate_tokens(control_desc or "")
    
    # Split objectives into batches based on token limits
    batches = []
    current_batch = []
    current_tokens = control_tokens
    
    for obj, meta_score, meta_explanation in uncached_objectives:
        obj_tokens = estimate_tokens(obj.objective_text or "")
        
        # Check if adding this objective would exceed limits
        if (len(current_batch) >= max_batch_size or 
            current_tokens + obj_tokens > max_tokens_per_batch):
            if current_batch:
                batches.append(current_batch)
            current_batch = [(obj, meta_score, meta_explanation)]
            current_tokens = control_tokens + obj_tokens
        else:
            current_batch.append((obj, meta_score, meta_explanation))
            current_tokens += obj_tokens
    
    if current_batch:
        batches.append(current_batch)
    
    logger.debug(f"Batch scoring: {len(uncached_objectives)} objectives split into {len(batches)} batches (skipped {len(cached_scores)} cached)")
    
    # Process each batch
    all_scores = dict(cached_scores)  # Start with cached results
    for batch_idx, batch in enumerate(batches, 1):
        try:
            # Prepare objectives JSON for prompt
            objectives_list = [
                {
                    "objective_id": obj.objective_id,
                    "objective_text": obj.objective_text or ""
                }
                for obj, _, _ in batch
            ]
            objectives_json = json.dumps(objectives_list, indent=2)
            
            # Call GPT with batch prompt (includes feedback examples for few-shot learning)
            prompt = config.OBJECTIVE_CONTROL_ALIGNMENT_BATCH_PROMPT.format(
                control_desc=control_desc or "",
                objectives_json=objectives_json,
                feedback_examples=feedback_text or ""
            )
            
            response = gpt_extract(
                prompt=prompt,
                extractor_name="objective_alignment",
                override_model=OBJECTIVE_ALIGNMENT_MODEL
            )
            
            # Parse response
            results = json.loads(response)
            if not isinstance(results, list):
                raise ValueError(f"Expected list, got {type(results)}")
            
            # Extract scores and populate cache
            for result in results:
                obj_id = result.get("objective_id")
                score = float(result.get("alignment_score", 0.0))
                reasoning = result.get("reasoning", "No reasoning provided")
                
                # Find matching objective
                for obj, _, _ in batch:
                    if obj.objective_id == obj_id:
                        all_scores[obj.id] = (score, reasoning)
                        # Update cache
                        if alignment_cache is not None:
                            obj_hash = hashlib.md5((obj.objective_text or "").encode()).hexdigest()[:12]
                            alignment_cache[f"{control_hash}:{obj_hash}"] = (score, reasoning)
                        break
            
            logger.debug(f"Batch {batch_idx}/{len(batches)}: Scored {len(results)} objectives")
            
        except Exception as e:
            logger.warning(f"Batch {batch_idx} failed: {e}. Falling back to sequential scoring.")
            # Fallback: score individually
            for obj, _, _ in batch:
                try:
                    score, reasoning = calculate_alignment_score(
                        obj.objective_text or "",
                        control_desc or ""
                    )
                    all_scores[obj.id] = (score, reasoning)
                    # Update cache
                    if alignment_cache is not None:
                        obj_hash = hashlib.md5((obj.objective_text or "").encode()).hexdigest()[:12]
                        alignment_cache[f"{control_hash}:{obj_hash}"] = (score, reasoning)
                except Exception as e2:
                    logger.error(f"Sequential fallback failed for {obj.objective_id}: {e2}")
                    all_scores[obj.id] = (0.0, f"Error: {str(e2)}")
    
    return all_scores


def update_objective_alignment_confidence(scan_id: int, db_session: Session):
    """
    Update alignment_confidence for all objectives based on control mappings.
    
    Args:
        scan_id: Scan ID to process
        db_session: SQLAlchemy session
    """
    objectives = db_session.query(ControlObjective).filter_by(scan_id=scan_id).all()
    
    for objective in objectives:
        mappings = db_session.query(ControlObjectiveMapping).filter_by(objective_id=objective.id).all()
        
        if mappings:
            # Average of all mapping confidences
            avg_alignment = sum(m.mapping_confidence for m in mappings) / len(mappings)
            objective.alignment_confidence = avg_alignment
            
            # FIXED: Skip confidence recalculation for gap_search objectives
            # Gap extraction uses fixed 0.50 confidence, boost slightly if mapped successfully
            if objective.extraction_method == "gap_search":
                # Gap-extracted objective that got mapped - boost confidence to 0.60
                # Still below auto-approve (0.65) unless reasoning exists
                has_reasoning = bool(
                    objective.gpt_reasoning and
                    objective.gpt_reasoning.strip() not in {'', 'Gap extraction:', 'Gap extraction', 'N/A', 'None'} and
                    len(objective.gpt_reasoning.replace('Gap extraction:', '').strip()) > 5
                )
                if has_reasoning and avg_alignment >= 0.70:
                    objective.final_confidence = 0.70  # Good reasoning + strong mapping
                elif has_reasoning:
                    objective.final_confidence = 0.60  # Has reasoning but weak mapping
                else:
                    objective.final_confidence = 0.55  # Mapped but no reasoning
                confidence_calc = (
                    f"gap_search (mapped, alignment={avg_alignment:.2f}, "
                    f"reasoning={'yes' if has_reasoning else 'no'}) → {objective.final_confidence:.2f}"
                )
            else:
                # Recalculate with 4-factor weights (alignment now available post-mapping)
                # CRITICAL: Apply empty reasoning guard (same as initial calculation)
                gpt_score_for_recalc = objective.gpt_confidence or 0.0
                empty_reasoning_stubs = {'', 'Gap extraction:', 'Gap extraction', 'N/A', 'None'}
                gpt_reasoning = (objective.gpt_reasoning or '').strip()
                if not gpt_reasoning or gpt_reasoning in empty_reasoning_stubs:
                    if gpt_score_for_recalc > 0.0:
                        logger.info(
                            f"[RECALC] Zeroing GPT opinion ({gpt_score_for_recalc:.2f}) for "
                            f"'{objective.objective_id or 'UNKNOWN'}' - empty/stub reasoning"
                        )
                        gpt_score_for_recalc = 0.0
                
                # Use 4-factor recalculation weights (includes alignment)
                weights = config.OBJECTIVE_RECALC_WEIGHTS
                final_confidence = (
                    objective.keyword_confidence * weights['keyword'] +
                    gpt_score_for_recalc * weights['gpt_opinion'] +
                    avg_alignment * weights['alignment'] +
                    objective.format_confidence * weights['format']
                )

                if objective.extraction_method == "pattern_rescan_aligned":
                    final_confidence = min(
                        1.0,
                        final_confidence + config.OBJECTIVE_PATTERN_ALIGNMENT_BOOST
                    )
                
                # Apply ID penalties (same logic as initial scoring)
                id_penalties = _calculate_id_penalties(
                    (objective.objective_id or '').strip(),
                    objectives  # Pass all objective model objects for pattern analysis
                )
                for penalty_type, penalty_value, reason in id_penalties:
                    final_confidence = max(0.0, final_confidence * (1.0 - penalty_value))
                
                objective.final_confidence = final_confidence
                confidence_calc = (
                    f"keyword={objective.keyword_confidence:.2f}*{weights['keyword']:.2f} + "
                    f"gpt={gpt_score_for_recalc:.2f}*{weights['gpt_opinion']:.2f} + "
                    f"alignment={avg_alignment:.2f}*{weights['alignment']:.2f} + "
                    f"format={objective.format_confidence:.2f}*{weights['format']:.2f} = "
                    f"{final_confidence:.3f}"
                )

                if objective.extraction_method == "pattern_rescan_aligned":
                    confidence_calc = (
                        f"{confidence_calc} + pattern_boost={config.OBJECTIVE_PATTERN_ALIGNMENT_BOOST:.2f}"
                    )
                
                for _, penalty_value, reason in id_penalties:
                    confidence_calc += f" * {1.0-penalty_value:.2f} ({reason})"


            objective.confidence_calc = confidence_calc
    
    db_session.commit()
    logger.info(f"Updated alignment confidence for {len(objectives)} objectives")
    
    # Re-run auto-approval after confidence updates (use 0.65 threshold)
    AUTO_APPROVE_THRESHOLD = 0.65
    auto_approved = 0
    for objective in objectives:
        if objective.final_confidence >= AUTO_APPROVE_THRESHOLD and objective.status == 'pending':
            objective.status = 'approved'
            auto_approved += 1
            logger.info(f"[AUTO_APPROVAL_POST_ALIGNMENT] ✓ APPROVED '{objective.objective_id or 'UNKNOWN'}' (confidence={objective.final_confidence})")
    
    db_session.commit()
    logger.info(f"[AUTO_APPROVAL_POST_ALIGNMENT] Auto-approved {auto_approved} objectives after alignment confidence update (threshold={AUTO_APPROVE_THRESHOLD})")
