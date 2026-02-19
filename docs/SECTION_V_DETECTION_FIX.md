# Section V Detection Issue - Analysis and Fix Plan

## Problem Statement

Adobe SOC 2 report has 5 sections, but only 4 are detected:
- ✅ Section I: Independent Service Auditor's Report (Page 3)
- ✅ Section II: Assertion of Adobe Management (Page 8)
- ✅ Section III: Description of System (Page 10)
- ✅ Section IV: Trust Services Criteria / Controls (Page 46)
- ❌ **Section V: Other Information Provided (Page 112)** - NOT DETECTED

Result: Control_Descriptions section incorrectly ends at page 131 (last page) instead of page 111.

## Root Cause

**Location**: [backend/app/pdf_handler.py](backend/app/pdf_handler.py#L638)

The GPT-based `find_section_candidates` function only analyzes the first 10-20 pages:

```python
def extract_pages(text_lines, max_pages):
    """Extract text up to max_pages from document."""
    page_count = 0
    extracted_lines = []
    for line in text_lines:
        extracted_lines.append(line)
        if line.startswith('=== PAGE '):
            page_count += 1
            if page_count >= max_pages:  # ← STOPS AT 10-20 PAGES
                break
    return '\n'.join(extracted_lines)
```

**Result**: Section V on page 112 is never analyzed by GPT.

## Why This Happens

Current logic:
1. Extract first 10 pages → Send to GPT → Get sections
2. If confidence < 80%, extract 20 pages → Re-send to GPT
3. GPT returns sections found in those 20 pages only
4. Any sections beyond page 20 are never discovered

## Solution Options

### Option A: Parse Full TOC (RECOMMENDED)

Instead of analyzing pages sequentially, extract the complete Table of Contents (usually pages 1-3) and parse ALL section entries:

```python
def extract_full_toc(text_lines):
    """Extract complete TOC section from document."""
    toc_start = -1
    toc_end = -1
    
    for i, line in enumerate(text_lines):
        # Look for TOC markers
        if 'table of contents' in line.lower() or 'contents' in line.lower():
            toc_start = i
        # TOC usually ends when first main section starts
        if toc_start > 0 and (line.startswith('I.') or 'Independent Service Auditor' in line):
            toc_end = i
            break
    
    if toc_start > 0 and toc_end > toc_start:
        return '\n'.join(text_lines[toc_start:toc_end])
    return None
```

Then send ONLY the TOC to GPT with a prompt like:
```
Parse this Table of Contents and return ALL sections with their page numbers:
[TOC TEXT]

Return JSON with: {"sections": [{"name": "...", "toc_page": N, "roman_numeral": "I"}, ...]}
```

**Advantages**:
- Finds ALL sections regardless of where they appear
- Uses minimal tokens (TOC is only 1-2 pages)
- More reliable than analyzing arbitrary page ranges

### Option B: Increase Page Limit

Simple but wasteful:
```python
# Change from 10-20 pages to 120 pages
extracted_text = extract_pages(lines, max_pages=120)
```

**Disadvantages**:
- Wastes tokens analyzing content when we only need TOC
- Slower processing
- Still might miss sections beyond 120 pages in longer reports

### Option C: Two-Stage Detection

1. Stage 1: Parse TOC to get section list with page numbers
2. Stage 2: For each section, extract 2-3 pages around its start to confirm heading match

**Advantages**:
- Most accurate
- Validates TOC entries against actual document

**Disadvantages**:
- More complex
- Multiple GPT calls (slower, more expensive)

## Recommended Implementation

**Option A** - Parse full TOC comprehensively:

1. Extract TOC section (pages 1-3 usually)
2. Send to GPT with specialized prompt:
   ```
   Extract ALL sections from this Table of Contents.
   Include: section name, roman numeral (I, II, III, IV, V), page number.
   ```
3. For each TOC entry, map to document page using offset
4. Return ALL sections, including "Unknown" topic types

## Code Changes Required

### File: backend/app/pdf_handler.py

**Function to Add**:
```python
def extract_toc_section(text_lines, max_pages=5):
    """Extract just the TOC section from document."""
    toc_lines = []
    in_toc = False
    pages_seen = 0
    
    for line in text_lines:
        if line.startswith('=== PAGE '):
            pages_seen += 1
            if pages_seen > max_pages:
                break
        
        # Detect TOC start
        if not in_toc and ('table of contents' in line.lower() or 
                           line.strip().lower() == 'contents'):
            in_toc = True
        
        if in_toc:
            toc_lines.append(line)
            
            # Stop when we hit first main section
            if line.strip().startswith('I.') and 'Independent' in line:
                break
    
    return '\n'.join(toc_lines)
```

**Modify find_section_candidates**:
```python
def find_section_candidates(text, model=DEFAULT_GPT_MODEL, ...):
    lines = text.splitlines()
    
    # NEW: Extract and parse TOC
    toc_text = extract_toc_section(lines, max_pages=5)
    
    # Send TOC to GPT with specialized prompt
    toc_prompt = """
    Parse this Table of Contents and extract ALL section entries.
    
    For each section, identify:
    - name: Full section title
    - roman_numeral: Section number (I, II, III, IV, V, etc.)
    - toc_page: Page number listed in TOC
    
    Return ALL sections found, not just the first few.
    
    TOC Content:
    {toc_text}
    
    Return JSON: {{"sections": [{{"name": "...", "roman_numeral": "...", "toc_page": N}}]}}
    """
    
    result = gpt_extract(toc_prompt.format(toc_text=toc_text), 'section_detection')
    # ... rest of processing
```

## Testing Plan

1. Test with Adobe report (has 5 sections)
2. Verify all sections detected:
   ```sql
   SELECT topic, clean_heading, DOC_page_ref, end_DOC_page_ref 
   FROM (SELECT jsonb_array_elements(result_json->'sections') as section FROM scan WHERE id = 2) sub
   SELECT section->>'topic', section->>'clean_heading', 
          section->>'DOC_page_ref', section->>'end_DOC_page_ref';
   ```
3. Expected: 5 sections, Section V at page 112, Control_Descriptions ends at page 111
4. Regression test with other reports (Anaqua, SimpleLegal)

## Impact

- ✅ Fixes: Section boundary detection for reports with late sections
- ✅ Prevents: Objectives extracted from wrong sections
- ✅ Improves: Control page references accuracy
- ⚠️ Requires: Full re-scan of affected reports

## Alternative Workaround

If full fix is too complex, add a post-processing step to trim Control_Descriptions when "Other Information" appears in text:

```python
# After sections are detected
for i, section in enumerate(sections):
    if section['topic'] == 'Control_Descriptions':
        # Search for "Other Information" marker
        search_text = text[section['offset']:section['end_offset']]
        other_info_pos = search_text.find('Other Information Provided')
        if other_info_pos > 0:
            # Truncate section and create new "Other_Information" section
            # ... adjust boundaries
```

This is a band-aid but would work until proper TOC parsing is implemented.
