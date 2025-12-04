# --- All imports at the top (PEP8 best practice) ---
import os
import re
import collections
from dotenv import load_dotenv
import pathlib
import sys
import unicodedata
import string
import json
from . import config
from .config import (
    SOC2_REPORTS_DIR, OUTPUT_TEXT_FILE, SECTION_TOPICS, WATERMARK_PATTERNS, REGEX_PATTERNS,
    PRIORITY_KEYWORDS_MANAGEMENT_ASSERTION, PRIORITY_KEYWORDS_SERVICE_AUDITOR_REPORT, PRIORITY_KEYWORDS_DESCRIPTION_OF_SYSTEM, PRIORITY_KEYWORDS_CONTROL_DESCRIPTIONS,
    DEFAULT_GPT_MODEL, DEFAULT_TEMPERATURE, DEFAULT_TOP_P, LLM_PROVIDER,
    SECTION_DETECTION_PROMPT, EXTRACT_TOC_PROMPT, SECTION_HEADING_VALIDATION_PROMPT, EXTRACT_TOC_HEADINGS_AND_PAGES_PROMPT
)
from .gpt_client import run_gpt_inquiry, gpt_extract
import argparse

def load_api_key():
    """Deprecated: direct OpenAI key loading is no longer used for GPT calls.
    Retained for backward compatibility with any external imports."""
    load_dotenv()
    return os.getenv('OPENAI_API_KEY')

def extract_embedded_files(input_path, output_dir):
    """
    Extract embedded/attached files from a PDF.
    Many protected PDFs embed the actual content as an attachment.
    
    Args:
        input_path: Path to the input PDF
        output_dir: Directory to save extracted files
        
    Returns:
        list: Paths to extracted PDF files (empty if none found)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        import fitz  # pymupdf
    except ImportError:
        logger.error("PyMuPDF (fitz) is required")
        return []
    
    try:
        logger.error(f"[PDF_EMBED] Checking for embedded files in: {input_path}")
        
        doc = fitz.open(input_path)
        
        # Get list of embedded files
        embedded_files = doc.embfile_names()
        
        if not embedded_files:
            logger.error(f"[PDF_EMBED] No embedded files found")
            doc.close()
            return []
        
        logger.error(f"[PDF_EMBED] Found {len(embedded_files)} embedded file(s): {embedded_files}")
        
        extracted_pdfs = []
        os.makedirs(output_dir, exist_ok=True)
        
        for file_name in embedded_files:
            try:
                # Get embedded file data
                file_data = doc.embfile_get(file_name)
                
                logger.error(f"[PDF_EMBED] Extracting embedded file ({len(file_data)} bytes)")
                
                # Sanitize filename to avoid encoding issues
                # Use a simple safe name based on index if the original has encoding issues
                try:
                    safe_name = file_name
                    # Test if filename can be used safely
                    test_path = os.path.join(output_dir, safe_name)
                except (UnicodeEncodeError, UnicodeDecodeError):
                    safe_name = f"embedded_{embedded_files.index(file_name)}.pdf"
                    logger.error(f"[PDF_EMBED] Using safe filename: {safe_name}")
                
                # Save to output directory
                output_path = os.path.join(output_dir, safe_name)
                with open(output_path, 'wb') as f:
                    f.write(file_data)
                
                logger.error(f"[PDF_EMBED] Saved to: {output_path}")
                
                # Check if it's a PDF (by extension or content)
                is_pdf = safe_name.lower().endswith('.pdf') or file_name.lower().endswith('.pdf')
                if is_pdf:
                    extracted_pdfs.append(output_path)
                    logger.error(f"[PDF_EMBED] Extracted PDF successfully")
                else:
                    logger.error(f"[PDF_EMBED] Extracted non-PDF file")
                    
            except Exception as e:
                logger.error(f"[PDF_EMBED] Failed to extract {file_name}: {e}")
        
        doc.close()
        return extracted_pdfs
        
    except Exception as e:
        logger.error(f"[PDF_EMBED] Error checking for embedded files: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


def flatten_pdf(input_path, output_path):
    """
    Attempt to unlock/flatten a PDF by removing form fields, JavaScript, and encryption.
    This tries to expose hidden content without converting to images.
    
    Args:
        input_path: Path to the input PDF
        output_path: Path to save the flattened PDF
        
    Returns:
        bool: True if successful, False otherwise
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        import fitz  # pymupdf
    except ImportError:
        logger.error("PyMuPDF (fitz) is required for PDF flattening")
        return False
    
    try:
        logger.error(f"[PDF_FLATTEN] Processing PDF: {input_path}")
        
        # Open the source PDF
        doc = fitz.open(input_path)
        
        logger.error(f"[PDF_FLATTEN] PDF has {len(doc)} pages, encrypted={doc.is_encrypted}")
        
        # Check if document is encrypted or has restrictions
        if doc.is_encrypted:
            logger.error(f"[PDF_FLATTEN] PDF is encrypted, attempting to decrypt...")
            # Try to authenticate with empty password (often works for "secured" PDFs)
            if not doc.authenticate(""):
                logger.error(f"[PDF_FLATTEN] Cannot decrypt PDF")
                doc.close()
                return False
        
        # Try removing interactive elements while preserving text
        modified = False
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Remove form fields/widgets (buttons, text fields, etc.)
            widgets = list(page.widgets())  # Convert generator to list
            if widgets:
                logger.error(f"[PDF_FLATTEN] Page {page_num + 1}: Found {len(widgets)} widgets, removing...")
                for widget in widgets:
                    page.delete_widget(widget)
                modified = True
            
            # Check for JavaScript actions
            annots = list(page.annots()) if page.annots() else []
            if annots:
                for annot in annots:
                    # Remove annotations with JavaScript actions
                    annot_info = annot.info
                    if annot_info and annot_info.get("JavaScript"):
                        logger.error(f"[PDF_FLATTEN] Page {page_num + 1}: Removing JavaScript annotation")
                        page.delete_annot(annot)
                        modified = True
        
        if modified:
            # Save the modified PDF
            doc.save(output_path, garbage=4, deflate=True, clean=True)
            logger.error(f"[PDF_FLATTEN] Saved modified PDF to: {output_path}")
        else:
            # No modifications needed, just copy
            doc.save(output_path)
            logger.error(f"[PDF_FLATTEN] No interactive elements found, saved copy to: {output_path}")
        
        doc.close()
        return True
        
    except Exception as e:
        logger.error(f"[PDF_FLATTEN] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def get_section_positions(text, model="gpt-3.5-turbo", temperature=0, top_p=1):
    """Use the configured provider (Dataiku by default) to estimate section positions."""
    prompt = SECTION_DETECTION_PROMPT.format(
        section_keys=list(SECTION_TOPICS.keys()),
        text=text[:20000]
    )
    # Route through provider adapter (no direct OpenAI calls)
    return gpt_extract(prompt, 'section_detection')

def is_watermark(line):
    for pat in WATERMARK_PATTERNS:
        if re.search(pat, line, re.IGNORECASE):
            return True
    return False

def is_legal_agreement_page(text):
    """
    Detect if a page contains legal agreement/disclaimer content that should be skipped.
    
    Common patterns in SOC report legal agreements:
    - "I Agree" / "I Do Not Agree" buttons
    - "Limits on Report Access and Distribution"
    - "NOTICE" or "CONFIDENTIAL INFORMATION" headers
    - "solely for the benefit and use of"
    - "not intended to be used by anyone other than"
    
    Args:
        text: Page text content
        
    Returns:
        bool: True if page appears to be a legal agreement/disclaimer
    """
    text_lower = text.lower()
    
    # Strong indicators (any one confirms it's an agreement page)
    strong_indicators = [
        'i agree',
        'i do not agree',
        'limits on report access and distribution',
        'solely for the benefit and use of',
        'not intended to be used by anyone other than'
    ]
    
    for indicator in strong_indicators:
        if indicator in text_lower:
            return True
    
    # Weak indicators (need multiple to confirm)
    weak_indicators = [
        ('notice', 'confidential'),
        ('recipient agrees', 'report'),
        ('ownership', 'property of'),
        ('dissemination', 'prohibited'),
        ('as is', 'sole risk')
    ]
    
    weak_indicator_count = 0
    for indicator_pair in weak_indicators:
        if all(ind in text_lower for ind in indicator_pair):
            weak_indicator_count += 1
    
    # If 2+ weak indicator pairs match, likely an agreement page
    return weak_indicator_count >= 2


def extract_text_from_pdf(pdf_path, output_path):
    """
    Extracts all text from a PDF file and writes it to a text file.
    Maintains pagination by inserting a page break marker between pages.
    Removes repetitive watermark-like patterns (dates, emails) that appear on >80% of pages.
    Automatically skips legal agreement/disclaimer pages at the beginning of the document.
    
    Uses PyMuPDF's "blocks" extraction mode for better table and multi-column layout handling.
    
    Args:
        pdf_path (str): Path to the PDF file.
        output_path (str): Path to the output text file.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        import fitz  # pymupdf
    except ImportError:
        raise ImportError("pymupdf (fitz) is required for PDF extraction. Please install it with 'pip install pymupdf'.")
    doc = fitz.open(pdf_path)
    logger.info(f"Extracting text from PDF: {pdf_path} ({len(doc)} pages)")
    
    # First pass: detect and skip legal agreement pages at the beginning
    # Only skip consecutive agreement pages from the start
    start_page = 0
    max_check_pages = min(5, len(doc))  # Only check first 5 pages for agreements
    logger.error(f"[PDF_EXTRACTION] Checking first {max_check_pages} pages for legal agreements (total pages: {len(doc)})")
    
    consecutive_agreement_pages = 0
    for page_num in range(max_check_pages):
        text = doc[page_num].get_text() or ""   # type: ignore[attr-defined]
        is_agreement = is_legal_agreement_page(text)
        logger.error(f"[PDF_EXTRACTION] Page {page_num + 1}: is_agreement={is_agreement}, text_length={len(text)}")
        if is_agreement:
            consecutive_agreement_pages += 1
        else:
            # Once we hit a non-agreement page, stop checking and use that as start
            logger.error(f"[PDF_EXTRACTION] Non-agreement page detected at page {page_num + 1}, stopping check")
            break
    
    logger.error(f"[PDF_EXTRACTION] Check complete: consecutive_agreement_pages={consecutive_agreement_pages}, max_check_pages={max_check_pages}")
    
    # Only skip pages if we found consecutive agreements from the start
    if consecutive_agreement_pages > 0 and consecutive_agreement_pages < max_check_pages:
        start_page = consecutive_agreement_pages
        logger.error(f"[PDF_EXTRACTION] Skipping {start_page} legal agreement page(s), starting extraction from page {start_page + 1}")
    elif consecutive_agreement_pages >= max_check_pages:
        # Safety check: if all checked pages are agreements, something is wrong - don't skip anything
        logger.error(f"[PDF_EXTRACTION] All checked pages appear to be agreements, not skipping any pages (possible detection error)")
        start_page = 0
    else:
        logger.error(f"[PDF_EXTRACTION] No agreement pages detected, starting from page 1")
    
    all_text = []
    page_patterns = []
    date_regex = REGEX_PATTERNS['date']
    email_regex = REGEX_PATTERNS['email']
    time_regex = REGEX_PATTERNS['time']
    
    # Collect patterns per page (only from non-skipped pages)
    for page_num in range(start_page, len(doc)):
        text = doc[page_num].get_text() or ""   # type: ignore[attr-defined]
        patterns = set()
        for regex in [date_regex, email_regex, time_regex]:
            for match in re.findall(regex, text):
                patterns.add(match.strip())
        page_patterns.append(patterns)
    # Count pattern occurrences across pages
    pattern_counter = collections.Counter()
    for patterns in page_patterns:
        pattern_counter.update(patterns)
    num_pages = len(page_patterns)
    # Identify patterns that appear on >80% of pages
    watermark_patterns = set([
        pat for pat, count in pattern_counter.items() if count / num_pages > 0.8
    ])
    # Now extract and filter text (starting from start_page)
    for i in range(start_page, len(doc)):
        # Use "text" layout mode for better date/prose handling
        # The "blocks" method can break dates across blocks, causing extraction failures
        # The "text" method preserves natural line flow and is better for continuous prose
        try:
            # Use basic text extraction (preserves natural layout)
            text = doc[i].get_text() or ""   # type: ignore[attr-defined]
        except Exception as e:
            # Fallback to empty string on error
            logger.warning(f"Page {i+1} text extraction failed: {e}")
            text = ""
        
        lines = text.splitlines()
        filtered_lines = []
        for line in lines:
            # Remove lines that match is_watermark
            if is_watermark(line):
                continue
            # Remove lines containing repetitive watermark patterns
            # BUT: Only filter if the pattern is the ENTIRE line (not part of a sentence)
            # This prevents removing legitimate content like coverage period dates
            should_filter = False
            for pat in watermark_patterns:
                # Only filter if pattern is the entire line (with optional whitespace/punctuation)
                stripped_line = line.strip().rstrip('.')
                if stripped_line == pat or stripped_line == pat.rstrip(','):
                    should_filter = True
                    break
            if should_filter:
                continue
            filtered_lines.append(line)
        # Insert page break marker (logical page numbering: starts at 1 after skipped pages)
        logical_page_num = i - start_page + 1
        all_text.append(f"=== PAGE {logical_page_num} ===")
        all_text.append('\n'.join(filtered_lines))
    # Collapse extra blank lines before writing
    output_text = '\n'.join(all_text)
    output_text = collapse_extra_blank_lines(output_text, max_blank_lines=2)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output_text)
    
    logger.info(f"PDF extraction complete: {len(output_text)} characters, {len(output_text.splitlines())} lines written to {output_path}")
    
    # Return the extracted text for use by caller
    return output_text

def collapse_extra_blank_lines(text, max_blank_lines=2):
    """
    Collapse sequences of more than `max_blank_lines` consecutive blank lines into exactly `max_blank_lines`.
    """
    import re
    # Replace 3+ consecutive blank lines with exactly 2
    pattern = r'(\n[ \t]*){' + str(max_blank_lines + 1) + ',}'
    replacement = '\n' * max_blank_lines
    return re.sub(pattern, replacement, text)

def extract_toc_with_gpt(text, model="gpt-3.5-turbo", temperature=0.0, top_p=1.0):
    """Use the configured provider to extract the TOC text. Never raises; returns '' on error."""
    prompt = EXTRACT_TOC_PROMPT.format(text=text)
    try:
        content = gpt_extract(prompt, 'extract_toc') or ""
        # --- Debug: Log raw GPT content for TOC extraction ---
        gpt_raw_log_path = str(pathlib.Path(__file__).resolve().parents[2] / 'data/logs/toc_gpt_raw_response.log')
        with open(gpt_raw_log_path, 'w', encoding='utf-8') as gpt_log:
            gpt_log.write('Raw GPT Content from extract_toc_with_gpt (provider=' + str(LLM_PROVIDER) + '):\n')
            try:
                gpt_log.write(content + '\n')
            except Exception:
                gpt_log.write('<non-text content>\n')
        return content.strip()
    except Exception as e:
        # Log and gracefully fall back to heuristic-only path
        try:
            err_log_path = str(pathlib.Path(__file__).resolve().parents[2] / 'data/logs/backend_errors.log')
            with open(err_log_path, 'a', encoding='utf-8') as logf:
                logf.write(f"\n[extract_toc_with_gpt] GPT call failed: {e}\n")
        except Exception:
            pass
        return ""

def is_incomplete_sentence(line):
    # Heuristic: incomplete if no period, question, or exclamation at end, and not too short
    line = line.strip()
    if len(line) < 5:
        return False
    return not re.search(r'[.!?]$', line)

def is_line_isolated(line, text):
    # Heuristic: appears on a line by itself (surrounded by blank lines or start/end of text)
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if l.strip() == line.strip():
            prev_blank = (i == 0) or (lines[i-1].strip() == '')
            next_blank = (i == len(lines)-1) or (lines[i+1].strip() == '')
            return prev_blank and next_blank
    return False

def gpt_validate_section_heading(line, context, model=DEFAULT_GPT_MODEL, temperature=DEFAULT_TEMPERATURE, top_p=DEFAULT_TOP_P):
    """Use the configured provider to validate section headings. Returns (is_heading, response_text)."""
    prompt = SECTION_HEADING_VALIDATION_PROMPT.format(text=context, line=line)
    try:
        content = gpt_extract(prompt, 'section_heading_validation') or ""
        content = content.strip()
        is_heading = content.lower().startswith('yes')
        return is_heading, content
    except Exception as e:
        # Fallback: rely on heuristics only
        return False, f"gpt_error:{e}"

def chunk_lines(lines, chunk_size=100, overlap=50):
    """Yield (start_line, chunk_lines) for overlapping line chunks."""
    n = len(lines)
    i = 0
    while i < n:
        yield i, lines[i:i+chunk_size]
        if i + chunk_size >= n:
            break
        i += chunk_size - overlap

def find_section_candidates_legacy(text, model=DEFAULT_GPT_MODEL, temperature=DEFAULT_TEMPERATURE, top_p=DEFAULT_TOP_P, lookahead_lines=3):
    """
    LEGACY FUNCTION - Preserved for reference.
    Enhanced: Use TOC headings and page refs, align to section topics, search for normalized/fuzzy matches in the document (with lookahead), and output detailed JSON with TOC/DOC page refs, line, offset, and snippet.
    Adds robust section end detection (by page, line, and offset) using all TOC entries as boundaries.
    """
    from rapidfuzz import fuzz
    import os
    # --- Move core_heading_norm to the top and define only once ---
    def core_heading_norm(s):
        import unicodedata
        s = unicodedata.normalize('NFKC', s)
        # Remove leading 'Section', roman numerals, numbers, and dashes (but do not remove first letter of heading)
        s = re.sub(r'^(section\s*[ivxlcdm0-9]+\s*[\-–—:]?\s*)', '', s, flags=re.IGNORECASE)
        s = re.sub(r'^[ivxlcdm]+\.?\s*', '', s, flags=re.IGNORECASE)  # Remove leading roman numerals
        s = re.sub(r'^[0-9]+\.?\s*', '', s)  # Remove leading numbers
        s = re.sub(r'^[a-zA-Z]\.\s*', '', s)  # Remove single letter section labels (must be letter + dot)
        s = re.sub(r'\s+', '', s)
        s = re.sub(r'[^\w]', '', s)
        return s.lower()
    import pathlib
    PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
    os.makedirs(PROJECT_ROOT / 'data/logs', exist_ok=True)
    gpt_log_path = str(PROJECT_ROOT / 'data/logs/section_gpt_responses.log')
    with open(gpt_log_path, 'w', encoding='utf-8') as gpt_log:
        toc_text = extract_toc_with_gpt(text[:20000], model, temperature, top_p)
        toc_lines = [line.strip() for line in toc_text.splitlines() if line.strip() and 'TOC NOT FOUND' not in line]
        toc_lines = join_multiline_toc_entries(toc_lines)
        toc_headings = extract_toc_headings_and_pages_with_gpt(toc_text, model='gpt-3.5-turbo', temperature=0.0, top_p=0.0)
        lines = text.splitlines()
        toc_page, toc_detect_method = detect_toc_page(
            lines, max_pages=5, gpt_fallback_fn=gpt_find_toc_page, model=model, temperature=temperature, top_p=top_p
        )
        print(f"[DEBUG] TOC detection method: {toc_detect_method}")
        # --- Only search for section headings after the TOC page ---
        # Use the detected TOC page and start searching at the first line of the next page
        search_start_line = 0
        found_next_page = False
        for i, line in enumerate(lines):
            if line.startswith('=== PAGE '):
                try:
                    page_num_marker = int(line.split()[2])
                    if page_num_marker == toc_page + 1:
                        search_start_line = i + 1  # Start at first line after the page marker
                        found_next_page = True
                        break
                except Exception:
                    continue
        if not found_next_page:
            search_start_line = 0  # Fallback: search from start if not found
        doc_page_offset = toc_page  # Keep doc_page_offset logic unchanged
        results = {}
        # --- Section-specific logging for troubleshooting ---
        section_log_map = {
            'Management_Assertion': str(config.LOGS_DIR / 'management_assertion.log'),
            'Service_Auditor_Report': str(config.LOGS_DIR / 'service_auditor_report.log'),
            'Description_of_System': str(config.LOGS_DIR / 'description_of_system.log'),
            'Control_Descriptions': str(config.LOGS_DIR / 'control_descriptions.log'),
        }
        # Clear section logs at the start of each run
        for log_path in section_log_map.values():
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            open(log_path, "w").close()
        # --- Debug: Log normalized TOC headings and priority keywords for each topic ---
        debug_log_path = str(PROJECT_ROOT / 'data/logs/toc_normalization_debug.log')
        with open(debug_log_path, 'w', encoding='utf-8') as debug_log:
            debug_log.write('Normalized TOC Headings:\n')
            for heading, page_ref, raw_toc in toc_headings:
                heading_norm = aggressive_normalize(heading)
                debug_log.write(f"  TOC: '{heading}' => '{heading_norm}'\n")
            debug_log.write('\n')
            for topic, keywords in SECTION_TOPICS.items():
                debug_log.write(f"Topic: {topic}\n")
                debug_log.write('  Priority Keywords (normalized):\n')
                if topic == 'Management_Assertion':
                    priority_keywords = PRIORITY_KEYWORDS_MANAGEMENT_ASSERTION
                elif topic == 'Service_Auditor_Report':
                    priority_keywords = PRIORITY_KEYWORDS_SERVICE_AUDITOR_REPORT
                elif topic == 'Description_of_System':
                    priority_keywords = PRIORITY_KEYWORDS_DESCRIPTION_OF_SYSTEM
                else:
                    priority_keywords = []
                for pk in priority_keywords:
                    pk_norm = aggressive_normalize(pk)
                    debug_log.write(f"    '{pk}' => '{pk_norm}'\n")
                debug_log.write('\n')
        # --- Debug: Log raw TOC text and parsed TOC headings ---
        toc_debug_log_path = str(PROJECT_ROOT / 'data/logs/toc_extraction_debug.log')
        with open(toc_debug_log_path, 'w', encoding='utf-8') as toc_debug_log:
            toc_debug_log.write('Raw TOC text from extract_toc_with_gpt:\n')
            toc_debug_log.write(toc_text + '\n\n')
            try:
                toc_debug_log.write('Parsed TOC headings from extract_toc_headings_and_pages_with_gpt:\n')
                for heading, page_ref, raw_toc in toc_headings:
                    toc_debug_log.write(f"  Heading: '{heading}' | Page: {page_ref} | Raw: '{raw_toc}'\n")
            except Exception as e:
                toc_debug_log.write(f"Error parsing TOC headings: {e}\n")
        for topic, keywords in SECTION_TOPICS.items():
            log_path = section_log_map.get(topic)
            # --- Collect all TOC candidates that match priority keyword logic ---
            priority_candidates = []
            for heading, page_ref, raw_toc in toc_headings:
                heading_norm = aggressive_normalize(heading)
                # Heuristic: main section if heading starts with 'Section', roman numeral, or number
                is_main_section = bool(re.match(r'^(section\s*[ivxlcdm0-9]+|[ivxlcdm0-9]+\.|\d+\.|[A-Z]\.)', heading.strip(), re.IGNORECASE))
                if topic == 'Control_Descriptions':
                    has_tsc = any(aggressive_normalize(pk) in heading_norm for pk in ['trust services criteria'])
                    has_tests = any(aggressive_normalize(pk) in heading_norm for pk in ['tests of controls', 'test of controls', 'testing of controls'])
                    if has_tsc and has_tests:
                        priority_candidates.append((heading, page_ref, raw_toc, len(heading), is_main_section))
                else:
                    if topic == 'Management_Assertion':
                        priority_keywords = PRIORITY_KEYWORDS_MANAGEMENT_ASSERTION
                    elif topic == 'Service_Auditor_Report':
                        priority_keywords = PRIORITY_KEYWORDS_SERVICE_AUDITOR_REPORT
                    elif topic == 'Description_of_System':
                        priority_keywords = PRIORITY_KEYWORDS_DESCRIPTION_OF_SYSTEM
                    else:
                        priority_keywords = []
                    if any(aggressive_normalize(pk) in heading_norm for pk in priority_keywords):
                        priority_candidates.append((heading, page_ref, raw_toc, len(heading), is_main_section))
            # --- Prefer main section candidates (with section label/number), then by length, then by page_ref ---
            best_toc = None
            best_page_ref = None
            best_raw_toc = None
            best_score = 0
            found_priority = False
            if topic == 'Service_Auditor_Report' and priority_candidates:
                # Sort by page_ref ascending
                sorted_candidates = sorted(priority_candidates, key=lambda x: (x[1] if x[1] is not None else float('inf')))
                # Look for first candidate with main keywords
                found_sa = False
                for idx, (heading, page_ref, raw_toc, length, is_main_section) in enumerate(sorted_candidates):
                    heading_norm = aggressive_normalize(heading)
                    if (
                        'independentserviceauditor' in heading_norm or
                        'serviceauditorreport' in heading_norm or
                        "serviceauditor'sreport" in heading_norm or
                        'serviceauditorsreport' in heading_norm
                    ):
                        best_toc, best_page_ref, best_raw_toc, _, _ = (heading, page_ref, raw_toc, length, is_main_section)
                        best_score = 2000
                        found_priority = True
                        found_sa = True
                        break
                if not found_sa:
                    # Fallback to previous logic (longest, then lowest page_ref)
                    main_section_candidates = [c for c in priority_candidates if c[4]]
                    candidates = main_section_candidates if main_section_candidates else priority_candidates
                    candidates.sort(key=lambda x: (-x[3], x[1] if x[1] is not None else float('inf')))
                    best_toc, best_page_ref, best_raw_toc, _, _ = candidates[0]
                    best_score = 1000
                    found_priority = True
                # Boost confidence for first 3 TOC entries/pages
                if best_page_ref is not None and best_page_ref <= 3:
                    best_score += 50
            elif priority_candidates:
                # First, filter to only main section candidates if any exist
                main_section_candidates = [c for c in priority_candidates if c[4]]
                candidates = main_section_candidates if main_section_candidates else priority_candidates
                candidates.sort(key=lambda x: (-x[3], x[1] if x[1] is not None else float('inf')))
                best_toc, best_page_ref, best_raw_toc, _, _ = candidates[0]
                best_score = 2000 if topic == 'Control_Descriptions' else 1000
                found_priority = True
            else:
                found_priority = False
                best_toc = None
                best_page_ref = None
                best_raw_toc = None
                best_score = 0
            for heading, page_ref, raw_toc in toc_headings:
                for keyword in keywords:
                    score = fuzz.ratio(keyword.lower(), heading.lower())
                    if score > best_score:
                        best_score = score
                        best_toc = heading
                        best_page_ref = page_ref
                        best_raw_toc = raw_toc
            found = False
            found_line = None
            found_page = None
            found_heading = None
            found_offset = None
            found_snippet = None
            best_confidence = 0
            best_candidate = None
            best_candidate_line = None
            best_candidate_page = None
            best_candidate_offset = None
            best_candidate_snippet = None
            best_candidate_reason = None
            if best_toc:
                heading_core = core_heading_norm(best_toc)
                # Extract section number if present (e.g., 'SECTION 1', 'SECTION 3')
                section_num_match = re.search(r'SECTION\s*([0-9]+)', best_toc, re.IGNORECASE)
                expected_section_num = section_num_match.group(1) if section_num_match else None
            else:
                heading_core = None
                expected_section_num = None
            expected_doc_page = None
            if best_page_ref is not None and toc_page is not None:
                expected_doc_page = best_page_ref + toc_page
                search_pages = {expected_doc_page - 1, expected_doc_page, expected_doc_page + 1}
            else:
                search_pages = set()
            for i in range(search_start_line, len(lines)):
                candidate_page = get_page_for_line(lines, i)
                if candidate_page <= toc_page:
                    continue
                if search_pages and candidate_page not in search_pages:
                    continue
                for n in range(1, lookahead_lines+1):
                    joined_lines = []
                    j = i
                    while j < len(lines) and len(joined_lines) < n:
                        line = lines[j].strip()
                        if is_page_number_line(line):
                            j += 1
                            continue
                        joined_lines.append(line)
                        j += 1
                    if not joined_lines:
                        continue
                    candidate = ' '.join(joined_lines)
                    candidate_core = core_heading_norm(candidate)
                    if heading_core:
                        fuzzy_score = fuzz.ratio(heading_core, candidate_core)
                    else:
                        fuzzy_score = 0
                    threshold = 85
                    # Disabled: logging each candidate to reduce log file size
                    # if fuzzy_score > 70:
                    #     logf.write(f"[CANDIDATE] Topic: {topic} | i: {i} | n: {n} | candidate: '{candidate}' | candidate_core: '{candidate_core}' | heading_core: '{heading_core}' | fuzzy_score: {fuzzy_score}\n")
                    if fuzzy_score > threshold:
                        confidence = fuzzy_score
                        if expected_doc_page is not None and candidate_page == expected_doc_page:
                            confidence += 5
                        if candidate_core == heading_core:
                            confidence += 5
                        if heading_core and candidate_core:
                            if not candidate_core.startswith(heading_core) and not candidate_core.endswith(heading_core):
                                confidence -= 2
                        if confidence > best_confidence:
                            best_confidence = confidence
                            best_candidate = candidate
                            best_candidate_line = i+1
                            best_candidate_page = candidate_page
                            best_candidate_offset = sum(len(l)+1 for l in lines[:i])
                            best_candidate_snippet = '\n'.join(lines[max(0, i-3):i+4])
                            best_candidate_reason = f'Rapidfuzz match (score={fuzzy_score})'
                if best_confidence >= 100:
                    break
            # --- Prefer exact/near-exact normalized match for section heading for all main sections ---
            best_exact_line = None
            best_exact_page = None
            best_exact_offset = None
            best_exact_snippet = None
            max_heading_lines = 12  # Increase to match multi-line headings robustly
            for i in range(search_start_line, len(lines)):
                for n in range(1, max_heading_lines+1):
                    joined_lines = []
                    j = i
                    while j < len(lines) and len(joined_lines) < n:
                        line = lines[j].strip()
                        if is_page_number_line(line) or not line:
                            j += 1
                            continue
                        joined_lines.append(line)
                        j += 1
                    if not joined_lines:
                        continue
                    candidate_joined = ' '.join(joined_lines)
                    candidate_core = core_heading_norm(candidate_joined)
                    # Disabled: logging each candidate for exact match to reduce log file size
                    # if log_path:
                    #     with open(log_path, "a", encoding="utf-8") as logf:
                    #         logf.write(f"[EXACT] Topic: {topic} | i: {i} | n: {n} | candidate_joined: '{candidate_joined}' | candidate_core: '{candidate_core}' | heading_core: '{heading_core}'\n")
                    if heading_core and candidate_core == heading_core:
                        best_exact_line = i + 1
                        best_exact_page = get_page_for_line(lines, i)
                        best_exact_offset = sum(len(l)+1 for l in lines[:i])
                        best_exact_snippet = '\n'.join(lines[max(0, i-3):i+4])
                        break
                if best_exact_line is not None:
                    break
            if best_exact_line is not None and (not found or best_confidence < 100):
                found = True
                best_candidate = lines[best_exact_line-1].strip()
                best_candidate_line = best_exact_line
                best_candidate_page = best_exact_page
                best_candidate_offset = best_exact_offset
                best_candidate_snippet = best_exact_snippet
                best_candidate_reason = 'Exact normalized heading match (multi-line)'
                best_confidence = 110
            # --- Fallback: fuzzy match for all main sections if still not found ---
            threshold = 85  # Ensure threshold is always defined for fuzzy match
            if not found:
                max_fuzzy = 0
                best_fuzzy_line = None
                best_fuzzy_page = None
                best_fuzzy_offset = None
                best_fuzzy_snippet = None
                for i in range(search_start_line, len(lines)):
                    for n in range(1, max_heading_lines+1):
                        joined_lines = []
                        j = i
                        while j < len(lines) and len(joined_lines) < n:
                            line = lines[j].strip()
                            if is_page_number_line(line) or not line:
                                j += 1
                                continue
                            joined_lines.append(line)
                            j += 1
                        if not joined_lines:
                            continue
                        candidate_joined = ' '.join(joined_lines)
                        candidate_core = core_heading_norm(candidate_joined)
                        if heading_core:
                            fuzzy_score = fuzz.ratio(heading_core, candidate_core)
                        else:
                            fuzzy_score = 0
                        if fuzzy_score > max_fuzzy:
                            max_fuzzy = fuzzy_score
                            best_fuzzy_line = i + 1
                            best_fuzzy_page = get_page_for_line(lines, i)
                            best_fuzzy_offset = sum(len(l)+1 for l in lines[:i])
                            best_fuzzy_snippet = '\n'.join(lines[max(0, i-3):i+4])
                if best_fuzzy_line is not None and max_fuzzy > threshold:
                    found = True
                    best_candidate = lines[best_fuzzy_line-1].strip()
                    best_candidate_line = best_fuzzy_line
                    best_candidate_page = best_fuzzy_page
                    best_candidate_offset = best_fuzzy_offset
                    best_candidate_snippet = best_fuzzy_snippet
                    best_candidate_reason = f'Fuzzy match (score={max_fuzzy})'
                    best_confidence = max_fuzzy
            # --- Always use page_offset for DOC_page_ref calculation ---
            if best_page_ref is not None and toc_page is not None:
                doc_page_ref = best_page_ref + toc_page
            elif found_page is not None:
                doc_page_ref = found_page
            else:
                doc_page_ref = best_page_ref
            toc_page_ref = best_page_ref
            section_level = 'first' if is_main_section_heading(best_toc or '') else 'subsection'
            results[topic] = {
                'topic': topic,
                'clean_heading': best_toc.strip() if best_toc else None,
                'TOC_page_ref': toc_page_ref,
                'DOC_page_ref': doc_page_ref,
                'start_line': best_candidate_line if found else None,
                'confidence': best_confidence if found else 0,
                'gpt_reason': best_candidate_reason if found else 'Not found',
                'offset': best_candidate_offset if found else None,
                'snippet': best_candidate_snippet if found else None,
                'type': 'mapped',
                'level': section_level
            }
            # --- Section-specific logging for troubleshooting ---
            section_log_map = {
                'Management_Assertion': str(config.LOGS_DIR / 'management_assertion.log'),
                'Service_Auditor_Report': str(config.LOGS_DIR / 'service_auditor_report.log'),
                'Description_of_System': str(config.LOGS_DIR / 'description_of_system.log'),
                'Control_Descriptions': str(config.LOGS_DIR / 'control_descriptions.log'),
            }
            log_path = section_log_map.get(topic)
            if log_path:
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                with open(log_path, "a", encoding="utf-8") as logf:
                    logf.write(f"Section: {topic}\n")
                    logf.write(f"Found: {found}\n")
                    logf.write(f"Best candidate: {best_candidate}\n")
                    logf.write(f"Best candidate line: {best_candidate_line}\n")
                    logf.write(f"Best candidate page: {best_candidate_page}\n")
                    logf.write(f"Best candidate reason: {best_candidate_reason}\n")
                    logf.write(f"Best confidence: {best_confidence}\n")
                    logf.write(f"TOC heading: {best_toc}\n")
                    logf.write(f"TOC page ref: {best_page_ref}\n")
                    logf.write(f"TOC raw: {best_raw_toc}\n")
                    logf.write(f"---\n")
    # --- Section END detection logic using mapped section starts ---
    section_list = list(results.values())
    def safe(x, key):
        v = x.get(key)
        return v if v is not None else float('inf')
    section_list.sort(key=lambda x: (safe(x, 'DOC_page_ref'), safe(x, 'start_line'), safe(x, 'offset')))

    # --- Add unmapped TOC entries as 'other' sections ---
    mapped_toc_page_refs = set(s['TOC_page_ref'] for s in section_list if s.get('TOC_page_ref') is not None)
    last_section_end_line = max([s.get('end_line', 0) for s in section_list] or [0])
    # Find the first line after the TOC page marker
    toc_search_start_line = 0
    found_next_page = False
    for i, line in enumerate(lines):
        if line.startswith('=== PAGE '):
            try:
                page_num_marker = int(line.split()[2])
                if page_num_marker == toc_page + 1:
                    toc_search_start_line = i + 1
                    found_next_page = True
                    break
            except Exception:
                continue
    if not found_next_page:
        toc_search_start_line = 0  # fallback
    for heading, page_ref, raw_toc in toc_headings:
        heading_stripped = heading.strip().lower()
        if heading_stripped.startswith('table of') or heading_stripped in ['table of contents', 'contents', 'toc', 'table of content', 'the table of contents']:
            continue
        if page_ref not in mapped_toc_page_refs:
            doc_page_ref = page_ref + toc_page if page_ref is not None and toc_page is not None else page_ref
            # Normalize the clean_heading for robust matching (remove punctuation, whitespace, etc.)
            import string
            def normalize_heading(s):
                s = s.lower()
                s = s.replace('\u2019', "'")  # normalize curly apostrophes
                s = s.replace('\u201c', '"').replace('\u201d', '"')
                s = s.replace('\u2013', '-').replace('\u2014', '-')
                s = s.translate(str.maketrans('', '', string.punctuation))
                s = ''.join(s.split())
                return s
            heading_norm = normalize_heading(heading)
            found_line = None
            max_heading_lines = 8
            i = toc_search_start_line
            while i < len(lines):
                # If this is a page marker, skip to the next non-page-number, non-blank line
                if lines[i].strip().startswith('=== PAGE'):
                    j = i + 1
                    # Skip page number
                    while j < len(lines) and (lines[j].strip() == '' or lines[j].strip().isdigit()):
                        j += 1
                    # Now try to join up to max_heading_lines lines from here
                    for n in range(1, max_heading_lines+1):
                        joined_lines = []
                        k = j
                        while k < len(lines) and len(joined_lines) < n:
                            joined_lines.append(lines[k].strip())
                            k += 1
                        if not joined_lines:
                            continue
                        candidate = ' '.join(joined_lines)
                        candidate_norm = normalize_heading(candidate)
                        if heading_norm == candidate_norm:
                            found_line = j + 1  # first line of heading
                            break
                    if found_line is not None:
                        break
                    i = j
                    continue
                # Otherwise, try joining from this line
                for n in range(1, max_heading_lines+1):
                    joined_lines = []
                    j = i
                    while j < len(lines) and len(joined_lines) < n:
                        joined_lines.append(lines[j].strip())
                        j += 1
                    if not joined_lines:
                        continue
                    candidate = ' '.join(joined_lines)
                    candidate_norm = normalize_heading(candidate)
                    if heading_norm == candidate_norm:
                        found_line = i + 1
                        break
                if found_line is not None:
                    break
                i += 1
            # If not found, set to after last mapped section's end_line
            if found_line is None:
                found_line = last_section_end_line + 1
            # Ensure found_line is never less than last_section_end_line + 1
            if found_line <= last_section_end_line:
                found_line = last_section_end_line + 1
            # Determine level for 'other' sections: treat as 'first' if it looks like a main section, else 'subsection'
            other_level = 'first' if is_main_section_heading(heading) else 'subsection'
            section_list.append({
                'topic': None,
                'clean_heading': heading.strip(),
                'TOC_page_ref': page_ref,
                'DOC_page_ref': doc_page_ref,
                'start_line': found_line,
                'confidence': 0,
                'gpt_reason': 'Unmapped TOC entry',
                'offset': 0,
                'snippet': '',
                'type': 'other',
                'level': other_level
            })
            last_section_end_line = found_line
    for section in section_list:
        if section.get('start_line') is None:
            section['start_line'] = 0
        if section.get('offset') is None:
            section['offset'] = 0
        if section.get('snippet') is None:
            section['snippet'] = ''
    section_list.sort(key=lambda x: (safe(x, 'DOC_page_ref'), safe(x, 'start_line'), safe(x, 'offset')))

    # --- Identify main and 'other' sections for boundary assignment ---
    def is_main_or_other_section(section):
        return section.get('level') == 'first' and section.get('type') in ['mapped', 'other']
    main_or_other_sections = [s for s in section_list if is_main_or_other_section(s)]
    main_or_other_sections.sort(key=lambda x: (safe(x, 'DOC_page_ref'), safe(x, 'start_line'), safe(x, 'offset')))

    # --- Assign ends for all mapped sections (not just main/other) ---
    for idx, section in enumerate(section_list):
        # Find the next section (mapped or unmapped) in document order
        next_section = section_list[idx+1] if idx+1 < len(section_list) else None
        section_doc_page_ref = section.get('DOC_page_ref') if section.get('DOC_page_ref') is not None else None
        if next_section and next_section.get('DOC_page_ref') is not None:
            section['end_DOC_page_ref'] = max((next_section['DOC_page_ref'] - 1), section_doc_page_ref or 1)
        elif section_doc_page_ref is not None:
            section['end_DOC_page_ref'] = section_doc_page_ref
        else:
            # fallback: use last page in document
            last_page = 1
            for i in range(len(lines)):
                if lines[i].startswith('=== PAGE '):
                    try:
                        last_page = int(lines[i].split()[2])
                    except Exception:
                        continue
            section['end_DOC_page_ref'] = last_page
        section['end_line'] = (next_section.get('start_line') or section.get('start_line') or len(lines)) - 1 if next_section else len(lines)
        if section.get('start_line') is not None and section['end_line'] < section['start_line']:
            section['end_line'] = section['start_line']
        section['end_offset'] = (next_section.get('offset') or section.get('offset') or sum(len(l)+1 for l in lines)) - 1 if next_section else sum(len(l)+1 for l in lines)
        if section.get('offset') is not None and section['end_offset'] < section['offset']:
            section['end_offset'] = section['offset']
    section_results = section_list
    # Output as a list in document order (with all end_ fields)
    # --- Clamp DOC_page_ref and end_DOC_page_ref to total number of pages ---
    # Find total number of pages
    total_pages = 1
    for line in lines:
        if line.startswith('=== PAGE '):
            try:
                page_num = int(line.split()[2])
                if page_num > total_pages:
                    total_pages = page_num
            except Exception:
                continue
    for section in section_list:
        if section.get('DOC_page_ref') is not None and section['DOC_page_ref'] > total_pages:
            section['DOC_page_ref'] = total_pages
        if section.get('end_DOC_page_ref') is not None and section['end_DOC_page_ref'] > total_pages:
            section['end_DOC_page_ref'] = total_pages
    # --- Ensure last section ends at the true end of the document ---
    if section_list:
        last_section = section_list[-1]
        last_section['end_DOC_page_ref'] = total_pages
        last_section['end_line'] = len(lines)
        last_section['end_offset'] = sum(len(l)+1 for l in lines)
    return section_list


def find_section_candidates(text, model=DEFAULT_GPT_MODEL, temperature=DEFAULT_TEMPERATURE, top_p=DEFAULT_TOP_P, lookahead_lines=3):
    """
    GPT-based section identification with confidence scoring and retry logic.
    
    Extracts first 10 pages, uses GPT to identify sections with confidence scores.
    If confidence < 80%, retries with first 20 pages (if token budget allows).
    Returns list of sections compatible with existing section_results.json format.
    
    Raises:
        Exception with user-friendly message if confidence remains < 80% after retry.
    """
    import pathlib
    import json
    
    PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
    os.makedirs(PROJECT_ROOT / 'data/logs', exist_ok=True)
    
    lines = text.splitlines()
    
    def extract_pages(text_lines, max_pages):
        """Extract text up to max_pages from document."""
        page_count = 0
        extracted_lines = []
        for line in text_lines:
            extracted_lines.append(line)
            if line.startswith('=== PAGE '):
                page_count += 1
                if page_count >= max_pages:
                    break
        return '\n'.join(extracted_lines)
    
    def estimate_tokens(text_content):
        """Rough token estimation: character count / 4."""
        return len(text_content) // 4
    
    def parse_gpt_response(gpt_content):
        """Parse GPT JSON response, handling markdown code blocks."""
        # Remove markdown code blocks if present
        content = gpt_content.strip()
        if content.startswith('```'):
            # Remove opening ```json or ```
            content = re.sub(r'^```(?:json)?\s*\n', '', content)
            # Remove closing ```
            content = re.sub(r'\n```\s*$', '', content)
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse GPT response as JSON: {e}\n{content[:500]}")
    
    def convert_to_legacy_format(gpt_result, text_lines):
        """Convert GPT section identification to legacy section_results.json format."""
        import logging
        logger = logging.getLogger(__name__)
        
        sections_list = []
        
        gpt_sections = gpt_result.get('sections', [])
        controls_section_name = gpt_result.get('controls_section_name', '')
        system_desc_section_name = gpt_result.get('system_description_section_name', '')
        
        # Find total number of pages
        total_pages = 1
        for line in text_lines:
            if line.startswith('=== PAGE '):
                try:
                    page_num = int(line.split()[2])
                    if page_num > total_pages:
                        total_pages = page_num
                except Exception:
                    continue
        
        # Convert each GPT section to legacy format
        for i, gpt_sec in enumerate(gpt_sections):
            section_name = gpt_sec.get('name', '')
            toc_page = gpt_sec.get('toc_page')
            doc_page = gpt_sec.get('doc_page')
            confidence = gpt_sec.get('confidence', 0)
            
            # Fallback: if toc_page missing, use doc_page for both
            if toc_page is None:
                toc_page = doc_page if doc_page else 1
            if doc_page is None:
                doc_page = toc_page if toc_page else 1
            
            # Validate and log significant offsets
            offset_diff = abs(doc_page - toc_page)
            if offset_diff > 10:
                logger.warning(f"[SECTION_DETECT] Large page offset detected for '{section_name}': TOC={toc_page}, DOC={doc_page}, offset={offset_diff}")
            
            start_page = doc_page  # Use DOC page for line/offset calculations
            
            # Determine topic mapping based on GPT's explicit identification first
            section_lower = section_name.lower()
            if controls_section_name and section_name == controls_section_name:
                # GPT explicitly identified this as the controls section
                topic = 'Control_Descriptions'
            elif system_desc_section_name and section_name == system_desc_section_name:
                # GPT explicitly identified this as the system description
                topic = 'Description_of_System'
            elif 'auditor' in section_lower and 'report' in section_lower:
                topic = 'Service_Auditor_Report'
            elif 'management' in section_lower and ('assertion' in section_lower or 'statement' in section_lower):
                topic = 'Management_Assertion'
            elif 'description' in section_lower and 'system' in section_lower:
                topic = 'Description_of_System'
            elif 'control' in section_lower:
                topic = 'Control_Descriptions'
            else:
                topic = 'Unknown'
            
            # Find start line for this page
            start_line = 0
            for idx, line in enumerate(text_lines):
                if line.startswith(f'=== PAGE {start_page} ==='):
                    start_line = idx + 1
                    break
            
            # Calculate offset
            offset = sum(len(l) + 1 for l in text_lines[:start_line])
            
            # Get snippet
            snippet_lines = text_lines[start_line:start_line+5]
            snippet = '\n'.join(snippet_lines)[:300]
            
            # Determine end boundaries (next section or document end)
            if i + 1 < len(gpt_sections):
                next_doc_page = gpt_sections[i+1].get('doc_page')
                next_toc_page = gpt_sections[i+1].get('toc_page')
                # Use doc_page from next section, fallback to toc_page if null
                end_page = next_doc_page if next_doc_page else (next_toc_page if next_toc_page else total_pages)
                # Find end line
                end_line = len(text_lines)
                for idx, line in enumerate(text_lines[start_line:], start_line):
                    if line.startswith(f'=== PAGE {end_page} ==='):
                        end_line = idx
                        break
            else:
                end_page = total_pages
                end_line = len(text_lines)
            
            end_offset = sum(len(l) + 1 for l in text_lines[:end_line])
            
            # Calculate end_TOC_page_ref by maintaining the same offset
            page_offset = doc_page - toc_page
            end_toc_page = end_page - page_offset
            
            section_dict = {
                'topic': topic,
                'clean_heading': section_name,
                'TOC_page_ref': toc_page,
                'DOC_page_ref': doc_page,
                'start_line': start_line,
                'confidence': confidence,
                'gpt_reason': 'GPT section identification',
                'offset': offset,
                'snippet': snippet,
                'type': 'mapped',
                'level': 'section',
                'end_TOC_page_ref': end_toc_page,
                'end_DOC_page_ref': end_page,
                'end_line': end_line,
                'end_offset': end_offset
            }
            
            sections_list.append(section_dict)
        
        return sections_list
    
    # Attempt 1: Extract first 15 pages
    extracted_text_15 = extract_pages(lines, max_pages=15)
    token_count_15 = estimate_tokens(extracted_text_15)
    
    log_path = PROJECT_ROOT / 'data/logs/section_identification.log'
    with open(log_path, 'w', encoding='utf-8') as log_file:
        log_file.write(f"=== Section Identification Attempt 1 (15 pages, ~{token_count_15} tokens) ===\n\n")
        
        try:
            prompt = config.SECTION_IDENTIFICATION_PROMPT.format(text=extracted_text_15)
            gpt_response = gpt_extract(prompt, 'section_identification')
            
            log_file.write(f"GPT Response:\n{gpt_response}\n\n")
            
            result = parse_gpt_response(gpt_response)
            overall_confidence = result.get('overall_confidence', 0)
            
            log_file.write(f"Overall Confidence: {overall_confidence}\n")
            log_file.write(f"Sections Found: {len(result.get('sections', []))}\n")
            
            if overall_confidence >= 80:
                log_file.write("\n✓ Confidence threshold met (>=80), using results.\n")
                return convert_to_legacy_format(result, lines)
            
            # Low confidence - attempt retry with more pages
            log_file.write(f"\n⚠ Low confidence ({overall_confidence}%), attempting retry with 20 pages...\n")
            
        except Exception as e:
            log_file.write(f"\n✗ Error in first attempt: {e}\n")
            log_file.write("Attempting retry with 20 pages...\n")
    
    # Attempt 2: Extract first 20 pages
    extracted_text_20 = extract_pages(lines, max_pages=20)
    token_count_20 = estimate_tokens(extracted_text_20)
    
    with open(log_path, 'a', encoding='utf-8') as log_file:
        log_file.write(f"\n=== Section Identification Attempt 2 (20 pages, ~{token_count_20} tokens) ===\n\n")
        
        # Check token budget (rough limit: 7500 tokens for GPT-3.5)
        if token_count_20 > 7500:
            log_file.write(f"⚠ Token count ({token_count_20}) exceeds budget (7500), truncating...\n")
            # Truncate to approximately 30,000 characters (7500 tokens)
            extracted_text_20 = extracted_text_20[:30000]
            token_count_20 = 7500
        
        try:
            prompt = config.SECTION_IDENTIFICATION_PROMPT.format(text=extracted_text_20)
            gpt_response = gpt_extract(prompt, 'section_identification')
            
            log_file.write(f"GPT Response:\n{gpt_response}\n\n")
            
            result = parse_gpt_response(gpt_response)
            overall_confidence = result.get('overall_confidence', 0)
            
            log_file.write(f"Overall Confidence: {overall_confidence}\n")
            log_file.write(f"Sections Found: {len(result.get('sections', []))}\n")
            
            if overall_confidence >= 80:
                log_file.write("\n✓ Confidence threshold met (>=80), using results.\n")
                return convert_to_legacy_format(result, lines)
            
            # Still low confidence after retry
            log_file.write(f"\n✗ Confidence still below threshold ({overall_confidence}%) after retry.\n")
            raise Exception(
                f"Unable to reliably identify report sections (confidence {overall_confidence}% < 80%). "
                "Please ensure this is a standard SOC 1 or SOC 2 report."
            )
            
        except json.JSONDecodeError as e:
            log_file.write(f"\n✗ Failed to parse GPT response: {e}\n")
            raise Exception(
                "Failed to parse section identification response. "
                "Please ensure this is a standard SOC 1 or SOC 2 report."
            )
        except Exception as e:
            log_file.write(f"\n✗ Error in second attempt: {e}\n")
            # Re-raise if it's our confidence error
            if "Unable to reliably identify" in str(e):
                raise
            # Otherwise wrap in user-friendly message
            raise Exception(
                f"Section identification failed: {str(e)}. "
                "Please ensure this is a standard SOC 1 or SOC 2 report."
            )


def clean_toc_heading(heading):
    """Remove trailing spaces, dots, and normalize whitespace from a TOC heading."""
    # Remove trailing dots and spaces
    heading = re.sub(r'[.\s]+$', '', heading)
    # Collapse multiple spaces
    heading = re.sub(r'\s+', ' ', heading)
    return heading.strip()

def get_page_for_line(lines, line_num):
    """Given a list of lines and a line number, return the page number (1-based) for that line, using the page break markers."""
    page = 1
    for i in range(min(line_num, len(lines))):
        if lines[i].startswith('=== PAGE '):
            try:
                page = int(lines[i].split()[2])
            except Exception:
                continue
    return page

def extract_toc_headings_and_pages(toc_lines):
    """Extract (heading, page_ref) pairs from TOC lines using regex. Ensures each entry is a single section, even if multiple are on one line."""
    import re
    results = []
    # Regex to match multiple (heading, page number) pairs in a line
    # Example: 'SECTION 2 ... 5 SECTION 3 ... 7' -> [('SECTION 2 ...', 5), ('SECTION 3 ...', 7)]
    # This regex matches: (heading text)(page number)
    entry_re = re.compile(r'(.*?)(\d{1,4})\s*(?=(?:SECTION|[IVXLC0-9]+\.|\d+\.|[A-Z]\.|$))', re.IGNORECASE)
    for line in toc_lines:
        line = line.strip()
        if not line:
            continue
        matches = list(entry_re.finditer(line))
        if matches:
            for m in matches:
                heading = m.group(1).strip(' .')
                page_ref = int(m.group(2))
                raw = m.group(0).strip()
                if heading:
                    results.append((heading, page_ref, raw))
        else:
            # If no page number, add as is
            if line:
                results.append((line, None, line))
    return results

def extract_toc_headings_and_pages_with_gpt(toc_text, model='gpt-3.5-turbo', temperature=0.0, top_p=0.0):
    """Use the configured provider to extract (heading, page_ref) pairs from TOC text."""
    prompt = EXTRACT_TOC_HEADINGS_AND_PAGES_PROMPT.format(toc_text=toc_text)
    try:
        content = gpt_extract(prompt, 'extract_toc_headings_and_pages') or "[]"
        try:
            toc_list = json.loads(content)
            results = [(entry.get('heading'), entry.get('page'), entry.get('heading')) for entry in toc_list if isinstance(entry, dict)]
            # Filter out entries without heading
            return [(h, p, r) for (h, p, r) in results if h]
        except Exception:
            return []
    except Exception:
        # Graceful fallback to regex-only extraction if GPT fails
        try:
            toc_lines = [line.strip() for line in toc_text.splitlines() if line.strip()]
            return extract_toc_headings_and_pages(toc_lines)
        except Exception:
            return []

def detect_toc_page(lines, max_pages=5, gpt_fallback_fn=None, model=DEFAULT_GPT_MODEL, temperature=DEFAULT_TEMPERATURE, top_p=DEFAULT_TOP_P):
    """
    Robustly detect the TOC page number in the first `max_pages` pages.
    Handles:
      - 'Table of Contents' (single line, any case)
      - 'Table', 'of', 'Contents' on consecutive lines (allowing blank lines)
      - 'Contents' as a heading
    Optionally uses GPT fallback if not found.
    Returns: (toc_page_num, detection_method)
    """
    page_indices = []
    for i, line in enumerate(lines):
        if line.startswith('=== PAGE '):
            try:
                page_num = int(line.split()[2])
                page_indices.append((page_num, i))
            except Exception:
                continue
    # Only scan first N pages
    scan_limit = page_indices[min(max_pages, len(page_indices))-1][1] if page_indices else len(lines)
    i = 0
    while i < scan_limit:
        line = lines[i].strip().lower()
        print(f"[DEBUG] Checking line {i}: '{line}'")  # Debug log
        # Single-line 'table of contents'
        if 'table of contents' in line:
            print(f"[DEBUG] Single-line TOC detected at line {i}")  # Debug log
            return get_page_for_line(lines, i), 'single-line'
        # Single-line 'contents' as heading
        if line == 'contents':
            print(f"[DEBUG] Single-line 'contents' detected at line {i}")  # Debug log
            return get_page_for_line(lines, i), 'contents-alone'
        # Multi-line: 'table', 'of', 'contents' (allow blank lines)
        if line == 'table':
            j = i + 1
            while j < scan_limit and not lines[j].strip():
                j += 1
            if j < scan_limit and lines[j].strip().lower() == 'of':
                k = j + 1
                while k < scan_limit and not lines[k].strip():
                    k += 1
                if k < scan_limit and lines[k].strip().lower() == 'contents':
                    print(f"[DEBUG] Multi-line TOC detected starting at line {i}")  # Debug log
                    return get_page_for_line(lines, i), 'multi-line'
        i += 1
    # Fallback: use GPT if provided
    if gpt_fallback_fn is not None:
        toc_page = gpt_fallback_fn(lines, max_pages, model, temperature, top_p)
        if toc_page:
            print(f"[DEBUG] GPT fallback TOC detected at page {toc_page}")  # Debug log
            return toc_page, 'gpt-fallback'
    print("[DEBUG] TOC not found, defaulting to page 1")  # Debug log
    return 1, 'not-found'

def gpt_find_toc_page(lines, max_pages, model, temperature, top_p):
    """Use the configured provider to find the TOC page in the first `max_pages` pages."""
    text = []
    page_count = 0
    for line in lines:
        if line.startswith('=== PAGE '):
            page_count += 1
            if page_count > max_pages:
                break
        text.append(line)
    # Build a self-contained prompt (avoid missing config entries)
    prompt = (
        "You are analyzing the first {max_pages} pages of a report. "
        "Determine the page number (1-based) where the Table of Contents begins. "
        "Respond ONLY with a single integer (the page number). If not found, respond with 'null'.\n\n"
        "Text:\n{body}"
    ).format(max_pages=max_pages, body='\n'.join(text))
    try:
        content = (gpt_extract(prompt, 'find_toc_page') or "").strip()
        # Accept plain integer or JSON null-like
        if content.lower() == 'null':
            return None
        m = re.search(r"\d+", content)
        if m:
            return int(m.group(0))
        return None
    except Exception:
        return None

def is_toc_entry_start(line):
    """Heuristic: Returns True if the line looks like the start of a new TOC entry (main or sub)."""
    # Typical TOC entry: starts with capital letter, may have dots, ends with a page number
    # e.g., 'Section III – Description of System ............................................. 7'
    # or 'Company Background ............................................................. 8'
    # Accepts lines that end with a number (page number)
    line = line.strip()
    if not line:
        return False
    # Ends with a page number
    if re.search(r'(\.{2,}|\s)\d{1,4}$', line):
        return True
    # Or just a number at the end
    if re.search(r'\d{1,4}$', line) and line[0].isupper():
        return True
    # Or starts with 'Section', roman numeral, number, or multi-level number
    if re.match(r'^(section\s*[ivxlcdm0-9]+|[ivxlcdm0-9]+\.|\d+(\.\d+)*\.?|[A-Z]\.)', line, re.IGNORECASE):
        return True
    return False

def join_multiline_toc_entries(lines, debug_log_path=None):
    import pathlib
    PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
    if debug_log_path is None:
        debug_log_path = str(PROJECT_ROOT / 'data/logs/toc_join_debug.log')
    """Join TOC lines into full headings, joining all consecutive lines after a main section heading until a new TOC entry is detected. This robustly reconstructs split main headings, regardless of line content. Sub-entries remain single lines. Logs joined TOC entries for debugging."""
    toc = []
    buffer = []
    os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
    debug_log = open(debug_log_path, 'w', encoding='utf-8')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or is_toc_label(line):
            i += 1
            continue
        # If this line starts a main section heading, join all following lines until a new TOC entry is detected
        if is_main_section_heading(line):
            buffer = [line]
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line or is_toc_label(next_line) or is_toc_entry_start(next_line):
                    break
                buffer.append(next_line)
                j += 1
            toc_entry = " ".join(buffer).strip()
            toc.append(toc_entry)
            debug_log.write(f"[TOC-ENTRY] {toc_entry}\n")
            i = j
        else:
            # Sub-entry or orphaned line, treat as single line
            toc.append(line)
            debug_log.write(f"[TOC-ENTRY] {line}\n")
            i += 1
    debug_log.close()
    return toc

def is_toc_label(line):
    """Return True if the line is a TOC label (e.g., 'Table of Contents', 'Contents', 'TOC'), or a partial TOC title (e.g., 'Table', 'of', 'Table of', 'of Contents'), ignoring case and whitespace."""
    import re
    toc_labels = [
        r"^table\s*of\s*contents$",
        r"^contents$",
        r"^toc$",
        r"^table\s*of\s*content$",
        r"^the\s*table\s*of\s*contents$",
        r"^table$",
        r"^of$",
        r"^of\s*contents$",
        r"^table\s*$",
        r"^of\s*$",
        r"^contents\s*$",
        r"^table of$",  # Add this pattern to match 'TABLE OF' exactly
    ]
    s = line.strip().lower()
    for pat in toc_labels:
        if re.match(pat, s, re.IGNORECASE):
            return True
    return False

# --- Identify main section headings (with section label/number) ---
def is_main_section_heading(heading):
    """Return True if the heading looks like a main section heading in a SOC 2 TOC.
    Matches lines starting with 'Section' (case-insensitive), possibly with whitespace, dashes, or punctuation after the section number.
    Also matches lines that are all uppercase and long enough (>=40 chars), to catch stylized main headings.
    """
    s = heading.strip()
    # Match 'Section' + roman numeral/number + dash/en-dash/em-dash + text
    if re.match(r'^(section\s*[ivxlcdm0-9]+\s*[-–—]?)', s, re.IGNORECASE):
        return True
    # Match 'Section' + roman numeral/number + any text
    if re.match(r'^(section\s*[ivxlcdm0-9]+)', s, re.IGNORECASE):
        return True
    # Match all uppercase, long lines (stylized headings)
    if len(s) >= 40 and s == s.upper():
        return True
    # Optionally: match lines that start with a number and a dash (e.g., '1 - Introduction')
    if re.match(r'^[ivxlcdm0-9]+\s*[-–—]', s, re.IGNORECASE):
        return True
    return False

def aggressive_normalize(s):
    import unicodedata
    s = unicodedata.normalize('NFKC', s)
    s = re.sub(r'\s+', '', s)
    s = re.sub(r'[^\w]', '', s)
    return s.lower()

def is_page_number_line(line):
    return bool(re.match(r'^\d{1,4}$', line.strip()))

def main():
    parser = argparse.ArgumentParser(description="Extract sections from a SOC report PDF.")
    parser.add_argument("pdf_path", help="Path to the SOC report PDF file.")
    args = parser.parse_args()

    # Extract text from the PDF
    output_text_path = "data/output/output.txt"
    os.makedirs(os.path.dirname(output_text_path), exist_ok=True)
    extract_text_from_pdf(args.pdf_path, output_text_path)

    # Read the extracted text
    with open(output_text_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # Find section candidates
    section_candidates = find_section_candidates(text)
    print("Section Candidates:", section_candidates)

    # Write section candidates to section_results.json
    section_json_path = str(config.SECTION_JSON_PATH)
    os.makedirs(os.path.dirname(section_json_path), exist_ok=True)
    with open(section_json_path, 'w', encoding='utf-8') as jf:
        json.dump(section_candidates, jf, indent=2)
    print(f"Section results written to {section_json_path}")

if __name__ == "__main__":
    main()

# Explicitly export main functions for import
__all__ = ["extract_text_from_pdf", "find_section_candidates"]
