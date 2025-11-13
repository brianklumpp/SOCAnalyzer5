"""
Enhanced Subservice Organizations Post-Processor

This module provides intelligent deduplication and confidence adjustment
for subservice organizations using GPT-4 analysis.

Addresses two main issues:
1. Duplicate/similar entries (e.g., AWS, Amazon Web Services, Amazon Web Services (AWS))
2. SaaS applications incorrectly classified as subservice orgs (Splunk, Workday, etc.)
"""

import json
import logging
import time
from ..config import DEDUPLICATION_PROMPT, SAAS_CLASSIFICATION_PROMPT


def deduplicate_with_gpt(subservice_orgs):
    """
    Use GPT to identify duplicate/similar entries and merge them.
    
    Args:
        subservice_orgs: List of subservice org dicts
        
    Returns:
        Deduplicated list with merged entries
    """
    if not subservice_orgs:
        return subservice_orgs
    
    logger.info(f"[Dedup] Starting GPT-based deduplication for {len(subservice_orgs)} entries...")
    
    # Prepare simplified data for GPT
    simplified = [
        {
            "name": org.get("third_party_name"),
            "description": org.get("third_party_description", "")[:200],  # Truncate long descriptions
            "confidence": org.get("third_party_confidence")
        }
        for org in subservice_orgs
        if org.get("third_party_confidence", 0) >= 0.7  # Only look at high-confidence entries
    ]
    
    if len(simplified) < 2:
        logger.info("[Dedup] Less than 2 entries, skipping deduplication")
        return subservice_orgs
    
    prompt = DEDUPLICATION_PROMPT.format(json_data=json.dumps(simplified, indent=2))
    
    try:
        response = gpt_extract(prompt, 'subservice_orgs_dedup')
        
        # Parse response
        clean_response = response.strip()
        if clean_response.startswith('```json'):
            clean_response = clean_response[7:]
        if clean_response.startswith('```'):
            clean_response = clean_response[3:]
        if clean_response.endswith('```'):
            clean_response = clean_response[:-3]
        clean_response = clean_response.strip()
        
        result = json.loads(clean_response)
        groups = result.get("groups", [])
        
        if not groups:
            logger.info("[Dedup] No duplicate groups found")
            return subservice_orgs
        
        logger.info(f"[Dedup] Found {len(groups)} duplicate groups")
        
        # Build mapping: variation name (lowercase) -> canonical name
        variation_to_canonical = {}
        for group in groups:
            canonical = group.get("canonical_name")
            variations = group.get("variations", [])
            reason = group.get("reason", "")
            
            logger.info(f"[Dedup] Group: {canonical} with {len(variations)} variations - {reason}")
            
            for var in variations:
                variation_to_canonical[var.lower().strip()] = canonical
        
        # Merge entries
        merged = {}
        low_conf_variations = set()
        for org in subservice_orgs:
            name = org.get("third_party_name", "")
            name_lower = name.lower().strip()
            # Check if this is a variation that should be merged
            if name_lower in variation_to_canonical:
                canonical = variation_to_canonical[name_lower]
                canonical_lower = canonical.lower().strip()
                if canonical_lower in merged:
                    # Merge with existing canonical entry
                    existing = merged[canonical_lower]
                    # Merge page refs
                    if org.get("third_party_page_ref"):
                        if existing.get("third_party_page_ref"):
                            existing["third_party_page_ref"] += "," + str(org["third_party_page_ref"])
                        else:
                            existing["third_party_page_ref"] = str(org["third_party_page_ref"])
                    # Merge controls
                    if org.get("third_party_controls"):
                        if existing.get("third_party_controls"):
                            existing["third_party_controls"].extend(org["third_party_controls"])
                        else:
                            existing["third_party_controls"] = org["third_party_controls"]
                    # Use higher confidence
                    if org.get("third_party_confidence", 0) > existing.get("third_party_confidence", 0):
                        existing["third_party_confidence"] = org["third_party_confidence"]
                    # Merge confidence justifications
                    existing_just = existing.get("confidence_justification", [])
                    if isinstance(existing_just, str):
                        existing_just = [existing_just]
                    org_just = org.get("confidence_justification", [])
                    if isinstance(org_just, str):
                        org_just = [org_just]
                    existing["confidence_justification"] = existing_just + org_just + [f"Merged duplicate: {name}"]
                    logger.info(f"[Dedup] Merged '{name}' into '{canonical}'")
                    # Mark this variation for low confidence
                    low_conf_variations.add(name_lower)
                else:
                    # First entry for this canonical name
                    org_copy = org.copy()
                    org_copy["third_party_name"] = canonical
                    # Add justification
                    just = org_copy.get("confidence_justification", [])
                    if isinstance(just, str):
                        just = [just]
                    if name.lower() != canonical.lower():
                        just.append(f"Standardized from: {name}")
                    org_copy["confidence_justification"] = just
                    merged[canonical_lower] = org_copy
                    logger.info(f"[Dedup] Standardized '{name}' to '{canonical}'")
                    # Mark this variation for low confidence
                    low_conf_variations.add(name_lower)
            else:
                # No duplicate, keep as-is
                if name_lower not in merged:
                    merged[name_lower] = org
        # After merging, set low confidence for all variations except canonical
        result_list = list(merged.values())
        for org in result_list:
            canonical = org["third_party_name"].lower().strip()
            # If this is a canonical entry, keep its confidence
            # If not, set confidence low and add justification
            if canonical not in variation_to_canonical.values():
                org["third_party_confidence"] = 0.2
                just = org.get("confidence_justification", [])
                if isinstance(just, str):
                    just = [just]
                just.append("Set low confidence: not canonical after deduplication")
                org["confidence_justification"] = just
        logger.info(f"[Dedup] Reduced from {len(subservice_orgs)} to {len(result_list)} entries")
        return result_list
        
    except Exception as e:
        logger.error(f"[Dedup] GPT deduplication failed: {e}")
        return subservice_orgs


def adjust_saas_confidence(subservice_orgs):
    """
    Use GPT to identify SaaS applications that shouldn't be high-confidence subservice orgs.
    
    Args:
        subservice_orgs: List of subservice org dicts
        
    Returns:
        List with adjusted confidence scores
    """
    if not subservice_orgs:
        return subservice_orgs
    
    logger.info(f"[SaaS Adjust] Starting GPT-based SaaS classification for {len(subservice_orgs)} entries...")
    
    # Only analyze high-confidence entries
    high_conf = [
        org for org in subservice_orgs
        if org.get("third_party_confidence", 0) >= 0.8
    ]
    
    if not high_conf:
        logger.info("[SaaS Adjust] No high-confidence entries to analyze")
        return subservice_orgs
    
    # Prepare simplified data for GPT
    simplified = [
        {
            "name": org.get("third_party_name"),
            "description": org.get("third_party_description", "")[:300],
            "confidence": org.get("third_party_confidence")
        }
        for org in high_conf
    ]
    
    prompt = SAAS_CLASSIFICATION_PROMPT.format(json_data=json.dumps(simplified, indent=2))
    
    try:
        response = gpt_extract(prompt, 'subservice_orgs_saas_classify')
        
        # Parse response
        clean_response = response.strip()
        if clean_response.startswith('```json'):
            clean_response = clean_response[7:]
        if clean_response.startswith('```'):
            clean_response = clean_response[3:]
        if clean_response.endswith('```'):
            clean_response = clean_response[:-3]
        clean_response = clean_response.strip()
        
        result = json.loads(clean_response)
        adjustments = result.get("adjustments", [])
        
        if not adjustments:
            logger.info("[SaaS Adjust] No adjustments needed")
            return subservice_orgs
        
        logger.info(f"[SaaS Adjust] Found {len(adjustments)} entries needing adjustment")
        
        # Build mapping: name (lowercase) -> adjustment
        adjustment_map = {}
        for adj in adjustments:
            if adj.get("should_reduce"):
                name = adj.get("name", "").lower().strip()
                adjustment_map[name] = adj
                logger.info(f"[SaaS Adjust] {adj['name']}: {adj['current_confidence']} -> {adj['suggested_confidence']} ({adj['category']})")
        
        # Apply adjustments
        adjusted_count = 0
        for org in subservice_orgs:
            name = org.get("third_party_name", "").lower().strip()
            
            if name in adjustment_map:
                adj = adjustment_map[name]
                old_conf = org.get("third_party_confidence", 0)
                new_conf = adj.get("suggested_confidence", old_conf)
                
                org["third_party_confidence"] = new_conf
                
                # Add justification
                just = org.get("confidence_justification", [])
                if isinstance(just, str):
                    just = [just]
                just.append(f"Confidence adjusted: {old_conf} -> {new_conf}. Reason: {adj.get('reason', 'SaaS tool classification')}")
                org["confidence_justification"] = just
                
                adjusted_count += 1
                logger.info(f"[SaaS Adjust] Applied adjustment to {org['third_party_name']}")
        
        logger.info(f"[SaaS Adjust] Adjusted {adjusted_count} entries")
        
        return subservice_orgs
        
    except Exception as e:
        logger.error(f"[SaaS Adjust] GPT classification failed: {e}")
        return subservice_orgs


def enhance_subservice_orgs(subservice_orgs):
    """
    Main enhancement function that applies both deduplication and confidence adjustment.
    
    Args:
        subservice_orgs: List of subservice org dicts
        
    Returns:
        Enhanced list with deduplication and adjusted confidence
    """
    logger.info("="*80)
    logger.info("[Enhance] Starting enhanced subservice orgs processing...")
    logger.info(f"[Enhance] Input: {len(subservice_orgs)} organizations")
    logger.info("="*80)
    
    # Step 1: Deduplicate similar entries
    deduplicated = deduplicate_with_gpt(subservice_orgs)
    logger.info(f"[Enhance] After deduplication: {len(deduplicated)} organizations")
    
    # Rate limit between GPT calls
    time.sleep(1)
    
    # Step 2: Adjust confidence for SaaS applications
    enhanced = adjust_saas_confidence(deduplicated)
    logger.info(f"[Enhance] After SaaS adjustment: {len(enhanced)} organizations")
    
    # Step 3: Final confidence adjustment based on likely_so, common_so, and distance_from_so_keywords
    for org in enhanced:
        just = org.get("confidence_justification", [])
        if isinstance(just, str):
            just = [just]
        conf = org.get("third_party_confidence", 0)
        # likely_so
        likely_so = str(org.get("likely_so", "")).strip().lower()
        if likely_so == "no":
            conf -= 0.2
            just.append("-0.2: likely_so is No")
        elif likely_so == "yes":
            conf += 0.1
            just.append("+0.1: likely_so is Yes")
        # common_so
        common_so = str(org.get("common_so", "")).strip().lower()
        if common_so == "yes":
            conf += 0.1
            just.append("+0.1: common_so is Yes")
        # distance_from_so_keywords
        dist = org.get("distance_from_so_keywords", None)
        try:
            dist = float(dist)
        except Exception:
            dist = None
        if dist is not None:
            if dist <= 2:
                conf += 0.1
                just.append(f"+0.1: distance_from_so_keywords is {dist} (very close)")
            elif dist >= 10:
                conf -= 0.1
                just.append(f"-0.1: distance_from_so_keywords is {dist} (far)")
        # Clamp confidence
        conf = min(1.0, max(0.0, conf))
        org["third_party_confidence"] = round(conf, 3)
        org["confidence_justification"] = just
    # Step 4: Re-sort by confidence
    enhanced.sort(key=lambda x: x.get("third_party_confidence", 0), reverse=True)
    logger.info("="*80)
    logger.info("[Enhance] Enhancement complete!")
    logger.info(f"[Enhance] Final count: {len(enhanced)} organizations")
    logger.info("="*80)
    return enhanced


__all__ = ["enhance_subservice_orgs", "deduplicate_with_gpt", "adjust_saas_confidence"]
