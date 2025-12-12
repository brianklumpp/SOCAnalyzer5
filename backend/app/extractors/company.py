# --- All imports at the top (PEP8 best practice) ---
import json
import logging
from typing import Any, List, Optional
from .. import config
from ..gpt_client import gpt_extract

logger = logging.getLogger(__name__)

# Use centralized config paths
SECTION_JSON_PATH = str(config.SECTION_JSON_PATH)
COMPANY_JSON_PATH = str(config.JSON_DIR / "company_result.json")
PDF_TXT_PATH = str(config.PDF_TXT_PATH)

def load_json(path: str) -> Any:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(obj: Any, path: str):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

def extract_text_for_pages(txt_lines: List[str], page_numbers: List[int]) -> str:
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
    if max_tokens is None:
        max_tokens = getattr(config, 'GPT_CHUNK_TOKENS', None)
        if max_tokens is None:
            max_tokens = getattr(config, 'DEFAULT_CHUNK_SIZE', None)
        if max_tokens is None:
            max_tokens = 1500
    chunk_size = max_tokens * 4
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def extract_title_page(txt_lines):
    title_page_lines = []
    for line in txt_lines:
        if line.strip().startswith('=== PAGE 2'):
            break
        title_page_lines.append(line)
    return ''.join(title_page_lines)

def extract_company_from_report():
    # Reset output file at the start of extraction
    with open(config.JSON_DIR / 'company_result.json', 'w', encoding='utf-8') as f:
        f.write('{}\n')
    section_results = load_json(SECTION_JSON_PATH)
    # Use Management Assertion, Service Auditor Report, and title page
    with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    text_sections = []
    # Add title page (up to PAGE 2 marker)
    text_sections.append(extract_title_page(txt_lines))
    for topic in ("Management_Assertion", "Service_Auditor_Report"):
        section = next((s for s in section_results if s.get('topic') == topic), None)
        if section:
            start_line = section.get('start_line')
            end_line = section.get('end_line')
            if start_line and end_line:
                text_sections.append(extract_text_for_lines(txt_lines, start_line, end_line))
            elif section.get('DOC_page_ref') is not None and section.get('end_DOC_page_ref') is not None:
                pages = list(range(section['DOC_page_ref'], section['end_DOC_page_ref'] + 1))
                text_sections.append(extract_text_for_pages(txt_lines, pages))
            else:
                logging.error('DOC_page_ref or end_DOC_page_ref is None for section: {}'.format(topic))
    text = '\n'.join(text_sections)
    chunks = chunk_text(text)
    prompt = config.COMPANY_EXTRACTION_PROMPT
    responses = []
    for idx, chunk in enumerate(chunks):
        full_prompt = prompt.format(text=chunk)
        logging.debug(f'Prompt chunk {idx}: {full_prompt[:500]}...')
        response = gpt_extract(full_prompt, 'company_extractor')
        logging.debug(f'GPT response chunk {idx}: {response}')
        responses.append(response)
    company = None
    parent_company = None
    company_domain = None
    confidence = 0
    for resp in responses:
        try:
            data = json.loads(resp)
            if data.get('company'):
                company = data['company']
                parent_company = data.get('parent_company', None)
                company_domain = data.get('company_domain', None)
                confidence = data.get('confidence', 1)
                break
        except Exception as e:
            logging.error(f'Failed to parse GPT response: {resp} | Error: {e}')
    
    # Fallback: Infer domain for well-known companies if not found in text
    if company and not company_domain:
        domain_map = {
            # Big 4 Accounting Firms
            'deloitte': 'deloitte.com',
            'pwc': 'pwc.com',
            'pricewaterhousecoopers': 'pwc.com',
            'ernst & young': 'ey.com',
            'ey': 'ey.com',
            'kpmg': 'kpmg.com',
            # Major Tech Companies
            'microsoft': 'microsoft.com',
            'google': 'google.com',
            'amazon': 'amazon.com',
            'aws': 'aws.amazon.com',
            'salesforce': 'salesforce.com',
            'oracle': 'oracle.com',
            'ibm': 'ibm.com',
            'sap': 'sap.com',
            # Major Banks
            'jpmorgan': 'jpmorgan.com',
            'bank of america': 'bankofamerica.com',
            'wells fargo': 'wellsfargo.com',
            'citibank': 'citibank.com',
            'citigroup': 'citigroup.com',
            'citi': 'citi.com',
            'goldman sachs': 'goldmansachs.com',
            'morgan stanley': 'morganstanley.com',
            'barclays': 'barclays.com',
            'hsbc': 'hsbc.com',
        }
        
        # Normalize company name for lookup
        company_lower = company.lower()
        for key, domain in domain_map.items():
            if key in company_lower:
                company_domain = domain
                logger.info(f'[COMPANY] Inferred domain "{domain}" for company "{company}"')
                break
    
    result = {
        'company': company,
        'parent_company': parent_company,
        'company_domain': company_domain,
        'confidence': confidence,
        'raw_gpt_responses': responses
    }
    save_json(result, COMPANY_JSON_PATH)
    logging.info(f'Company extraction result: {result}')
    return result

__all__ = ["extract_company_from_report"]

if __name__ == '__main__':
    extract_company_from_report()
