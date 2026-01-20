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
    
    # Build GPT prompt - different format for SOX vendors
    if is_sox_vendor:
        prompt = f"""You are an expert SOC 2 auditor conducting a SOX compliance review. Based on the following SOC 2 report data, provide a comprehensive executive summary for SOX compliance assessment.

Report Statistics:
- Controls Identified: {len(controls_for_stats)} (high-confidence, non-duplicate controls)
- Subservice Organizations: {suborg_count}
- Complementary User Entity Controls (CUECs): {cuec_count}

TSC Framework Coverage:
{tsc_table_str}

COSO 2013 Framework Coverage:
{coso_table_str}

Sample Control Test Results (prioritizing deviations):
{control_results_str}

Please provide a SOX-focused executive summary with the following sections:

1. **SOX Objective**: Brief statement of the purpose of this SOX review (1-2 sentences)
2. **Key Findings**: 3-5 bullet points summarizing the most important findings related to financial reporting controls
3. **Areas of Concern**: 3-5 bullet points describing risks or deficiencies that could impact financial reporting
4. **Recommendations - Risk Mitigations**: 3-5 customer-actionable items to mitigate SOX compliance risks
5. **Recommendations - Contract Enhancements**: 2-4 contract-related improvements for SOX compliance
6. **SOX Assessor's Conclusion**: Assessment of control adequacy, operating effectiveness, and material weaknesses

Format your response as JSON with this exact structure:
{{
    "sox_objective": "Brief statement of SOX review purpose",
    "key_findings": ["finding 1", "finding 2", ...],
    "areas_of_concern": ["concern 1", "concern 2", ...],
    "recommendations_risk_mitigations": ["risk mitigation 1", "risk mitigation 2", ...],
    "recommendations_contract_enhancements": ["contract enhancement 1", "contract enhancement 2", ...],
    "sox_assessors_conclusion": {{
        "adequacy": "Assessment of control coverage adequacy for financial reporting",
        "operating_effectiveness": "Assessment of how effectively controls operate",
        "material_weaknesses": "Statement of any material weaknesses identified or 'None identified'"
    }}
}}

Note: Keep each item concise (1-2 sentences). Focus on SOX compliance and financial reporting impact."""
    else:
        prompt = f"""You are an expert SOC 2 auditor. Based on the following SOC 2 report data, provide a comprehensive executive summary.

Report Statistics:
- Controls Identified: {len(controls_for_stats)} (high-confidence, non-duplicate controls)
- Subservice Organizations: {suborg_count}
- Complementary User Entity Controls (CUECs): {cuec_count}

TSC Framework Coverage:
{tsc_table_str}

COSO 2013 Framework Coverage:
{coso_table_str}

Sample Control Test Results (prioritizing deviations):
{control_results_str}

Please provide a comprehensive executive summary with the following sections:

1. **Key Findings**: 3-5 bullet points summarizing the most important findings
2. **Areas of Concern**: 3-5 bullet points describing risks or deficiencies identified
3. **Recommendations - Risk Mitigations**: 3-5 customer-actionable items to mitigate risks (e.g., implement MFA, enable logging, review access controls)
4. **Recommendations - Contract Enhancements**: 2-4 contract-related improvements (e.g., negotiate audit rights, add SLA terms, review DPA clauses)

Format your response as JSON with this exact structure:
{{
    "key_findings": ["finding 1", "finding 2", ...],
    "areas_of_concern": ["concern 1", "concern 2", ...],
    "recommendations_risk_mitigations": ["risk mitigation 1", "risk mitigation 2", ...],
    "recommendations_contract_enhancements": ["contract enhancement 1", "contract enhancement 2", ...]
}}

Note: Keep each item concise (1-2 sentences). Focus on actionable insights."""
    
    # Call GPT in executor to prevent blocking (gpt_extract is synchronous)
    import asyncio
    loop = asyncio.get_event_loop()
    
    try:
        response_text = await loop.run_in_executor(None, lambda: gpt_extract(prompt, "executive_summary"))
    except Exception as gpt_error:
        logger.error(f"GPT call failed for scan {scan_id}: {gpt_error}")
        # Return a fallback summary instead of failing completely
        return {
            "error": "Failed to generate summary via GPT",
            "key_findings": ["GPT service unavailable - summary generation failed"],
            "areas_of_concern": [],
            "recommendations_risk_mitigations": [],
            "recommendations_contract_enhancements": []
        }
    
    # Parse JSON response
    try:
        summary_data = json.loads(response_text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse GPT response as JSON: {response_text}")
        # Fallback structure
        summary_data = {
            "summary": response_text,
            "strengths": [],
            "risks": [],
            "rating": "Unknown"
        }
    
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
