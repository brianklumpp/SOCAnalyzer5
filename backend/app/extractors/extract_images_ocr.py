import os
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import argparse

# Set this to your Tesseract executable path if not in PATH
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Configuration
PDF_PATH = os.path.join('soc2_reports', 'Bitwarden.pdf')  # Change as needed
OUTPUT_IMG_DIR = os.path.join('data', 'output', 'images')
OUTPUT_OCR_DIR = os.path.join('data', 'output', 'ocr')
PAGES_TO_EXTRACT = [1, 5]  # Example: cover and auditor section; adjust as needed

os.makedirs(OUTPUT_IMG_DIR, exist_ok=True)
os.makedirs(OUTPUT_OCR_DIR, exist_ok=True)

def extract_images_from_pdf(pdf_path, pages):
    doc = fitz.open(pdf_path)
    for page_num in pages:
        page_index = page_num - 1  # fitz is 0-based
        if page_index < 0 or page_index >= len(doc):
            continue
        page = doc[page_index]
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image['image']
            image_ext = base_image['ext']
            img_filename = f'page{page_num}_img{img_index + 1}.{image_ext}'
            img_path = os.path.join(OUTPUT_IMG_DIR, img_filename)
            with open(img_path, 'wb') as img_file:
                img_file.write(image_bytes)
            print(f'Extracted image: {img_path}')
            # OCR
            ocr_text = ocr_image_bytes(image_bytes)
            ocr_filename = f'page{page_num}_img{img_index + 1}.txt'
            ocr_path = os.path.join(OUTPUT_OCR_DIR, ocr_filename)
            with open(ocr_path, 'w', encoding='utf-8') as ocr_file:
                ocr_file.write(ocr_text)
            print(f'OCR saved: {ocr_path}')

def ocr_image_bytes(image_bytes):
    image = Image.open(io.BytesIO(image_bytes))
    text = pytesseract.image_to_string(image)
    return text

def parse_page_ranges(page_str):
    pages = set()
    for part in page_str.split(','):
        if '-' in part:
            start, end = part.split('-')
            pages.update(range(int(start), int(end) + 1))
        else:
            pages.add(int(part))
    return sorted(pages)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Extract images and OCR from PDF pages.')
    parser.add_argument('--file', type=str, required=True, help='Path to PDF file (relative to workspace or absolute)')
    parser.add_argument('--pages', type=str, required=True, help='Pages to extract (e.g. "1,3-5,7")')
    args = parser.parse_args()

    pdf_path = args.file if os.path.isabs(args.file) else os.path.join('soc2_reports', args.file)
    pages = parse_page_ranges(args.pages)
    extract_images_from_pdf(pdf_path, pages)
    print('Image extraction and OCR complete.')
