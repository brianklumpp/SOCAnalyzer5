"""
Utility functions service
Common helper functions for parsing, file operations, and data transformation.
"""

import os
import json
import pathlib
import logging
from typing import Dict, Any, List, Union

logger = logging.getLogger(__name__)


def parse_page_refs(value: Union[List, str, int, None]) -> List[int]:
    """
    Parse page references from various input formats to JSON array.
    
    Accepts:
    - Array: [51, 52, 89]
    - Comma-separated string: "51, 52, 89"
    - Single integer: 51
    - None/empty: returns []
    
    Returns: Sorted list of unique integers
    """
    if value is None:
        return []
    
    # Already an array
    if isinstance(value, list):
        # Filter and convert to integers
        result = []
        for item in value:
            try:
                result.append(int(item))
            except (ValueError, TypeError):
                continue
        return sorted(list(set(result)))
    
    # Single integer
    if isinstance(value, (int, float)):
        return [int(value)]
    
    # Comma-separated string
    if isinstance(value, str):
        result = []
        for part in value.split(','):
            part = part.strip()
            if part:
                try:
                    result.append(int(part))
                except ValueError:
                    continue
        return sorted(list(set(result)))
    
    return []


def get_project_root() -> pathlib.Path:
    """Get the project root directory (2 levels up from this file)."""
    return pathlib.Path(__file__).resolve().parents[3]


def get_artifact_presence() -> Dict[str, bool]:
    """
    Check which analysis artifact files exist.
    
    Returns:
        Dictionary mapping artifact names to existence boolean
    """
    base = get_project_root()
    files = {
        "controls": base / "data/json/control_result.json",
        "cuecs": base / "data/json/cuec_result.json",
        "subservice_orgs": base / "data/json/subservice_orgs_result.json",
        "product": base / "data/json/product_result.json",
        "auditor": base / "data/json/auditor_result.json",
        "company": base / "data/json/company_result.json",
        "report_date": base / "data/json/report_date_result.json",
        "coverage_period": base / "data/json/coverage_period_result.json",
        "combined": base / "data/json/combined_result.json",
        "sections": base / "data/json/section_results.json",
        "extracted_text": base / "data/output/output.txt",
    }
    return {k: p.is_file() for k, p in files.items()}


def reset_scan_state() -> None:
    """
    Remove prior JSON artifacts and truncate logs to ensure a clean run for a new scan.

    This clears only analyzer-generated outputs under data/json and data/output, and truncates
    files under data/logs. It does not touch the database or user-uploaded PDFs.
    """
    try:
        base = get_project_root()
        # JSON artifacts to remove
        json_rel_paths = [
            'data/json/control_result.json',
            'data/json/cuec_result.json',
            'data/json/subservice_orgs_result.json',
            'data/json/subservice_orgs_result_postprocessed.json',
            'data/json/product_result.json',
            'data/json/auditor_result.json',
            'data/json/company_result.json',
            'data/json/report_date_result.json',
            'data/json/coverage_period_result.json',
            'data/json/combined_result.json',
            'data/json/section_results.json',
        ]
        for rel in json_rel_paths:
            try:
                p = base / rel
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
        # Output text (legacy extracted text)
        try:
            out_txt = base / 'data/output/output.txt'
            if out_txt.is_file():
                out_txt.unlink()
        except Exception:
            pass
        # Truncate logs
        try:
            logs_dir = base / 'data/logs'
            logs_dir.mkdir(parents=True, exist_ok=True)
            for entry in logs_dir.iterdir():
                try:
                    if entry.is_file():
                        # Truncate file
                        with open(str(entry), 'w', encoding='utf-8'):
                            pass
                except Exception:
                    pass
        except Exception:
            pass
        logger.info("[RESET] Cleared prior JSON artifacts and truncated logs for new scan")
    except Exception as e:
        logger.error(f"[RESET] Unexpected error during cleanup: {e}")


def safe_len(val) -> int:
    """Safely get length of a value, returning 0 for non-measurable types."""
    try:
        return len(val) if isinstance(val, (list, dict, str)) else (int(val) if isinstance(val, (int, float)) else 0)
    except Exception:
        return 0


def get_result_counts_from_obj(result: Dict[str, Any]) -> Dict[str, int]:
    """
    Count entities in a combined result object.
    
    Args:
        result: Combined result dictionary
        
    Returns:
        Dictionary with counts for each entity type
    """
    counts = {
        "company": 1 if bool(result.get("company")) else 0,
        "product": 1 if bool(result.get("product")) else 0,
        "auditor": 1 if bool(result.get("auditor")) else 0,
        "report_date": 1 if bool(result.get("report_date")) else 0,
        "coverage_period": 1 if bool(result.get("coverage_period")) else 0,
        "control": safe_len(result.get("controls") or []),
        "cuec": safe_len(result.get("cuecs") or []),
        "subservice_org": safe_len(result.get("subservice_orgs") or []),
    }
    return counts


def get_result_counts_from_disk() -> Dict[str, int]:
    """
    Count entities from JSON files on disk.
    
    Returns:
        Dictionary with counts for each entity type
    """
    base = get_project_root()
    
    def _load(path: str):
        try:
            with open(str(base / path), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    def _streaming_array_count(path: str) -> int:
        """
        Best-effort count for a file being incrementally written as JSON objects separated by commas.

        control_extractor_v2 writes an initial '[]\n' then appends each object with a leading comma, finally
        overwriting the whole file with a proper {"controls": [...]} structure when complete. While in-flight,
        json.load() fails; this heuristic counts objects so UI progress/counts reflect partial extraction.
        """
        file_path = str(base / path)
        if not os.path.isfile(file_path):
            return 0
        count = 0
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    ls = line.lstrip()
                    # Skip the opening [] line
                    if ls.startswith('[]'):
                        continue
                    # Detect start of an object
                    if ls.startswith('{'):
                        count += 1
            return count
        except Exception:
            return 0
    
    counts = {
        "company": 0, 
        "product": 0, 
        "auditor": 0, 
        "report_date": 0, 
        "coverage_period": 0, 
        "control": 0, 
        "cuec": 0, 
        "subservice_org": 0
    }
    
    # company/product/auditor/report_date/coverage_period are dict-ish
    counts["company"] = 1 if _load('data/json/company_result.json') else 0
    counts["product"] = 1 if _load('data/json/product_result.json') else 0
    counts["auditor"] = 1 if _load('data/json/auditor_result.json') else 0
    counts["report_date"] = 1 if _load('data/json/report_date_result.json') else 0
    counts["coverage_period"] = 1 if _load('data/json/coverage_period_result.json') else 0
    
    # list-like inside dicts
    cuec_obj = _load('data/json/cuec_result.json') or {}
    ctrl_obj = _load('data/json/control_result.json') or {}
    so_obj = _load('data/json/subservice_orgs_result.json') or {}
    
    counts["cuec"] = safe_len((cuec_obj or {}).get("cuecs") or cuec_obj.get("third_parties") or [])
    
    if isinstance(ctrl_obj, dict) and "controls" in ctrl_obj:
        counts["control"] = safe_len(ctrl_obj.get("controls") or [])
    else:
        # Fallback to streaming partial file heuristic while control extractor still running
        counts["control"] = _streaming_array_count('data/json/control_result.json')
    
    counts["subservice_org"] = safe_len((so_obj or {}).get("third_parties") or [])
    
    return counts


def normalize_percent_like(val) -> float:
    """
    Normalize percentage-like values to decimal (0.0-1.0).
    
    Handles values like:
    - "95%" -> 0.95
    - 95 -> 0.95
    - 0.95 -> 0.95
    """
    if val is None:
        return 0.0
    
    if isinstance(val, str):
        val = val.strip().rstrip('%')
        try:
            num = float(val)
        except ValueError:
            return 0.0
    else:
        try:
            num = float(val)
        except (ValueError, TypeError):
            return 0.0
    
    # If value is > 1, assume it's a percentage (e.g., 95 means 95%)
    if num > 1.0:
        return num / 100.0
    return num


def as_float_or_none(v) -> float:
    """
    Convert value to float, returning None if conversion fails.
    
    Args:
        v: Value to convert
        
    Returns:
        Float value or None
    """
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None
