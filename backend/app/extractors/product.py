
import os
import json
import logging
from typing import Dict, Any, List, Optional
from app import config
from app.gpt_client import gpt_extract

logger = logging.getLogger(__name__)

# Use centralized config paths
SECTION_JSON_PATH = str(config.SECTION_JSON_PATH)
PRODUCT_JSON_PATH = str(config.JSON_DIR / "product_result.json")
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

def extract_product_from_report():
    section_results = load_json(SECTION_JSON_PATH)
    # Use Description of System, Management Assertion, and title page
    with open(PDF_TXT_PATH, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    text_sections = [extract_title_page(txt_lines)]
    for topic in ("Description_of_System", "Management_Assertion"):
        section = next((s for s in section_results if s.get('topic') == topic), None)
        if section:
            start_line = section.get('line')
            end_line = section.get('end_line')
            if start_line and end_line:
                text_sections.append(extract_text_for_lines(txt_lines, start_line, end_line))
            else:
                pages = list(range(section['DOC_page_ref'], section['end_DOC_page_ref'] + 1))
                text_sections.append(extract_text_for_pages(txt_lines, pages))
    text = '\n'.join(text_sections)
    chunks = chunk_text(text)
    prompt = config.PRODUCT_EXTRACTION_PROMPT
    responses = []
    for idx, chunk in enumerate(chunks):
        full_prompt = prompt.format(text=chunk)
        logging.debug(f'Prompt chunk {idx}: {full_prompt[:500]}...')
        response = gpt_extract(full_prompt)
        logging.debug(f'GPT response chunk {idx}: {response}')
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
            logging.error(f'Failed to parse GPT response: {resp} | Error: {e}')
    result = {
        'product': product,
        'confidence': confidence,
        'raw_gpt_responses': responses
    }
    save_json(result, PRODUCT_JSON_PATH)
    logging.info(f'Product extraction result: {result}')
    return result

__all__ = ["extract_product_from_report"]

if __name__ == '__main__':
    extract_product_from_report()
