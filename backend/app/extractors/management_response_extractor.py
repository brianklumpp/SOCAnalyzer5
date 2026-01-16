"""
Management Response Extractor

Extracts management responses to control deviations using cascading search strategies:
1. Inline nearby: Search within N pages after deviation control
2. Inline expanded: Expand search window by +1 page if not found
3. Section-based: Find "Management Response" section and match to controls

Uses GPT for semantic matching with confidence self-evaluation.
"""

import logging
import re
import hashlib
from typing import Dict, List, Optional, Tuple
import redis.asyncio as aioredis

from ..gpt_client import gpt_extract
from .. import config as cfg

logger = logging.getLogger(__name__)


# Cache for tracking duplicate responses across controls
_response_hash_cache: Dict[str, List[int]] = {}


def get_page_text(txt_lines: List[str], page_number: int) -> str:
    """
    Extract text for a specific page from txt_lines with page markers.
    
    Args:
        txt_lines: List of text lines with page markers (=== PAGE X ===)
        page_number: Page number to extract
        
    Returns:
        Text content for the specified page
    """
    result = []
    current_page = None
    
    for line in txt_lines:
        # Check for page marker
        if line.strip().startswith('=== PAGE '):
            try:
                current_page = int(line.strip().split()[2])
            except (IndexError, ValueError):
                continue
        elif current_page == page_number:
            result.append(line)
    
    return ''.join(result)


def get_page_range_text(txt_lines: List[str], start_page: int, end_page: int) -> str:
    """
    Extract text for a range of pages.
    
    Args:
        txt_lines: List of text lines with page markers
        start_page: Starting page number (inclusive)
        end_page: Ending page number (inclusive)
        
    Returns:
        Combined text content for the page range
    """
    result = []
    current_page = None
    
    for line in txt_lines:
        if line.strip().startswith('=== PAGE '):
            try:
                current_page = int(line.strip().split()[2])
            except (IndexError, ValueError):
                continue
        elif current_page is not None and start_page <= current_page <= end_page:
            result.append(line)
    
    return ''.join(result)


def find_management_response_section(txt_lines: List[str], total_pages: int) -> Optional[Dict[str, int]]:
    """
    Search for "Management Response" section in the last 10 pages of the document.
    
    Args:
        txt_lines: List of text lines with page markers
        total_pages: Total number of pages in document
        
    Returns:
        Dict with {start_page, end_page, start_line, end_line} or None if not found
    """
    # Search patterns for management response section headers
    patterns = [
        r'management[\s\']?s?\s+response',
        r'corrective\s+action',
        r'remediation\s+plan',
        r'management\s+action\s+plan'
    ]
    
    # Search in last 10 pages
    search_start_page = max(1, total_pages - 10)
    
    current_page = None
    found_page = None
    found_line = None
    
    for line_idx, line in enumerate(txt_lines):
        if line.strip().startswith('=== PAGE '):
            try:
                current_page = int(line.strip().split()[2])
            except (IndexError, ValueError):
                continue
        elif current_page is not None and current_page >= search_start_page:
            # Check if line matches any pattern
            line_lower = line.lower()
            for pattern in patterns:
                if re.search(pattern, line_lower):
                    # Check if this looks like a section header (short line, possibly uppercase/bold indicators)
                    if len(line.strip()) < 100:  # Headers are typically short
                        found_page = current_page
                        found_line = line_idx + 1
                        logger.info(f"Found management response section at page {found_page}, line {found_line}")
                        
                        # Estimate end of section (next section header or end of document)
                        end_page = min(total_pages, found_page + 5)  # Assume section is ~5 pages
                        end_line = found_line + 500  # Estimate lines
                        
                        return {
                            'start_page': found_page,
                            'end_page': end_page,
                            'start_line': found_line,
                            'end_line': end_line
                        }
    
    return None


async def extract_management_response_nearby(
    control: Dict,
    txt_lines: List[str],
    search_window: int = 1
) -> Optional[Dict]:
    """
    Strategy 1 & 2: Search for management response in pages near the control.
    
    Args:
        control: Control dict with control_page_refs, control_id, deviation_desc, etc.
        txt_lines: Full document text lines with page markers
        search_window: Number of pages after control to search
        
    Returns:
        Dict with {text, page_refs, line_ref, confidence, method} or None
    """
    if not control.get('control_page_refs'):
        return None
    
    control_page = control['control_page_refs'][0]  # First page where control appears
    end_page = control_page + search_window
    
    logger.error(f"[MGMT EXTRACT] Control {control.get('control_id')}: Searching pages {control_page} to {end_page} (window={search_window})")
    
    # Extract text from control page through search window
    search_text = get_page_range_text(txt_lines, control_page, end_page)
    
    logger.error(f"[MGMT EXTRACT] Extracted {len(search_text) if search_text else 0} characters of text")
    
    if not search_text or len(search_text) < 50:
        return None
    
    # Truncate for GPT context (max ~3000 tokens)
    if len(search_text) > 12000:
        search_text = search_text[:12000] + "\n\n[... text truncated ...]"
    
    # Build GPT prompt for semantic identification
    prompt = f"""You are analyzing a SOC audit report to find management's response to a control deviation.

CONTROL INFORMATION:
Control ID: {control.get('control_id', 'N/A')}
Control Description: {control.get('control_desc', 'N/A')[:300]}
Deviation: {control.get('deviation_desc', 'N/A')[:500]}

TEXT TO SEARCH (pages {control_page}-{end_page}):
{search_text}

TASK:
Identify if there is a management response, remediation plan, or corrective action for this specific deviation.
Management responses typically include:
- Acknowledgment of the deviation
- Explanation of root cause
- Planned corrective actions
- Timeline for remediation
- Responsible parties

Respond in JSON format:
{{
  "found": true or false,
  "response_text": "exact text of management response (if found)",
  "confidence": 0.0 to 1.0 (your confidence in this match),
  "reasoning": "brief explanation of why this is/isn't a management response"
}}

If multiple responses exist in the text, match to the specific control deviation described above.
If no management response is found, return found: false.
"""
    
    try:
        logger.error(f"[MGMT EXTRACT] Calling GPT for control {control.get('control_id')}")
        response = gpt_extract(
            prompt=prompt,
            extractor_name="management_response_nearby"
        )
        
        logger.error(f"[MGMT EXTRACT] GPT returned, type={type(response)}, len={len(response) if response else 0}")
        logger.error(f"[MGMT EXTRACT] GPT raw response: {response[:500] if response else 'None'}")
        
        import json
        # Handle markdown code blocks from GPT
        response_clean = response.strip()
        if response_clean.startswith('```'):
            json_match = re.search(r'```(?:json)?\s*\n(.*?)\s*```', response_clean, re.DOTALL)
            if json_match:
                response_clean = json_match.group(1).strip()
        
        result = json.loads(response_clean)
        logger.error(f"[MGMT EXTRACT] GPT result: found={result.get('found')}, confidence={result.get('confidence')}")
        
        if result.get('found') and result.get('response_text'):
            confidence = float(result.get('confidence', 0))
            
            # Only return if confidence meets minimum threshold
            min_conf = cfg.MANAGEMENT_RESPONSE_MIN_CONFIDENCE
            logger.error(f"[MGMT EXTRACT] Confidence {confidence:.2f} vs min {min_conf}")
            if confidence >= min_conf:
                logger.error(f"[MGMT EXTRACT] ✓ FOUND management response for {control.get('control_id')}")
                logger.info(f"Found management response for control {control.get('control_id')} "
                          f"(confidence: {confidence:.2f}) using nearby search (window={search_window})")
                
                return {
                    'text': result['response_text'],
                    'page_refs': list(range(control_page, end_page + 1)),
                    'line_ref': None,  # Don't have precise line ref for nearby search
                    'confidence': confidence,
                    'method': 'inline_nearby',
                    'reasoning': result.get('reasoning', '')
                }
    
    except Exception as e:
        logger.error(f"[MGMT EXTRACT] ❌ EXCEPTION in nearby extraction: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"[MGMT EXTRACT] Traceback: {traceback.format_exc()}")
    
    return None


async def extract_management_response_from_section(
    control: Dict,
    txt_lines: List[str],
    section_info: Dict,
    redis_client: Optional[aioredis.Redis] = None
) -> Optional[Dict]:
    """
    Strategy 3: Extract management response from dedicated section.
    
    Args:
        control: Control dict with control_id, deviation_desc, etc.
        txt_lines: Full document text lines
        section_info: Dict with {start_page, end_page, start_line, end_line}
        redis_client: Optional Redis client for caching
        
    Returns:
        Dict with {text, page_refs, line_ref, confidence, method} or None
    """
    # Extract section text
    section_text = get_page_range_text(
        txt_lines,
        section_info['start_page'],
        section_info['end_page']
    )
    
    if not section_text or len(section_text) < 50:
        return None
    
    # Truncate for GPT context
    if len(section_text) > 15000:
        section_text = section_text[:15000] + "\n\n[... section truncated ...]"
    
    # Build GPT prompt for section-based matching
    prompt = f"""You are analyzing a SOC audit report's "Management Response" section to find the response for a specific control deviation.

CONTROL INFORMATION:
Control ID: {control.get('control_id', 'N/A')}
Control Description: {control.get('control_desc', 'N/A')[:300]}
Deviation: {control.get('deviation_desc', 'N/A')[:500]}

MANAGEMENT RESPONSE SECTION (pages {section_info['start_page']}-{section_info['end_page']}):
{section_text}

TASK:
Find the management response that corresponds to this specific control.
Look for references to the control ID, control description keywords, or deviation details.

Respond in JSON format:
{{
  "found": true or false,
  "response_text": "exact text of the management response for this control",
  "confidence": 0.0 to 1.0 (your confidence this response matches this control),
  "reasoning": "explanation of how you matched this response to the control"
}}

If the section contains responses for multiple controls, extract only the one matching the control above.
If no matching response is found, return found: false.
"""
    
    try:
        response = gpt_extract(
            prompt=prompt,
            extractor_name="management_response_section",
            json_mode=True
        )
        
        import json
        # Handle markdown code blocks from GPT
        response_clean = response.strip()
        if response_clean.startswith('```'):
            json_match = re.search(r'```(?:json)?\s*\n(.*?)\s*```', response_clean, re.DOTALL)
            if json_match:
                response_clean = json_match.group(1).strip()
        
        result = json.loads(response_clean)
        
        if result.get('found') and result.get('response_text'):
            confidence = float(result.get('confidence', 0))
            
            # Only return if confidence meets minimum threshold
            if confidence >= cfg.MANAGEMENT_RESPONSE_MIN_CONFIDENCE:
                logger.info(f"Found management response for control {control.get('control_id')} "
                          f"(confidence: {confidence:.2f}) using section matching")
                
                return {
                    'text': result['response_text'],
                    'page_refs': [section_info['start_page']],  # Could be more precise
                    'line_ref': section_info['start_line'],
                    'confidence': confidence,
                    'method': 'section_match',
                    'reasoning': result.get('reasoning', '')
                }
    
    except Exception as e:
        logger.warning(f"GPT extraction failed for section-based management response: {e}")
    
    return None


async def extract_management_responses_for_scan(
    controls: List[Dict],
    txt_lines: List[str],
    total_pages: int,
    scan_id: int,
    redis_client: Optional[aioredis.Redis] = None
) -> Dict[int, Dict]:
    """
    Extract management responses for all deviation controls in a scan.
    
    Uses cascading search strategies:
    1. Search N pages after control (config.MANAGEMENT_RESPONSE_SEARCH_WINDOW)
    2. Expand to N+1 pages if not found
    3. Find and search dedicated management response section if exists
    
    Args:
        controls: List of control dicts (must include controls with has_deviation=True)
        txt_lines: Full document text lines with page markers
        total_pages: Total number of pages in document
        scan_id: Scan ID for caching
        redis_client: Optional Redis client for caching section location
        
    Returns:
        Dict mapping control IDs to response dicts: {control_id: {text, page_refs, confidence, ...}}
    """
    results = {}
    deviation_controls = [c for c in controls if c.get('has_deviation')]
    
    if not deviation_controls:
        logger.info("No deviation controls found, skipping management response extraction")
        return results
    
    logger.info(f"Extracting management responses for {len(deviation_controls)} deviation controls")
    
    # Check Redis cache for management response section location
    section_info = None
    cache_key = f"scan:{scan_id}:mgmt_response_section"
    
    if redis_client:
        try:
            cached_section = await redis_client.get(cache_key)
            if cached_section:
                import json
                section_info = json.loads(cached_section)
                logger.info(f"Using cached management response section location: pages {section_info['start_page']}-{section_info['end_page']}")
        except Exception as e:
            logger.warning(f"Failed to retrieve cached section info: {e}")
    
    # Track responses by hash to identify duplicates
    response_hashes = {}
    
    for control in deviation_controls:
        control_id = control.get('control_id', 'Unknown')
        logger.info(f"Processing management response for control: {control_id}")
        
        response_data = None
        
        # Strategy 1: Search nearby pages (N pages after control)
        response_data = await extract_management_response_nearby(
            control,
            txt_lines,
            search_window=cfg.MANAGEMENT_RESPONSE_SEARCH_WINDOW
        )
        
        # Strategy 2: Expand search window if not found
        if not response_data:
            logger.info(f"Strategy 1 failed for {control_id}, trying expanded window (+1 page)")
            response_data = await extract_management_response_nearby(
                control,
                txt_lines,
                search_window=cfg.MANAGEMENT_RESPONSE_SEARCH_WINDOW + 1
            )
        
        # Strategy 3: Further expand search window
        if not response_data:
            logger.info(f"Strategy 2 failed for {control_id}, trying larger window (+4 pages)")
            response_data = await extract_management_response_nearby(
                control,
                txt_lines,
                search_window=cfg.MANAGEMENT_RESPONSE_SEARCH_WINDOW + 4
            )
        
        # Strategy 4: Search in dedicated management response section
        if not response_data:
            logger.info(f"Strategy 3 failed for {control_id}, trying section-based search")
            
            # Find section if not already found
            if section_info is None:
                section_info = find_management_response_section(txt_lines, total_pages)
                
                # Cache section location in Redis with 7-day TTL
                if section_info and redis_client:
                    try:
                        import json
                        await redis_client.setex(
                            cache_key,
                            7 * 24 * 60 * 60,  # 7 days in seconds
                            json.dumps(section_info)
                        )
                        logger.info(f"Cached management response section location for scan {scan_id}")
                    except Exception as e:
                        logger.warning(f"Failed to cache section info: {e}")
            
            if section_info:
                response_data = await extract_management_response_from_section(
                    control,
                    txt_lines,
                    section_info,
                    redis_client
                )
        
        # Store result if found
        if response_data:
            # Calculate hash to track duplicates
            response_hash = hashlib.md5(response_data['text'].encode()).hexdigest()
            
            if response_hash in response_hashes:
                # This is a duplicate response - add to related controls list
                response_hashes[response_hash].append(control_id)
                logger.info(f"Duplicate response detected for {control_id} (matches {response_hashes[response_hash][0]})")
            else:
                response_hashes[response_hash] = [control_id]
            
            # Store response with related control IDs
            response_data['related_control_ids'] = response_hashes[response_hash]
            results[control_id] = response_data
            
            logger.info(f"Successfully extracted management response for {control_id} "
                       f"(method: {response_data['method']}, confidence: {response_data['confidence']:.2f})")
        else:
            logger.info(f"No management response found for {control_id}")
    
    logger.info(f"Management response extraction complete: {len(results)}/{len(deviation_controls)} controls have responses")
    
    return results
