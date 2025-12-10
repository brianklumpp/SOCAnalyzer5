"""
Multi-Framework Support Module

This module provides the foundation for supporting multiple attestation frameworks
beyond TSC and COSO, including international standards like ISAE 3402, CSAE 3416,
AAF 01/06, GS 007, and others.

Key components:
- registry.py: Defines all supported frameworks with metadata
- loader.py: Dynamically loads framework criteria based on report type
- criteria/: Directory containing framework criteria JSON files
"""

from .registry import FRAMEWORK_REGISTRY, FrameworkType, get_framework_info
from .loader import load_framework_criteria, get_available_frameworks, detect_frameworks_from_standards
from .migration_helper import consolidate_framework_mappings, migrate_control_frameworks, migrate_cuec_frameworks, migrate_scan_frameworks
from .mapper import (
    map_control_to_frameworks_dynamic,
    map_cuec_to_frameworks_dynamic,
    extract_mapping_fields_for_db,
    get_primary_criterion_details
)

__all__ = [
    'FRAMEWORK_REGISTRY',
    'FrameworkType',
    'get_framework_info',
    'load_framework_criteria',
    'get_available_frameworks',
    'detect_frameworks_from_standards',
    'consolidate_framework_mappings',
    'migrate_control_frameworks',
    'migrate_cuec_frameworks',
    'migrate_scan_frameworks',
    # Multi-framework mapper functions
    'map_control_to_frameworks_dynamic',
    'map_cuec_to_frameworks_dynamic',
    'extract_mapping_fields_for_db',
    'get_primary_criterion_details',
]
