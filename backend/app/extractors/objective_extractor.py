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
OBJECTIVE_MODEL = config.EXTRACTOR_MODEL_OVERRIDES.get('objective_extractor', config.DEFAULT_GPT_MODEL)


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
            model_override=OBJECTIVE_MODEL
        )
        
        # Parse JSON response
        result = json.loads(response)
        objectives = result.get('objectives', [])
        
        logger.info(f"Chunk {chunk_index}: Extracted {len(objectives)} objectives")
        return objectives
        
    except json.JSONDecodeError as e:
        logger.error(f"Chunk {chunk_index}: Failed to parse GPT response: {e}")
        return []
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
            model_override=OBJECTIVE_MODEL
        )
        
        result = json.loads(response)
        deduplicated = result.get('deduplicated', [])
        
        logger.info(f"Deduplicated {len(objectives)} objectives to {len(deduplicated)} unique objectives")
        return deduplicated
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse deduplication response: {e}")
        return objectives  # Return original if deduplication fails
    except Exception as e:
        logger.error(f"Objective deduplication failed: {e}")
        return objectives


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
    
    # Update progress
    if job_id and redis_client:
        redis_client.hset(f"job:{job_id}", "progress_status", "Extracting control objectives...")
    
    # Step 1: Chunk text by tokens with overlap
    chunks = chunk_text_by_tokens(
        extracted_text,
        config.OBJECTIVE_TOKENS_PER_CHUNK,
        config.OBJECTIVE_CHUNK_OVERLAP_TOKENS
    )
    logger.info(f"Split text into {len(chunks)} chunks")
    
    # Step 2: Extract objectives from each chunk
    all_objectives = []
    for i, (chunk_text, start_line, end_line) in enumerate(chunks):
        chunk_objectives = extract_objectives_from_chunk(chunk_text, i, scan_id)
        all_objectives.extend(chunk_objectives)
    
    logger.info(f"Extracted {len(all_objectives)} total objectives (before deduplication)")
    
    # Step 3: Deduplicate across chunks
    if len(all_objectives) > 0:
        deduplicated_objectives = deduplicate_objectives(all_objectives)
    else:
        deduplicated_objectives = []
    
    logger.info(f"Deduplicated to {len(deduplicated_objectives)} unique objectives")
    
    # Step 4: Calculate multi-factor confidence and create model instances
    objective_models = []
    for obj in deduplicated_objectives:
        # Calculate line reference (approximate from text search)
        objective_text = obj.get('objective_text', '')
        lines = extracted_text.split('\n')
        line_ref = None
        for i, line in enumerate(lines):
            if objective_text[:50] in line:
                line_ref = i + 1
                break
        
        # Calculate confidence
        final_confidence, confidence_calc = calculate_multi_factor_confidence(
            obj, extracted_text, line_ref
        )
        
        # Find page refs
        page_refs = find_page_refs(objective_text, extracted_text)
        
        # Extract confidence factors
        factors = obj.get('confidence_factors', {})
        
        # Create model instance
        objective_model = ControlObjective(
            scan_id=scan_id,
            objective_id=obj.get('objective_id'),
            objective_text=objective_text,
            keyword_confidence=factors.get('keyword_match', 0.0),
            distance_confidence=1.0 - (calculate_distance_from_keywords(extracted_text, line_ref or 0) / config.OBJECTIVE_MAX_DISTANCE_FROM_KEYWORDS) if line_ref else 0.0,
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
        logger.info(f"Saved {len(objective_models)} objectives to database")
    
    # Update progress
    if job_id and redis_client:
        redis_client.hset(f"job:{job_id}", "progress_status", f"Extracted {len(objective_models)} control objectives")
    
    return objective_models


def map_controls_to_objectives(
    scan_id: int,
    db_session: Session,
    job_id: Optional[str] = None,
    redis_client: Optional[Any] = None
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
    
    # For each control, find nearby objectives (proximity-based)
    for control in controls:
        control_line = control.control_line_ref
        if not control_line:
            continue
        
        # Find objectives within reasonable distance (±50 lines)
        nearby_objectives = [
            obj for obj in objectives
            if obj.line_ref and abs(obj.line_ref - control_line) <= 50
        ]
        
        if not nearby_objectives:
            continue
        
        # Use GPT to validate alignment and score
        for objective in nearby_objectives:
            try:
                alignment_score, reasoning = calculate_alignment_score(
                    objective.objective_text,
                    control.control_desc or ""
                )
                
                # Create mapping if alignment is reasonable (≥0.6)
                if alignment_score >= 0.6:
                    mapping = ControlObjectiveMapping(
                        control_id=control.id,
                        objective_id=objective.id,
                        mapping_confidence=alignment_score,
                        mapping_method='auto_proximity',
                        is_primary=(alignment_score >= 0.8),  # Primary if very strong alignment
                        created_at=datetime.utcnow()
                    )
                    db_session.add(mapping)
                    mappings_created += 1
                    
                    logger.debug(f"Mapped control {control.control_id} to objective {objective.objective_id} (score={alignment_score:.2f})")
                
            except Exception as e:
                logger.error(f"Failed to calculate alignment for control {control.id} and objective {objective.id}: {e}")
                continue
    
    # Commit mappings
    if mappings_created > 0:
        db_session.commit()
        logger.info(f"Created {mappings_created} control-objective mappings")
        
        # Update alignment confidence for objectives
        update_objective_alignment_confidence(scan_id, db_session)
    
    # Update progress
    if job_id and redis_client:
        redis_client.hset(f"job:{job_id}", "progress_status", f"Mapped {mappings_created} control-objective relationships")
    
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
            model_override=OBJECTIVE_MODEL
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
            
            objective.final_confidence = final_confidence
            objective.confidence_calc = (
                f"keyword={objective.keyword_confidence:.2f}*{weights['keyword']:.2f} + "
                f"distance={objective.distance_confidence:.2f}*{weights['distance']:.2f} + "
                f"gpt={objective.gpt_confidence:.2f}*{weights['gpt_opinion']:.2f} + "
                f"alignment={avg_alignment:.2f}*{weights['alignment']:.2f} + "
                f"format={objective.format_confidence:.2f}*{weights['format']:.2f} = "
                f"{final_confidence:.3f}"
            )
    
    db_session.commit()
    logger.info(f"Updated alignment confidence for {len(objectives)} objectives")
