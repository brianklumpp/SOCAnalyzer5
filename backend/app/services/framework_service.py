"""
Framework Service
Handles framework criteria loading and management.
"""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def get_all_framework_criteria() -> Dict[str, Any]:
    """
    Get all framework criteria grouped by framework and section.
    Returns a dynamic structure supporting all registered frameworks.
    
    Returns:
        Dictionary mapping framework names to their criteria grouped by section
    """
    from ..frameworks import FRAMEWORK_REGISTRY, load_framework_criteria
    
    result = {}
    
    for framework_name, framework_info in FRAMEWORK_REGISTRY.items():
        criteria_list = load_framework_criteria(framework_name)
        
        if not criteria_list:
            continue  # Skip frameworks without criteria definitions
        
        # Group criteria by section/component/category
        grouped = {}
        for crit in criteria_list:
            # Determine grouping key based on framework structure
            # TSC uses "domain", COSO uses "component", others use "section" or "category"
            section_key = (
                crit.get("section") or 
                crit.get("component") or 
                crit.get("category") or 
                crit.get("domain") or 
                "Unspecified"
            )
            
            if section_key not in grouped:
                grouped[section_key] = []
            
            grouped[section_key].append({
                "id": crit["id"],
                "description": crit.get("description") or crit.get("name") or "",
                "name": crit.get("name", "")
            })
        
        result[framework_name.lower()] = {
            "framework_name": framework_name,
            "display_name": framework_info.display_name,
            "sections": grouped,
            "color": framework_info.color,
            "icon": framework_info.icon
        }
    
    return result
