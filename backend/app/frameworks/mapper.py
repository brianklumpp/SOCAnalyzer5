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
from typing import Dict, Any, Optional

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
            
            # Call GPT
            response = gpt_extract(framework_prompt, f"framework_{framework_name.lower()}_matching")
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


__all__ = [
    # Dynamic multi-framework mapping
    'map_control_to_frameworks_dynamic',
    'map_cuec_to_frameworks_dynamic',
    
    # Helper functions
    'extract_mapping_fields_for_db',
    'get_primary_criterion_details',
    'log_token_usage'
]
