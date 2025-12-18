# Manual Extraction Feature - Implementation Complete

## Overview
Implemented manual extraction feature for CUECs and Subservice Organizations, allowing users to extract from specific PDF pages when automatic extraction struggles.

## Implementation Summary

### Backend Components

#### 1. Configuration (`backend/app/config.py`)
Added settings:
- `MANUAL_EXTRACTION_CONFIDENCE_BOOST = 0.2` - Confidence boost for manually extracted items
- `MANUAL_EXTRACTION_SIMILARITY_THRESHOLD = 0.80` - Deduplication threshold (80% similarity)
- `MANUAL_EXTRACTION_LOG_PATH = 'data/logs/manual_extractions.log'` - Separate log file

#### 2. Service Layer (`backend/app/services/manual_extraction_service.py`)
Complete implementation with:

**Helper Functions:**
- `parse_page_ranges(pages_str)` - Parses "5,7-9,12" → [5,7,8,9,12] with validation
- `extract_text_from_pages(pdf_bytes, page_numbers)` - PyMuPDF extraction from specific pages
- `calculate_similarity(text1, text2)` - SequenceMatcher ratio for deduplication
- `log_manual_extraction()` - JSON logging to separate file

**Main Functions:**
- `manual_extract_cuecs(scan_id, pages, db, username)` - Full CUEC extraction pipeline
- `manual_extract_subservice_orgs(scan_id, pages, db, username)` - Full subservice org extraction

**Two-Phase Logic:**
1. Extract from specified pages
   - Check for duplicates using 80% similarity threshold
   - Boost confidence by +0.2 (minimum HIGH_CONFIDENCE_THRESHOLD)
   - Map frameworks (CUECs only)
   - Update edit_log

2. Invalidate false positives
   - Find high-confidence items NOT on specified pages
   - Set confidence to 0
   - Update edit_log with invalidation reason

#### 3. API Endpoint (`backend/app/routers/report_router.py`)
```python
@router.post("/report/{scan_id}/manual-extract")
async def manual_extract(scan_id: int, data: dict, db, current_user: User)
```
- Validates entity_type ("cuec" or "subservice_org")
- Validates page ranges
- Calls appropriate service function
- Returns extraction results

### Frontend Components

#### 1. Dialog Component (`frontend/src/components/report/ManualExtractionDialog.tsx`)
- Material-UI dialog with page input field
- Real-time validation with regex `/^[\d,\s-]+$/`
- Preview showing parsed page count
- Loading indicator during extraction
- Success message with counts (new/updated/invalidated)
- Auto-refresh after completion

#### 2. CUEC Tab Integration (`frontend/src/components/report/tabs/ReportCuecsTab.tsx`)
- Added "Manual Extract" button with PlaylistAdd icon
- Opens dialog with entityType="cuec"
- Positioned next to "Add CUEC" button

#### 3. Subservice Org Tab Integration (`frontend/src/components/report/tabs/ReportSuborgsTab.tsx`)
- Added "Manual Extract" button with PlaylistAdd icon
- Opens dialog with entityType="subservice_org"
- Positioned next to "Add Subservice Org" button

## Usage

### User Workflow
1. Navigate to CUECs or Subservice Orgs tab
2. Click "Manual Extract" button
3. Enter page numbers (e.g., "5, 7-9, 12")
4. Preview shows: "Will extract from 5 pages: 5, 7, 8, 9, 12"
5. Click "Extract" button
6. System processes extraction:
   - Extracts text from specified pages
   - Runs extractor on text
   - Maps frameworks (CUECs only)
   - Deduplicates at 80% similarity
   - Boosts confidence +0.2 (min 0.75)
   - Invalidates high-confidence items NOT on those pages
7. Dialog shows results:
   - X new items added
   - X items updated (confidence boosted)
   - X items invalidated
8. Page auto-refreshes with updated data

## Technical Details

### Deduplication Logic
- Uses `difflib.SequenceMatcher` for similarity calculation
- 80% similarity threshold (configurable)
- Compares extracted text against existing items
- For duplicates: boosts confidence instead of creating new item

### Confidence Management
- Boost: `min(1.0, current_confidence + 0.2)`
- Minimum after boost: `HIGH_CONFIDENCE_THRESHOLD` (0.75)
- Invalidation: sets confidence to 0 for items NOT on specified pages

### Framework Mapping
- CUEC extraction includes framework mapping
- Uses existing `_run_control_framework_mapping()` function
- Maps extracted CUECs to TSC and COSO criteria

### Edit Log Tracking
Appends to `edit_log` field:
```
[YYYY-MM-DD HH:MM by username] Manual extraction: confidence 0.65 → 0.85 (from pages: 45-48)
[YYYY-MM-DD HH:MM by username] Invalidated by manual extraction (not on pages: 45-48): 0.90 → 0.00
```

### Logging
Separate log file at `data/logs/manual_extractions.log` with JSON entries:
```json
{
  "timestamp": "2025-01-07T10:30:45.123Z",
  "scan_id": 123,
  "entity_type": "cuec",
  "pages": [45, 46, 47, 48],
  "username": "john.doe",
  "new_count": 3,
  "updated_count": 2,
  "invalidated_count": 1
}
```

## Testing Checklist

- [ ] Open scan with missing CUECs
- [ ] Click "Manual Extract" on CUECs tab
- [ ] Enter valid page range (e.g., "45-48")
- [ ] Verify preview shows correct page count
- [ ] Click Extract and wait for completion
- [ ] Verify success message shows counts
- [ ] Verify page refreshes automatically
- [ ] Check new CUECs have confidence ≥ 0.75
- [ ] Check existing duplicates have boosted confidence
- [ ] Check false positives have confidence = 0
- [ ] Verify edit_log tracking on affected items
- [ ] Check `data/logs/manual_extractions.log` for entry
- [ ] Repeat test for Subservice Orgs tab

## Files Modified

### Backend
- `backend/app/config.py` - Added manual extraction settings
- `backend/app/services/manual_extraction_service.py` - NEW FILE (400+ lines)
- `backend/app/routers/report_router.py` - Added manual_extract endpoint

### Frontend
- `frontend/src/components/report/ManualExtractionDialog.tsx` - NEW FILE (210+ lines)
- `frontend/src/components/report/tabs/ReportCuecsTab.tsx` - Added button and dialog
- `frontend/src/components/report/tabs/ReportSuborgsTab.tsx` - Added button and dialog

## Deployment Status

✅ Backend restarted with new endpoint
✅ Frontend rebuilt and restarted with dialog
✅ Manual extraction feature live and ready for testing

## Future Enhancements

Potential improvements:
1. Batch extraction across multiple page ranges
2. Preview extracted items before committing
3. Undo/rollback manual extraction
4. Export manual extraction history report
5. Confidence boost customization per extraction
6. Visual page range selector with PDF preview
