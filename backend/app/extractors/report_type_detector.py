"""
Report Type Detector - GPT-based detection of SOC report types

This module implements a two-stage GPT analysis to detect:
- Report standard: SOC 1 vs SOC 2
- Report type: Type 1 vs Type 2

Detection is GPT-only (no regex/keyword fallbacks) and returns a confidence score.
If confidence is below threshold, user confirmation is required.
"""

import logging
import hashlib
from typing import Dict, Optional

from ..gpt_client import gpt_extract
from ..config import (
    REPORT_TYPE_CONFIDENCE_THRESHOLD,
    REPORT_TYPE_QUICK_SCAN_PAGES,
    REPORT_TYPE_DEEP_SCAN_PAGES
)

logger = logging.getLogger(__name__)


def compute_pdf_hash(pdf_bytes: bytes) -> str:
    """Compute SHA-256 hash of PDF file for caching."""
    return hashlib.sha256(pdf_bytes).hexdigest()


def detect_report_type(
    extracted_text: str,
    pdf_hash: Optional[str] = None,
    job_id: Optional[str] = None
) -> Dict:
    """
    Detect SOC report type using two-stage GPT analysis.
    
    Stage 1: Quick scan (first N pages)
    Stage 2: Deep scan (more pages if needed for confidence)
    
    Args:
        extracted_text: Full text extracted from PDF
        pdf_hash: SHA-256 hash of PDF for caching
        job_id: Job ID for tracking/logging
        
    Returns:
        {
            'detected_type': 'SOC1' | 'SOC2' | 'COMBINED',
            'detected_subtype': 'TYPE1' | 'TYPE2',
            'confidence': float (0.0-1.0),
            'evidence': [str, ...],  # Key textual evidence found
            'requires_confirmation': bool,
            'analysis_stage': 'quick' | 'deep',
            'pdf_hash': str
        }
    """
    logger.info(f"[REPORT_TYPE_DETECTOR] Starting detection for job_id={job_id}")
    
    # Split text into pages (assuming page markers from PDF extraction)
    # TODO: Adjust this based on your actual PDF extraction format
    pages = extracted_text.split('\n--- Page ')
    
    # Stage 1: Quick scan
    logger.info(f"[REPORT_TYPE_DETECTOR] Stage 1: Quick scan ({REPORT_TYPE_QUICK_SCAN_PAGES} pages)")
    quick_scan_text = '\n'.join(pages[:REPORT_TYPE_QUICK_SCAN_PAGES])
    
    quick_result = _analyze_with_gpt(
        text=quick_scan_text,
        stage='quick',
        job_id=job_id
    )
    
    # Check if confidence is sufficient
    if quick_result['confidence'] >= REPORT_TYPE_CONFIDENCE_THRESHOLD:
        logger.info(
            f"[REPORT_TYPE_DETECTOR] Quick scan sufficient: "
            f"{quick_result['detected_type']} {quick_result['detected_subtype']} "
            f"(confidence={quick_result['confidence']:.2f})"
        )
        return {
            **quick_result,
            'requires_confirmation': False,
            'analysis_stage': 'quick',
            'pdf_hash': pdf_hash
        }
    
    # Stage 2: Deep scan
    logger.info(
        f"[REPORT_TYPE_DETECTOR] Quick scan insufficient (confidence={quick_result['confidence']:.2f}), "
        f"running deep scan ({REPORT_TYPE_DEEP_SCAN_PAGES} pages)"
    )
    deep_scan_text = '\n'.join(pages[:REPORT_TYPE_DEEP_SCAN_PAGES])
    
    deep_result = _analyze_with_gpt(
        text=deep_scan_text,
        stage='deep',
        job_id=job_id,
        prior_result=quick_result
    )
    
    requires_confirmation = deep_result['confidence'] < REPORT_TYPE_CONFIDENCE_THRESHOLD
    
    logger.info(
        f"[REPORT_TYPE_DETECTOR] Deep scan complete: "
        f"{deep_result['detected_type']} {deep_result['detected_subtype']} "
        f"(confidence={deep_result['confidence']:.2f}, requires_confirmation={requires_confirmation})"
    )
    
    return {
        **deep_result,
        'requires_confirmation': requires_confirmation,
        'analysis_stage': 'deep',
        'pdf_hash': pdf_hash
    }


def _analyze_with_gpt(
    text: str,
    stage: str,
    job_id: Optional[str] = None,
    prior_result: Optional[Dict] = None
) -> Dict:
    """
    Run GPT analysis to detect report type.
    
    Args:
        text: Text to analyze
        stage: 'quick' or 'deep'
        job_id: Job ID for tracking
        prior_result: Result from previous stage (if applicable)
        
    Returns:
        {
            'detected_type': str,
            'detected_subtype': str,
            'confidence': float,
            'evidence': [str, ...]
        }
    """
    
    # Build prompt
    if stage == 'quick':
        prompt = _build_quick_scan_prompt(text)
    else:
        prompt = _build_deep_scan_prompt(text, prior_result)
    
    # Call GPT - let exceptions propagate to caller, no silent fallback
    response = gpt_extract(
        prompt=prompt,
        extractor_name='report_type_detector'
    )
    
    # Parse response
    return _parse_gpt_response(response)


def _build_quick_scan_prompt(text: str) -> str:
    """Build prompt for quick scan stage."""
    return f"""You are an expert in SOC (Service Organization Control) reports. Analyze the following excerpt from a SOC report and determine:

1. **Report Standard**: Is this a SOC 1 or SOC 2 report?
   - SOC 1: Focuses on controls relevant to financial reporting
   - SOC 2: Focuses on security, availability, processing integrity, confidentiality, and privacy

2. **Report Type**: Is this a Type 1 or Type 2 report?
   - Type 1: Opinion on design of controls at a point in time
   - Type 2: Opinion on design AND operating effectiveness over a period of time

Return your analysis in JSON format:
{{
  "detected_type": "SOC1" or "SOC2",
  "detected_subtype": "TYPE1" or "TYPE2",
  "confidence": 0.0 to 1.0,
  "evidence": ["Key phrase 1", "Key phrase 2", ...],
  "reasoning": "Brief explanation of your decision"
}}

**Confidence Guidelines:**
- 0.90-1.00: Explicit statements clearly identify both standard and type
- 0.75-0.89: Strong indicators present but may lack explicit statements
- 0.50-0.74: Some indicators but ambiguous or conflicting signals
- 0.00-0.49: Insufficient information or highly uncertain

**Report Excerpt:**
{text[:8000]}

Return ONLY valid JSON, no additional text."""


def _build_deep_scan_prompt(text: str, prior_result: Optional[Dict]) -> str:
    """Build prompt for deep scan stage."""
    prior_info = ""
    if prior_result:
        prior_info = f"""
**Prior Quick Scan Result:**
- Detected: {prior_result.get('detected_type')} {prior_result.get('detected_subtype')}
- Confidence: {prior_result.get('confidence', 0):.2f}
- Evidence: {', '.join(prior_result.get('evidence', [])[:3])}

Please analyze the extended text below to confirm or revise this assessment.
"""
    
    return f"""You are an expert in SOC (Service Organization Control) reports. {prior_info}

Analyze the following extended excerpt from a SOC report and determine:

1. **Report Standard**: Is this a SOC 1 or SOC 2 report?
   - SOC 1: Focuses on controls relevant to financial reporting (ICFR - Internal Controls over Financial Reporting)
   - SOC 2: Focuses on Trust Services Criteria (security, availability, processing integrity, confidentiality, privacy)

2. **Report Type**: Is this a Type 1 or Type 2 report?
   - Type 1: Opinion on design of controls at a specific point in time
   - Type 2: Opinion on design AND operating effectiveness over a period of time (includes test results)

**Key Indicators to Look For:**

SOC 1 indicators:
- References to "financial reporting" or "user entity financial statements"
- SSAE 18, AT-C 320, or similar attestation standards
- Controls relevant to ICFR

SOC 2 indicators:
- References to "Trust Services Criteria" or "TSC"
- Security, Availability, Confidentiality, Processing Integrity, Privacy criteria
- SSAE 18 SOC 2, AT-C 105 + AT-C 205

Type 1 indicators:
- "at [specific date]" or "as of [date]"
- Focus on design only
- No test results or operating effectiveness testing

Type 2 indicators:
- "for the period [date] to [date]"
- Test results for operating effectiveness
- Multiple test procedures and results documented

Return your analysis in JSON format:
{{
  "detected_type": "SOC1" or "SOC2",
  "detected_subtype": "TYPE1" or "TYPE2",
  "confidence": 0.0 to 1.0,
  "evidence": ["Key phrase 1", "Key phrase 2", ...],
  "reasoning": "Brief explanation of your decision"
}}

**Confidence Guidelines:**
- 0.90-1.00: Explicit statements clearly identify both standard and type with multiple corroborating indicators
- 0.85-0.89: Strong indicators present, clear pattern matches one type
- 0.75-0.84: Good indicators but may have minor ambiguities
- 0.60-0.74: Some indicators but conflicting signals or unclear language
- 0.00-0.59: Insufficient information, highly ambiguous, or unable to determine

**Extended Report Excerpt:**
{text[:16000]}

Return ONLY valid JSON, no additional text."""


def _parse_gpt_response(response: str) -> Dict:
    """
    Parse GPT response into structured result.
    
    Args:
        response: Raw GPT response text
        
    Returns:
        Structured detection result
    """
    import json
    import re
    
    try:
        # Try to extract JSON from response
        # GPT might wrap it in markdown code blocks
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            response = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                response = json_match.group(0)
        
        result = json.loads(response)
        
        # Validate and normalize
        detected_type = result.get('detected_type', 'SOC2').upper()
        detected_subtype = result.get('detected_subtype', 'TYPE2').upper()
        confidence = float(result.get('confidence', 0.0))
        evidence = result.get('evidence', [])
        
        # Ensure valid values
        if detected_type not in ['SOC1', 'SOC2']:
            detected_type = 'SOC2'
        if detected_subtype not in ['TYPE1', 'TYPE2']:
            detected_subtype = 'TYPE2'
        
        confidence = max(0.0, min(1.0, confidence))
        
        return {
            'detected_type': detected_type,
            'detected_subtype': detected_subtype,
            'confidence': confidence,
            'evidence': evidence[:10]  # Limit evidence items
        }
        
    except Exception as e:
        logger.error(f"[REPORT_TYPE_DETECTOR] Failed to parse GPT response: {e}", exc_info=True)
        logger.error(f"[REPORT_TYPE_DETECTOR] Raw response: {response[:500]}")
        
        # Return low-confidence default
        return {
            'detected_type': 'SOC2',
            'detected_subtype': 'TYPE2',
            'confidence': 0.0,
            'evidence': [f"Parse error: {str(e)}"]
        }
