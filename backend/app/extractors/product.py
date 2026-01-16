import json
import logging
from typing import Any, List, Optional
from pathlib import Path
from .. import config
from ..gpt_client import gpt_extract

logger = logging.getLogger(__name__)

def load_json(path: str) -> Any:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(obj: Any, path: str):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

def extract_text_for_pages(txt_lines: List[str], page_numbers: List[int]) -> str:
    """Extract all lines between the first and last page in page_numbers."""
    if not page_numbers:
        return ''
    
    result = []
    current_page = None
    min_page = min(page_numbers)
    max_page = max(page_numbers)
    capturing = False
    
    for line in txt_lines:
        # Check if this line is a page marker
        if line.strip().startswith('=== PAGE '):
            try:
                current_page = int(line.strip().split()[2])
                # Start capturing when we hit the min page
                if current_page == min_page:
                    capturing = True
                # Stop capturing after we've collected all lines from max page
                # and hit the next page marker
                elif current_page > max_page:
                    break
            except Exception:
                pass
        
        # Capture all lines while we're in range
        if capturing:
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

def extract_product_from_report(job_paths=None, job_id=None):
    """Extract product information from SOC report.
    
    Args:
        job_paths: Dict with 'json_dir', 'logs_dir', 'temp_dir' Path objects
        job_id: Unique job identifier for logging
    """
    if not job_paths:
        raise ValueError("[PRODUCT] job_paths parameter is required for job isolation")
    if not job_id:
        raise ValueError("[PRODUCT] job_id parameter is required for logging")
    
    # Set up job-specific paths
    section_json_path = str(job_paths['json_dir'] / 'section_results.json')
    product_json_path = str(job_paths['json_dir'] / 'product_result.json')
    pdf_txt_path = str(job_paths['temp_dir'] / 'output.txt')
    
    logger.info(f"[JOB {job_id}] Starting product extraction")
    
    # Reset output file at the start of extraction
    with open(product_json_path, 'w', encoding='utf-8') as f:
        f.write('{}\n')
    section_results = load_json(section_json_path)
    # Use Description of System, Management Assertion, and title page
    with open(pdf_txt_path, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    text_sections = [extract_title_page(txt_lines)]
    for topic in ("Description_of_System", "Management_Assertion"):
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
                logger.info(f'[JOB {job_id}] DOC_page_ref or end_DOC_page_ref is None for section: {topic}')
    text = '\n'.join(text_sections)
    chunks = chunk_text(text)
    prompt = config.PRODUCT_EXTRACTION_PROMPT
    responses = []
    for idx, chunk in enumerate(chunks):
        full_prompt = prompt.format(text=chunk)
        logger.debug(f'[JOB {job_id}] Prompt chunk {idx}: {full_prompt[:500]}...')
        response = gpt_extract(full_prompt, 'product_extractor')
        logger.debug(f'[JOB {job_id}] GPT response chunk {idx}: {response}')
        responses.append(response)
    product = None
    confidence = 0
    for resp in responses:
        try:
            data = json.loads(resp)
            if data.get('product'):
                product = data['product']
                confidence = data.get('confidence', 1)
                break
        except Exception as e:
            logger.info(f'[JOB {job_id}] Failed to parse GPT response: {resp} | Error: {e}')
    result = {
        'product': product,
        'confidence': confidence,
        'raw_gpt_responses': responses
    }
    save_json(result, product_json_path)
    logger.info(f'[JOB {job_id}] Product extraction result: {result}')
    return result

__all__ = ["extract_product_from_report"]

if __name__ == '__main__':
    extract_product_from_report()
