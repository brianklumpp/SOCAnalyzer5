"""
Objective ID Normalization Utilities

Provides functions to normalize objective IDs for consistent sorting, searching,
and display while preserving original formats for PDF matching.

Normalization Rules:
- Remove spaces before dots: "CC 6.1" → "CC6.1"
- Remove spaces before dashes: "ID - 23" → "ID-23"
- Remove spaces after dashes: "ID- 23" → "ID-23"
- Preserve casing (as extracted from PDF)
- Multiple spaces become single space
- Trim leading/trailing spaces
"""

import re
from typing import Optional


def normalize_objective_id(objective_id: Optional[str]) -> Optional[str]:
    """
    Normalize an objective ID for consistent storage and comparison.
    
    Args:
        objective_id: The original objective ID from the PDF
        
    Returns:
        Normalized objective ID, or None if input is None/empty
        
    Examples:
        >>> normalize_objective_id("CC 6.1")
        "CC6.1"
        >>> normalize_objective_id("ID - 23")
        "ID-23"
        >>> normalize_objective_id("HR  -  01")
        "HR-01"
        >>> normalize_objective_id("  CC1.1  ")
        "CC1.1"
    """
    if not objective_id:
        return None
    
    # Strip ALL whitespace including newlines, tabs, etc.
    normalized = objective_id.strip()
    
    # Remove any remaining newlines or tabs within the string
    normalized = normalized.replace('\n', '').replace('\r', '').replace('\t', ' ')
    
    if not normalized:
        return None
    
    # Remove spaces before dots
    normalized = re.sub(r'\s+\.', '.', normalized)
    
    # Remove spaces around dashes
    normalized = re.sub(r'\s*-\s*', '-', normalized)
    
    # Collapse multiple spaces into single space
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Final trim
    normalized = normalized.strip()
    
    return normalized if normalized else None


def get_pattern_for_objective(objective_id: str, pattern_info: Optional[dict]) -> Optional[dict]:
    """
    Find the pattern group that matches the given objective ID.
    
    Args:
        objective_id: The objective ID to match
        pattern_info: The pattern_info JSON from the Scan record
        
    Returns:
        The matching pattern group dict, or None if no match
        
    Example:
        >>> pattern_info = {
        ...     "groups": [
        ...         {"prefix": "CC1.", "format_template": "CC1.", "examples": ["CC1.1"]},
        ...         {"prefix": "CC6.", "format_template": "CC ", "examples": ["CC 6.1"]}
        ...     ]
        ... }
        >>> get_pattern_for_objective("CC6.1", pattern_info)
        {"prefix": "CC6.", "format_template": "CC ", "examples": ["CC 6.1"]}
    """
    if not pattern_info or not objective_id:
        return None
    
    groups = pattern_info.get("groups", [])
    if not groups:
        return None
    
    # Normalize the objective ID for comparison
    normalized_id = normalize_objective_id(objective_id)
    if not normalized_id:
        return None
    
    # Remove all non-alphanumeric for loose matching
    id_alphanum = re.sub(r'[^A-Za-z0-9]', '', normalized_id)
    
    # Try to find a matching group
    for group in groups:
        prefix = group.get("prefix", "")
        format_template = group.get("format_template", "")
        
        # Normalize prefix and template for comparison
        prefix_norm = re.sub(r'[^A-Za-z0-9]', '', prefix)
        
        if id_alphanum.upper().startswith(prefix_norm.upper()):
            return group
    
    return None


def denormalize_objective_id(normalized_id: str, pattern_info: Optional[dict]) -> str:
    """
    Convert a normalized objective ID back to its original format using pattern info.
    
    This is useful for PDF searches where we need the original spacing.
    
    Args:
        normalized_id: The normalized objective ID (e.g., "CC6.1")
        pattern_info: The pattern_info JSON from the Scan record
        
    Returns:
        Original format objective ID (e.g., "CC 6.1"), or normalized_id if pattern not found
        
    Example:
        >>> pattern_info = {
        ...     "groups": [
        ...         {"prefix": "CC6.", "format_template": "CC ", "examples": ["CC 6.1"]}
        ...     ]
        ... }
        >>> denormalize_objective_id("CC6.1", pattern_info)
        "CC 6.1"
    """
    if not normalized_id or not pattern_info:
        return normalized_id
    
    pattern = get_pattern_for_objective(normalized_id, pattern_info)
    if not pattern:
        return normalized_id
    
    format_template = pattern.get("format_template", "")
    if not format_template:
        return normalized_id
    
    # Extract the variable part (segment) from the normalized ID
    prefix = pattern.get("prefix", "")
    prefix_alphanum = re.sub(r'[^A-Za-z0-9]', '', prefix)
    id_alphanum = re.sub(r'[^A-Za-z0-9]', '', normalized_id)
    
    if not id_alphanum.upper().startswith(prefix_alphanum.upper()):
        return normalized_id
    
    # Get the segment (the part after the prefix)
    segment = id_alphanum[len(prefix_alphanum):]
    
    # Reconstruct with the original format template
    return f"{format_template}{segment}"


def bulk_normalize_ids(objective_ids: list[str]) -> list[str]:
    """
    Normalize a list of objective IDs.
    
    Args:
        objective_ids: List of objective IDs to normalize
        
    Returns:
        List of normalized objective IDs (None values filtered out)
    """
    return [normalize_objective_id(oid) for oid in objective_ids if normalize_objective_id(oid)]
