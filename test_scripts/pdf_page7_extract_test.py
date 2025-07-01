# Quick test: Extract text from page 7 of Anaqua.pdf using pdfminer.six and pymupdf
# Usage: python pdf_page7_extract_test.py

import os
from pathlib import Path

PDF_PATH = os.path.join('soc2_reports', 'Anaqua.pdf')
PAGE_NUM = 7  # 1-based page number

print(f"Extracting page {PAGE_NUM} from {PDF_PATH}\n")

# --- pdfminer.six ---
try:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer
    print("[pdfminer.six] Results:")
    for i, page_layout in enumerate(extract_pages(PDF_PATH)):
        if i == PAGE_NUM - 1:
            text = ''
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    text += element.get_text()
            print(text.strip() or "[No text extracted]")
            break
except ImportError:
    print("[pdfminer.six] Not installed.")

print("\n" + "-"*60 + "\n")

# --- pymupdf (fitz) ---
try:
    import fitz
    print("[pymupdf] Results:")
    doc = fitz.open(PDF_PATH)
    if PAGE_NUM - 1 < len(doc):
        page = doc[PAGE_NUM - 1]
        text = page.get_text()  # type: ignore[attr-defined]
        print(text.strip() or "[No text extracted]")
    else:
        print(f"Page {PAGE_NUM} not found in document.")
except ImportError:
    print("[pymupdf] Not installed.")

print("\nDone.")
