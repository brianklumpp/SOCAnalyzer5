"""
Service module for control merging and deduplication logic.

Handles automated cleanup, merge suggestion generation, and control merging operations.
"""
import logging
import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy import and_
from sqlalchemy.future import select

from ..models import Control, CUEC, SubserviceOrg, Scan
from ..gpt_client import gpt_extract
from .. import config as cfg
from ..utils.audit import mark_system_update


async def automated_cleanup(scan_id: int, db) -> Optional[Dict[str, int]]:
    """
    Automated cleanup tasks that run after scan completion.
    
    1. Flag extraction errors (blank control_ids, duplicate control_ids with low similarity)
    2. Auto-merge high-confidence duplicate controls (score >= AUTO_MERGE_MIN_CONFIDENCE)
    3. Flag low-confidence CUECs and subservice orgs
    
    Args:
        scan_id: Scan identifier
        db: Async database session
        
    Returns:
        Dictionary with cleanup statistics or None on error
    """
    try:
        logging.error(f"[CLEANUP] Starting automated cleanup for scan {scan_id}")
        cleanup_stats = {
            "extraction_errors_flagged": 0,
            "controls_auto_merged": 0,
            "low_confidence_cuecs": 0,
            "low_confidence_subservice_orgs": 0
        }
        
        # 1. Get all controls for analysis (include duplicate instances)
        result = await db.execute(
            select(Control).where(
                Control.scan_id == scan_id,
                and_(
                    (Control.merged_to_control_id == None) | 
                    (Control.merged_to_control_id == 'DUPLICATE_INSTANCE')
                )
            ).order_by(Control.control_seq)
        )
        controls = result.scalars().all()
        
        # 2. Flag blank control_ids as extraction errors
        blank_controls = [c for c in controls if not c.control_id or str(c.control_id).strip() == ""]
        for ctrl in blank_controls:
            if ctrl.control_confidence > 0.1:
                ctrl.control_confidence = 0.1
                note = "\\nAutomated cleanup: Extraction error - no valid control_id extracted"
                ctrl.confidence_calc = (ctrl.confidence_calc or "") + note
                mark_system_update(ctrl, "Extraction error flagged - missing control_id")
                db.add(ctrl)
                cleanup_stats["extraction_errors_flagged"] += 1
        
        # 3. Group by control_id and process duplicates
        control_groups = {}
        for ctrl in controls:
            if not ctrl.control_id or str(ctrl.control_id).strip() == "":
                continue
            ctrl_id = str(ctrl.control_id).strip()
            if ctrl_id not in control_groups:
                control_groups[ctrl_id] = []
            control_groups[ctrl_id].append(ctrl)
        
        # 4. Process each duplicate group
        for ctrl_id, group in control_groups.items():
            if len(group) < 2:
                continue
            
            # Sort by confidence to pick primary
            group.sort(key=lambda c: c.control_confidence or 0, reverse=True)
            primary = group[0]
            candidates = group[1:]
            
            # Evaluate each candidate for merging or flagging
            for candidate in candidates:
                confidence_score = 0.0
                
                # Calculate similarity (same logic as suggest-merges)
                desc1 = (primary.control_desc or "").strip()
                desc2 = (candidate.control_desc or "").strip()
                
                if desc1 and desc2:
                    try:
                        similarity_prompt = f"""Rate the semantic similarity between these two control descriptions on a scale of 0.0 to 1.0.
Return ONLY a number between 0.0 and 1.0, nothing else.

Description 1: {desc1[:500]}
Description 2: {desc2[:500]}"""
                        
                        sim_response = gpt_extract(similarity_prompt, "automated_cleanup")
                        desc_similarity = float(sim_response.strip())
                        desc_similarity = max(0.0, min(1.0, desc_similarity))
                        confidence_score += desc_similarity * 0.65
                    except Exception:
                        if desc1.lower() == desc2.lower():
                            confidence_score += 0.65
                        else:
                            confidence_score += 0.39
                
                # Framework mapping match
                if primary.primary_criterion_id and candidate.primary_criterion_id:
                    if primary.primary_criterion_id == candidate.primary_criterion_id:
                        confidence_score += 0.15
                
                # Test procedure similarity
                test1 = (primary.control_test or "").strip()
                test2 = (candidate.control_test or "").strip()
                if test1 and test2:
                    if test1.lower() == test2.lower():
                        confidence_score += 0.10
                    elif len(test1) > 20 and len(test2) > 20 and test1[:50].lower() == test2[:50].lower():
                        confidence_score += 0.07
                
                # Deviation flag agreement
                if primary.has_deviation == candidate.has_deviation:
                    confidence_score += 0.05
                
                # Page proximity bonus
                primary_pages = primary.control_page_refs or []
                candidate_pages = candidate.control_page_refs or []
                if primary_pages and candidate_pages:
                    primary_min = min([int(p) for p in primary_pages if str(p).isdigit()])
                    primary_max = max([int(p) for p in primary_pages if str(p).isdigit()])
                    candidate_min = min([int(p) for p in candidate_pages if str(p).isdigit()])
                    candidate_max = max([int(p) for p in candidate_pages if str(p).isdigit()])
                    
                    if abs(primary_max - candidate_min) <= 1 or abs(candidate_max - primary_min) <= 1:
                        confidence_score += cfg.PAGE_PROXIMITY_WEIGHT
                
                # Decision: merge if high confidence, flag if low confidence
                if confidence_score >= cfg.AUTO_MERGE_MIN_CONFIDENCE:
                    # Auto-merge high-confidence duplicates
                    candidate.merged_to_control_id = str(primary.id)
                    original_conf = candidate.control_confidence
                    candidate.control_confidence = 0.0
                    note = f"\\nAutomated cleanup: Merged to control {primary.id} on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Original confidence: {original_conf:.2f} | Merge confidence: {confidence_score:.2f} | New confidence: 0.0 (merged duplicate)"
                    candidate.confidence_calc = (candidate.confidence_calc or "") + note
                    
                    # Consolidate page refs to primary
                    primary_pages_set = set(primary.control_page_refs or [])
                    candidate_pages_set = set(candidate.control_page_refs or [])
                    merged_pages = sorted(primary_pages_set | candidate_pages_set)
                    primary.control_page_refs = merged_pages
                    
                    # Update primary annotation
                    merge_note = f"Consolidated from automated cleanup on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    primary.annotation = merge_note
                    
                    # Track merge history
                    merge_event = {
                        "timestamp": datetime.datetime.now().isoformat(),
                        "type": "auto",
                        "confidence": round(confidence_score, 3),
                        "merged_from_ids": [str(candidate.id)],
                        "reason": f"Automated cleanup: duplicate control_id with {confidence_score:.2f} similarity"
                    }
                    if not primary.merge_history:
                        primary.merge_history = []
                    primary.merge_history.append(merge_event)
                    
                    db.add(candidate)
                    db.add(primary)
                    cleanup_stats["controls_auto_merged"] += 1
                    logging.error(f"[CLEANUP] Auto-merged control {candidate.id} to {primary.id} (score: {confidence_score:.2f})")
                    
                elif confidence_score < 0.60:
                    # Flag as extraction error if similarity is low
                    if candidate.control_confidence > 0.3:
                        candidate.control_confidence = 0.3
                        note = f"\\nAutomated cleanup: Likely extraction error - duplicate control_id with dissimilar description (similarity score: {confidence_score:.2f})"
                        candidate.confidence_calc = (candidate.confidence_calc or "") + note
                        db.add(candidate)
                        cleanup_stats["extraction_errors_flagged"] += 1
        
        # 5. Flag low-confidence CUECs
        cuec_result = await db.execute(
            select(CUEC).where(CUEC.scan_id == scan_id)
        )
        cuecs = cuec_result.scalars().all()
        for cuec in cuecs:
            if cuec.cuec_confidence and cuec.cuec_confidence < 0.5:
                if not cuec.cuec_justification or "low confidence" not in cuec.cuec_justification.lower():
                    note = f"\\nAutomated cleanup: Low confidence CUEC (confidence: {cuec.cuec_confidence:.2f})"
                    cuec.cuec_justification = (cuec.cuec_justification or "") + note
                    db.add(cuec)
                    cleanup_stats["low_confidence_cuecs"] += 1
        
        # 6. Flag low-confidence subservice orgs
        so_result = await db.execute(
            select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id)
        )
        subservice_orgs = so_result.scalars().all()
        for so in subservice_orgs:
            if so.confidence and so.confidence < 0.5:
                if not so.confidence_justification or "low confidence" not in so.confidence_justification.lower():
                    note = f"\\nAutomated cleanup: Low confidence subservice org (confidence: {so.confidence:.2f})"
                    so.confidence_justification = (so.confidence_justification or "") + note
                    db.add(so)
                    cleanup_stats["low_confidence_subservice_orgs"] += 1
        
        # Commit all changes
        await db.commit()
        
        logging.error(f"[CLEANUP] Completed for scan {scan_id}: {cleanup_stats}")
        return cleanup_stats
        
    except Exception as e:
        logging.error(f"[CLEANUP] Error in automated cleanup for scan {scan_id}: {e}", exc_info=True)
        await db.rollback()
        return None


async def penalize_incomplete_controls(scan_id: int, db) -> int:
    """
    Apply confidence penalty to controls missing required fields.
    
    Reduces confidence by CONTROL_INCOMPLETE_PENALTY for controls missing:
    - control_id, control_desc, control_test, control_test_results
    
    Args:
        scan_id: Scan identifier
        db: Async database session
        
    Returns:
        Number of controls penalized
    """
    try:
        logging.error(f"[INCOMPLETE-PENALTY] Starting for scan {scan_id}")
        
        result = await db.execute(
            select(Control).where(
                Control.scan_id == scan_id,
                and_(
                    (Control.merged_to_control_id == None) | 
                    (Control.merged_to_control_id == 'DUPLICATE_INSTANCE')
                )
            )
        )
        controls = result.scalars().all()
        
        penalized_count = 0
        for ctrl in controls:
            missing_fields = []
            if not ctrl.control_id or str(ctrl.control_id).strip() == "":
                missing_fields.append("control_id")
            if not ctrl.control_desc or str(ctrl.control_desc).strip() == "":
                missing_fields.append("control_desc")
            if not ctrl.control_test or str(ctrl.control_test).strip() == "":
                missing_fields.append("control_test")
            if not ctrl.control_test_results or str(ctrl.control_test_results).strip() == "":
                missing_fields.append("control_test_results")
            
            if missing_fields:
                original_conf = ctrl.control_confidence or 0.0
                penalty = cfg.CONTROL_INCOMPLETE_PENALTY
                new_conf = max(0.0, original_conf - penalty)
                
                ctrl.control_confidence = new_conf
                note = f"\\nIncomplete control penalty: -{penalty:.2f} for missing fields: {', '.join(missing_fields)} | Original: {original_conf:.2f} → New: {new_conf:.2f}"
                ctrl.confidence_calc = (ctrl.confidence_calc or "") + note
                db.add(ctrl)
                penalized_count += 1
        
        await db.commit()
        logging.error(f"[INCOMPLETE-PENALTY] Penalized {penalized_count} controls for scan {scan_id}")
        return penalized_count
        
    except Exception as e:
        logging.error(f"[INCOMPLETE-PENALTY] Error for scan {scan_id}: {e}", exc_info=True)
        await db.rollback()
        return 0


def detect_duplicate_type(ctrl1: Control, ctrl2: Control) -> tuple[str, float, Dict[str, Any]]:
    """
    Determine duplicate type and confidence score for two controls.
    
    Duplicate Types:
    - IDENTICAL: Same description and criteria (merge recommended)
    - CRITERIA_VARIANT: Same description, different TSC/COSO mapping (link as instances)
    - TEST_VARIANT: Same control, different test procedures or deviation status (link as instances)
    - AMBIGUOUS: Unclear relationship (manual review needed)
    
    Args:
        ctrl1: First control (typically higher confidence)
        ctrl2: Second control
        
    Returns:
        Tuple of (duplicate_type, confidence_score, metadata_dict)
    """
    metadata: Dict[str, Any] = {}
    confidence_score = 0.0
    
    # 1. Description similarity (70% weight)
    desc1 = (ctrl1.control_desc or "").strip()
    desc2 = (ctrl2.control_desc or "").strip()
    
    if desc1 and desc2:
        try:
            similarity_prompt = f"""Rate the semantic similarity between these two control descriptions on a scale of 0.0 to 1.0.
Return ONLY a number between 0.0 and 1.0, nothing else.

Description 1: {desc1[:500]}
Description 2: {desc2[:500]}"""
            
            sim_response = gpt_extract(similarity_prompt, "detect_duplicate_type")
            desc_similarity = float(sim_response.strip())
            desc_similarity = max(0.0, min(1.0, desc_similarity))
            confidence_score += desc_similarity * 0.70
            metadata["description_similarity"] = desc_similarity
        except Exception as e:
            logging.warning(f"GPT similarity scoring failed: {e}, using exact match fallback")
            if desc1.lower() == desc2.lower():
                confidence_score += 0.70
                metadata["description_similarity"] = 1.0
            else:
                confidence_score += 0.42
                metadata["description_similarity"] = 0.6
    
    # 2. Framework mapping analysis (15% weight)
    criterion1 = (ctrl1.primary_criterion_id or "").strip()
    criterion2 = (ctrl2.primary_criterion_id or "").strip()
    framework1 = (ctrl1.primary_framework or "").strip()
    framework2 = (ctrl2.primary_framework or "").strip()
    
    criteria_match = False
    criteria_differ = False
    
    # Compare primary framework mappings
    if criterion1 and criterion2:
        metadata["criterion1_primary"] = criterion1
        metadata["criterion1_primary"] = criterion1
        metadata["criterion2_primary"] = criterion2
        metadata["framework1"] = framework1
        metadata["framework2"] = framework2
        if criterion1 == criterion2:
            confidence_score += 0.15
            criteria_match = True
        else:
            criteria_differ = True
    
    # 3. Test procedure similarity (10% weight)
    test1 = (ctrl1.control_test or "").strip()
    test2 = (ctrl2.control_test or "").strip()
    test_differ = False
    
    if test1 and test2:
        if test1.lower() == test2.lower():
            confidence_score += 0.10
            metadata["test_difference"] = 0.0
        elif len(test1) > 20 and len(test2) > 20 and test1[:50].lower() == test2[:50].lower():
            confidence_score += 0.07
            metadata["test_difference"] = 0.15
            test_differ = True
        else:
            metadata["test_difference"] = 0.50
            test_differ = True
    
    # 4. Deviation flag agreement (5% weight)
    dev1 = ctrl1.has_deviation or False
    dev2 = ctrl2.has_deviation or False
    deviation_differs = (dev1 != dev2)
    
    if not deviation_differs:
        confidence_score += 0.05
    metadata["deviation_differs"] = deviation_differs
    
    # 5. Page proximity analysis
    pages1 = ctrl1.control_page_refs or []
    pages2 = ctrl2.control_page_refs or []
    
    if pages1 and pages2:
        pages1_nums = [int(p) for p in pages1 if str(p).isdigit()]
        pages2_nums = [int(p) for p in pages2 if str(p).isdigit()]
        if pages1_nums and pages2_nums:
            min_distance = min(abs(p1 - p2) for p1 in pages1_nums for p2 in pages2_nums)
            metadata["page_distance"] = min_distance
            
            # Bonus for adjacent pages
            if min_distance <= 1:
                confidence_score += cfg.PAGE_PROXIMITY_WEIGHT
    
    # Determine duplicate type based on description similarity and criteria differences
    desc_sim = metadata.get("description_similarity", 0.6)
    
    if desc_sim >= 0.85:
        # High description similarity
        if criteria_differ:
            # Same control, different criteria mapping → CRITERIA_VARIANT
            return ("CRITERIA_VARIANT", min(confidence_score, 0.95), metadata)
        elif test_differ or deviation_differs:
            # Same control, different test or deviation → TEST_VARIANT
            return ("TEST_VARIANT", min(confidence_score, 0.90), metadata)
        else:
            # Same everything → IDENTICAL
            return ("IDENTICAL", confidence_score, metadata)
    elif desc_sim >= 0.70:
        # Medium-high description similarity
        if not criteria_differ and not test_differ and not deviation_differs:
            # Everything matches at medium level → likely IDENTICAL
            return ("IDENTICAL", confidence_score, metadata)
        else:
            # Some differences → AMBIGUOUS but lean towards variant
            ambiguity_confidence = confidence_score * 0.85
            return ("AMBIGUOUS", min(ambiguity_confidence, 0.80), metadata)
    else:
        # Low description similarity → AMBIGUOUS
        ambiguity_confidence = confidence_score * 0.80
        return ("AMBIGUOUS", min(ambiguity_confidence, 0.75), metadata)


async def suggest_control_merges(scan_id: int, db) -> Dict[str, Any]:
    """
    Analyze controls and suggest merges for identical control_ids.
    
    Returns merge suggestions with confidence scores based on:
    - Description similarity (GPT-based, 70% weight)
    - TSC/COSO mapping matches (15% weight)
    - Test procedure similarity (10% weight)
    - Deviation flag agreement (5% weight)
    
    Only returns suggestions with confidence >= MERGE_SUGGESTION_MIN_CONFIDENCE (default 0.85)
    
    Args:
        scan_id: Scan identifier
        db: Async database session
        
    Returns:
        Dictionary with suggestions array, total count, and threshold
    """
    try:
        # Get all controls for this scan that haven't been merged away
        result = await db.execute(
            select(Control).where(
                Control.scan_id == scan_id,
                and_(
                    (Control.merged_to_control_id == None) | 
                    (Control.merged_to_control_id == 'DUPLICATE_INSTANCE')
                )
            ).order_by(Control.control_seq)
        )
        controls = result.scalars().all()
        
        # Group by control_id
        control_groups = {}
        for ctrl in controls:
            if not ctrl.control_id:
                continue
            ctrl_id = str(ctrl.control_id).strip()
            if ctrl_id not in control_groups:
                control_groups[ctrl_id] = []
            control_groups[ctrl_id].append(ctrl)
        
        suggestions = []
        
        logging.error(f"[SUGGEST-MERGES] Found {len(control_groups)} control_id groups total")
        
        for ctrl_id, group in control_groups.items():
            if len(group) < 2:
                continue
            
            logging.error(f"[SUGGEST-MERGES] Processing group {ctrl_id}: {len(group)} controls")
            
            # Sort by confidence (descending) to pick primary
            group.sort(key=lambda c: c.control_confidence or 0, reverse=True)
            primary = group[0]
            candidates = group[1:]
            
            logging.error(f"[SUGGEST-MERGES] Primary selected: DB ID {primary.id}, confidence={primary.control_confidence}")
            
            for idx, candidate in enumerate(candidates):
                logging.error(f"[SUGGEST-MERGES] Processing candidate {idx+1}/{len(candidates)}: DB ID {candidate.id}")
                
                # Use duplicate detection algorithm
                duplicate_type, confidence, metadata = detect_duplicate_type(primary, candidate)
                
                logging.error(f"[SUGGEST-MERGES] Duplicate type: {duplicate_type}, confidence: {confidence:.3f}")
                
                # Determine action based on duplicate type
                if duplicate_type == "IDENTICAL":
                    action = "merge"
                    recommended_action = "Merge - identical controls"
                elif duplicate_type in ["CRITERIA_VARIANT", "TEST_VARIANT"]:
                    action = "link_as_instances"
                    if duplicate_type == "CRITERIA_VARIANT":
                        recommended_action = "Link as instances - same control for different TSC/COSO criteria"
                    else:
                        recommended_action = "Link as instances - same control with different test procedures or deviation status"
                else:  # AMBIGUOUS
                    action = "review_manually"
                    recommended_action = "Manual review needed - unclear relationship"
                
                # Extract comparison details
                desc1 = (primary.control_desc or "").strip()
                desc2 = (candidate.control_desc or "").strip()
                test1 = (primary.control_test or "").strip()
                test2 = (candidate.control_test or "").strip()
                
                # Build criteria differences
                criteria_differences = {
                    "control_1_primary": [metadata.get("tsc1_primary")] if metadata.get("tsc1_primary") else [],
                    "control_2_primary": [metadata.get("tsc2_primary")] if metadata.get("tsc2_primary") else [],
                    "overlap": []
                }
                if metadata.get("tsc1_primary") and metadata.get("tsc2_primary") and metadata.get("tsc1_primary") == metadata.get("tsc2_primary"):
                    criteria_differences["overlap"].append(metadata.get("tsc1_primary"))
                
                # Build test differences summary
                test_differences = ""
                if metadata.get("test_difference", 0) > 0.3:
                    test_differences = f"Test procedures differ significantly (difference score: {metadata.get('test_difference', 0):.2f})"
                elif metadata.get("test_difference", 0) > 0:
                    test_differences = f"Test procedures somewhat similar (difference score: {metadata.get('test_difference', 0):.2f})"
                else:
                    test_differences = "Test procedures identical or very similar"
                
                # Build deviation differences
                deviation_differences = ""
                if metadata.get("deviation_differs"):
                    dev1 = primary.has_deviation or False
                    dev2 = candidate.has_deviation or False
                    deviation_differences = f"Control 1: {'has deviation' if dev1 else 'no deviation'}, Control 2: {'has deviation' if dev2 else 'no deviation'}"
                else:
                    deviation_differences = "Both controls have same deviation status"
                
                # Build rationale
                rationale = f"Description similarity: {metadata.get('description_similarity', 0):.2f}. "
                if duplicate_type == "CRITERIA_VARIANT":
                    rationale += f"Different TSC/COSO mappings ({metadata.get('tsc1_primary')} vs {metadata.get('tsc2_primary')}). "
                elif duplicate_type == "TEST_VARIANT":
                    rationale += "Same criteria but different test approaches. "
                if metadata.get("page_distance", 0) > 10:
                    rationale += f"Appears in different sections (page distance: {metadata.get('page_distance')})."
                
                # Only suggest if confidence meets threshold
                if confidence >= cfg.MERGE_SUGGESTION_MIN_CONFIDENCE:
                    logging.error(f"[SUGGEST-MERGES] Adding suggestion: {ctrl_id} (primary {primary.id}, candidate {candidate.id})")
                    suggestions.append({
                        "control_id": ctrl_id,
                        "primary_db_id": primary.id,
                        "candidate_db_id": candidate.id,
                        "primary_pages": primary.control_page_refs or [],
                        "candidate_pages": candidate.control_page_refs or [],
                        "merge_confidence": round(confidence, 3),
                        "duplicate_type": duplicate_type,
                        "action": action,
                        "recommended_action": recommended_action,
                        "criteria_differences": criteria_differences,
                        "test_differences": test_differences,
                        "deviation_differences": deviation_differences,
                        "rationale": rationale,
                        "metadata": metadata,
                        "primary_desc": desc1,
                        "candidate_desc": desc2,
                        "primary_test": test1,
                        "candidate_test": test2,
                        "primary_deviation": primary.deviation_desc or "",
                        "candidate_deviation": candidate.deviation_desc or "",
                        "primary_has_deviation": primary.has_deviation or False,
                        "candidate_has_deviation": candidate.has_deviation or False
                    })
                else:
                    logging.error(f"[SUGGEST-MERGES] Confidence {confidence:.3f} below threshold {cfg.MERGE_SUGGESTION_MIN_CONFIDENCE}, skipping")
                    
                    # Flag as extraction error if description similarity is very low (<0.60)
                    desc_sim = metadata.get("description_similarity", 0)
                    if desc_sim < 0.60 and candidate.control_confidence > 0.3:
                        candidate.control_confidence = 0.3
                        note = f"\\nConfidence reduced to 0.3: Likely extraction error - duplicate control_id with dissimilar description (similarity score {desc_sim:.2f} < 0.60)"
                        candidate.confidence_calc = (candidate.confidence_calc or "") + note
                        db.add(candidate)
                        logging.error(f"[SUGGEST-MERGES] Flagged control {candidate.id} as extraction error (similarity {desc_sim:.3f})")
        
        # Flag controls with blank/null control_id as extraction errors
        blank_controls = [c for c in controls if not c.control_id or str(c.control_id).strip() == ""]
        for ctrl in blank_controls:
            if ctrl.control_confidence > 0.1:
                ctrl.control_confidence = 0.1
                note = "\\nConfidence reduced to 0.1: Extraction error - no valid control_id extracted"
                ctrl.confidence_calc = (ctrl.confidence_calc or "") + note
                db.add(ctrl)
        
        if blank_controls:
            logging.error(f"[SUGGEST-MERGES] Flagged {len(blank_controls)} controls with blank control_id as extraction errors")
        
        # Commit any confidence updates for extraction errors
        await db.commit()
        
        # Limit results
        suggestions.sort(key=lambda s: s["merge_confidence"], reverse=True)
        suggestions = suggestions[:cfg.MERGE_SUGGESTION_MAX_RESULTS]
        
        logging.error(f"[SUGGEST-MERGES] Returning {len(suggestions)} suggestions (threshold: {cfg.MERGE_SUGGESTION_MIN_CONFIDENCE})")
        
        return {
            "suggestions": suggestions,
            "total_suggested": len(suggestions),
            "threshold": cfg.MERGE_SUGGESTION_MIN_CONFIDENCE
        }
        
    except Exception as e:
        logging.error(f"Error suggesting merges for scan {scan_id}: {e}", exc_info=True)
        return {"error": str(e), "suggestions": [], "total_suggested": 0}


async def intelligently_merge_field(
    field_name: str,
    controls: List[Control],
    use_ai: bool = True
) -> Dict[str, Any]:
    """
    Merge field values using tiered strategy (Tier 1: Exact/Substring, Tier 2: Bullets, Tier 3: AI).
    
    Tier 1: Fast exact match and substring detection
    Tier 2: Structural bullet merging with preservation
    Tier 3: AI-powered consolidation for complex cases
    
    Args:
        field_name: Name of Control model field to merge
        controls: List of Control objects to consolidate
        use_ai: Enable AI consolidation (respects MERGE_STRATEGY config)
        
    Returns:
        Dictionary with:
            - consolidated_value: The merged text
            - strategy_used: Which tier/method was applied
            - confidence: 0.0-1.0 merge confidence
            - rationale: Explanation of merge decision
            - preview_required: True if human review recommended
            - ai_response: Raw AI response (if Tier 3 used)
    """
    from ..utils.text_analysis import (
        extract_bullets, is_substring_match, calculate_text_difference,
        has_bullet_structure, merge_bullet_lists
    )
    from .. import config as cfg
    
    # Get all non-null values for this field
    values = [(c, getattr(c, field_name)) for c in controls if getattr(c, field_name, None)]
    
    if not values:
        return {
            "consolidated_value": None,
            "strategy_used": "none",
            "confidence": 1.0,
            "rationale": "No values to merge",
            "preview_required": False
        }
    
    if len(values) == 1:
        return {
            "consolidated_value": values[0][1],
            "strategy_used": "single_value",
            "confidence": 1.0,
            "rationale": "Only one control has this field",
            "preview_required": False
        }
    
    # Extract just the text values
    texts = [v[1] for v in values]
    
    # TIER 1: Exact Match Detection
    if all(t.strip() == texts[0].strip() for t in texts):
        return {
            "consolidated_value": texts[0],
            "strategy_used": "exact_match",
            "confidence": 1.0,
            "rationale": "All instances have identical text",
            "preview_required": False
        }
    
    # TIER 1: Substring Detection
    is_subset, longer_text = is_substring_match(texts[0], texts[1]) if len(texts) == 2 else (False, "")
    if is_subset and longer_text:
        # Verify with remaining texts if more than 2
        if len(texts) > 2:
            all_subsets = all(is_substring_match(longer_text, t)[0] for t in texts[2:])
            if all_subsets:
                return {
                    "consolidated_value": longer_text,
                    "strategy_used": "substring",
                    "confidence": 0.95,
                    "rationale": "One description is a superset containing all others",
                    "preview_required": False
                }
        else:
            return {
                "consolidated_value": longer_text,
                "strategy_used": "substring",
                "confidence": 0.95,
                "rationale": "One description contains the other as a substring",
                "preview_required": False
            }
    
    # TIER 2: Structural Analysis (Bullet Merging)
    if cfg.MERGE_PRESERVE_ALL_BULLETS and all(has_bullet_structure(t) for t in texts):
        # Extract bullets from all instances
        all_bullets = [extract_bullets(t) for t in texts]
        
        # Check if it's just ordering differences
        sets = [set(bullets) for bullets in all_bullets]
        if len(sets) > 1 and sets[0] == sets[1]:
            # Same bullets, different order - use first instance's order
            return {
                "consolidated_value": texts[0],
                "strategy_used": "bullet_reorder",
                "confidence": 0.90,
                "rationale": "Same bullet points in different order",
                "preview_required": False
            }
        
        # Merge bullets intelligently
        merged_bullets = all_bullets[0]
        for bullets in all_bullets[1:]:
            merged_bullets = merge_bullet_lists(merged_bullets, bullets)
        
        # Reconstruct with original bullet style from first instance
        sample_text = texts[0]
        bullet_char = '•' if '•' in sample_text else '-' if ' - ' in sample_text else '•'
        consolidated = '\n'.join(f"{bullet_char} {bullet}" for bullet in merged_bullets)
        
        return {
            "consolidated_value": consolidated,
            "strategy_used": "bullet_merge",
            "confidence": 0.85,
            "rationale": f"Merged {len(all_bullets)} bullet lists, preserving {len(merged_bullets)} unique points",
            "preview_required": len(merged_bullets) > sum(len(b) for b in all_bullets) * 0.6  # Review if >60% growth
        }
    
    # Check if AI merge is disabled or not needed
    if not use_ai or cfg.MERGE_STRATEGY == "longest":
        longest = max(texts, key=len)
        return {
            "consolidated_value": longest,
            "strategy_used": "longest",
            "confidence": 0.70,
            "rationale": "Using longest value (AI merge disabled)",
            "preview_required": True
        }
    
    # Calculate difference to decide if AI is worth it
    diff = calculate_text_difference(texts[0], texts[1])
    if diff < cfg.MERGE_AI_MIN_DIFF_THRESHOLD:
        # Very similar, just use longer
        longer = texts[0] if len(texts[0]) > len(texts[1]) else texts[1]
        return {
            "consolidated_value": longer,
            "strategy_used": "minimal_difference",
            "confidence": 0.85,
            "rationale": f"Texts differ by only {diff*100:.1f}%, using longer version",
            "preview_required": False
        }
    
    # TIER 3: AI-Powered Consolidation
    try:
        # Build context for GPT
        instances_text = ""
        for idx, (ctrl, text) in enumerate(values, 1):
            pages = ctrl.control_page_refs or []
            instances_text += f"\n### Instance {idx} (DB ID: {ctrl.id}, Pages: {pages})\n{text}\n"
        
        # Use configured prompt from config.py
        field_label = field_name.replace('_', ' ')
        prompt = cfg.MERGE_CONSOLIDATION_PROMPT.format(
            control_id=controls[0].control_id,
            field_name=field_name,
            field_label=field_label,
            instances_text=instances_text
        )

        response = await gpt_extract(prompt, model="gpt-4", max_tokens=3000)
        
        # Parse GPT response
        import json
        result = json.loads(response)
        
        if not result.get("is_truly_duplicate", True):
            # AI detected these should NOT be merged
            logging.error(f"[AI-MERGE] AI determined controls are not duplicates: {result.get('merge_rationale')}")
            longest = max(texts, key=len)
            return {
                "consolidated_value": longest,
                "strategy_used": "ai_rejected",
                "confidence": 0.0,
                "rationale": f"AI analysis: {result.get('merge_rationale', 'Not truly duplicate controls')}",
                "preview_required": True,
                "ai_response": result
            }
        
        return {
            "consolidated_value": result["consolidated_text"],
            "strategy_used": "ai_consolidation",
            "confidence": result.get("confidence", 0.80),
            "rationale": result.get("merge_rationale", "AI-powered intelligent consolidation"),
            "preview_required": result.get("requires_review", False) or result.get("confidence", 0.80) < cfg.MERGE_AI_AUTO_APPLY_THRESHOLD,
            "ai_response": result
        }
        
    except Exception as e:
        logging.error(f"[AI-MERGE] Error in AI consolidation: {e}", exc_info=True)
        # Fallback to longest
        longest = max(texts, key=len)
        return {
            "consolidated_value": longest,
            "strategy_used": "ai_error_fallback",
            "confidence": 0.70,
            "rationale": f"AI merge failed ({str(e)}), using longest value",
            "preview_required": True
        }


async def merge_controls_action(
    scan_id: int,
    primary_control_id: Optional[int],
    merge_control_ids: List[int],
    db
) -> Dict[str, Any]:
    """
    Merge duplicate controls into a primary control with intelligent selection.
    
    Actions:
    - Intelligently selects primary (longest description, highest confidence, lowest ID)
    - Consolidates all data fields into primary (longest non-null values)
    - Merges page_refs arrays
    - Sets merged_to_control_id and confidence=0 on secondary controls
    - Ensures primary has merged_to_control_id=NULL
    
    Args:
        scan_id: Scan identifier
        primary_control_id: Optional suggested primary control DB ID
        merge_control_ids: List of control DB IDs to merge
        db: Async database session
        
    Returns:
        Dictionary with merge status and details
    """
    import json
    try:
        if not merge_control_ids:
            return {"error": "merge_control_ids required", "status": "error"}
        
        # Get all controls involved (suggested primary + merge candidates)
        all_ids = [primary_control_id] + merge_control_ids if primary_control_id else merge_control_ids
        result = await db.execute(
            select(Control).where(Control.scan_id == scan_id, Control.id.in_(all_ids))
        )
        all_controls = result.scalars().all()
        
        if len(all_controls) < 2:
            return {"error": "Need at least 2 controls to merge", "status": "error"}
        
        # Intelligently select primary control
        def control_score(ctrl):
            desc_len = len(ctrl.control_desc or "")
            conf = ctrl.control_confidence or 0
            return (desc_len, conf, -ctrl.id)  # Negative ID so max() picks lowest
        
        primary = max(all_controls, key=control_score)
        secondaries = [c for c in all_controls if c.id != primary.id]
        
        logging.error(f"[MERGE] Control IDs involved: {[c.id for c in all_controls]}, control_id: {primary.control_id}")
        logging.error(f"[MERGE] Selected primary control {primary.id} (desc_len={len(primary.control_desc or '')}, conf={primary.control_confidence})")
        logging.error(f"[MERGE] Secondaries to merge: {[c.id for c in secondaries]}")
        
        # Helper function to get highest value
        def get_max(field_name):
            values = [getattr(c, field_name) for c in all_controls if getattr(c, field_name, None) is not None]
            return max(values) if values else None
        
        # Import config to check merge strategy
        from .. import config as cfg
        use_ai_merge = cfg.MERGE_STRATEGY == "ai_enhanced"
        
        # Consolidate data into primary from all controls using intelligent merge
        merge_metadata = {}
        
        # Merge control_desc
        desc_result = await intelligently_merge_field('control_desc', all_controls, use_ai=use_ai_merge)
        primary.control_desc = desc_result['consolidated_value'] or primary.control_desc
        merge_metadata['control_desc'] = {
            'strategy': desc_result['strategy_used'],
            'confidence': desc_result['confidence'],
            'rationale': desc_result['rationale']
        }
        logging.error(f"[MERGE] control_desc: {desc_result['strategy_used']} (confidence: {desc_result['confidence']:.2f})")
        
        # Merge control_test (if config includes test procedures)
        if cfg.MERGE_AI_INCLUDE_TEST_PROCEDURES:
            test_result = await intelligently_merge_field('control_test', all_controls, use_ai=use_ai_merge)
            primary.control_test = test_result['consolidated_value'] or primary.control_test
            merge_metadata['control_test'] = {
                'strategy': test_result['strategy_used'],
                'confidence': test_result['confidence'],
                'rationale': test_result['rationale']
            }
            logging.error(f"[MERGE] control_test: {test_result['strategy_used']} (confidence: {test_result['confidence']:.2f})")
        else:
            # Fallback to longest
            test_values = [c.control_test for c in all_controls if c.control_test]
            primary.control_test = max(test_values, key=len) if test_values else primary.control_test
            merge_metadata['control_test'] = {'strategy': 'longest', 'confidence': 0.70, 'rationale': 'AI merge disabled for test procedures'}
        
        # Merge control_test_results
        results_result = await intelligently_merge_field('control_test_results', all_controls, use_ai=use_ai_merge)
        primary.control_test_results = results_result['consolidated_value'] or primary.control_test_results
        merge_metadata['control_test_results'] = {
            'strategy': results_result['strategy_used'],
            'confidence': results_result['confidence'],
            'rationale': results_result['rationale']
        }
        
        # Merge deviation_desc
        deviation_result = await intelligently_merge_field('deviation_desc', all_controls, use_ai=use_ai_merge)
        primary.deviation_desc = deviation_result['consolidated_value'] or primary.deviation_desc
        merge_metadata['deviation_desc'] = {
            'strategy': deviation_result['strategy_used'],
            'confidence': deviation_result['confidence'],
            'rationale': deviation_result['rationale']
        }
        
        # Preserve has_deviation flag - set to True if ANY control has a deviation
        has_any_deviation = any(getattr(c, 'has_deviation', False) for c in all_controls)
        if has_any_deviation:
            primary.has_deviation = True
            if not primary.deviation_desc:
                primary.deviation_desc = get_longest('deviation_desc')
        
        # Use highest confidence
        max_confidence = get_max('control_confidence')
        if max_confidence and max_confidence > (primary.control_confidence or 0):
            old_conf = primary.control_confidence
            primary.control_confidence = max_confidence
            conf_note = f"Confidence increased from {old_conf:.2f} to {max_confidence:.2f} during merge (took highest from duplicates)"
            primary.confidence_calc = f"{primary.confidence_calc}\\n{conf_note}" if primary.confidence_calc else conf_note
        
        # Merge page references from all controls
        all_pages = []
        for ctrl in all_controls:
            if ctrl.control_page_refs:
                all_pages.extend(ctrl.control_page_refs)
        primary.control_page_refs = sorted(list(set(all_pages)))
        
        # Ensure primary is NOT marked as merged
        primary.merged_to_control_id = None
        
        # Process secondary controls
        merged_ids_list = []
        for ctrl in secondaries:
            original_conf = ctrl.control_confidence or 0
            
            # Mark as merged to primary
            ctrl.merged_to_control_id = str(primary.id)
            ctrl.control_confidence = 0.0
            
            # Document the merge in confidence_calc
            merge_calc_note = f"Merged to control {primary.id} on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Original confidence: {original_conf:.2f} | New confidence: 0.0 (merged duplicate)"
            ctrl.confidence_calc = f"{ctrl.confidence_calc}\\n{merge_calc_note}" if ctrl.confidence_calc else merge_calc_note
            
            # Store original data in annotation for undo
            annotation_data = {
                "merged_at": str(datetime.datetime.now()),
                "original_confidence": original_conf,
                "merged_to": primary.id,
                "original_desc_length": len(ctrl.control_desc or ""),
                "original_pages": ctrl.control_page_refs
            }
            ctrl.annotation = json.dumps(annotation_data) if not ctrl.annotation else f"{ctrl.annotation}\\n{json.dumps(annotation_data)}"
            
            merged_ids_list.append(ctrl.id)
            db.add(ctrl)
        
        # Update primary annotation
        merge_note = f"Consolidated from {len(secondaries)} duplicate(s) (IDs: {', '.join(map(str, merged_ids_list))}) on {datetime.datetime.now()}"
        primary.annotation = f"{primary.annotation}\\n{merge_note}" if primary.annotation else merge_note
        
        # Track merge history
        merge_event = {
            "timestamp": datetime.datetime.now().isoformat(),
            "type": "manual",
            "confidence": None,
            "merged_from_ids": [str(sid) for sid in merged_ids_list],
            "reason": "Manual merge via UI"
        }
        if not primary.merge_history:
            primary.merge_history = []
        primary.merge_history.append(merge_event)
        
        db.add(primary)
        
        # Mark executive summary stale
        scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if scan_row:
            scan_row.executive_summary_stale = True
            db.add(scan_row)
        
        await db.commit()
        
        logging.error(f"[MERGE] Commit successful. Primary {primary.id}, Secondaries {merged_ids_list} now have merged_to_control_id={primary.id}, confidence=0")
        
        return {
            "status": "ok",
            "primary_id": primary.id,
            "merged_count": len(secondaries),
            "merged_ids": merged_ids_list,
            "consolidated_pages": primary.control_page_refs,
            "primary_confidence": primary.control_confidence,
            "consolidation_details": {
                "selected_primary": f"ID {primary.id} (desc_len={len(primary.control_desc or '')}, conf={primary.control_confidence})",
                "consolidated_fields": ["control_desc", "control_test", "control_test_results", "deviation_desc", "has_deviation", "control_page_refs", "control_confidence"]
            },
            "merge_metadata": merge_metadata
        }
        
    except Exception as e:
        await db.rollback()
        logging.error(f"Error merging controls for scan {scan_id}: {e}", exc_info=True)
        return {"error": str(e), "status": "error"}


async def split_control(scan_id: int, control_db_id: int, db) -> Dict[str, Any]:
    """
    Undo a control merge by restoring merged controls.
    
    If this control has been merged INTO another control:
    - Clears merged_to_control_id
    - Restores original confidence from annotation backup
    
    Args:
        scan_id: Scan identifier
        control_db_id: Control database ID to split
        db: Async database session
        
    Returns:
        Dictionary with split status and details
    """
    import json
    try:
        # Get the control
        ctrl = (await db.execute(
            select(Control).where(Control.scan_id == scan_id, Control.id == control_db_id)
        )).scalar_one_or_none()
        
        if not ctrl:
            return {"error": "Control not found", "status": "error"}
        
        # Check if this control was merged into another
        if not ctrl.merged_to_control_id:
            return {"error": "This control is not merged, nothing to split", "status": "error"}
        
        # Restore from annotation backup
        original_confidence = 0.5  # Default fallback
        
        if ctrl.annotation:
            try:
                # Try to parse JSON backup
                lines = ctrl.annotation.split("\\n")
                for line in lines:
                    if line.strip().startswith("{"):
                        annotation_data = json.loads(line)
                        if "original_confidence" in annotation_data:
                            original_confidence = annotation_data["original_confidence"]
                            break
            except Exception as e:
                logging.warning(f"Could not parse annotation backup for control {control_db_id}: {e}")
        
        # Restore control
        ctrl.merged_to_control_id = None
        ctrl.control_confidence = original_confidence
        
        # Add split note to annotation
        split_note = f"Split/unmerged on {datetime.datetime.now()}, confidence restored to {original_confidence}"
        ctrl.annotation = f"{ctrl.annotation}\\n{split_note}" if ctrl.annotation else split_note
        
        db.add(ctrl)
        
        # Mark executive summary stale
        scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if scan_row:
            scan_row.executive_summary_stale = True
            db.add(scan_row)
        
        await db.commit()
        
        logging.error(f"[SPLIT] Control {control_db_id} unmerged, confidence restored to {original_confidence}")
        
        return {
            "status": "ok",
            "control_id": control_db_id,
            "restored_confidence": original_confidence
        }
        
    except Exception as e:
        await db.rollback()
        logging.error(f"Error splitting control {control_db_id} for scan {scan_id}: {e}", exc_info=True)
        return {"error": str(e), "status": "error"}
