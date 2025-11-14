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
from ..gpt_client import gpt_extract

# Module logger
logger = logging.getLogger(__name__)


def _ensure_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def _merge_unique(a, b):
    out = list(a or [])
    for item in (b or []):
        if item not in out:
            out.append(item)
    return out


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

    # Prepare simplified data for GPT (include all entries so GPT can see lower-confidence variants)
    simplified = [
        {
            "name": org.get("third_party_name"),
            "description": org.get("third_party_description", "")[:200],
            "confidence": org.get("third_party_confidence")
        }
        for org in subservice_orgs
    ]

    if len(simplified) < 2:
        logger.info("[Dedup] Less than 2 entries, skipping deduplication")
        return subservice_orgs

    # Use replace instead of format to avoid KeyError when the prompt contains braces
    prompt = DEDUPLICATION_PROMPT.replace("{json_data}", json.dumps(simplified, indent=2))

    try:
        response = gpt_extract(prompt, 'subservice_orgs_dedup')

        # Parse response defensively
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

        # Build variation -> canonical mapping and store group reasons and variations
        variation_to_canonical = {}
        canonical_groups = {}
        for group in groups:
            canonical = group.get("canonical_name")
            variations = group.get("variations", [])
            reason = group.get("reason", "")
            if not canonical:
                continue
            canonical_lower = canonical.lower().strip()
            canonical_groups[canonical_lower] = {
                "canonical_name": canonical,
                "aliases": [v for v in variations],
                "dedup_reason": reason,
                "aggregated_third_party_page_ref": [],
                "aggregated_third_party_controls": [],
                "canonical_confidence": 0.0,
            }
            logger.info(f"[Dedup] Group: {canonical} with {len(variations)} variations - {reason}")
            for var in variations:
                variation_to_canonical[var.lower().strip()] = canonical

        # Annotate originals and gather aggregation for canonical summaries
        for org in subservice_orgs:
            # Normalize page refs to lists
            pr = org.get("third_party_page_ref")
            if pr is not None:
                if isinstance(pr, list):
                    pr_list = [str(x) for x in pr]
                else:
                    pr_list = [str(pr)]
            else:
                pr_list = []
            org["third_party_page_ref"] = pr_list

            name = org.get("third_party_name", "")
            name_lower = name.lower().strip()

            # If this entry maps to a canonical, annotate and adjust confidence (non-destructive)
            if name_lower in variation_to_canonical:
                canonical = variation_to_canonical[name_lower]
                canonical_lower = canonical.lower().strip()
                org["canonical_name"] = canonical
                
                # Only reduce confidence if this is NOT the canonical form itself
                # (e.g., "AWS" is a variant, but "Amazon Web Services, Inc. (AWS)" is canonical)
                is_canonical_form = (name_lower == canonical_lower)
                
                old_conf = org.get("third_party_confidence", 0)
                if not is_canonical_form:
                    # Lower variant confidence (keep primary high). Use conservative reduction.
                    new_conf = min(old_conf, 0.2)
                    if new_conf != old_conf:
                        org["third_party_confidence"] = new_conf
                        just = org.get("confidence_justification", [])
                        if isinstance(just, str):
                            just = [just]
                        just.append(f"Marked as variant of {canonical}; confidence reduced {old_conf} -> {new_conf}")
                        org["confidence_justification"] = just
                else:
                    # This IS the canonical form - preserve confidence, just annotate
                    just = org.get("confidence_justification", [])
                    if isinstance(just, str):
                        just = [just]
                    just.append(f"Identified as canonical form of group; confidence preserved at {old_conf}")
                    org["confidence_justification"] = just
                # Aggregate into canonical summary
                cg = canonical_groups.get(canonical_lower)
                if cg is not None:
                    cg["aggregated_third_party_page_ref"] = _merge_unique(cg["aggregated_third_party_page_ref"], pr_list)
                    cg["aggregated_third_party_controls"] = _merge_unique(cg["aggregated_third_party_controls"], org.get("third_party_controls") or [])
                    try:
                        cg["canonical_confidence"] = max(cg.get("canonical_confidence", 0.0), float(old_conf or 0))
                    except Exception:
                        pass
            else:
                # If entry itself looks like the canonical name, include it in aggregation
                if name_lower in canonical_groups:
                    org["canonical_name"] = canonical_groups[name_lower]["canonical_name"]
                    cg = canonical_groups[name_lower]
                    cg["aggregated_third_party_page_ref"] = _merge_unique(cg["aggregated_third_party_page_ref"], pr_list)
                    cg["aggregated_third_party_controls"] = _merge_unique(cg["aggregated_third_party_controls"], org.get("third_party_controls") or [])
                    try:
                        cg["canonical_confidence"] = max(cg.get("canonical_confidence", 0.0), float(org.get("third_party_confidence", 0) or 0))
                    except Exception:
                        pass

        # Build canonical summary objects to return alongside originals
        canonical_summaries = []
        for cl, cg in canonical_groups.items():
            # Ensure lists are unique and strings
            page_refs = [str(x) for x in cg.get("aggregated_third_party_page_ref", [])]
            controls = cg.get("aggregated_third_party_controls", [])

            # Deterministic aggregation: canonical confidence is the max of member confidences
            canonical_conf = round(cg.get("canonical_confidence", 0.0) or 0.0, 3)

            # Merge justifications from member variants where present (de-duplicate)
            merged_just = []
            aliases = cg.get("aliases", []) or []
            # Build a short aggregation summary
            merged_just.append(f"Aggregated from {len(aliases)} variant rows; canonical_confidence = max(variant_confidences) = {canonical_conf}")
            # We will not attempt to harvest every variant's justification here (they remain on the variants),
            # but include a note that variants exist and where to find them.
            if aliases:
                merged_just.append("Variants: " + ", ".join(aliases[:10]))

            summary_obj = {
                "is_canonical_summary": True,
                "canonical_name": cg["canonical_name"],
                "aliases": aliases,
                # Expose aggregated page refs under the canonical standard field name used elsewhere
                "third_party_page_ref": page_refs or None,
                "aggregated_third_party_controls": controls,
                "dedup_reason": cg.get("dedup_reason", ""),
                # Provide canonical confidence in the same field used by downstream logic
                "third_party_confidence": canonical_conf,
                # Helpful audit/provenance
                "confidence_justification": merged_just,
                "merged_from_count": len(aliases),
                "merged_from_variants": aliases,
                "merged_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            }
            canonical_summaries.append(summary_obj)

        logger.info(f"[Dedup] Annotated {len(subservice_orgs)} originals; produced {len(canonical_summaries)} canonical summaries")
        # Return originals (possibly adjusted) plus canonical summaries (non-destructive)
        return list(subservice_orgs) + canonical_summaries

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
    
    # Use replace instead of format to avoid KeyError when prompt contains braces
    prompt = SAAS_CLASSIFICATION_PROMPT.replace("{json_data}", json.dumps(simplified, indent=2))
    
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
            # Match against raw name and optional canonical_name
            name = org.get("third_party_name", "").lower().strip()
            cname = (org.get("canonical_name") or "").lower().strip()

            key = None
            if name in adjustment_map:
                key = name
            elif cname and cname in adjustment_map:
                key = cname

            if key:
                adj = adjustment_map[key]
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
                logger.info(f"[SaaS Adjust] Applied adjustment to {org.get('third_party_name')} (matched {key})")
        
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
