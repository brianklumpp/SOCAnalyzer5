"""
Executive Summary Service
Handles executive summary generation, caching, and staleness management.
"""

import json
import logging
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Scan, Control, CUEC, SubserviceOrg, Company, Product
from ..config import TSC_CRITERIA, COSO_2013_CRITERIA
from ..gpt_client import gpt_extract

logger = logging.getLogger(__name__)


async def mark_executive_summary_stale(scan_id: int, db: AsyncSession) -> None:
    """Mark the executive summary as stale when data changes that could impact it"""
    scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if scan_row:
        scan_row.executive_summary_stale = True
        db.add(scan_row)


async def get_executive_summary(
    scan_id: int, 
    db: AsyncSession,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Get or generate executive summary for a scan.
    
    Args:
        scan_id: The scan ID
        db: Database session
        force_refresh: If True, regenerate even if cached version exists
        
    Returns:
        Dictionary with executive_summary and is_stale fields
    """
    scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if not scan_row:
        raise ValueError(f"Scan {scan_id} not found")
    
    # Get existing summary and staleness flag
    existing_summary = getattr(scan_row, "executive_summary", None)
    is_stale = bool(getattr(scan_row, "executive_summary_stale", False))
    
    # Do NOT auto-generate an executive summary on page load.
    # Always return the cached summary (even if null) and the staleness flag
    # when force_refresh is not requested. Generation is expensive (GPT call)
    # and should only be triggered explicitly.
    if not force_refresh:
        summary = existing_summary
        await db.rollback()  # Clean up any pending transaction

        # Parse the JSON if it's stored as a string
        if isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except Exception:
                pass  # If parsing fails, return as-is

        return {"executive_summary": summary, "is_stale": is_stale}
    
    # Generate summary using GPT (only if force_refresh=True)
    logger.info(f"Generating executive summary for scan {scan_id}")
    summary = await generate_executive_summary(scan_id, db)
    
    # Save the generated summary
    scan_row.executive_summary = summary
    scan_row.executive_summary_stale = False
    db.add(scan_row)
    await db.commit()
    
    return {"executive_summary": summary, "is_stale": False}


async def generate_executive_summary(scan_id: int, db: AsyncSession) -> Dict[str, Any]:
    """
    Generate executive summary using GPT based on scan data.
    
    Args:
        scan_id: The scan ID
        db: Database session
        
    Returns:
        Dictionary containing the generated executive summary
    """
    # Get scan to check if SOX vendor
    scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if not scan_row:
        raise ValueError(f"Scan {scan_id} not found")
    
    is_sox_vendor = getattr(scan_row, 'is_sox_vendor', False)
    
    # Get all controls, then filter to high-confidence non-duplicates
    controls = (await db.execute(select(Control).where(Control.scan_id == scan_id))).scalars().all()
    high_conf_controls = [
        ctrl for ctrl in controls
        if isinstance(getattr(ctrl, 'control_confidence', 0), (int, float)) 
        and getattr(ctrl, 'control_confidence', 0) >= 0.89
        and not getattr(ctrl, 'is_duplicate_instance', False)  # Exclude duplicates
    ]
    
    # Only use high-confidence non-duplicates for statistics and coverage
    controls_for_stats = high_conf_controls
    cuecs = (await db.execute(select(CUEC).where(CUEC.scan_id == scan_id))).scalars().all()
    suborgs = (await db.execute(select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id))).scalars().all()
    
    # Build framework coverage tables from framework_mappings (using high-confidence non-duplicates only)
    tsc_ids_found = set()
    coso_ids_found = set()
    for ctrl in controls_for_stats:
        if ctrl.framework_mappings:
            if "TSC" in ctrl.framework_mappings:
                for mapping in ctrl.framework_mappings["TSC"]:
                    if mapping.get("id"):
                        tsc_ids_found.add(mapping["id"])
            if "COSO" in ctrl.framework_mappings:
                for mapping in ctrl.framework_mappings["COSO"]:
                    if mapping.get("id"):
                        coso_ids_found.add(mapping["id"])
    
    tsc_table = [
        {
            "id": crit["id"], 
            "description": crit["description"], 
            "section": crit.get("section", "Unspecified"), 
            "present": crit["id"] in tsc_ids_found
        }
        for crit in TSC_CRITERIA
    ]
    coso_table = [
        {
            "id": crit["id"], 
            "description": crit["description"], 
            "section": crit.get("component", "Unspecified"), 
            "present": crit["id"] in coso_ids_found
        }
        for crit in COSO_2013_CRITERIA
    ]
    
    suborg_count = len([o for o in suborgs if getattr(o, "confidence", 0) >= 0.9])
    cuec_count = len([c for c in cuecs if getattr(c, "cuec_confidence", 0) >= 0.9])
    
    tsc_table_str = "\n".join([
        f"{row['section']}: {row['id']} - {row['description']} ({'✔' if row['present'] else '✗'})" 
        for row in tsc_table
    ])
    coso_table_str = "\n".join([
        f"{row['section']}: {row['id']} - {row['description']} ({'✔' if row['present'] else '✗'})" 
        for row in coso_table
    ])
    
    # Build control test results string
    def _truncate(s: str, max_chars: int) -> str:
        if len(s) <= max_chars:
            return s
        return s[:max_chars - 3] + "..."
    
    # Prioritize deviations, then include up to N non-deviations
    deviation_results = []
    non_deviation_results = []
    
    for ctrl in high_conf_controls:
        ctrl_id = getattr(ctrl, "control_id", "Unknown")
        ctrl_desc = _truncate(getattr(ctrl, "control_description", "N/A"), 100)
        test_performed = _truncate(getattr(ctrl, "test_performed", "N/A"), 150)
        test_result = _truncate(getattr(ctrl, "control_test_results", "N/A"), 150)
        
        result_str = f"Control {ctrl_id}: {ctrl_desc}\nTest: {test_performed}\nResult: {test_result}\n"
        
        # Append management response if available (for deviations)
        mgmt_response = getattr(ctrl, "management_response_text", None)
        if mgmt_response:
            result_str += f"Management Response: {_truncate(mgmt_response, 200)}\n"
        
        if getattr(ctrl, 'has_deviation', False):
            deviation_results.append(result_str)
        else:
            non_deviation_results.append(result_str)
    
    # Budget: Include all deviations + fill remaining with non-deviations up to 15 total
    MAX_RESULTS = 15
    budgeted_results = deviation_results[:MAX_RESULTS]
    remaining_budget = MAX_RESULTS - len(budgeted_results)
    if remaining_budget > 0:
        budgeted_results.extend(non_deviation_results[:remaining_budget])
    
    control_results_str = "\n---\n".join(budgeted_results) if budgeted_results else "No control test results available."
    
    # Detected deviations list
    detected_deviations_list = [
        f"Control {getattr(ctrl, 'control_id', 'Unknown')}: {getattr(ctrl, 'deviation_desc', '').strip()}"
        for ctrl in high_conf_controls
        if bool(getattr(ctrl, 'has_deviation', False)) and getattr(ctrl, 'deviation_desc', '').strip()
    ]
    detected_deviations_str = "\n".join(detected_deviations_list) if detected_deviations_list else "None."
    
    # CUEC control strength assessments
    high_conf_cuecs_with_strength = [
        cuec for cuec in cuecs 
        if getattr(cuec, 'cuec_confidence', 0) >= 0.9 and getattr(cuec, 'control_strength', None)
    ]
    cuec_control_strengths_str = "\n".join([
        f"CUEC {getattr(cuec, 'cuec_tsc_id', 'Unknown')} - {getattr(cuec, 'control_strength', 'Not Set')}: {getattr(cuec, 'cuec_description', '')[:150]}..."
        for cuec in high_conf_cuecs_with_strength
    ]) if high_conf_cuecs_with_strength else "No high-confidence CUECs with control strength assessments found."
    
    # Get company and product names
    company_name = "Unknown Company"
    product_name = "Unknown Product"
    company_row = (await db.execute(select(Company).where(Company.scan_id == scan_id))).scalars().first()
    if company_row:
        company_name = getattr(company_row, 'name', '') or company_name
    product_row = (await db.execute(select(Product).where(Product.scan_id == scan_id))).scalars().first()
    if product_row:
        product_name = getattr(product_row, 'name', '') or product_name
    
    # Get coverage period
    coverage_start = getattr(scan_row, 'coverage_start', None)
    coverage_end = getattr(scan_row, 'coverage_end', None)
    if coverage_start and coverage_end:
        coverage_period_str = f"{coverage_start.strftime('%B %d, %Y')} to {coverage_end.strftime('%B %d, %Y')}"
    elif coverage_start:
        coverage_period_str = f"starting {coverage_start.strftime('%B %d, %Y')}"
    elif coverage_end:
        coverage_period_str = f"ending {coverage_end.strftime('%B %d, %Y')}"
    else:
        coverage_period_str = "the audit period"
    
    sox_vendor_str = "Yes - Subject to SOX Compliance" if is_sox_vendor else "No"
    
    # Use comprehensive prompt from config
    from ..config import EXECUTIVE_SUMMARY_PROMPT
    
    prompt = EXECUTIVE_SUMMARY_PROMPT.format(
        suborg_count=suborg_count,
        cuec_count=cuec_count,
        tsc_covered=sum(1 for row in tsc_table if row['present']),
        tsc_total=len(tsc_table),
        coso_covered=sum(1 for row in coso_table if row['present']),
        coso_total=len(coso_table),
        tsc_table=tsc_table_str,
        coso_table=coso_table_str,
        coverage_period=coverage_period_str,
        control_test_results=control_results_str,
        detected_deviations=detected_deviations_str,
        cuec_control_strengths=cuec_control_strengths_str,
        company=company_name,
        product=product_name,
        is_sox_vendor=sox_vendor_str
    )
    
    # Call GPT in executor to prevent blocking (gpt_extract is synchronous)
    import asyncio
    import traceback
    loop = asyncio.get_event_loop()
    
    try:
        response_text = await loop.run_in_executor(None, lambda: gpt_extract(prompt, "executive_summary"))
    except Exception as gpt_error:
        error_tb = traceback.format_exc()
        logger.error(f"GPT call failed for scan {scan_id}: {gpt_error}")
        logger.error(f"Full traceback:\n{error_tb}")
        logger.error(f"Prompt length: {len(prompt)} chars")
        # Return a fallback summary instead of failing completely
        return {
            "error": f"Failed to generate summary via GPT: {str(gpt_error)}",
            "about_company": f"{company_name} - {product_name}",
            "key_findings": [f"GPT service error: {str(gpt_error)[:200]}"],
            "areas_of_concern": [],
            "recommendations_risk_mitigations": [],
            "recommendations_contract_enhancements": [],
            "recommendations": []
        }
    
    # Parse JSON response - clean markdown code fences
    cleaned_response = response_text.strip()
    if cleaned_response.startswith('```json'):
        cleaned_response = cleaned_response[7:]
    elif cleaned_response.startswith('```'):
        cleaned_response = cleaned_response[3:]
    if cleaned_response.endswith('```'):
        cleaned_response = cleaned_response[:-3]
    cleaned_response = cleaned_response.strip()
    
    try:
        summary_data = json.loads(cleaned_response)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse GPT response as JSON for scan {scan_id}: {e}")
        logger.error(f"Response preview: {response_text[:500]}")
        # Fallback structure
        summary_data = {
            "about_company": f"{company_name} - {product_name}",
            "key_findings": ["Unable to parse GPT response"],
            "areas_of_concern": [],
            "recommendations_risk_mitigations": [],
            "recommendations_contract_enhancements": [],
            "recommendations": []
        }
    
    # Ensure legacy recommendations field includes all recommendations
    risk_list = summary_data.get("recommendations_risk_mitigations") or []
    contract_list = summary_data.get("recommendations_contract_enhancements") or []
    base_list = summary_data.get("recommendations") or []
    
    # Union while preserving order and avoiding duplicates
    combined = []
    seen = set()
    for item in list(base_list) + list(risk_list) + list(contract_list):
        key = (item or "").strip()
        if key and key not in seen:
            combined.append(item)
            seen.add(key)
    
    summary_data["recommendations"] = combined
    
    return summary_data


async def update_executive_summary(
    scan_id: int,
    summary_data: Dict[str, Any],
    db: AsyncSession
) -> Dict[str, str]:
    """
    Update the executive summary for a scan.
    
    Args:
        scan_id: The scan ID
        summary_data: Dictionary containing executive_summary field
        db: Database session
        
    Returns:
        Status dictionary
    """
    if "executive_summary" not in summary_data:
        raise ValueError("No executive_summary provided")
    
    scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if not scan_row:
        raise ValueError(f"Scan {scan_id} not found")
    
    scan_row.executive_summary = summary_data["executive_summary"]
    db.add(scan_row)
    await db.commit()
    
    return {"status": "ok"}
