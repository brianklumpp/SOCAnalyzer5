# --- All imports at the top (PEP8 best practice) ---
import os
import re
import collections
from dotenv import load_dotenv
import pathlib
import json
from . import config
from .config import (
    SECTION_TOPICS, WATERMARK_PATTERNS, REGEX_PATTERNS, PRIORITY_KEYWORDS_MANAGEMENT_ASSERTION, PRIORITY_KEYWORDS_SERVICE_AUDITOR_REPORT,
    PRIORITY_KEYWORDS_DESCRIPTION_OF_SYSTEM, DEFAULT_GPT_MODEL, DEFAULT_TEMPERATURE, DEFAULT_TOP_P,
    LLM_PROVIDER, SECTION_DETECTION_PROMPT, EXTRACT_TOC_PROMPT, SECTION_HEADING_VALIDATION_PROMPT,
    EXTRACT_TOC_HEADINGS_AND_PAGES_PROMPT, SECTION_TOPIC_KEYWORD_RULES
)
from .gpt_client import gpt_extract
import argparse

def load_api_key():
    """Deprecated: direct OpenAI key loading is no longer used for GPT calls.
    Retained for backward compatibility with any external imports."""
    load_dotenv()
    return os.getenv('OPENAI_API_KEY')

def decrypt_and_save_pdf(input_path, output_path, password=None):
    """
    Decrypt a password-protected PDF and save the decrypted version.
    
    If the PDF is encrypted and a password is provided, this function authenticates
    and saves a decrypted copy. If the PDF is not encrypted, it simply copies the file.
    This ensures the stored PDF does not require re-authentication.
    
    Args:
        input_path: Path to the encrypted PDF file
        output_path: Path to save the decrypted PDF
        password: Optional password for encrypted PDFs
        
    Returns:
        str: Path to the decrypted PDF (output_path)
        
    Raises:
        ValueError: If PDF is encrypted and password is invalid
    """
    import logging
    import shutil
    logger = logging.getLogger(__name__)
    
    try:
        import fitz  # pymupdf
    except ImportError:
        logger.error("PyMuPDF (fitz) is required for PDF decryption")
        # Fallback: just copy the file
        shutil.copy(input_path, output_path)
        return output_path
    
    try:
        logger.info(f"[PDF_DECRYPT] Opening PDF: {input_path}")
        doc = fitz.open(input_path)
        
        # Check if PDF is encrypted
        if doc.is_encrypted:
            logger.info(f"[PDF_DECRYPT] PDF is encrypted, attempting authentication")
            
            if password and doc.authenticate(password):
                logger.info(f"[PDF_DECRYPT] Successfully authenticated with provided password")
            elif doc.authenticate(""):
                # Try empty password (some PDFs are "secured" but not password-protected)
                logger.info(f"[PDF_DECRYPT] Authenticated with empty password")
            else:
                logger.error(f"[PDF_DECRYPT] Failed to decrypt PDF with provided password")
                doc.close()
                raise ValueError("Invalid PDF password - please check your password and try again")
        else:
            logger.info(f"[PDF_DECRYPT] PDF is not encrypted")
        
        # Save decrypted PDF
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
        logger.info(f"[PDF_DECRYPT] Saved decrypted PDF to {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"[PDF_DECRYPT] Error decrypting PDF: {e}")
        # Fallback: copy original file
        shutil.copy(input_path, output_path)
        return output_path

def extract_embedded_files(input_path, output_dir, password=None):
    """
    Extract embedded/attached files from a PDF.
    Many protected PDFs embed the actual content as an attachment.
    
    Args:
        input_path: Path to the input PDF
        output_dir: Directory to save extracted files
        password: Optional password for encrypted PDFs
        
    Returns:
        list: Paths to extracted PDF files (empty if none found)
        
    Raises:
        ValueError: If PDF is encrypted and password is invalid
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
        
        # Open PDF with password if provided
        if password:
            doc = fitz.open(input_path)
            if doc.is_encrypted and not doc.authenticate(password):
                logger.error(f"[PDF_EMBED] Failed to decrypt PDF with provided password")
                doc.close()
                raise ValueError("Invalid PDF password - please check your password and try again")
        else:
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


def flatten_pdf(input_path, output_path, password=None):
    """
    Attempt to unlock/flatten a PDF by removing form fields, JavaScript, and encryption.
    This tries to expose hidden content without converting to images.
    
    Args:
        input_path: Path to the input PDF
        output_path: Path to save the flattened PDF
        password: Optional password for encrypted PDFs
        
    Returns:
        bool: True if successful, False otherwise
        
    Raises:
        ValueError: If PDF is encrypted and password is invalid
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
        
        # Open the source PDF with password if provided
        if password:
            doc = fitz.open(input_path)
            if doc.is_encrypted and not doc.authenticate(password):
                logger.error(f"[PDF_FLATTEN] Failed to decrypt PDF with provided password")
                doc.close()
                raise ValueError("Invalid PDF password - please check your password and try again")
        else:
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


def extract_text_from_pdf(pdf_path, output_path, password=None):
    """
    Extracts all text from a PDF file and writes it to a text file.
    Maintains pagination by inserting a page break marker between pages.
    Removes repetitive watermark-like patterns (dates, emails) that appear on >80% of pages.
    Automatically skips legal agreement/disclaimer pages at the beginning of the document.
    
    Uses PyMuPDF's "blocks" extraction mode for better table and multi-column layout handling.
    
    Args:
        pdf_path (str): Path to the PDF file.
        output_path (str): Path to the output text file.
        password (str, optional): Password for encrypted PDFs.
        
    Raises:
        ValueError: If PDF is encrypted and password is invalid
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        import fitz  # pymupdf
    except ImportError:
        raise ImportError("pymupdf (fitz) is required for PDF extraction. Please install it with 'pip install pymupdf'.")
    
    # Open PDF with password if provided
    if password:
        doc = fitz.open(pdf_path)
        if doc.is_encrypted and not doc.authenticate(password):
            logger.error(f"[PDF_EXTRACT] Failed to decrypt PDF with provided password")
            doc.close()
            raise ValueError("Invalid PDF password - please check your password and try again")
    else:
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
    
    # First pass: Collect patterns per page (only from non-skipped pages)
    # Look for both specific patterns (dates/emails) AND arbitrary repeated lines
    for page_num in range(start_page, len(doc)):
        text = doc[page_num].get_text() or ""   # type: ignore[attr-defined]
        patterns = set()
        
        # Collect regex-based patterns (dates, emails, times)
        for regex in [date_regex, email_regex, time_regex]:
            for match in re.findall(regex, text):
                patterns.add(match.strip())
        
        # Also collect lines that might be watermarks (short, non-empty, alphanumeric)
        # This catches things like "term-token-XXX", "Confidential", company names, etc.
        for line in text.splitlines():
            line_stripped = line.strip()
            # Consider lines that are:
            # - Between 10-80 chars (not too short, not too long)
            # - Mostly alphanumeric or common punctuation
            # - Not likely to be normal content
            if 10 <= len(line_stripped) <= 80:
                # Skip lines that look like normal sentences (have spaces, lowercase, punctuation)
                if not re.search(r'[a-z].*\s.*[a-z]', line_stripped):
                    patterns.add(line_stripped)
        
        page_patterns.append(patterns)
    
    # Count pattern occurrences across pages
    pattern_counter = collections.Counter()
    for patterns in page_patterns:
        pattern_counter.update(patterns)
    num_pages = len(page_patterns)
    
    # Identify patterns that appear on >80% of pages as watermarks
    watermark_patterns = set([
        pat for pat, count in pattern_counter.items() if count / num_pages > 0.8
    ])
    
    if watermark_patterns:
        logger.info(f"Detected {len(watermark_patterns)} watermark patterns appearing on >80% of pages")
    
    # Now extract and filter text (starting from start_page)
    for i in range(start_page, len(doc)):
        try:
            # Step 1: Extract text using default mode
            text = doc[i].get_text() or ""   # type: ignore[attr-defined]
            
            # Step 2: Remove detected watermarks FIRST
            if watermark_patterns:
                for watermark in watermark_patterns:
                    text = text.replace(str(watermark), '')
            
            # Step 3: Check if page has minimal content after watermark removal
            # If < 40 chars, try blocks mode
            if len(text.strip()) < 40:
                logger.warning(f"Page {i+1} has minimal text after watermark removal ({len(text.strip())} chars), trying 'blocks' mode")
                try:
                    blocks = doc[i].get_text("blocks")  # type: ignore[attr-defined]
                    block_text = "\n".join([block[4] for block in blocks if len(block) > 4 and isinstance(block[4], str)])
                    # Remove watermarks from block text too
                    if watermark_patterns:
                        for watermark in watermark_patterns:
                            block_text = block_text.replace(str(watermark), '')
                    
                    if len(block_text.strip()) > len(text.strip()):
                        text = block_text
                        logger.info(f"Page {i+1}: blocks mode extracted {len(block_text.strip())} chars after watermark removal")
                except Exception as block_err:
                    logger.warning(f"Page {i+1} blocks extraction failed: {block_err}")
            
            # Step 4: If still < 40 chars, try OCR (page is likely a scanned image)
            if len(text.strip()) < 40:
                logger.warning(f"Page {i+1} still has minimal text ({len(text.strip())} chars), attempting OCR extraction")
                try:
                    import pytesseract
                    from PIL import Image
                    import io
                    
                    page = doc[i]  # type: ignore[index]
                    # Convert page to high-res image for OCR
                    pix = page.get_pixmap(dpi=300)  # Higher DPI for better OCR accuracy
                    
                    # Convert pixmap to PIL Image
                    img_data = pix.tobytes("png")
                    img = Image.open(io.BytesIO(img_data))
                    
                    # Run Tesseract OCR
                    ocr_text = pytesseract.image_to_string(img, lang='eng')
                    
                    if len(ocr_text.strip()) > len(text.strip()):
                        text = ocr_text
                        logger.info(f"Page {i+1}: OCR extracted {len(ocr_text.strip())} chars from image-based page")
                    else:
                        logger.warning(f"Page {i+1}: OCR returned minimal text ({len(ocr_text.strip())} chars)")
                except ImportError:
                    logger.warning(f"Page {i+1}: pytesseract not available for OCR, page content will be minimal")
                except Exception as ocr_err:
                    logger.warning(f"Page {i+1}: OCR extraction failed: {ocr_err}")
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
        # Insert page break marker (using actual PDF page number, 1-based)
        logical_page_num = i + 1
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


def _match_topic_keywords(section_lower: str):
    """Match a lowercased section name against SECTION_TOPIC_KEYWORD_RULES.

    Returns the topic string (e.g. 'Control_Descriptions') on first match,
    or None if no rule matches.  Rules are evaluated in dict-order; within
    each topic the rule list is evaluated top-to-bottom — first match wins.
    """
    for topic, rules in SECTION_TOPIC_KEYWORD_RULES.items():
        for primary_kw, secondary_kws in rules:
            if primary_kw not in section_lower:
                continue
            # If no secondary keywords, the primary alone is sufficient
            if not secondary_kws or any(sk in section_lower for sk in secondary_kws):
                return topic
    return None


def find_section_candidates(text, model=DEFAULT_GPT_MODEL, temperature=DEFAULT_TEMPERATURE, top_p=DEFAULT_TOP_P, lookahead_lines=3):
    """
    GPT-based section identification with TOC-focused approach.
    
    Extracts the Table of Contents (first 5-10 pages) and parses ALL section entries.
    This ensures we capture all sections regardless of where they appear in the document.
    
    Returns dict with 'sections' list and 'toc_page_offset' for database persistence.
    """
    import pathlib
    import json
    
    PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
    os.makedirs(PROJECT_ROOT / 'data/logs', exist_ok=True)
    
    lines = text.splitlines()
    
    def extract_toc_area(text_lines, max_pages=10):
        """Extract just the TOC area from document (usually first 5-10 pages)."""
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
        
        # Filter out subsections (e.g., "Section II.A", "III.B") unless they match our 4 main topics
        # Keep only main sections (I, II, III, IV, V) or sections matching our core topics
        def is_subsection(section_name):
            """Check if section name indicates a subsection (e.g., II.A, III.1, IV.B.2)."""
            # Pattern: Roman numeral or digit followed by dot/letter (II.A, III.1, IV.B.2)
            import re
            subsection_patterns = [
                r'(?:^|section\s+)([IVX]+|[0-9]+)\.[A-Z0-9]',  # II.A, III.1, IV.B
                r'(?:^|section\s+)([IVX]+|[0-9]+)\.[0-9]+\.',  # IV.1.2, III.2.3
            ]
            section_norm = section_name.strip().upper()
            for pattern in subsection_patterns:
                if re.search(pattern, section_norm, re.IGNORECASE):
                    return True
            return False
        
        # Pre-filter: Remove subsections unless they match our core topics
        filtered_gpt_sections = []
        for sec in gpt_sections:
            section_name = sec.get('name', '')
            section_lower = section_name.lower()
            
            # Check if this is one of our 4 core sections using config-driven rules.
            # Also use containment check for GPT-identified names since GPT may return
            # a short name (e.g. "TESTING MATRICES") while section name includes
            # prefix (e.g. "SECTION 4 TESTING MATRICES")
            is_core_section = (
                _match_topic_keywords(section_lower) is not None or
                (controls_section_name and controls_section_name.lower() in section_lower) or
                (system_desc_section_name and system_desc_section_name.lower() in section_lower)
            )
            
            # Keep if: (1) not a subsection, OR (2) is a subsection but matches core topic
            if not is_subsection(section_name) or is_core_section:
                filtered_gpt_sections.append(sec)
                if is_subsection(section_name) and is_core_section:
                    logger.info(f"[SUBSECTION_FILTER] Keeping subsection '{section_name}' because it matches core topic")
            else:
                logger.info(f"[SUBSECTION_FILTER] Filtering out subsection: '{section_name}'")
        
        gpt_sections = filtered_gpt_sections
        
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
        # Calculate global page offset from the FIRST section (lowest toc_page)
        # This ensures consistent offset across all sections
        global_page_offset = 0
        global_offset_calculated = False
        
        # Sort sections by toc_page to process earliest first
        gpt_sections_sorted = sorted(gpt_sections, key=lambda s: s.get('toc_page', 999))
        
        for i, gpt_sec in enumerate(gpt_sections_sorted):
            section_name = gpt_sec.get('name', '')
            toc_page = gpt_sec.get('toc_page')
            doc_page = gpt_sec.get('doc_page')
            confidence = gpt_sec.get('confidence', 0)
            
            # Fallback: if toc_page missing, use doc_page for both
            if toc_page is None:
                toc_page = doc_page if doc_page else 1
            if doc_page is None:
                doc_page = toc_page if toc_page else 1
            
            # If this section's offset differs from global, correct it using global offset
            section_offset = doc_page - toc_page
            if section_offset != global_page_offset and global_page_offset != 0:
                logger.warning(f"[SECTION_DETECT] Section '{section_name}' has inconsistent offset ({section_offset} vs global {global_page_offset}), correcting DOC_page_ref")
                doc_page = toc_page + global_page_offset
            
            # Validate and log significant offsets
            offset_diff = abs(doc_page - toc_page)
            if offset_diff > 10:
                logger.warning(f"[SECTION_DETECT] Large page offset detected for '{section_name}': TOC={toc_page}, DOC={doc_page}, offset={offset_diff}")
            
            start_page = doc_page  # Use DOC page for line/offset calculations
            
            # Determine topic mapping based on GPT's explicit identification first
            section_lower = section_name.lower()
            if controls_section_name and controls_section_name.lower() in section_lower:
                # GPT explicitly identified this as the controls section
                # Use containment: GPT may return "TESTING MATRICES" while
                # section name is "SECTION 4 TESTING MATRICES"
                topic = 'Control_Descriptions'
                explicit_match = True
            elif system_desc_section_name and system_desc_section_name.lower() in section_lower:
                # GPT explicitly identified this as the system description
                topic = 'Description_of_System'
                explicit_match = True
            else:
                # Fallback: match against SECTION_TOPIC_KEYWORD_RULES from config
                matched_topic = _match_topic_keywords(section_lower)
                if matched_topic:
                    topic = matched_topic
                    explicit_match = False
                else:
                    topic = 'Unknown'
                    explicit_match = False
            
            # Find the actual section start by searching for the section heading in the document
            # Start search from the TOC page (toc_page), not doc_page (which is where TOC entry appears)
            # This fixes the issue where doc_page pointed to TOC location instead of section content
            search_start_page = toc_page if toc_page else doc_page
            start_line = 0
            found_section = False
            
            # First, find the page marker near toc_page
            for idx, line in enumerate(text_lines):
                if line.startswith(f'=== PAGE {search_start_page} ==='):
                    # Start searching from this page
                    search_start_idx = idx + 1
                    # Search within a reasonable window (e.g., 3 pages = ~150 lines)
                    search_end_idx = min(len(text_lines), search_start_idx + 150)
                    
                    # Look for the section heading within this window
                    for search_idx in range(search_start_idx, search_end_idx):
                        search_line = text_lines[search_idx].strip()
                        # Check if this line matches the section name (allowing for minor variations)
                        if section_name.lower() in search_line.lower() and len(search_line) < 150:
                            # Additional check: line should look like a heading (not part of paragraph)
                            # Headings are usually short, standalone, and may have section markers
                            if not search_line.endswith('.') or 'section' in search_line.lower():
                                start_line = search_idx
                                found_section = True
                                logger.info(f"[SECTION_DETECT] Found section '{section_name}' at line {start_line} (page ~{search_start_page})")
                                break
                    
                    if found_section:
                        break
            
            # Fallback: if section not found, use the page marker approach (old behavior)
            if not found_section:
                logger.warning(f"[SECTION_DETECT] Could not find section heading for '{section_name}', falling back to toc_page={toc_page}")
                for idx, line in enumerate(text_lines):
                    if line.startswith(f'=== PAGE {search_start_page} ==='):
                        start_line = idx + 1
                        break
            
            # Update DOC_page_ref to match where we actually found the section
            # Find which page the start_line is on
            actual_doc_page = search_start_page  # default
            for idx in range(start_line - 1, -1, -1):
                if text_lines[idx].startswith('=== PAGE '):
                    try:
                        actual_doc_page = int(text_lines[idx].split()[2])
                        break
                    except Exception:
                        pass
            
            # Update doc_page to actual location
            doc_page = actual_doc_page
            
            # Calculate or validate global offset
            calculated_offset = doc_page - toc_page
            if not global_offset_calculated:
                # First section: establish the global offset
                global_page_offset = calculated_offset
                global_offset_calculated = True
                logger.info(f"[SECTION_DETECT] Established global offset={global_page_offset} from first section '{section_name}' (TOC={toc_page}, DOC={doc_page})")
            else:
                # Subsequent sections: validate against global offset
                if abs(calculated_offset - global_page_offset) > 2:
                    logger.warning(f"[SECTION_DETECT] Section '{section_name}' has offset={calculated_offset} (TOC={toc_page}, DOC={doc_page}), differs from global={global_page_offset} by {abs(calculated_offset - global_page_offset)} pages")
                else:
                    logger.debug(f"[SECTION_DETECT] Section '{section_name}' offset={calculated_offset} matches global={global_page_offset} (within tolerance)")
            
            # Calculate character offset
            offset = sum(len(l) + 1 for l in text_lines[:start_line])
            
            # Get snippet
            snippet_lines = text_lines[start_line:start_line+5]
            snippet = '\n'.join(snippet_lines)[:300]
            
            # Determine end boundaries (next section or document end)
            if i + 1 < len(gpt_sections_sorted):
                next_sec = gpt_sections_sorted[i+1]
                next_toc_page = next_sec.get('toc_page')
                next_doc_page_raw = next_sec.get('doc_page')
                
                # Apply global offset correction to next section's doc_page
                if next_toc_page is not None and next_doc_page_raw is not None:
                    next_section_offset = next_doc_page_raw - next_toc_page
                    if next_section_offset != global_page_offset and global_page_offset != 0:
                        next_doc_page = next_toc_page + global_page_offset
                        logger.debug(f"[SECTION_DETECT] Corrected next section doc_page from {next_doc_page_raw} to {next_doc_page}")
                    else:
                        next_doc_page = next_doc_page_raw
                else:
                    next_doc_page = next_doc_page_raw
                
                # Use doc_page from next section, fallback to toc_page if null
                # IMPORTANT: Use next section REGARDLESS of its topic to get accurate boundaries
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
            
            # Calculate end_TOC_page_ref and end_DOC_page_ref
            # end_page is the first page of the NEXT section, so the last page of current section is end_page - 1
            last_page_of_section = end_page - 1 if (i + 1 < len(gpt_sections_sorted)) else end_page
            end_toc_page = last_page_of_section - global_page_offset
            end_doc_page = last_page_of_section
            
            # Note: These will be corrected in the second pass after all sections are identified
            
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
                'end_DOC_page_ref': end_doc_page,
                'end_line': end_line,
                'end_offset': end_offset,
                'explicit_match': explicit_match  # Track if GPT explicitly identified this section
            }
            
            sections_list.append(section_dict)
        
        # SECOND PASS: Fix end_DOC_page_ref and end_line using actual section boundaries
        # Now that all sections are identified, we can properly set where each section ends
        sections_list_sorted = sorted(sections_list, key=lambda s: s['DOC_page_ref'])
        for i, section in enumerate(sections_list_sorted):
            if i + 1 < len(sections_list_sorted):
                next_section = sections_list_sorted[i + 1]
                next_start_page = next_section['DOC_page_ref']
                next_start_line = next_section['start_line']
                
                # Current section ends where next section begins
                section['end_DOC_page_ref'] = next_start_page - 1
                section['end_TOC_page_ref'] = section['end_DOC_page_ref'] - global_page_offset
                section['end_line'] = next_start_line - 1
                
                logger.debug(f"[SECTION_DETECT] Second pass: '{section['topic']}' ends at page {section['end_DOC_page_ref']}, line {section['end_line']}")
            else:
                # Last section goes to document end
                section['end_DOC_page_ref'] = total_pages
                section['end_TOC_page_ref'] = total_pages - global_page_offset
                section['end_line'] = len(text_lines)
                logger.debug(f"[SECTION_DETECT] Second pass: '{section['topic']}' (last) ends at document end page {total_pages}")
        
        # Deduplicate: Ensure only ONE section per topic
        # Priority: GPT explicit matches > first occurrence
        topic_assignments = {}
        for section in sections_list:
            topic = section['topic']
            if topic == 'Unknown':
                continue  # Allow multiple Unknown sections
            
            if topic not in topic_assignments:
                # First occurrence of this topic
                topic_assignments[topic] = section
            else:
                # Duplicate found - decide which to keep
                existing = topic_assignments[topic]
                current_explicit = section.get('explicit_match', False)
                existing_explicit = existing.get('explicit_match', False)
                
                if current_explicit and not existing_explicit:
                    # Current has explicit GPT match, existing doesn't - replace
                    logger.info(f"[TOPIC_DEDUP] Replacing '{existing['clean_heading']}' with '{section['clean_heading']}' for topic {topic} (GPT explicit match)")
                    existing['topic'] = 'Unknown'  # Mark old one as Unknown
                    topic_assignments[topic] = section
                elif not current_explicit and existing_explicit:
                    # Existing has explicit match, current doesn't - keep existing
                    logger.info(f"[TOPIC_DEDUP] Marking '{section['clean_heading']}' as Unknown (duplicate {topic}, keeping GPT explicit match)")
                    section['topic'] = 'Unknown'
                else:
                    # Both explicit or both non-explicit - keep first occurrence
                    logger.info(f"[TOPIC_DEDUP] Marking '{section['clean_heading']}' as Unknown (duplicate {topic}, keeping first occurrence)")
                    section['topic'] = 'Unknown'
        
        # Filter to keep only the 4 main sections we care about
        # Keep all sections for proper boundary calculation, but only return the ones we need
        filtered_sections = [
            s for s in sections_list 
            if s['topic'] in ['Management_Assertion', 'Service_Auditor_Report', 'Description_of_System', 'Control_Descriptions']
        ]
        
        logger.info(f"[SECTION_FILTER] Total sections detected: {len(sections_list)}, keeping {len(filtered_sections)} main sections")
        if len(sections_list) > len(filtered_sections):
            discarded = [s['clean_heading'] for s in sections_list if s not in filtered_sections]
            logger.info(f"[SECTION_FILTER] Discarded sections: {discarded}")
        
        # Return both sections and the toc_page_offset for database storage
        return {
            'sections': filtered_sections,
            'toc_page_offset': global_page_offset if global_page_offset > 0 else None
        }
    
    # Extract TOC area (first 10 pages to ensure we capture full TOC)
    toc_area = extract_toc_area(lines, max_pages=10)
    token_count = estimate_tokens(toc_area)
    
    log_path = PROJECT_ROOT / 'data/logs/section_identification.log'
    with open(log_path, 'w', encoding='utf-8') as log_file:
        log_file.write(f"=== TOC-Based Section Identification (~{token_count} tokens from first 10 pages) ===\n\n")
        log_file.write(f"Strategy: Extract TOC and parse ALL section entries comprehensively\n\n")
        
        try:
            prompt = config.SECTION_IDENTIFICATION_PROMPT.format(text=toc_area)
            gpt_response = gpt_extract(prompt, 'section_identification')
            
            log_file.write(f"GPT Response:\n{gpt_response}\n\n")
            
            result = parse_gpt_response(gpt_response)
            overall_confidence = result.get('overall_confidence', 0)
            sections_found = len(result.get('sections', []))
            
            log_file.write(f"Overall Confidence: {overall_confidence}\n")
            log_file.write(f"Sections Found: {sections_found}\n")
            
            if sections_found == 0:
                log_file.write("\n✗ No sections found. Ensure document has a valid TOC.\n")
                raise Exception("No sections identified in TOC. Please ensure this is a standard SOC 1 or SOC 2 report.")
            
            log_file.write(f"\n✓ Successfully identified {sections_found} sections from TOC.\n")
            return convert_to_legacy_format(result, lines)
            
        except Exception as e:
            log_file.write(f"\n✗ Error during TOC-based section identification: {e}\n")
            raise


def clean_toc_heading(heading):
    """Remove trailing spaces, dots, and normalize whitespace from a TOC heading."""
    # Remove trailing dots and spaces
    heading = re.sub(r'[.\s]+$', '', heading)
    # Collapse multiple spaces
    heading = re.sub(r'\s+', ' ', heading)
    return heading.strip()

def get_page_for_line(lines, line_num):
    """Given a list of lines and a line number, return the page number (1-based) for that line, using the page break markers.
    
    The page marker that PRECEDES the control line is the correct page reference.
    For example, if line 100 has '=== PAGE 5 ===' and line 101 has the control, the control is on page 5.
    
    Args:
        lines: List of document lines (0-indexed)
        line_num: 1-based line number in the document
    """
    page = 1
    # Convert line_num (1-based) to index (0-based), then iterate through all preceding lines
    target_index = line_num - 1  # Convert to 0-based index
    # Iterate up to (but not including) the target line to find the preceding page marker
    for i in range(min(target_index, len(lines))):
        line = lines[i].strip()
        if line.startswith('=== PAGE '):
            try:
                page = int(line.split()[2])
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
    section_result = find_section_candidates(text)
    # Handle both dict format (new) and list format (legacy compatibility)
    if isinstance(section_result, dict):
        section_candidates = section_result.get('sections', [])
        toc_page_offset = section_result.get('toc_page_offset')
        print(f"TOC Page Offset: {toc_page_offset}")
    else:
        section_candidates = section_result  # Legacy list format
        toc_page_offset = None
    print("Section Candidates:", section_candidates)

    # Write section candidates to section_results.json
    section_json_path = str(config.SECTION_JSON_PATH)
    os.makedirs(os.path.dirname(section_json_path), exist_ok=True)
    with open(section_json_path, 'w', encoding='utf-8') as jf:
        json.dump(section_candidates, jf, indent=2)
    print(f"Section results written to {section_json_path}")
    if toc_page_offset is not None:
        print(f"TOC page offset: {toc_page_offset} (should be saved to scan table)")

if __name__ == "__main__":
    main()

# Explicitly export main functions for import
__all__ = ["extract_text_from_pdf", "find_section_candidates"]
