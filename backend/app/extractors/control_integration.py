"""
Control Extractor Integration Module
======================================

Provides a unified interface for switching between control extraction versions:
- v2: Line-based overlapping chunks with dynamic GPT breakpoint detection
- v4: Token-based aware chunks with Chain-of-Thought and continuation handling

Usage:
    from backend.app.extractors.control_integration import extract_controls
    
    # Use V4 (default)
    result = extract_controls(version="v4")
    
    # Use V2 (legacy)
    result = extract_controls(version="v2")
"""

import logging
from typing import Dict, Any, Optional

# Import both versions
try:
    from .control_extractor_v2 import extract_controls_v2
    V2_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Control extractor v2 not available: {e}")
    V2_AVAILABLE = False

try:
    from .control_extractor_v4 import extract_controls_v4
    V4_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Control extractor v4 not available: {e}")
    V4_AVAILABLE = False

try:
    from .control_extractor_v4_soc1 import extract_controls_v4 as extract_controls_v4_soc1
    V4_SOC1_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Control extractor v4_soc1 not available: {e}")
    V4_SOC1_AVAILABLE = False

try:
    from .control_extractor_combined import extract_controls_v4 as extract_controls_combined
    COMBINED_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Control extractor combined not available: {e}")
    COMBINED_AVAILABLE = False

# Default version
DEFAULT_VERSION = "v4"

def extract_controls(
    version: str = DEFAULT_VERSION,
    start_at_control: Optional[int] = None,
    start_at_line: Optional[int] = None
) -> None:
    """
    Unified control extraction interface.
    
    Both v2 and v4 write results to config.CONTROL_JSON_PATH and return None.
    Results are saved as {"controls": [...], "diagnostics": {...}} (v4) or {"controls": [...]} (v2).
    
    Args:
        version: Extractor version ("v2" or "v4")
        start_at_control: Resume from control sequence number (optional)
        start_at_line: Resume from line number (optional)
        
    Returns:
        None (results written to config.CONTROL_JSON_PATH)
        
    Raises:
        ValueError: If specified version is not available
    """
    version = version.lower()
    
    if version == "v2":
        if not V2_AVAILABLE:
            raise ValueError("Control extractor v2 is not available")
        
        logging.info("Using control extractor v2 (line-based dynamic chunking)")
        extract_controls_v2(
            start_at_control=start_at_control,
            start_at_line=start_at_line
        )
    
    elif version == "v4":
        if not V4_AVAILABLE:
            raise ValueError("Control extractor v4 is not available")
        
        logging.info("Using control extractor v4 (SOC 2 - AWARE-CHUNK + Chain-of-Thought)")
        extract_controls_v4(
            start_at_control=start_at_control,
            start_at_line=start_at_line
        )
    
    elif version == "v4_soc1":
        if not V4_SOC1_AVAILABLE:
            raise ValueError("Control extractor v4_soc1 is not available")
        
        logging.info("Using control extractor v4_soc1 (SOC 1 - Financial Assertions)")
        extract_controls_v4_soc1(
            start_at_control=start_at_control,
            start_at_line=start_at_line
        )
    
    elif version == "combined":
        if not COMBINED_AVAILABLE:
            raise ValueError("Control extractor combined is not available")
        
        logging.info("Using control extractor combined (Dual Framework Mapping)")
        extract_controls_combined(
            start_at_control=start_at_control,
            start_at_line=start_at_line
        )
    
    else:
        raise ValueError(f"Unknown extractor version: {version}. Must be 'v2', 'v4', 'v4_soc1', or 'combined'")

def get_available_versions() -> list:
    """
    Get list of available extractor versions.
    
    Returns:
        List of version strings (e.g., ["v2", "v4"])
    """
    versions = []
    if V2_AVAILABLE:
        versions.append("v2")
    if V4_AVAILABLE:
        versions.append("v4")
    return versions

def get_version_info(version: str) -> Dict[str, Any]:
    """
    Get information about a specific extractor version.
    
    Args:
        version: Extractor version ("v2" or "v4")
        
    Returns:
        Dictionary with version information
    """
    version = version.lower()
    
    info = {
        "v2": {
            "name": "Control Extractor v2",
            "architecture": "Line-based overlapping chunks with dynamic GPT breakpoint detection",
            "features": [
                "Dynamic chunking with GPT-based breakpoints",
                "4-category classification (control_id, description, test, result)",
                "Overlap and tail-guard for chunk continuity",
                "Safeguards: timeout, hang prevention, non-control detection",
                "Progress tracking and resume capability"
            ],
            "chunk_method": "Lines per chunk with overlap",
            "prompt_style": "Multi-field extraction with 8 rules",
            "available": V2_AVAILABLE
        },
        "v4": {
            "name": "Control Extractor v4 - AWARE-CHUNK + CoT",
            "architecture": "Token-based aware chunks with Chain-of-Thought and continuation handling",
            "features": [
                "Token-based aware chunking (~1000 tokens, ~200 overlap)",
                "Chunk metadata (chunk_id, start_line, end_line, continuation hints)",
                "Chain-of-Thought reasoning embedded in prompt",
                "Linguistic cue detection (not table-based)",
                "Continuation merging across chunks",
                "Confidence filtering (< 0.5 threshold)",
                "Post-merge validation",
                "Comprehensive diagnostics"
            ],
            "chunk_method": "Token-based with metadata",
            "prompt_style": "Single-control extraction with 7 parsing strategies",
            "available": V4_AVAILABLE
        }
    }
    
    return info.get(version, {"error": f"Unknown version: {version}"})

def compare_versions():
    """
    Print comparison of available extractor versions.
    """
    print("=" * 80)
    print("CONTROL EXTRACTOR VERSION COMPARISON")
    print("=" * 80)
    
    for version in ["v2", "v4"]:
        info = get_version_info(version)
        if "error" in info:
            continue
        
        status = "✓ Available" if info["available"] else "✗ Not Available"
        
        print(f"\n{info['name']} ({status})")
        print("-" * 80)
        print(f"Architecture: {info['architecture']}")
        print(f"Chunk Method: {info['chunk_method']}")
        print(f"Prompt Style: {info['prompt_style']}")
        print("Features:")
        for feature in info['features']:
            print(f"  • {feature}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    # Display comparison when run directly
    compare_versions()
    
    print("\nAvailable versions:", get_available_versions())
    print(f"Default version: {DEFAULT_VERSION}")
