# Objective Page Navigation Fix

## Problem Identified

**Symptoms:**
- Objective text clicks navigate to WRONG pages
- Offsets are inconsistent:
  - CC7.2: Off by 12 pages (navigates to 104, should be 92)
  - CC1.3: Off by 31 pages (navigates to 84, should be 53)
  - C1.2: Off by 2 pages (navigates to 113, should be 111)

**Root Cause:**
Objectives were using `find_page_refs()` which searches text and returns the PDF page number from `=== PAGE X ===` markers. These are sequential PDF pages (1, 2, 3...), NOT the document page numbers (53, 92, 111...).

Controls use a different method: `get_page_for_line()` which looks up the line_ref in the full document and finds the PAGE marker that precedes it, returning the correct document page number.

## Solution Implemented

### 1. Updated objective extraction to use `get_page_for_line()`

**File:** `backend/app/extractors/objective_extractor.py`

Changed the page_refs extraction logic from:
```python
# OLD METHOD - searches text and finds wrong pages
page_refs = find_page_refs(objective_text, full_text)
```

To:
```python
# NEW METHOD - uses line_ref with get_page_for_line (same as controls)
page_refs = []
if line_ref is not None and full_doc_lines:
    try:
        from ..pdf_handler import get_page_for_line
        page_num = get_page_for_line(full_doc_lines, line_ref)
        if page_num:
            page_refs = [page_num]
    except Exception as e:
        # Fallback to old method
        page_refs = find_page_refs(objective_text, full_text)
```

### 2. Reset toc_page_offset to 0

**Action Required:** Run SQL update to set `toc_page_offset = 0` for scan 3
```sql
UPDATE scan SET toc_page_offset = 0 WHERE id = 3;
```

User confirmed: "Page offset should be 0 as in this case the document page number is the same as the TOC pages"

### 3. Created backfill script

**File:** `backfill_objective_page_refs_v2.py`

This script will:
1. Update toc_page_offset to 0 for scan 3
2. Load extracted text with page markers
3. For each objective, use `get_page_for_line(line_ref)` to get correct page
4. Update page_refs with corrected values

## Next Steps

### When Docker is running:

1. **Run the backfill script:**
   ```bash
   cd "c:\Users\bklumpp\OneDrive - NANDPS\Documents\Python Scripts\SOCAnalyzer5"
   docker compose exec backend python /app/backfill_objective_page_refs_v2.py
   ```

2. **Restart frontend to pick up backend changes:**
   ```bash
   docker compose restart frontend
   ```

3. **Test objective navigation:**
   - Click on objective text for CC7.2, CC1.3, C1.2
   - Verify PDF navigates to correct pages (92, 53, 111 respectively)

## Technical Details

### How Controls Get Page Refs

Controls use:
1. **Line number** (`source_start_line`) - the line where control starts in the document
2. **Full document lines** (`text_lines`) - array of all lines with page markers
3. **get_page_for_line(text_lines, line_num)** - walks through lines, finds the `=== PAGE X ===` marker that precedes the line

Example:
```
Line 100: === PAGE 92 ===
Line 101: CC7.2: The Company has implemented...
```
`get_page_for_line(lines, 101)` returns `92` because line 100 has the PAGE marker.

### Why Objectives Were Wrong

Objectives were using `find_page_refs()` which:
1. Splits text by page markers
2. Searches for objective text in each section
3. Returns the section number (which is the PDF page, not document page)

Example:
```
=== PAGE 1 ===
... (cover page)
=== PAGE 2 ===
... (TOC)
=== PAGE 47 ===
CC7.2: The Company has implemented...
```

`find_page_refs()` would find CC7.2 in section 47, return [47], but this is PDF page 47, not document page 92!

### The Fix

Now objectives use the same method as controls:
- They already have `line_ref` from extraction
- We pass `full_doc_lines` (the full document with page markers)
- We use `get_page_for_line(full_doc_lines, line_ref)` to get the correct document page

This ensures consistent, correct page navigation for both controls and objectives.

## Files Modified

1. ✅ `backend/app/extractors/objective_extractor.py` - Updated page_refs extraction logic
2. ✅ `backfill_objective_page_refs_v2.py` - Created backfill script
3. ⏳ Database scan table - Need to run: `UPDATE scan SET toc_page_offset = 0 WHERE id = 3`
4. ⏳ Database control_objective table - Need to run backfill script

## Verification Steps

After running the backfill script:

1. **Check toc_page_offset:**
   ```sql
   SELECT id, pdf_filename, toc_page_offset FROM scan WHERE id = 3;
   ```
   Expected: `toc_page_offset = 0`

2. **Check objective page_refs:**
   ```sql
   SELECT objective_id, line_ref, page_refs FROM control_objective WHERE scan_id = 3 LIMIT 5;
   ```
   Expected: page_refs should match document pages, not PDF pages

3. **Test navigation:**
   - Click CC7.2 objective text → PDF should navigate to page 92
   - Click CC1.3 objective text → PDF should navigate to page 53
   - Click C1.2 objective text → PDF should navigate to page 111
