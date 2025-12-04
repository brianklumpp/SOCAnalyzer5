# What's New

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

