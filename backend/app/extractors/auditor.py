
import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
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

def extract_auditor_from_report():
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
        logging.error('No Service_Auditor_Report section found.')
        return None
    with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    text_sections = [extract_title_page(txt_lines)]
    start_line = auditor_section.get('line')
    end_line = auditor_section.get('end_line')
    if start_line and end_line:
        text_sections.append(extract_text_for_lines(txt_lines, start_line, end_line))
    else:
        pages = set([1])
        start = auditor_section['DOC_page_ref']
        end = auditor_section['end_DOC_page_ref']
        pages.update(range(start, end + 1))
        pages = sorted(pages)
        text_sections.append(extract_text_for_pages(txt_lines, pages))
    text = '\n'.join(text_sections)
    # Chunk text
    chunks = chunk_text(text)
    # Prepare prompt
    prompt_template = config.AUDITOR_EXTRACTION_PROMPT_EXCLUDE
    responses = []
    for idx, chunk in enumerate(chunks):
        full_prompt = prompt_template.format(
            text=chunk,
            company_line=company_line
        )
        logging.debug(f'Prompt chunk {idx}: {full_prompt[:500]}...')
        response = gpt_extract(full_prompt)
        logging.debug(f'GPT response chunk {idx}: {response}')
        responses.append(response)
    # Parse responses (simple: take first non-empty auditor name)
    auditor = None
    confidence = 0
    for resp in responses:
        try:
            data = json.loads(resp)
            if data.get('auditor'):
                auditor = data['auditor']
                confidence = data.get('confidence', 1)
                break
        except Exception as e:
            logging.error(f'Failed to parse GPT response: {resp} | Error: {e}')
    result = {
        'auditor': auditor,
        'confidence': confidence,
        'source_section': auditor_section.get('clean_heading'),
        'source_page': auditor_section.get('DOC_page_ref'),
        'raw_gpt_responses': responses
    }
    # Follow-up confirmation if an auditor was found
    if auditor:
        confirmed_auditor, confirm_confidence, confirm_explanation = confirm_auditor_with_followup(auditor, text)
        if confirmed_auditor:
            # If confirmation confidence is higher, average the two; if lower, use the minimum
            if confirm_confidence > confidence:
                result['confidence'] = round((confidence + confirm_confidence) / 2, 3)
            else:
                result['confidence'] = min(confidence, confirm_confidence)
            result['confirmation_explanation'] = confirm_explanation
            logging.info(f"Auditor confirmation succeeded. Adjusted confidence: {result['confidence']}. Explanation: {confirm_explanation}")
        else:
            result['auditor'] = None
            result['confidence'] = 0
            result['confirmation_explanation'] = confirm_explanation
            logging.info(f"Auditor confirmation failed. Explanation: {confirm_explanation}")
    # Fallback: search for known auditor firms if GPT failed
    if not result['auditor']:
        # First, try fallback on the section text
        fallback_candidate = fallback_auditor_search(text)
        if not fallback_candidate:
            # If still not found, search the entire document
            with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f:
                full_doc_text = f.read()
            fallback_candidate = fallback_auditor_search(full_doc_text)
            logging.info("Fallback: Searched full document for auditor firm.")
        if fallback_candidate:
            logging.info(f"Fallback auditor candidate found: {fallback_candidate}")
            # Confirm with GPT
            confirmed_auditor, confirm_confidence, confirm_explanation = confirm_auditor_with_followup(fallback_candidate, text)
            if confirmed_auditor:
                result['auditor'] = confirmed_auditor
                result['confidence'] = confirm_confidence
                result['confirmation_explanation'] = f"Fallback: {confirm_explanation}"
            else:
                result['auditor'] = None
                result['confidence'] = 0
                result['confirmation_explanation'] = f"Fallback failed: {confirm_explanation}"
        else:
            logging.info("No fallback auditor candidate found.")
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
    response = gpt_extract(followup_prompt)
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
