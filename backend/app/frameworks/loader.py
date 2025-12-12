"""
Framework Criteria Loader

Dynamically loads framework criteria based on report type and detected standards.
Supports loading from:
- Python config constants (TSC_CRITERIA, COSO_2013_CRITERIA, FINANCIAL_ASSERTIONS)
- JSON files (for future expansion)
"""

import re
from typing import Dict, List, Optional, Any
from pathlib import Path

from .registry import (
    FRAMEWORK_REGISTRY,
    ReportType,
    get_frameworks_by_report_type,
    get_frameworks_by_standard,
)


def load_framework_criteria(framework_name: str) -> Optional[List[Dict[str, Any]]]:
    """
    Load criteria for a specific framework.
    
    Currently loads from Python config.py constants:
    - TSC -> TSC_CRITERIA
    - COSO -> COSO_2013_CRITERIA
    - FINANCIAL_ASSERTIONS -> FINANCIAL_ASSERTIONS
    
    Future: Will support loading from JSON files in criteria/ directory.
    
    Args:
        framework_name: Framework identifier (e.g., "TSC", "COSO")
        
    Returns:
        List of criteria dictionaries or None if not found/implemented
    """
    framework_info = FRAMEWORK_REGISTRY.get(framework_name)
    if not framework_info:
        return None
    
    # Load from existing Python constants (backwards compatibility)
    if framework_name == "TSC":
        from ..config import TSC_CRITERIA
        return TSC_CRITERIA
    elif framework_name == "COSO":
        from ..config import COSO_2013_CRITERIA
        return COSO_2013_CRITERIA
    elif framework_name == "FINANCIAL_ASSERTIONS":
        from ..config import FINANCIAL_ASSERTIONS
        return FINANCIAL_ASSERTIONS
    
    # Load from JSON files for new frameworks
    if framework_info.criteria_file:
        criteria_path = Path(__file__).parent / "criteria" / framework_info.criteria_file
        if criteria_path.exists():
            import json
            try:
                with open(criteria_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                import logging
                logging.error(f"Failed to load criteria file {criteria_path}: {e}")
                return None
    
    return None


def get_available_frameworks(report_type: str, detected_standards: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Get all frameworks available for a given report type and detected standards.
    
    DETECTION STRATEGY:
    - Primary signal: report_type (SOC1 → Financial Assertions, SOC2 → TSC, etc.)
    - Secondary: detected_standards list contains ADDITIONAL frameworks found in text
    - Most reports don't explicitly name frameworks, so report_type is most reliable
    
    Args:
        report_type: "SOC1", "SOC2", or "COMBINED"
        detected_standards: Optional list of framework names detected from text 
                          (e.g., ["TSC", "COSO", "ISAE3402"])
        
    Returns:
        Dictionary of {framework_name: {info: FrameworkInfo, criteria: List[Dict]}}
    """
    try:
        report_type_enum = ReportType(report_type)
    except ValueError:
        # Default to SOC2 if invalid
        report_type_enum = ReportType.SOC2
    
    # Get frameworks by report type
    applicable_frameworks = get_frameworks_by_report_type(report_type_enum)
    
    # Expand with frameworks detected from standards
    if detected_standards:
        for standard in detected_standards:
            standard_frameworks = get_frameworks_by_standard(standard)
            applicable_frameworks.update(standard_frameworks)
    
    # Load criteria for each framework
    result = {}
    for fw_name, fw_info in applicable_frameworks.items():
        criteria = load_framework_criteria(fw_name)
        if criteria:  # Only include frameworks with loaded criteria
            result[fw_name] = {
                "info": fw_info,
                "criteria": criteria
            }
    
    return result


def detect_frameworks_from_standards(standards_text: str, report_type: Optional[str] = None) -> List[str]:
    """
    Detect frameworks based on standards mentioned in report text.
    
    NOTE: Most SOC reports don't explicitly mention framework names (TSC, COSO, etc.).
    This function primarily detects ADDITIONAL international/regional standards beyond
    the defaults implied by report_type.
    
    Args:
        standards_text: Text containing potential standard references
        report_type: Optional report type to get baseline frameworks ("SOC1", "SOC2", "COMBINED")
        
    Returns:
        List of detected framework names (may include defaults + explicitly mentioned standards)
    """
    detected = []
    
    # Start with defaults based on report_type (most reliable signal)
    if report_type:
        defaults = get_default_frameworks_for_report(report_type)
        detected.extend(defaults)
    
    standards_upper = standards_text.upper()
    
    # ONLY detect ADDITIONAL regional/international standards that are explicitly mentioned
    # (TSC, COSO, FINANCIAL_ASSERTIONS are implied by report type, not typically stated)
    additional_patterns = {
        "ISAE3402": [r'ISAE\s*3402', r'INTERNATIONAL STANDARD ON ASSURANCE ENGAGEMENTS'],
        "CSAE3416": [r'CSAE\s*3416', r'CANADIAN STANDARD ON ASSURANCE'],
        "AAF0106": [r'AAF\s*01/?06', r'AUSTRALIAN AUDITING FRAMEWORK'],
        "GS007": [r'GS\s*007', r'IDW\s*PS\s*951', r'GERMAN AUDITING STANDARD'],
        "ISO27001": [r'ISO\s*/?27001', r'ISO/IEC\s*27001'],
        "NIST": [r'NIST\s*CSF', r'NIST CYBERSECURITY FRAMEWORK', r'NIST\s*800'],
    }
    
    for framework_name, pattern_list in additional_patterns.items():
        for pattern in pattern_list:
            if re.search(pattern, standards_upper):
                if framework_name not in detected:
                    detected.append(framework_name)
                break
    
    return detected


def get_frameworks_for_report_type(report_type: str, include_criteria: bool = True) -> Dict[str, Any]:
    """
    Convenience function to get frameworks with metadata for a report type.
    
    Args:
        report_type: "SOC1", "SOC2", or "COMBINED"
        include_criteria: Whether to load full criteria lists (default: True)
        
    Returns:
        Dictionary with framework information
    """
    frameworks = get_available_frameworks(report_type)
    
    if not include_criteria:
        # Strip out criteria to reduce payload size
        for fw_name in frameworks:
            frameworks[fw_name]["criteria"] = []
    
    return frameworks


def get_default_frameworks_for_report(report_type: str) -> List[str]:
    """
    Get default framework list for a report type (used for initial mapping).
    
    Args:
        report_type: "SOC1", "SOC2", or "COMBINED"
        
    Returns:
        List of framework names to use by default
    """
    defaults = {
        "SOC1": ["FINANCIAL_ASSERTIONS", "COSO_ICFR", "COSO"],
        "SOC2": ["TSC", "COSO"],
        "COMBINED": ["TSC", "COSO", "FINANCIAL_ASSERTIONS", "COSO_ICFR"],
    }
    
    return defaults.get(report_type, ["TSC", "COSO"])
