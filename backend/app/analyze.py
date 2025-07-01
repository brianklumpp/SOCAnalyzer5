def analyze_pdf_file(pdf_path, output_json_path='data/json/section_results.json'):
    """
    Extracts text from a SOC 2 PDF report, analyzes sections, and returns section results as a list of dicts.
    Args:
        pdf_path (str): Path to the PDF file to analyze.
        output_json_path (str): Path to save the section results JSON.
    Returns:
        List[dict]: Section analysis results.
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"File {pdf_path} not found.")
    extract_text_from_pdf(pdf_path, OUTPUT_TEXT_FILE)
    with open(OUTPUT_TEXT_FILE, 'r', encoding='utf-8') as f:
        text = f.read()
    section_results = find_section_candidates(text)
    # Add text snippets and line numbers, but preserve all other fields
    for section in section_results:
        if section.get('confidence', 0) > 0 and section.get('clean_heading') is not None:
            heading = section['clean_heading']
            offset = section.get('offset', None)
            if offset in (None, -1):
                offset = text.find(heading)
            section['offset'] = offset if offset is not None and offset >= 0 else 0
            section['line'] = offset_to_line(text, section['offset']) if section['offset'] is not None and section['offset'] >= 0 else 0
            section['snippet'] = get_text_snippet(text, section['offset']) if section['offset'] is not None and section['offset'] >= 0 else ''
        else:
            if section.get('offset') is None:
                section['offset'] = 0
            if section.get('line') is None:
                section['line'] = 0
            if section.get('snippet') is None:
                section['snippet'] = ''
    # Save to JSON if requested
    if output_json_path:
        with open(output_json_path, 'w', encoding='utf-8') as jf:
            json.dump(section_results, jf, indent=2)
    return section_results
import argparse
import json
from pdf_handler import extract_text_from_pdf, find_section_candidates  # changed import
from config import SOC2_REPORTS_DIR, OUTPUT_TEXT_FILE
import os

def get_text_snippet(text, offset, context=200):
    start = max(0, offset - context)
    end = min(len(text), offset + context)
    return text[start:end]

def offset_to_line(text, offset):
    return text[:offset].count('\n') + 1

def main():
    parser = argparse.ArgumentParser(description="Extract text from a SOC 2 PDF report and analyze sections.")
    parser.add_argument('--file', type=str, help='PDF filename in soc2_reports to analyze')
    parser.add_argument('--json', type=str, default='data/json/section_results.json', help='Output JSON file for section results')
    args = parser.parse_args()

    if args.file:
        pdf_path = os.path.join(SOC2_REPORTS_DIR, args.file)
        if not os.path.isfile(pdf_path):
            print(f"File {args.file} not found in soc2_reports.")
            return
    else:
        pdf_files = [f for f in os.listdir(SOC2_REPORTS_DIR) if f.lower().endswith('.pdf')]
        if not pdf_files:
            print("No PDF files found in soc2_reports.")
            return
        pdf_path = os.path.join(SOC2_REPORTS_DIR, pdf_files[0])

    extract_text_from_pdf(pdf_path, OUTPUT_TEXT_FILE)
    print(f"Extracted text from {pdf_path} to {OUTPUT_TEXT_FILE}")

    # Call robust GPT section analysis after extraction
    with open(OUTPUT_TEXT_FILE, 'r', encoding='utf-8') as f:
        text = f.read()
    total_chars = len(text)
    print(f"Total character count: {total_chars}")
    section_results = find_section_candidates(text)  # changed function call
    print("\nSection positions and confidence:")
    print(json.dumps(section_results, indent=2))

    # Add text snippets and line numbers, but preserve all other fields
    for section in section_results:
        # Only update/add offset, line, snippet; preserve all other fields
        if section.get('confidence', 0) > 0 and section.get('clean_heading') is not None:
            heading = section['clean_heading']
            offset = section.get('offset', None)
            if offset in (None, -1):
                offset = text.find(heading)
            section['offset'] = offset if offset is not None and offset >= 0 else 0
            section['line'] = offset_to_line(text, section['offset']) if section['offset'] is not None and section['offset'] >= 0 else 0
            section['snippet'] = get_text_snippet(text, section['offset']) if section['offset'] is not None and section['offset'] >= 0 else ''
        else:
            if section.get('offset') is None:
                section['offset'] = 0
            if section.get('line') is None:
                section['line'] = 0
            if section.get('snippet') is None:
                section['snippet'] = ''
    # Print details to console
    print("\nSection details:")
    for section in section_results:
        print(f"Topic: {section.get('topic')} | Offset: {section.get('offset')} | Line: {section.get('line')} | Confidence: {section.get('confidence')}%\nSnippet:\n{section.get('snippet')}\n{'-'*60}")
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as jf:
            json.dump(section_results, jf, indent=2)
        print(f"Section results with snippets saved to {args.json}")
    else:
        print("No JSON output file specified.")

if __name__ == "__main__":
    main()
