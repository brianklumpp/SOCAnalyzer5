import fitz
import sys
import os

# Usage: python debug_pdf_extract.py <pdf_path> <page_numbers_comma_separated>
# Example: python debug_pdf_extract.py ../soc2_reports/Bitwarden.pdf 3,27

def extract_all_modes(pdf_path, page_numbers):
    doc = fitz.open(pdf_path)
    for page_num in page_numbers:
        if page_num < 1 or page_num > len(doc):
            print(f"Page {page_num} out of range.")
            continue
        page = doc[page_num-1]
        print(f"\n{'='*40}\nPage {page_num}\n{'='*40}")
        # get_text('text')
        print("\n--- get_text('text') ---\n")
        try:
            text = page.get_text("text")
            print(text)
            print(f"[Length: {len(text)} characters]")
            print("[Summary]")
            print(summarize_text(text))
        except Exception as e:
            print(f"Error: {e}")
        # get_text('blocks')
        print("\n--- get_text('blocks') ---\n")
        try:
            blocks = page.get_text("blocks")
            print(f"[Block count: {len(blocks)}]")
            for block in blocks:
                print(block)
            print("[Summary]")
            print(summarize_blocks(blocks))
        except Exception as e:
            print(f"Error: {e}")
        # get_text('dict')
        print("\n--- get_text('dict') ---\n")
        try:
            d = page.get_text("dict")
            print(f"[Keys: {list(d.keys())}]")
            print(d)
            print("[Summary]")
            print(summarize_dict(d))
        except Exception as e:
            print(f"Error: {e}")
        # get_text('rawdict')
        print("\n--- get_text('rawdict') ---\n")
        try:
            rd = page.get_text("rawdict")
            print(f"[Keys: {list(rd.keys())}]")
            print(rd)
            print("[Summary]")
            print(summarize_rawdict(rd))
        except Exception as e:
            print(f"Error: {e}")

def summarize_text(text):
    lines = text.strip().splitlines()
    preview = '\n'.join(lines[:5]) + ('\n...' if len(lines) > 5 else '')
    return f"Preview:\n{preview}\nTotal lines: {len(lines)}, Total characters: {len(text)}"

def summarize_blocks(blocks):
    summary = f"Block count: {len(blocks)}\n"
    for i, block in enumerate(blocks[:3]):
        if len(block) > 4 and isinstance(block[4], str):
            text_preview = block[4][:60].replace('\n', ' ')
        else:
            text_preview = str(block[4])[:60]
        summary += f"  Block {i+1}: bbox={block[:4]}, text='{text_preview}'...\n"
    if len(blocks) > 3:
        summary += f"  ... ({len(blocks)-3} more blocks)\n"
    return summary

def summarize_dict(d):
    blocks = d.get('blocks', [])
    lines = sum(len(b.get('lines', [])) for b in blocks)
    spans = sum(len(l.get('spans', [])) for b in blocks for l in b.get('lines', []))
    summary = f"Blocks: {len(blocks)}, Lines: {lines}, Spans: {spans}\n"
    if blocks:
        b = blocks[0]
        summary += f"  First block type: {b.get('type')}, lines: {len(b.get('lines', []))}\n"
        if b.get('lines'):
            l = b['lines'][0]
            summary += f"    First line spans: {len(l.get('spans', []))}\n"
            if l.get('spans'):
                s = l['spans'][0]
                summary += f"      First span text: '{s.get('text', '')[:60]}'\n"
    return summary

def summarize_rawdict(rd):
    keys = list(rd.keys())
    summary = f"Top-level keys: {keys}\n"
    for k in keys:
        v = rd[k]
        if isinstance(v, list):
            summary += f"  {k}: {len(v)} items\n"
        elif isinstance(v, dict):
            summary += f"  {k}: dict with {len(v)} keys\n"
        else:
            summary += f"  {k}: {type(v).__name__}\n"
    return summary

def main():
    if len(sys.argv) < 3:
        print("Usage: python debug_pdf_extract.py <pdf_path> <page_numbers_comma_separated>")
        sys.exit(1)
    pdf_path = sys.argv[1]
    page_numbers = [int(x) for x in sys.argv[2].split(",") if x.strip().isdigit()]
    extract_all_modes(pdf_path, page_numbers)

if __name__ == "__main__":
    main()
