"""
Analysis Service
Handles analysis job orchestration and result building.
"""

import os
import json
import logging
import pathlib
import traceback
from typing import Dict, Any

logger = logging.getLogger(__name__)


def build_combined_results_from_disk() -> Dict[str, Any]:
    """
    Rebuild a combined result from any extractor JSONs already on disk.
    
    Returns:
        Dictionary containing all extracted data from disk
    """
    try:
        PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
        
        def data_path(rel: str) -> str:
            return str((PROJECT_ROOT / rel).resolve())

        # Load extractor JSONs if present
        extractor_json_map = {
            'control_extraction': 'data/json/control_result.json',
            'cuec_extraction': 'data/json/cuec_result.json',
            'subservice_orgs_extraction': 'data/json/subservice_orgs_result.json',
            'product_extraction': 'data/json/product_result.json',
            'auditor_extraction': 'data/json/auditor_result.json',
            'company_extraction': 'data/json/company_result.json',
            'report_date_extraction': 'data/json/report_date_result.json',
            'coverage_period_extraction': 'data/json/coverage_period_result.json',
        }
        
        extractor_results: Dict[str, Any] = {}
        for ext_key, rel_path in extractor_json_map.items():
            fpath = data_path(rel_path)
            if os.path.isfile(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as pf:
                        extractor_results[ext_key] = json.load(pf)
                except Exception as e:
                    logger.error(f"[build_combined] Failed to load {rel_path}: {e}")

        # Flatten to standardized keys expected by the app
        flatten_map = {
            'control_extraction': ('controls', 'controls'),
            'cuec_extraction': ('cuecs', 'cuecs'),
            'subservice_orgs_extraction': ('subservice_orgs', 'third_parties'),
            'product_extraction': ('product', 'product'),
            'auditor_extraction': ('auditor', 'auditor'),
            'company_extraction': ('company', 'company'),
            'report_date_extraction': ('report_date', 'report_date'),
            'coverage_period_extraction': ('coverage_period', 'coverage_period'),
        }
        
        standardized_results: Dict[str, Any] = {}
        for ext_key, (short_key, inner_key) in flatten_map.items():
            val = extractor_results.get(ext_key)
            if val is None:
                continue
            if isinstance(val, dict) and inner_key in val:
                # For controls, ensure list of dicts
                if short_key == 'controls' and isinstance(val[inner_key], list):
                    standardized_results[short_key] = [dict(c) for c in val[inner_key]]
                else:
                    standardized_results[short_key] = val[inner_key]
            else:
                standardized_results[short_key] = val

        # Persist bad_chunks meta where present (cuecs/controls/subservice_orgs)
        try:
            if isinstance(extractor_results.get('cuec_extraction'), dict):
                cuec_res = extractor_results['cuec_extraction']
                if isinstance(cuec_res.get('bad_chunks'), list) and len(cuec_res['bad_chunks']) > 0:
                    standardized_results.setdefault('cuecs_meta', {})
                    standardized_results['cuecs_meta']['bad_chunks'] = cuec_res['bad_chunks']
                    standardized_results['cuecs_meta']['bad_chunk_count'] = cuec_res.get('bad_chunk_count', len(cuec_res['bad_chunks']))
            if isinstance(extractor_results.get('control_extraction'), dict):
                ctrl_res = extractor_results['control_extraction']
                if isinstance(ctrl_res.get('bad_chunks'), list) and len(ctrl_res['bad_chunks']) > 0:
                    standardized_results.setdefault('controls_meta', {})
                    standardized_results['controls_meta']['bad_chunks'] = ctrl_res['bad_chunks']
                    standardized_results['controls_meta']['bad_chunk_count'] = ctrl_res.get('bad_chunk_count', len(ctrl_res['bad_chunks']))
            if isinstance(extractor_results.get('subservice_orgs_extraction'), dict):
                so_res = extractor_results['subservice_orgs_extraction']
                if isinstance(so_res.get('bad_chunks'), list) and len(so_res['bad_chunks']) > 0:
                    standardized_results.setdefault('subservice_orgs_meta', {})
                    standardized_results['subservice_orgs_meta']['bad_chunks'] = so_res['bad_chunks']
                    standardized_results['subservice_orgs_meta']['bad_chunk_count'] = so_res.get('bad_chunk_count', len(so_res['bad_chunks']))
        except Exception:
            pass

        # Always include sections if available
        try:
            with open(data_path('data/json/section_results.json'), 'r', encoding='utf-8') as sf:
                standardized_results['sections'] = json.load(sf)
        except Exception:
            standardized_results['sections'] = []

        # Attach extracted text if present
        try:
            with open(data_path('data/output/output.txt'), 'r', encoding='utf-8') as tf:
                standardized_results['extracted_text'] = tf.read()
        except Exception:
            standardized_results['extracted_text'] = None

        # Attach GPT usage summary if available
        try:
            from ..gpt_tracker import get_usage_summary
            gpt_summary = get_usage_summary()
            if isinstance(gpt_summary, dict):
                standardized_results.update(gpt_summary)
        except Exception:
            pass

        # Also write combined_result.json for troubleshooting only if we have content to write
        try:
            if isinstance(standardized_results, dict) and len(standardized_results.keys()) > 0:
                combined_result_path = data_path('data/json/combined_result.json')
                # Filter out pdf_file bytes before JSON serialization (safety measure)
                results_for_json = {k: v for k, v in standardized_results.items() if k != 'pdf_file'}
                with open(combined_result_path, 'w', encoding='utf-8') as f:
                    json.dump(results_for_json, f, indent=2, ensure_ascii=False)
                logger.info(f"[build_combined] Wrote combined_result.json to {combined_result_path}")
            else:
                logger.info("[build_combined] Skipping combined_result.json write (no content yet)")
        except Exception as e:
            logger.error(f"[build_combined] Failed to write combined_result.json: {e}")

        return standardized_results
    except Exception as e:
        logger.error(f"[build_combined] Unexpected error: {e}\n{traceback.format_exc()}")
        return {}
