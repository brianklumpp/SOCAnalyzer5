# --- All imports at the top (PEP8 best practice) ---
import os
import json
import logging
from typing import Any, List, Optional, Tuple
from .. import config
from ..gpt_client import gpt_extract

logger = logging.getLogger(__name__)

# Use centralized config paths
SECTION_JSON_PATH = str(config.SECTION_JSON_PATH)
AUDITOR_JSON_PATH = str(config.JSON_DIR / "auditor_result.json")
PDF_TXT_PATH = str(config.PDF_TXT_PATH)


def load_json(path: str) -> Any:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(obj: Any, path: str):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

def extract_text_for_pages(txt_lines: List[str], page_numbers: List[int]) -> str:
    """Extracts all text for the given 1-based page numbers from the extracted txt file."""
    result = []
    current_page = 1
    for line in txt_lines:
        if line.strip().startswith('=== PAGE '):
            try:
                current_page = int(line.strip().split()[2])
            except Exception:
                continue
        if current_page in page_numbers:
            result.append(line)
    return ''.join(result)

def extract_text_for_lines(txt_lines, start_line, end_line):
    # Lines are 1-indexed in section_results.json
    return ''.join(txt_lines[start_line-1:end_line])

def chunk_text(text: str, max_tokens: Optional[int] = None) -> List[str]:
    # Use config or default chunk size
    if max_tokens is None:
        max_tokens = getattr(config, 'GPT_CHUNK_TOKENS', None)
        if max_tokens is None:
            max_tokens = getattr(config, 'DEFAULT_CHUNK_SIZE', None)
        if max_tokens is None:
            max_tokens = 1500
    chunk_size = max_tokens * 4  # rough char/token ratio
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def extract_title_page(txt_lines):
    title_page_lines = []
    for line in txt_lines:
        if line.strip().startswith('=== PAGE 2'):
            break
        title_page_lines.append(line)
    return ''.join(title_page_lines)

def extract_pages_range(txt_lines: List[str], start_page: int, end_page: int) -> str:
    """
    Extract text from a range of pages.
    
    Args:
        txt_lines: List of text lines from extracted PDF
        start_page: Starting page number (1-indexed)
        end_page: Ending page number (1-indexed, inclusive)
        
    Returns:
        Extracted text from specified page range
    """
    result = []
    current_page = 0
    in_range = False
    
    for line in txt_lines:
        if line.strip().startswith('=== PAGE '):
            try:
                current_page = int(line.strip().split()[2])
                in_range = start_page <= current_page <= end_page
            except Exception:
                continue
        
        if in_range:
            result.append(line)
    
    return ''.join(result)

def detect_header_footer_auditor(txt_lines: List[str]) -> Tuple[Optional[str], float]:
    """
    Detect auditor firm from header/footer patterns across multiple pages.
    
    Looks for repeated text in the first/last 2 lines of pages 1-5 and matches
    against known auditor firms.
    
    Args:
        txt_lines: List of text lines from extracted PDF
        
    Returns:
        Tuple of (auditor_name, confidence_boost)
        confidence_boost is +0.20 if match found, 0 otherwise
    """
    firms = load_auditor_firms()
    
    # Extract first/last 2 lines from pages 1-5
    page_boundaries = {}
    current_page = 0
    page_lines = []
    
    for line in txt_lines:
        if line.strip().startswith('=== PAGE '):
            # Save previous page if exists
            if current_page > 0 and 1 <= current_page <= 5:
                page_boundaries[current_page] = page_lines.copy()
            
            # Start new page
            try:
                current_page = int(line.strip().split()[2])
                page_lines = []
            except Exception:
                continue
        else:
            page_lines.append(line.strip())
    
    # Save last page if in range
    if current_page > 0 and 1 <= current_page <= 5:
        page_boundaries[current_page] = page_lines
    
    # Extract headers and footers (first/last 2 non-empty lines)
    headers = []
    footers = []
    
    for page_num in sorted(page_boundaries.keys()):
        lines = [l for l in page_boundaries[page_num] if l]  # Filter empty
        if len(lines) >= 2:
            headers.extend(lines[:2])
            footers.extend(lines[-2:])
    
    # Find repeated patterns (appearing on >=3 pages)
    all_header_footer = headers + footers
    header_footer_lower = [h.lower() for h in all_header_footer]
    
    # Count occurrences
    from collections import Counter
    pattern_counts = Counter(header_footer_lower)
    
    # Find patterns that appear >= 3 times
    repeated_patterns = [pattern for pattern, count in pattern_counts.items() if count >= 3]
    
    if not repeated_patterns:
        return None, 0.0
    
    # Search for auditor firms in repeated patterns
    for pattern in repeated_patterns:
        for short, legal in firms:
            short_lower = short.lower()
            if short_lower in pattern or f"{short_lower}'s" in pattern or f"{short_lower}'s" in pattern:
                logging.info(f"Header/footer detection found auditor: {legal} (pattern: '{pattern[:50]}...')")
                return legal, 0.20
    
    return None, 0.0

def verify_auditor_in_text(auditor_name: str, text: str) -> bool:
    """Check if the auditor name actually appears in the source text."""
    if not auditor_name:
        return False
    # Case-insensitive search for the auditor name in text
    return auditor_name.lower() in text.lower()

def extract_auditor_with_validation(text: str, company_line: str) -> Tuple[Optional[str], float, List[str], str]:
    """
    Two-stage auditor extraction with single-pass approach:
    Stage 1: Extract all company names from text (chunked)
    Stage 2: Identify which is the audit firm (single GPT call)
    
    Returns: (auditor_name, confidence, responses, validation_note)
    """
    # Initialize debug log file
    debug_log_path = config.JSON_DIR.parent / 'logs' / 'auditor_extraction_debug.log'
    debug_log_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(debug_log_path, 'w', encoding='utf-8') as debug_log:
        debug_log.write("=" * 80 + "\n")
        debug_log.write("TWO-STAGE AUDITOR EXTRACTION\n")
        debug_log.write("=" * 80 + "\n\n")
        debug_log.write(f"Text preview (first 500 chars):\n{text[:500]}...\n\n")
        debug_log.write(f"Company exclusion context: {company_line}\n\n")
        
        # ============================================================
        # STAGE 1: Extract all company names from text (chunked)
        # ============================================================
        debug_log.write("=" * 80 + "\n")
        debug_log.write("STAGE 1: COMPANY NAME EXTRACTION\n")
        debug_log.write("=" * 80 + "\n")
        
        chunks = chunk_text(text)
        logging.info(f"Stage 1: Processing {len(chunks)} text chunks to extract company names")
        debug_log.write(f"Text split into {len(chunks)} chunks\n\n")
        
        all_companies = []
        stage1_responses = []
        
        for idx, chunk in enumerate(chunks):
            full_prompt = config.AUDITOR_COMPANY_EXTRACTION_PROMPT.format(text=chunk)
            logging.debug(f'Stage 1, Chunk {idx + 1}/{len(chunks)}: Prompt length = {len(full_prompt)} chars')
            
            response = gpt_extract(full_prompt, 'auditor_extractor')
            stage1_responses.append(response)
            
            # Parse JSON array of company names
            try:
                companies = json.loads(response)
                if isinstance(companies, list):
                    all_companies.extend(companies)
                    debug_log.write(f"Chunk {idx + 1}: Found {len(companies)} companies\n")
                    for company in companies:
                        debug_log.write(f"  - {company}\n")
                else:
                    logging.warning(f"Stage 1, Chunk {idx + 1}: Response is not a list: {response}")
                    debug_log.write(f"Chunk {idx + 1}: Invalid response (not a list)\n")
            except Exception as e:
                logging.error(f'Stage 1, Chunk {idx + 1}: Failed to parse GPT response: {response} | Error: {e}')
                debug_log.write(f"Chunk {idx + 1}: Parse error - {e}\n")
        
        # Deduplicate companies (case-insensitive)
        unique_companies = []
        seen_lower = set()
        for company in all_companies:
            if company and company.lower() not in seen_lower:
                unique_companies.append(company)
                seen_lower.add(company.lower())
        
        logging.info(f"Stage 1: Processed {len(chunks)} chunks, found {len(unique_companies)} unique companies")
        debug_log.write(f"\nStage 1 Result: {len(unique_companies)} unique companies\n")
        debug_log.write("Unique companies found:\n")
        for company in unique_companies:
            debug_log.write(f"  - {company}\n")
        
        # If no companies found, try regex fallback immediately
        if not unique_companies:
            logging.warning("Stage 1: No companies extracted by GPT - trying regex fallback")
            debug_log.write("\nNo companies found - attempting regex fallback...\n")
            fallback_auditor = _regex_fallback_search(text)
            if fallback_auditor:
                debug_log.write(f"Regex fallback found: {fallback_auditor}\n")
                debug_log.write(f"Final confidence: 0.65 (regex fallback)\n")
                return fallback_auditor, 0.65, stage1_responses, "Regex fallback (Stage 1 found no companies)"
            else:
                debug_log.write("Regex fallback found nothing\n")
                return None, 0, stage1_responses, "No companies found in Stage 1 or regex fallback"
        
        # ============================================================
        # STAGE 2: Identify which company is the audit firm
        # ============================================================
        debug_log.write("\n" + "=" * 80 + "\n")
        debug_log.write("STAGE 2: AUDITOR IDENTIFICATION\n")
        debug_log.write("=" * 80 + "\n")
        
        companies_list = json.dumps(unique_companies, indent=2)
        identification_prompt = config.AUDITOR_IDENTIFICATION_PROMPT.format(
            company_line=company_line,
            companies=companies_list
        )
        
        logging.info(f"Stage 2: Identifying auditor from {len(unique_companies)} companies")
        debug_log.write(f"Companies sent to Stage 2:\n{companies_list}\n\n")
        
        stage2_response = gpt_extract(identification_prompt, 'auditor_extractor')
        
        # Parse Stage 2 response
        try:
            data = json.loads(stage2_response)
            auditor = data.get('auditor')
            base_confidence = float(data.get('confidence', 0))
            reasoning = data.get('reasoning', '')
            
            debug_log.write(f"Stage 2 Response:\n")
            debug_log.write(f"  Auditor: {auditor}\n")
            debug_log.write(f"  Base confidence: {base_confidence:.3f}\n")
            debug_log.write(f"  Reasoning: {reasoning}\n\n")
            
            logging.info(f"Stage 2: GPT identified auditor = '{auditor}', confidence = {base_confidence:.3f}")
            logging.info(f"Stage 2: GPT reasoning = {reasoning}")
            
        except Exception as e:
            logging.error(f'Stage 2: Failed to parse GPT response: {stage2_response} | Error: {e}')
            debug_log.write(f"Stage 2 Parse Error: {e}\n")
            debug_log.write(f"Raw response: {stage2_response}\n")
            
            # Try fallback sequence on parse error
            debug_log.write("Parse error - attempting fallback sequence...\n")
            
            # Fallback 1: Regex search
            fallback_auditor = _regex_fallback_search(text)
            if fallback_auditor:
                debug_log.write(f"Regex fallback found: {fallback_auditor}\n")
                return fallback_auditor, 0.65, [stage2_response], "Regex fallback (Stage 2 parse error)"
            
            # Fallback 2: Control section
            control_auditor = _extract_from_control_section(debug_log)
            if control_auditor:
                debug_log.write(f"Control section fallback found: {control_auditor}\n")
                return control_auditor, 0.60, [stage2_response], "Found in control section (Stage 2 parse error)"
            
            # Fallback 3: Context inference
            inferred_auditor = _infer_auditor_from_context(text, debug_log)
            if inferred_auditor:
                debug_log.write(f"Context inference found: {inferred_auditor}\n")
                return inferred_auditor, 0.55, [stage2_response], "Context inference (Stage 2 parse error)"
            
            # All fallbacks failed
            return "Auditor Could Not Be Identified", 0, [stage2_response], f"Stage 2 parse error: {e}"
        
        # If no auditor identified, try fallback sequence: regex -> control section -> context inference
        if not auditor:
            logging.warning("Stage 2: GPT did not identify an auditor - trying fallback sequence")
            debug_log.write("\nNo auditor identified - attempting fallback sequence...\n")
            
            # Fallback 1: Regex search
            debug_log.write("Fallback 1: Regex search...\n")
            fallback_auditor = _regex_fallback_search(text)
            if fallback_auditor:
                debug_log.write(f"Regex fallback found: {fallback_auditor}\n")
                debug_log.write(f"Final confidence: 0.65 (regex fallback)\n")
                return fallback_auditor, 0.65, [stage2_response], "Regex fallback (Stage 2 found no auditor)"
            
            # Fallback 2: Control section headings
            debug_log.write("Fallback 2: Control section headings...\n")
            control_auditor = _extract_from_control_section(debug_log)
            if control_auditor:
                debug_log.write(f"Control section fallback found: {control_auditor}\n")
                debug_log.write(f"Final confidence: 0.60 (control section)\n")
                return control_auditor, 0.60, [stage2_response], "Found in control section headings"
            
            # Fallback 3: Context inference from letterhead/location
            debug_log.write("Fallback 3: Context inference...\n")
            inferred_auditor = _infer_auditor_from_context(text, debug_log)
            if inferred_auditor:
                debug_log.write(f"Context inference found: {inferred_auditor}\n")
                debug_log.write(f"Final confidence: 0.55 (context inference)\n")
                return inferred_auditor, 0.55, [stage2_response], "Inferred from letterhead/location context"
            
            # All fallbacks failed
            debug_log.write("All fallback methods failed\n")
            return "Auditor Could Not Be Identified", 0, [stage2_response], "All extraction methods unsuccessful"
        
        # ============================================================
        # CONFIDENCE ADJUSTMENTS
        # ============================================================
        debug_log.write("\n" + "=" * 80 + "\n")
        debug_log.write("CONFIDENCE ADJUSTMENTS\n")
        debug_log.write("=" * 80 + "\n")
        debug_log.write(f"Base confidence from GPT: {base_confidence:.3f}\n")
        
        adjusted_confidence = base_confidence
        adjustments = []
        
        # Adjustment 1: Text verification
        text_verified = verify_auditor_in_text(auditor, text)
        if text_verified:
            logging.info(f"Text verification: PASSED - '{auditor}' found in source text")
            debug_log.write(f"Text verification: PASSED (no penalty)\n")
        else:
            adjusted_confidence -= 0.15
            adjustments.append("Text verification failed (-0.15)")
            logging.warning(f"Text verification: FAILED - '{auditor}' NOT found in source text (penalty -0.15)")
            debug_log.write(f"Text verification: FAILED (-0.15 penalty)\n")
            debug_log.write(f"  Confidence after text verification: {adjusted_confidence:.3f}\n")
        
        all_responses = stage1_responses + [stage2_response]
        validation_note = f"Two-stage extraction: {reasoning[:100]}..."
        if adjustments:
            validation_note += f" | Adjustments: {', '.join(adjustments)}"
        
        # Cap confidence at 1.0
        final_confidence = min(1.0, max(0.0, adjusted_confidence))
        
        debug_log.write(f"\nFinal confidence: {final_confidence:.3f} (capped at [0.0, 1.0])\n")
        debug_log.write(f"Validation note: {validation_note}\n")
        
        logging.info(f"Final result: auditor = '{auditor}', confidence = {final_confidence:.3f}")
        
        return auditor, final_confidence, all_responses, validation_note


def _regex_fallback_search(text: str) -> Optional[str]:
    """
    Regex fallback: Search for known Big 4 + top regional audit firm patterns.
    Uses word boundary matching for short abbreviations to avoid false positives (e.g., 'EY' in 'Journey').
    Returns first match found or None.
    """
    import re
    
    # Known audit firms (Big 4 + top regional firms)
    # Order by specificity: check full legal names first, then abbreviations
    known_firms = [
        "BDO USA, P.C.",
        "BDO USA",
        "KPMG LLP",
        "Deloitte & Touche LLP",
        "PricewaterhouseCoopers",
        "Ernst & Young LLP",
        "Grant Thornton LLP",
        "RSM US LLP",
        "Crowe LLP",
        "Moss Adams LLP",
        "CliftonLarsonAllen LLP",
        "Schellman & Company, LLC",
        "KPMG",
        "Deloitte",
        "PwC",
        "BDO",
        "Grant Thornton",
        "RSM",
        "Crowe",
        "Moss Adams",
        "CliftonLarsonAllen",
        "Schellman"
    ]
    
    # For short abbreviations (2-3 letters), require word boundaries to avoid false positives
    short_abbrevs = {"EY", "PwC", "RSM", "BDO"}
    
    for firm in known_firms:
        if firm in short_abbrevs:
            # Use word boundary regex for short abbreviations
            pattern = r'\b' + re.escape(firm) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                logging.info(f"Regex fallback found (word boundary): {firm}")
                return firm
        else:
            # Case-insensitive substring search for longer names
            if firm.lower() in text.lower():
                logging.info(f"Regex fallback found: {firm}")
                return firm
    
    logging.warning("Regex fallback: No known audit firms found in text")
    return None

def _extract_from_control_section(debug_log) -> Optional[str]:
    """
    Fallback: Search control testing section for auditor name in headings.
    Common pattern: "<Auditor Name> Test of Controls" or "Tests of Controls Performed by <Auditor Name>"
    
    Returns: Auditor firm name if found, else None
    """
    try:
        # Load section results to find control testing section
        section_results = load_json(SECTION_JSON_PATH)
        
        # Find Control_Descriptions section
        control_section = None
        for s in section_results:
            topic = s.get('topic', '')
            if topic == 'Control_Descriptions':
                control_section = s
                break
        
        if not control_section:
            debug_log.write("Control section fallback: No Control_Descriptions section found\n")
            return None
        
        # Extract first 2-3 pages of control section
        with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f:
            txt_lines = f.readlines()
        
        start_line = control_section.get('start_line')
        end_line = control_section.get('end_line')
        
        if not start_line or not end_line:
            debug_log.write("Control section fallback: Missing line references\n")
            return None
        
        # Extract first 2-3 pages (approximately 100-150 lines)
        max_lines = min(150, end_line - start_line + 1)
        control_text = extract_text_for_lines(txt_lines, start_line, start_line + max_lines - 1)
        
        debug_log.write(f"Control section fallback: Extracted {len(control_text)} chars from control section\n")
        
        # Use GPT prompt from config to find auditor in control section headings
        prompt = config.AUDITOR_CONTROL_SECTION_PROMPT.format(text=control_text[:1500])
        response = gpt_extract(prompt, 'auditor_extractor')
        debug_log.write(f"Control section GPT response: {response}\n")
        
        data = json.loads(response)
        auditor = data.get('auditor')
        confidence = float(data.get('confidence', 0))
        reasoning = data.get('reasoning', '')
        
        if auditor and confidence > 0.5:
            logging.info(f"Control section fallback: Found '{auditor}' with confidence {confidence:.3f}")
            logging.info(f"Control section reasoning: {reasoning}")
            return auditor
        else:
            debug_log.write(f"Control section fallback: Low confidence or no firm (confidence={confidence:.3f})\n")
            return None
            
    except Exception as e:
        logging.error(f"Control section fallback failed: {e}")
        debug_log.write(f"Control section fallback error: {e}\n")
        return None

def _infer_auditor_from_context(text: str, debug_log) -> Optional[str]:
    """
    Infer auditor firm from context clues when the firm name is missing from extracted text.
    Common scenario: Firm name appears as logo/image on PDF and isn't extracted as text.
    
    Uses GPT to infer the firm based on:
    - Service lines mentioned in letterhead (e.g., "Assurance | Tax | Advisory")
    - City/location mentioned
    - Professional language patterns
    - Report structure and format
    
    Returns: Inferred firm name or None
    """
    # Use GPT prompt from config for context-based inference
    inference_prompt = config.AUDITOR_CONTEXT_INFERENCE_PROMPT.format(text=text[:2000])
    
    try:
        response = gpt_extract(inference_prompt, 'auditor_extractor')
        debug_log.write(f"Context inference GPT response: {response}\n")
        
        data = json.loads(response)
        inferred_firm = data.get('auditor')
        confidence = float(data.get('confidence', 0))
        reasoning = data.get('reasoning', '')
        
        if inferred_firm and confidence > 0.4:  # Only accept if reasonably confident
            logging.info(f"Context inference: Inferred '{inferred_firm}' with confidence {confidence:.3f}")
            logging.info(f"Context inference reasoning: {reasoning}")
            return inferred_firm
        else:
            logging.warning(f"Context inference: Low confidence or no firm identified (confidence={confidence:.3f})")
            return None
            
    except Exception as e:
        logging.error(f"Context inference failed: {e}")
        debug_log.write(f"Context inference error: {e}\n")
        return None

def extract_auditor_from_report():
    # Reset output file at the start of extraction
    with open(config.JSON_DIR / 'auditor_result.json', 'w', encoding='utf-8') as f:
        f.write('{}\n')
    # Load section results
    section_results = load_json(SECTION_JSON_PATH)
    # Load company and parent company for exclusion
    company_info = load_json(str(config.JSON_DIR / 'company_result.json'))
    company = company_info.get('company')
    parent_company = company_info.get('parent_company')
    if parent_company:
        company_line = f"The company being audited is: {company}, a {parent_company} company. "
    else:
        company_line = f"The company being audited is: {company}. "
    # Find the first Service_Auditor_Report section
    auditor_section = next((s for s in section_results if s.get('topic') == 'Service_Auditor_Report'), None)
    if not auditor_section:
        logging.warning('No Service_Auditor_Report section found. Falling back to full-document scan.')
    with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    
    # Build line indices set for deduplication
    line_indices = set()
    
    # ALWAYS include pages 1-5 (expanded search range to capture auditor letterhead/signatures)
    # Many auditor firms place their letterhead on page 4 (e.g., BDO, Schellman)
    pages_1_5_text = extract_pages_range(txt_lines, 1, 5)
    # Track line indices from pages 1-5
    current_page = 0
    for idx, line in enumerate(txt_lines):
        if line.strip().startswith('=== PAGE '):
            try:
                current_page = int(line.strip().split()[2])
            except Exception:
                pass
        if 1 <= current_page <= 5:
            line_indices.add(idx)
    
    text_sections = [pages_1_5_text]
    
    # Append Service_Auditor_Report section if found (deduplicate by line indices)
    if auditor_section:
        start_line = auditor_section.get('start_line')
        end_line = auditor_section.get('end_line')
        if start_line and end_line:
            # Check for overlap
            section_indices = set(range(start_line - 1, end_line))
            new_indices = section_indices - line_indices
            if new_indices:
                text_sections.append(extract_text_for_lines(txt_lines, start_line, end_line))
                line_indices.update(section_indices)
        elif auditor_section.get('DOC_page_ref') is not None and auditor_section.get('end_DOC_page_ref') is not None:
            start_page = auditor_section['DOC_page_ref']
            end_page = auditor_section['end_DOC_page_ref']
            # Add section pages (deduplicate)
            section_text_indices = set()
            current_page = 0
            for idx, line in enumerate(txt_lines):
                if line.strip().startswith('=== PAGE '):
                    try:
                        current_page = int(line.strip().split()[2])
                    except Exception:
                        pass
                if start_page <= current_page <= end_page:
                    section_text_indices.add(idx)
            
            new_indices = section_text_indices - line_indices
            if new_indices:
                text_sections.append(extract_text_for_pages(txt_lines, list(range(start_page, end_page + 1))))
                line_indices.update(section_text_indices)
        else:
            logging.error('DOC_page_ref or end_DOC_page_ref is None for auditor section. Using full document text for context.')
            # Fallback to full document text
            with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f2:
                text_sections.append(f2.read())
    else:
        # No section info detected: pages 1-5 already included, no additional text needed
        logging.warning('No Service_Auditor_Report section found. Using pages 1-5 only.')
    
    text = '\n'.join(text_sections)
    total_lines = sum(s.count('\n') for s in text_sections)
    logging.info(f"Searching pages 1-5 + Service_Auditor_Report section ({total_lines} lines total)")
    
    # Extract auditor with two-stage approach (single attempt)
    auditor, confidence, responses, validation_note = extract_auditor_with_validation(text, company_line)
    
    # Header/footer pattern detection for additional confidence boost
    header_footer_auditor, header_footer_boost = detect_header_footer_auditor(txt_lines)
    
    result = {
        'auditor': auditor,
        'confidence': confidence,
        'source_section': (auditor_section.get('clean_heading') if isinstance(auditor_section, dict) else None),
        'source_page': (auditor_section.get('DOC_page_ref') if isinstance(auditor_section, dict) else None),
        'raw_gpt_responses': responses,
        'validation_note': validation_note
    }
    
    # Apply header/footer confidence boost if detected
    if header_footer_auditor and auditor and auditor != "Auditor Could Not Be Identified":
        if header_footer_auditor.lower() == auditor.lower():
            # Match found - boost confidence (capped at 1.0)
            original_confidence = confidence
            result['confidence'] = min(1.0, confidence + header_footer_boost)
            result['header_footer_match'] = True
            result['header_footer_boost'] = header_footer_boost
            logging.info(f"Header/footer pattern matched GPT result. Confidence boosted from {original_confidence:.3f} to {result['confidence']:.3f}")
        else:
            # Different auditor detected - log warning but keep GPT result
            result['header_footer_mismatch'] = True
            result['header_footer_auditor'] = header_footer_auditor
            logging.warning(f"Header/footer detected different auditor: '{header_footer_auditor}' vs GPT: '{auditor}'. Keeping GPT result.")
    elif header_footer_auditor and (not auditor or auditor == "Auditor Could Not Be Identified"):
        # No GPT result (or identification failed) but header/footer found - use it with moderate confidence
        result['auditor'] = header_footer_auditor
        result['confidence'] = 0.70
        result['validation_note'] = 'Detected from header/footer patterns (GPT extraction unsuccessful)'
        result['header_footer_only'] = True
        logging.info(f"Using header/footer detected auditor: {header_footer_auditor} (GPT extraction unsuccessful)")
    
    # GPT-only approach: if GPT didn't return an auditor, leave it as None
    save_json(result, AUDITOR_JSON_PATH)
    logging.info(f'Auditor extraction result: {result}')
    return result

def confirm_auditor_with_followup(auditor_name: str, text: str) -> Tuple[Optional[str], float, str]:
    """Send a follow-up prompt to GPT to confirm if the extracted auditor is a real SOC auditing firm, and get a revised confidence score."""
    followup_prompt = (
        f"You are an expert in SOC 2 compliance. Is '{auditor_name}' an auditing firm that provides SOC audits? "
        "Respond with a JSON object: { 'is_auditor': true/false, 'confidence': 0-1, 'explanation': '...' } "
        "If you are not sure, set 'is_auditor' to false and confidence to 0."
    )
    from ..gpt_client import gpt_extract
    response = gpt_extract(followup_prompt, 'auditor_extractor')
    try:
        if not response:
            raise ValueError('No response from GPT')
        data = json.loads(response)
        is_auditor = data.get('is_auditor', False)
        confidence = float(data.get('confidence', 0))
        explanation = data.get('explanation', '')
        if not is_auditor:
            return None, confidence, explanation
        return auditor_name, confidence, explanation
    except Exception as e:
        logging.error(f'Failed to parse follow-up GPT response: {response} | Error: {e}')
        return auditor_name, 0, 'Follow-up confirmation failed.'

def load_auditor_firms(path: Optional[str] = None):
    """Load auditor firm short and legal names from a text file."""
    if not path:
        path = os.path.join(os.path.dirname(__file__), 'auditor_firms.txt')
    firms = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('|')
            if len(parts) == 2:
                short, legal = parts
                firms.append((short.strip(), legal.strip()))
    return firms

def fallback_auditor_search(text: str) -> Optional[str]:
    """Search for known auditor firm names (including possessive forms with both straight and curly apostrophes) in the text and return the legal name of the most frequent match, or None. Logs all candidates and counts for debugging."""
    from collections import Counter
    firms = load_auditor_firms()
    found = []
    text_lower = text.lower()
    candidate_counts = {}
    for short, legal in firms:
        short_lower = short.lower()
        # Count both exact and possessive (straight and curly apostrophes)
        count = text_lower.count(short_lower)
        count += text_lower.count(f"{short_lower}'s")
        count += text_lower.count(f"{short_lower}’s")
        if count > 0:
            found.extend([legal] * count)
            candidate_counts[legal] = candidate_counts.get(legal, 0) + count
    if candidate_counts:
        logging.info(f"Fallback auditor candidates and counts: {candidate_counts}")
    if not found:
        return None
    firm_counts = Counter(found)
    most_common = firm_counts.most_common(1)[0][0]
    return most_common

__all__ = ["extract_auditor_from_report"]

if __name__ == '__main__':
    extract_auditor_from_report()
