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
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from .. import config
from ..gpt_client import gpt_extract
from ..models import ControlObjective, ControlObjectiveMapping, Control

logger = logging.getLogger(__name__)

# GPT model configuration
# Use dedicated CONTROL_OBJECTIVES_MODEL (typically gpt-5 for high accuracy)
OBJECTIVE_MODEL = config.CONTROL_OBJECTIVES_MODEL
OBJECTIVE_PATTERN_MODEL = config.OBJECTIVE_PATTERN_LEARNER_MODEL


def _parse_json_response(response: str, context: str) -> Optional[Dict[str, Any]]:
    """Parse JSON from GPT response, handling common wrappers like code fences."""
    raw = (response or "").strip()
    if not raw:
        return None

    try:
        return json.loads(raw)
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

        try:
            return json.loads(cleaned)
        except Exception as e:
            logger.error(f"{context}: Failed to parse GPT response: {e}")
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


def extract_objectives_from_chunk(chunk_text: str, chunk_index: int, scan_id: int) -> List[Dict[str, Any]]:
    """
    Extract objectives from a single text chunk using GPT.
    
    Args:
        chunk_text: Text chunk to process
        chunk_index: Index of this chunk (for logging)
        scan_id: Scan ID for context
        
    Returns:
        List of extracted objective dictionaries
    """
    prompt = config.OBJECTIVE_EXTRACTION_PROMPT.format(text_chunk=chunk_text)
    
    try:
        response = gpt_extract(
            prompt=prompt,
            extractor_name="objective_extractor",
            override_model=OBJECTIVE_MODEL
        )
        
        # Parse JSON response
        result = _parse_json_response(response, f"Chunk {chunk_index}")
        objectives = (result or {}).get('objectives', [])
        
        logger.info(f"Chunk {chunk_index}: Extracted {len(objectives)} objectives")
        return objectives
        
    except Exception as e:
        logger.error(f"Chunk {chunk_index}: Objective extraction failed: {e}")
        return []


def deduplicate_objectives(objectives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate objectives extracted from overlapping chunks.
    
    Args:
        objectives: List of objective dictionaries
        
    Returns:
        Deduplicated list with best versions preserved
    """
    if len(objectives) <= 1:
        return objectives
    
    # Prepare objectives list for GPT
    objectives_json = json.dumps(objectives, indent=2)
    prompt = config.OBJECTIVE_DEDUPLICATION_PROMPT.format(objective_list=objectives_json)
    
    try:
        response = gpt_extract(
            prompt=prompt,
            extractor_name="objective_deduplication",
            override_model=OBJECTIVE_MODEL
        )
        
        result = _parse_json_response(response, "Objective deduplication")
        deduplicated = (result or {}).get('deduplicated') if result else None

        if not deduplicated:
            logger.warning("Objective deduplication returned no valid results; using original objectives")
            return objectives
        
        logger.info(f"Deduplicated {len(objectives)} objectives to {len(deduplicated)} unique objectives")
        return deduplicated
        
    except Exception as e:
        logger.error(f"Objective deduplication failed: {e}")
        return objectives


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
    high_conf = [c for c in sorted_controls if _get_control_confidence(c) >= threshold]
    return high_conf[:max(0, min_count)]


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
    high_conf = [obj for obj in sorted_scored if (obj.get("_final_confidence") or 0.0) >= threshold]
    return high_conf[:max(0, min_count)]


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


def _can_rescan_with_patterns(patterns: Optional[Dict[str, Any]]) -> bool:
    if not patterns:
        return False
    id_pattern = patterns.get("id_pattern") or {}
    text_cues = patterns.get("text_cues") or []
    return bool(text_cues) or bool(id_pattern.get("present"))


def _rescan_objectives_with_patterns(
    chunks: List[Tuple[str, int, int]],
    patterns: Dict[str, Any],
    existing_objectives: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    if not chunks:
        return []

    existing_payload = json.dumps(existing_objectives, indent=2, ensure_ascii=False)
    patterns_payload = json.dumps(patterns, indent=2, ensure_ascii=False)
    rescanned = []

    for i, (chunk_text, _start_line, _end_line) in enumerate(chunks):
        prompt = config.OBJECTIVE_PATTERN_RESCAN_PROMPT.format(
            patterns=patterns_payload,
            existing_objectives=existing_payload,
            text_chunk=chunk_text
        )
        try:
            response = gpt_extract(
                prompt=prompt,
                extractor_name="objective_pattern_rescan",
                override_model=OBJECTIVE_PATTERN_MODEL
            )
            result = _parse_json_response(response, f"Objective pattern rescan chunk {i}")
            objectives = (result or {}).get("objectives", [])
            for obj in objectives:
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
    line_ref: Optional[int] = None
) -> Tuple[float, str]:
    """
    Calculate weighted multi-factor confidence score for an objective.
    
    Factors:
    - keyword_match (25%): Presence of objective keywords
    - distance (20%): Proximity to objective section keywords
    - gpt_opinion (30%): GPT's confidence assessment
    - alignment (15%): Alignment with controls (calculated later)
    - format_clarity (10%): Format clarity score
    
    Args:
        objective: Objective dictionary with confidence_factors
        extracted_text: Full extracted text for distance calculation
        line_ref: Line reference for distance calculation
        
    Returns:
        (final_confidence, confidence_calc) tuple
    """
    factors = objective.get('confidence_factors', {})
    weights = config.OBJECTIVE_CONFIDENCE_WEIGHTS
    
    # Extract individual factor scores (default to 0.0 if missing)
    keyword_score = factors.get('keyword_match', 0.0)
    gpt_score = factors.get('gpt_opinion', 0.0)
    format_score = factors.get('format_clarity', 0.0)
    
    # Calculate distance score
    if line_ref is not None:
        distance = calculate_distance_from_keywords(extracted_text, line_ref)
        # Convert distance to score: 0 distance = 1.0, max distance = 0.0
        distance_score = 1.0 - (distance / config.OBJECTIVE_MAX_DISTANCE_FROM_KEYWORDS)
        distance_score = max(0.0, min(1.0, distance_score))
    else:
        distance_score = 0.0
    
    # Alignment score defaults to 0.0 (calculated after control mapping)
    alignment_score = 0.0
    
    # Calculate weighted final confidence
    final_confidence = (
        keyword_score * weights['keyword'] +
        distance_score * weights['distance'] +
        gpt_score * weights['gpt_opinion'] +
        alignment_score * weights['alignment'] +
        format_score * weights['format']
    )
    
    # Create human-readable breakdown
    confidence_calc = (
        f"keyword={keyword_score:.2f}*{weights['keyword']:.2f} + "
        f"distance={distance_score:.2f}*{weights['distance']:.2f} + "
        f"gpt={gpt_score:.2f}*{weights['gpt_opinion']:.2f} + "
        f"alignment={alignment_score:.2f}*{weights['alignment']:.2f} + "
        f"format={format_score:.2f}*{weights['format']:.2f} = "
        f"{final_confidence:.3f}"
    )
    
    return final_confidence, confidence_calc


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
    
    # Find where objective text appears in extracted text
    # Use first 100 chars of objective as search key
    search_key = objective_text[:100].lower()
    text_lower = extracted_text.lower()
    
    pos = text_lower.find(search_key)
    if pos == -1:
        return []
    
    # Find nearest page marker before this position
    text_before = extracted_text[:pos]
    page_matches = list(re.finditer(page_pattern, text_before))
    
    if page_matches:
        last_page = int(page_matches[-1].group(1))
        pages.append(last_page)
    
    return pages


def extract_objectives(
    extracted_text: str,
    scan_id: int,
    db_session: Session,
    sections: Optional[List[Dict[str, Any]]] = None,
    job_id: Optional[str] = None,
    redis_client: Optional[Any] = None
) -> List[ControlObjective]:
    """
    Extract control objectives from SOC report text.
    
    Args:
        extracted_text: Full extracted text from PDF
        scan_id: Scan ID for database association
        db_session: SQLAlchemy session
        job_id: Redis job ID for progress updates
        redis_client: Redis client for progress tracking
        
    Returns:
        List of ControlObjective model instances
    """
    if not config.ENABLE_OBJECTIVE_EXTRACTION:
        logger.info("Objective extraction disabled in config")
        return []
    
    logger.info(f"Starting objective extraction for scan_id={scan_id}")

    full_text = extracted_text or ""
    filtered_text = full_text
    if sections:
        control_section = next((s for s in sections if s.get("topic") == "Control_Descriptions"), None)
        if control_section:
            start_line = control_section.get("start_line")
            end_line = control_section.get("end_line")
            if isinstance(start_line, int) and isinstance(end_line, int) and end_line >= start_line:
                lines = full_text.split("\n")
                filtered_text = "\n".join(lines[start_line - 1:end_line])
                logger.info(
                    f"[OBJECTIVES] Using Control_Descriptions section lines {start_line}-{end_line}"
                )
            else:
                logger.warning("[OBJECTIVES] Control_Descriptions section missing line bounds; using full text")
        else:
            logger.warning("[OBJECTIVES] Control_Descriptions section not found; using full text")

    # If no objective keywords are found, continue but log for visibility
    keyword_haystack = filtered_text.lower()
    objective_keywords = set(config.OBJECTIVE_SECTION_KEYWORDS + config.OBJECTIVE_PATTERN_KEYWORDS)
    if not any(keyword in keyword_haystack for keyword in objective_keywords):
        logger.info("[OBJECTIVES] No objective keywords found in selected text; proceeding with extraction")
    
    # Update progress
    if job_id and redis_client:
        redis_client.hset(
            f"job:{job_id}",
            mapping={
                "status": "running",
                "progress_status": "Extracting control objectives...",
                "processed_chunks": 0,
                "total_chunks": 0,
                "objectives_found": 0,
                "updated_at": datetime.utcnow().isoformat()
            }
        )
    
    # Step 1: Chunk text by tokens with overlap
    chunks = chunk_text_by_tokens(
        filtered_text,
        config.OBJECTIVE_TOKENS_PER_CHUNK,
        config.OBJECTIVE_CHUNK_OVERLAP_TOKENS
    )
    logger.info(f"Split text into {len(chunks)} chunks")

    if job_id and redis_client:
        redis_client.hset(
            f"job:{job_id}",
            mapping={
                "total_chunks": len(chunks),
                "updated_at": datetime.utcnow().isoformat()
            }
        )
    
    # Step 2: Extract objectives from each chunk
    all_objectives = []
    total_found = 0
    for i, (chunk_text, start_line, end_line) in enumerate(chunks):
        chunk_objectives = extract_objectives_from_chunk(chunk_text, i, scan_id)
        all_objectives.extend(chunk_objectives)
        total_found += len(chunk_objectives)

        if job_id and redis_client:
            redis_client.hset(
                f"job:{job_id}",
                mapping={
                    "processed_chunks": i + 1,
                    "total_chunks": len(chunks),
                    "objectives_found": total_found,
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
    
    logger.info(f"Extracted {len(all_objectives)} total objectives (before deduplication)")
    
    # Step 3: Deduplicate across chunks
    if len(all_objectives) > 0:
        deduplicated_objectives = deduplicate_objectives(all_objectives)
        if not deduplicated_objectives:
            logger.warning("Deduplication produced no objectives; using raw extracted list")
            deduplicated_objectives = all_objectives
    else:
        deduplicated_objectives = []
    
    logger.info(f"Deduplicated to {len(deduplicated_objectives)} unique objectives")

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
                        existing_objectives_payload
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
    for obj in deduplicated_objectives:
        # Calculate line reference (approximate from text search)
        objective_text = obj.get('objective_text', '')
        lines = full_text.split('\n')
        line_ref = None
        for i, line in enumerate(lines):
            if objective_text[:50] in line:
                line_ref = i + 1
                break
        
        # Calculate confidence
        final_confidence, confidence_calc = calculate_multi_factor_confidence(
            obj, full_text, line_ref
        )

        if obj.get("pattern_alignment"):
            final_confidence = min(1.0, final_confidence + config.OBJECTIVE_PATTERN_ALIGNMENT_BOOST)
            confidence_calc = (
                f"{confidence_calc} + pattern_boost={config.OBJECTIVE_PATTERN_ALIGNMENT_BOOST:.2f}"
            )
        
        # Find page refs
        page_refs = find_page_refs(objective_text, full_text)
        
        # Extract confidence factors
        factors = obj.get('confidence_factors', {})
        
        # Create model instance
        objective_model = ControlObjective(
            scan_id=scan_id,
            objective_id=obj.get('objective_id'),
            objective_text=objective_text,
            keyword_confidence=factors.get('keyword_match', 0.0),
            distance_confidence=1.0 - (calculate_distance_from_keywords(full_text, line_ref or 0) / config.OBJECTIVE_MAX_DISTANCE_FROM_KEYWORDS) if line_ref else 0.0,
            gpt_confidence=factors.get('gpt_opinion', 0.0),
            alignment_confidence=0.0,  # Calculated after control mapping
            format_confidence=factors.get('format_clarity', 0.0),
            final_confidence=final_confidence,
            confidence_calc=confidence_calc,
            gpt_reasoning=obj.get('reasoning', ''),
            page_refs=page_refs,
            line_ref=line_ref,
            source_context=objective_text[:500],  # First 500 chars as context
            extraction_method=obj.get('extraction_method', 'gpt_inferred'),
            section_heading=obj.get('section_heading'),
            status='pending',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        objective_models.append(objective_model)
    
    # Step 5: Save to database
    if objective_models:
        db_session.add_all(objective_models)
        db_session.flush()  # Flush to get IDs
        db_session.commit()
        logger.info(f"Saved {len(objective_models)} objectives to database")
    
    # Update progress
    if job_id and redis_client:
        redis_client.hset(
            f"job:{job_id}",
            mapping={
                "status": "completed",
                "progress_status": f"Extracted {len(objective_models)} control objectives",
                "processed_chunks": len(chunks),
                "total_chunks": len(chunks),
                "objectives_found": len(objective_models),
                "updated_at": datetime.utcnow().isoformat()
            }
        )
    
    # Automatically trigger gap extraction after objective extraction completes
    if scan_id and len(objective_models) > 0:
        try:
            logger.info(f"[OBJECTIVE_GAP_AUTO] Starting automatic gap extraction for scan_id={scan_id}")
            import threading
            from ..routers.objective_router import run_gap_extraction_sync
            
            # Run gap extraction in background thread to avoid blocking
            def _run_gap_and_map():
                try:
                    result = run_gap_extraction_sync(scan_id, extracted_text)
                    logger.info(f"[OBJECTIVE_GAP_AUTO] Gap extraction completed: {result.get('status')}")
                    
                    # After gap extraction, re-run mapping to controls
                    if result.get("status") in ["completed", "started"]:
                        logger.info(f"[OBJECTIVE_GAP_AUTO] Re-mapping objectives to controls for scan_id={scan_id}")
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
                                job_id=None,
                                redis_client=None
                            )
                            logger.info(f"[OBJECTIVE_GAP_AUTO] Created {mappings_count} new mappings")
                        finally:
                            map_session.close()
                except Exception as gap_err:
                    logger.error(f"[OBJECTIVE_GAP_AUTO] Failed: {gap_err}")
            
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


def _page_proximity_score(control_page: Optional[int], objective_page: Optional[int]) -> float:
    if control_page is None or objective_page is None:
        return 0.0
    distance = abs(control_page - objective_page)
    return max(0.0, min(1.0, 1.0 / (1.0 + distance)))


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
    if control_page is None or objective_page is None:
        return 0.0
    if objective_page > control_page:
        return 0.0

    distance = control_page - objective_page
    score = 0.0
    if distance <= 2:
        score += 0.3
    elif 3 <= distance <= 6:
        score += 0.1

    if distance == 0:
        score += 0.1

    if score > 0.0:
        score += 0.2

    return score


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
            if obj_page > control_page + 1:
                continue
            if obj_page < control_page - 6:
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
        redis_client.hset(f"job:{job_id}", "progress_status", "Mapping controls to objectives...")
    
    # Fetch objectives and controls for this scan
    objectives = db_session.query(ControlObjective).filter_by(scan_id=scan_id).all()
    controls = db_session.query(Control).filter_by(scan_id=scan_id).all()
    
    if not objectives or not controls:
        logger.info("No objectives or controls found, skipping mapping")
        return 0
    
    logger.info(f"Found {len(objectives)} objectives and {len(controls)} controls")
    
    mappings_created = 0
    mappings_updated = 0
    
    control_ids = [control.id for control in controls]
    existing_mappings = db_session.query(ControlObjectiveMapping).filter(
        ControlObjectiveMapping.control_id.in_(control_ids)
    ).all()
    mappings_by_control: Dict[int, List[ControlObjectiveMapping]] = {}
    for mapping in existing_mappings:
        mappings_by_control.setdefault(mapping.control_id, []).append(mapping)

    for control in controls:
        existing_for_control = mappings_by_control.get(control.id, [])

        if existing_for_control and not force:
            # Ensure exactly one primary mapping per control
            primary_existing = [m for m in existing_for_control if m.is_primary]
            if not primary_existing:
                best_existing = max(
                    existing_for_control,
                    key=lambda m: m.mapping_confidence if m.mapping_confidence is not None else 0.0
                )
                best_existing.is_primary = True
                mappings_updated += 1
            continue

        if force and existing_for_control:
            for mapping in existing_for_control:
                db_session.delete(mapping)

        control_line = control.control_line_ref
        control_page = _min_page_ref(control.control_page_refs)
        candidates = _select_candidate_objectives(objectives, control_line, control_page)
        if not candidates:
            continue

        best_objective = None
        best_score = -1.0
        best_possible_objective = None
        best_possible_score = -1.0
        best_scores = {}
        best_possible_scores = {}

        for objective in candidates:
            try:
                alignment_score, _reasoning = calculate_alignment_score(
                    objective.objective_text,
                    control.control_desc or ""
                )
            except Exception as e:
                logger.error(
                    f"Failed alignment for control {control.id} and objective {objective.id}: {e}"
                )
                alignment_score = 0.0

            objective_page = _min_page_ref(objective.page_refs)
            page_score = _control_page_proximity_score(control_page, objective_page)
            gpt_score = 0.2 if alignment_score >= config.OBJECTIVE_MAPPING_GPT_ALIGNMENT_THRESHOLD else 0.0
            id_score = _id_alignment_score(control.control_id, objective.objective_id)
            combined_score = max(0.0, min(1.0, page_score + gpt_score + id_score))

            if combined_score >= config.OBJECTIVE_MAPPING_PRIMARY_THRESHOLD and combined_score > best_score:
                best_score = combined_score
                best_objective = objective
                best_scores = {
                    "page_proximity_score": page_score,
                    "gpt_alignment_score": gpt_score,
                    "id_alignment_score": id_score,
                }
            elif (
                combined_score >= config.OBJECTIVE_MAPPING_POSSIBLE_THRESHOLD
                and combined_score > best_possible_score
            ):
                best_possible_score = combined_score
                best_possible_objective = objective
                best_possible_scores = {
                    "page_proximity_score": page_score,
                    "gpt_alignment_score": gpt_score,
                    "id_alignment_score": id_score,
                }

        if best_objective is None and best_possible_objective is None:
            continue

        if best_objective is not None:
            mapping = ControlObjectiveMapping(
                control_id=control.id,
                objective_id=best_objective.id,
                mapping_confidence=max(0.0, best_score),
                mapping_method='auto_weighted',
                is_primary=True,
                page_proximity_score=best_scores.get("page_proximity_score"),
                gpt_alignment_score=best_scores.get("gpt_alignment_score"),
                id_alignment_score=best_scores.get("id_alignment_score"),
                created_at=datetime.utcnow()
            )
            db_session.add(mapping)
            mappings_created += 1
            logger.debug(
                f"Mapped control {control.control_id} to objective {best_objective.objective_id} "
                f"(score={best_score:.2f})"
                #...
            )
        elif best_possible_objective is not None:
            mapping = ControlObjectiveMapping(
                control_id=control.id,
                objective_id=best_possible_objective.id,
                mapping_confidence=max(0.0, best_possible_score),
                mapping_method='auto_weighted',
                is_primary=False,
                page_proximity_score=best_possible_scores.get("page_proximity_score"),
                gpt_alignment_score=best_possible_scores.get("gpt_alignment_score"),
                id_alignment_score=best_possible_scores.get("id_alignment_score"),
                created_at=datetime.utcnow()
            )
            db_session.add(mapping)
            mappings_created += 1
            logger.debug(
                f"Mapped control {control.control_id} to objective {best_possible_objective.objective_id} "
                f"(score={best_possible_score:.2f})"
                #...
            )
    # Commit mappings
    if mappings_created > 0 or mappings_updated > 0:
        db_session.commit()
        if mappings_created > 0:
            logger.info(f"Created {mappings_created} control-objective mappings")
        if mappings_updated > 0:
            logger.info(f"Updated {mappings_updated} control-objective mappings")
        
        # Update alignment confidence for objectives
        update_objective_alignment_confidence(scan_id, db_session)
    
    # Update progress
    if job_id and redis_client:
        redis_client.hset(
            f"job:{job_id}",
            "progress_status",
            f"Mapped {mappings_created} control-objective relationships"
        )
    
    return mappings_created


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
            override_model=OBJECTIVE_MODEL
        )
        
        result = json.loads(response)
        score = result.get('alignment_score', 0.0)
        reasoning = result.get('reasoning', '')
        
        return score, reasoning
        
    except Exception as e:
        logger.error(f"Alignment calculation failed: {e}")
        return 0.0, "Alignment calculation failed"


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
            
            # Recalculate final confidence with new alignment score
            final_confidence, confidence_calc = calculate_multi_factor_confidence(
                {
                    'confidence_factors': {
                        'keyword_match': objective.keyword_confidence,
                        'gpt_opinion': objective.gpt_confidence,
                        'format_clarity': objective.format_confidence
                    }
                },
                "",  # Don't need full text for recalc
                objective.line_ref
            )
            
            # Override alignment component
            weights = config.OBJECTIVE_CONFIDENCE_WEIGHTS
            final_confidence = (
                objective.keyword_confidence * weights['keyword'] +
                objective.distance_confidence * weights['distance'] +
                objective.gpt_confidence * weights['gpt_opinion'] +
                avg_alignment * weights['alignment'] +
                objective.format_confidence * weights['format']
            )

            if objective.extraction_method == "pattern_rescan_aligned":
                final_confidence = min(
                    1.0,
                    final_confidence + config.OBJECTIVE_PATTERN_ALIGNMENT_BOOST
                )
            
            objective.final_confidence = final_confidence
            confidence_calc = (
                f"keyword={objective.keyword_confidence:.2f}*{weights['keyword']:.2f} + "
                f"distance={objective.distance_confidence:.2f}*{weights['distance']:.2f} + "
                f"gpt={objective.gpt_confidence:.2f}*{weights['gpt_opinion']:.2f} + "
                f"alignment={avg_alignment:.2f}*{weights['alignment']:.2f} + "
                f"format={objective.format_confidence:.2f}*{weights['format']:.2f} = "
                f"{final_confidence:.3f}"
            )

            if objective.extraction_method == "pattern_rescan_aligned":
                confidence_calc = (
                    f"{confidence_calc} + pattern_boost={config.OBJECTIVE_PATTERN_ALIGNMENT_BOOST:.2f}"
                )

            objective.confidence_calc = confidence_calc
    
    db_session.commit()
    logger.info(f"Updated alignment confidence for {len(objectives)} objectives")
