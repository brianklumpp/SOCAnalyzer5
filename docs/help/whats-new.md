# What's New

## Version 5.1.0 - December 18, 2025

### 🆕 Management Response Extraction

**Automatic Extraction**
- Automatically extracts management's responses to control deviations from SOC reports
- Uses GPT semantic search with 3 cascading strategies:
  1. Search nearby pages (configurable window)
  2. Expand search window if not found
  3. Find dedicated "Management Response" section (cached for 7 days)
- Only extracts responses with ≥50% confidence (configurable)
- Identifies duplicate responses across multiple controls

**Data Storage**
- New database fields: `management_response_text`, `management_response_page_refs`, `management_response_confidence`, `response_detection_method`
- Alembic migration: `2ac3574edb1e` (applied)
- Stores page references and line numbers for traceability

**UI Display**
- Color-coded confidence badges (green >70%, orange 50-70%, red <40%)
- Page reference links to source location
- "Also applies to X other deviations" indicator for shared responses
- Manual edit capability with save/cancel
- Regenerate button to re-extract from report

**GPT Integration**
- Deviation summaries include management response in context
- Executive summary displays remediation plans (truncated to 200 chars)
- GPT acknowledges planned remediation in summaries

**API Endpoints**
- `GET /report/{scan_id}/deviations/{control_id}/management-response` - Fetch with related controls
- `PATCH /report/{scan_id}/deviations/{control_id}/management-response` - Manual edit
- `POST /report/{scan_id}/deviations/{control_id}/regenerate-management-response` - Re-extract

**Configuration**
- `MANAGEMENT_RESPONSE_SEARCH_WINDOW=1` - Pages to search after control
- `MANAGEMENT_RESPONSE_MIN_CONFIDENCE=0.5` - Minimum confidence to store
- Redis caching with 7-day TTL for section locations

### 🔧 CUEC Confidence Scoring Adjustments

**Refined Weights**
- GPT opinion "yes" boost: +0.2 → +0.1 (since already +0.3 for finding CUEC)
- Keyword proximity threshold: <5 → <2 words
- New penalty: GPT opinion "maybe" = -0.2
- Clarified entity responsibility vs individual user responsibility

### 🐛 Deviation Tab Authentication Fix

**Resolved**
- Fixed 401 Unauthorized errors when loading deviation tab
- Changed from plain `axios` to authenticated `api` client
- Ensures Bearer token included in all requests
- Windows SSO authentication now works properly

## Version 5.0.0 - December 2025

### Control Merge Enhancements 🎯

**Lower Auto-Merge Threshold**
- Reduced from 85% to 70% for more aggressive duplicate detection
- Catches 30-50% more duplicates automatically
- Configurable via `AUTO_MERGE_MIN_CONFIDENCE` environment variable

**Page Proximity Scoring**
- Added +5% bonus for controls on adjacent pages
- Detects controls split across PDF chunk boundaries
- Improves accuracy for large reports

**Incomplete Control Penalties**
- Automatic -20% confidence reduction for missing required fields
- Flags controls missing: control_id, description, test, or test results
- Helps identify low-quality extractions needing review

**Merge History Tracking**
- Full audit trail of all merge operations
- New `merge_history` JSON column in database
- Tracks timestamps, confidence scores, and merge reasons
- Separate tracking for auto vs manual merges

**Enhanced Scoring Algorithm**
- Description similarity: 70% → 65%
- Page proximity: NEW +5%
- TSC/COSO mapping: 15% (unchanged)
- Test procedure: 10% (unchanged)
- Deviation agreement: 5% (unchanged)

### Deviations Tab Improvements ✨

**High Confidence Filtering**
- Only shows deviations with ≥75% confidence
- Automatically excludes merged controls (confidence = 0%)
- Eliminates duplicate deviations after merging
- Consistent with Controls tab filtering

### Frontend Performance 🚀

**Batch Edit Optimization**
- Increased Node.js heap size to 8GB
- Added loading spinner for tables with 50+ rows
- Disabled ESLint in development mode
- Warning tooltip for tables with 100+ rows

**Memory Management**
- Fixed TypeScript compiler memory crashes
- Improved rendering performance for large datasets
- Better handling of batch operations

### Configuration Updates ⚙️

**New Environment Variables**
```bash
HIGH_CONFIDENCE_THRESHOLD=0.75  # System-wide confidence standard
AUTO_MERGE_MIN_CONFIDENCE=0.70  # Auto-merge threshold
PAGE_PROXIMITY_WEIGHT=0.05      # Bonus for adjacent pages
CONTROL_INCOMPLETE_PENALTY=0.20 # Penalty for missing fields
```

**API Enhancements**
- `/config/runtime` now exposes threshold values
- `/help/index` and `/help/content/{id}` endpoints added
- `/report/{scan_id}/deviations` filtered by confidence

### Database Schema Changes 📊

**New Column: `merge_history`**
- JSON array tracking all merge events
- Schema:
  ```json
  [{
    "timestamp": "2025-12-03T12:34:56",
    "type": "auto|manual",
    "confidence": 0.75,
    "merged_from_ids": ["123", "456"],
    "reason": "Automated cleanup with 0.75 similarity"
  }]
  ```

**Migration Applied**
- Alembic migration: `20250107_add_merge_history`
- Backward compatible (nullable column)
- Existing scans unaffected

### Documentation System 📚

**In-App Help**
- Press F1 to open help dialog
- Searchable help topics
- Markdown-based content
- Contextual help from feature buttons
- Deep linking support (`?help=topic-id`)

## Upgrade Notes

### Breaking Changes
None - all changes are backward compatible

### Recommended Actions
1. Review auto-merged controls in existing scans
2. Check merge_history for audit trail
3. Update confidence thresholds if needed via environment variables
4. Review flagged incomplete controls (< 75% confidence)

### Performance Tips
- First scan after restart may be slower (cache warming)
- Large reports benefit most from new merge threshold
- Batch edit performance improved for all table sizes

## Bug Fixes

- Fixed deviations showing duplicates after merging
- Fixed frontend memory crashes during batch edit
- Fixed column name mismatches in deviations endpoint
- Fixed page reference extraction from JSON arrays

## Known Issues

- Very large PDFs (>500 pages) may timeout
- Scanned image PDFs require OCR preprocessing
- Some non-standard control formats need manual review

## Previous Versions

### Version 4.x
- SOC 1 Type II support
- Enhanced framework mapping
- Pattern library for control verification
- 5-factor confidence scoring

### Version 3.x
- SOC 2 Type II initial release
- Multi-framework support (TSC/COSO)
- Subservice organization extraction
- Executive summary generation

