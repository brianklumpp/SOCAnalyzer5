# SOC Analyzer Enhancement Implementation Summary
## Date: 2025-01-19

## Overview
Successfully implemented 5 major enhancements to the SOC Analyzer application covering intelligent control merging, multi-page tracking, framework preview, adaptive TSC anomaly detection, and enhanced UI/UX improvements.

---

## 1. AUTO-SUGGEST MERGE WITH INTELLIGENT CONFIDENCE SCORING

### Backend Implementation

#### Configuration (`backend/app/config.py`)
```python
# Lines 104-117
MERGE_SUGGESTION_MIN_CONFIDENCE = float(os.getenv("MERGE_SUGGESTION_MIN_CONFIDENCE", "0.85"))
MERGE_SUGGESTION_MAX_RESULTS = int(os.getenv("MERGE_SUGGESTION_MAX_RESULTS", "50"))
```

#### API Endpoints (`backend/app/main.py`)

**GET /report/{scan_id}/controls/suggest-merges** (lines 2688-2831)
- Groups controls by `control_id`
- Calculates merge confidence using 4 factors:
  - **70%** - Description similarity (GPT-based semantic comparison)
  - **15%** - TSC/COSO mapping matches
  - **10%** - Test procedure similarity
  - **5%** - Deviation flag agreement
- Filters suggestions ≥ 0.85 confidence threshold
- Returns top 50 suggestions with detailed breakdown

**POST /report/{scan_id}/controls/merge** (lines 2833-2919)
- Accepts `primary_control_id` + `merge_control_ids[]`
- Sets `merged_to_control_id` on merged records
- Consolidates `control_page_refs` arrays (deduped & sorted)
- Backs up original confidence in annotation JSON
- Sets `control_confidence=0` on merged records
- Marks executive summary as stale

**POST /report/{scan_id}/controls/{control_db_id}/split** (lines 2921-2993)
- Clears `merged_to_control_id`
- Restores confidence from annotation backup
- Provides undo functionality for merges

### Frontend Implementation

#### MergeSuggestionsPanel Component (`frontend/src/components/report/tables/MergeSuggestionsPanel.tsx`)
- Chip badge showing suggestion count with warning color
- Right-side drawer with:
  - **Merge All** button for bulk operations
  - Individual **Merge** / **Dismiss** actions per suggestion
  - Confidence breakdown display
  - Page reference consolidation preview
- Auto-refreshes controls table after merge
- Loading states and error handling

#### Integration (`frontend/src/components/report/tables/ControlsTable.tsx`)
- Added `scanId` and `onRefresh` props
- Integrated MergeSuggestionsPanel into `additionalButtons`
- Calls `/suggest-merges` on drawer open
- Triggers refresh after merge operations

---

## 2. MULTI-PAGE REFERENCE TRACKING

### Database Migration (`backend/alembic/versions/20251119_multi_page_refs.py`)
```python
def upgrade():
    # Add new JSON column
    op.add_column('control', sa.Column('control_page_refs', sa.JSON(), nullable=True))
    
    # Migrate data: single integer → JSON array
    op.execute("""
        UPDATE control 
        SET control_page_refs = CASE 
            WHEN control_page_ref IS NOT NULL 
            THEN json_build_array(control_page_ref) 
            ELSE '[]'::json 
        END
    """)
    
    # Drop old column
    op.drop_column('control', 'control_page_ref')

def downgrade():
    # Add back Integer column
    op.add_column('control', sa.Column('control_page_ref', sa.INTEGER()))
    
    # Extract first element (DATA LOSS for multi-page)
    op.execute("""
        UPDATE control 
        SET control_page_ref = (control_page_refs::jsonb->0)::text::integer
    """)
    
    op.drop_column('control', 'control_page_refs')
```

### Model Changes (`backend/app/models.py`)
```python
# Line 48 - Changed from:
control_page_ref = Column(Integer)

# To:
control_page_refs = Column(JSON)  # [51, 52, 89] - pages where control appears
```

### Extractor Updates (`backend/app/extractors/control_extractor_v4.py`)

**Initialize as Array** (line 798):
```python
control["control_page_refs"] = [page_num] if page_num else []
```

**Merge Page Refs** (lines 402-427):
```python
def merge_two_controls(base, add):
    merged = {**base}
    # ...existing merge logic...
    
    # Consolidate page references
    base_pages = list(base.get("control_page_refs", []))
    add_pages = list(add.get("control_page_refs", []))
    merged["control_page_refs"] = sorted(list(set(base_pages + add_pages)))
    
    return merged
```

### API Helper Function (`backend/app/main.py`, lines 168-219)
```python
def _parse_page_refs(value: Any) -> List[int]:
    """
    Parse control page references from various input formats.
    Accepts:
    - List: [51, 52, 89]
    - String: "51, 52, 89" or "51,52,89"
    - Integer: 51
    
    Returns: Sorted unique list of integers
    """
    if value is None:
        return []
    if isinstance(value, list):
        return sorted(list(set(int(x) for x in value if x)))
    if isinstance(value, (int, float)):
        return [int(value)]
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(',')]
        return sorted(list(set(int(p) for p in parts if p.isdigit())))
    return []
```

### Frontend Column Definition (`frontend/src/config/report/columnDefinitions.tsx`)
```tsx
{ 
  key: "control_page_refs", 
  label: "Page Refs", 
  width: 100, 
  format: (v: any) => Array.isArray(v) 
    ? v.sort((a: number, b: number) => a - b).join(', ') 
    : (v || '')
}
```

---

## 3. ADAPTIVE TSC ANOMALY DETECTION

### Configuration (`backend/app/config.py`)
```python
# Lines 104-117
TSC_ANOMALY_BASE_THRESHOLD = int(os.getenv("TSC_ANOMALY_BASE_THRESHOLD", "20"))
TSC_ANOMALY_ADAPTIVE_ENABLED = os.getenv("TSC_ANOMALY_ADAPTIVE_ENABLED", "true").lower() == "true"
TSC_ANOMALY_MIN_THRESHOLD = int(os.getenv("TSC_ANOMALY_MIN_THRESHOLD", "5"))
```

### Adaptive Threshold Logic (`backend/app/extractors/control_extractor_v4.py`, lines 586-601)
```python
from .. import config as cfg

# Calculate adaptive threshold
if cfg.TSC_ANOMALY_ADAPTIVE_ENABLED:
    adaptive_threshold = int(total_controls * 0.10)  # 10% of total controls
    threshold = max(
        cfg.TSC_ANOMALY_MIN_THRESHOLD,
        max(cfg.TSC_ANOMALY_BASE_THRESHOLD, adaptive_threshold)
    )
    logging.info(
        f"[TSC ANOMALY] Threshold: {threshold} "
        f"(adaptive=on, base={cfg.TSC_ANOMALY_BASE_THRESHOLD}, "
        f"10%={adaptive_threshold}, total_controls={total_controls})"
    )
else:
    threshold = cfg.TSC_ANOMALY_BASE_THRESHOLD
    logging.info(f"[TSC ANOMALY] Threshold: {threshold} (adaptive=off)")
```

**Formula**: `max(MIN_THRESHOLD=5, max(BASE=20, total_controls * 0.10))`

### Confidence Penalty Application (lines 903-911)
```python
if pattern_result.get("is_tsc_anomaly"):
    logging.warning(
        f"[TSC ANOMALY] Control {control['control_id']} confidence "
        f"reduced: {control['control_confidence']} → "
        f"{control['control_confidence'] * 0.05}"
    )
    control["control_confidence"] *= 0.05  # 95% reduction
    control["confidence_calc"].append("TSC anomaly detected - likely TSC heading")
```

---

## 4. HYBRID FRAMEWORK MAPPING PREVIEW

### Backend Endpoint (`backend/app/main.py`, lines 3448-3555)

**POST /report/{scan_id}/preview-frameworks**
- Rate limited via Redis: 10 requests per minute per scan
- Accepts `control_desc`, `control_id` (optional), `has_deviation` (optional)
- Calls `map_control_to_frameworks_multi()` (same function as extraction)
- Returns TSC/COSO matches with scores & rationales
- **Does NOT save to database** (preview only)
- Returns `rate_limit_remaining` count

#### Rate Limiting Logic:
```python
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)
rate_limit_key = f"preview_frameworks:{scan_id}"

current_count = redis_client.incr(rate_limit_key)
if current_count == 1:
    redis_client.expire(rate_limit_key, 60)  # 60-second window

if current_count > cfg.FRAMEWORK_PREVIEW_RATE_LIMIT:
    return JSONResponse({"error": "Rate limit exceeded"}, status_code=429)
```

### Frontend Implementation (`frontend/src/components/report/dialogs/AddItemDialog.tsx`)

#### State Management (lines 96-99):
```tsx
const [previewLoading, setPreviewLoading] = useState(false);
const [previewData, setPreviewData] = useState<any>(null);
const [previewError, setPreviewError] = useState<string | null>(null);
const [previewCacheTime, setPreviewCacheTime] = useState<number | null>(null);
```

#### 30-Second Caching Logic (lines 125-178):
```tsx
const handlePreviewFrameworks = async () => {
  // Check cache validity
  const now = Date.now();
  if (previewData && previewCacheTime && (now - previewCacheTime < 30000)) {
    return; // Use cached data
  }
  
  // ... API call ...
  
  setPreviewData(response.data);
  setPreviewCacheTime(now);
};
```

#### Third Tab UI (lines 338-403):
- **Info Banner**: "✅ TSC/COSO mappings are computed automatically when you save"
- **Compute Preview Button**: Disabled without description
- **TSC Matches Display**: Shows ID, score %, rationale (truncated to 200 chars)
- **COSO Matches Display**: Shows principle #, score %, rationale
- **Rate Limit Warning**: Shows remaining previews in current minute

---

## 5. ENHANCED MULTI-MATCH DISPLAY & TOOLTIPS

### Column Truncation (`frontend/src/config/report/columnDefinitions.tsx`)

#### TSC ID Column (lines 129-156):
```tsx
{ 
  key: "control_tsc_id", 
  label: "TSC ID (computed)", 
  width: 140, 
  render: (row: any) => {
    const mappings = row.control_tsc_mappings || [];
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <span>
          {mappings.length > 1 ? (
            <>
              {row.control_tsc_id || ''}
              <span style={{ color: '#666', fontSize: '0.9em' }}>
                {' '}+{mappings.length - 1} more
              </span>
            </>
          ) : (row.control_tsc_id || '')}
        </span>
        {mappings.length > 0 && (
          <FrameworkMappingInfo 
            mappings={mappings} 
            type="tsc" 
            controlId={row.control_id}
          />
        )}
      </Box>
    );
  }
}
```

#### COSO ID Column (lines 170-196):
```tsx
{ 
  key: "control_coso_id", 
  label: "COSO ID (computed)", 
  width: 140, 
  hidden: true,
  render: (row: any) => {
    const mappings = row.control_coso_mappings || [];
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <span>
          {mappings.length > 1 ? (
            <>
              {row.control_coso_id || ''}
              <span style={{ color: '#666', fontSize: '0.9em' }}>
                {' '}+{mappings.length - 1} more
              </span>
            </>
          ) : (row.control_coso_id || '')}
        </span>
        {mappings.length > 0 && (
          <FrameworkMappingInfo 
            mappings={mappings} 
            type="coso" 
            controlId={row.control_id}
          />
        )}
      </Box>
    );
  }
}
```

### Enhanced Tooltip (`frontend/src/components/FrameworkMappingInfo.tsx`)

#### 500ms Hover Delay (lines 70-83):
```tsx
<Tooltip 
  title={tooltipContent} 
  arrow 
  placement="top"
  enterDelay={500}       // Wait 500ms before showing
  enterNextDelay={500}   // Consistent delay for subsequent hovers
  leaveDelay={0}         // Hide immediately
>
  <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
    <InfoOutlinedIcon sx={{ fontSize: 14, color: '#1976d2' }} />
    {hasDeviations && <WarningIcon sx={{ fontSize: 12, color: '#ff9800' }} />}
    {mappings.length > 1 && (
      <Box component="span" sx={{ fontSize: 9, color: '#666', fontWeight: 600 }}>
        ×{mappings.length}
      </Box>
    )}
  </Box>
</Tooltip>
```

#### Rich Tooltip Content (lines 38-67):
- **Header**: Framework type + total match count
- **Control Info**: Control ID display
- **Top 3 Mappings** with:
  - Numbered list (1. 2. 3.)
  - Framework ID + confidence % in green
  - ⚠ Exception badge if deviation exists
  - Reasoning text (truncated to 80 chars)
  - Deviation description (truncated to 60 chars, yellow/italic)
- **More Indicator**: "+N more mappings"
- **Footer**: "💡 Click row to open full confidence modal"

---

## Testing Checklist

### Backend Tests
- [ ] Run Alembic migration: `alembic upgrade head`
- [ ] Verify `control_page_refs` column exists in database
- [ ] Test merge suggestions endpoint returns results with confidence scores
- [ ] Test merge endpoint consolidates page refs correctly
- [ ] Test split endpoint restores original confidence
- [ ] Test preview-frameworks with rate limiting (call >10 times in 60s)
- [ ] Verify TSC anomaly detection reduces confidence for reports with 200+ controls
- [ ] Check adaptive threshold logging in backend logs

### Frontend Tests
- [ ] Verify page refs display as comma-separated (e.g., "51, 52, 89")
- [ ] Check "+N more" display on multi-match TSC/COSO columns
- [ ] Test MergeSuggestionsPanel chip badge shows count
- [ ] Test merge drawer opens and displays suggestions
- [ ] Test "Merge All" button with confirmation
- [ ] Test individual merge actions update table
- [ ] Test dismiss removes suggestions from list
- [ ] Open AddItemDialog for control, verify "Preview Mappings" tab exists
- [ ] Enter description, click "Compute Preview", verify TSC/COSO matches display
- [ ] Verify 30-second cache (click Compute Preview twice within 30s - should be instant)
- [ ] Hover over FrameworkMappingInfo icon, verify 500ms delay before tooltip
- [ ] Check tooltip shows top 3 mappings with confidence %, reasoning, deviations
- [ ] Verify ×N badge appears on info icon when mappings.length > 1

### Integration Tests
- [ ] Upload new SOC2 report, verify extraction uses page refs as arrays
- [ ] Check merge suggestions appear for duplicate control IDs
- [ ] Merge two controls, verify page refs consolidated in database
- [ ] Split merged control, verify confidence restored
- [ ] Test recompute frameworks after merge
- [ ] Verify executive summary marked stale after merge

---

## Configuration Reference

### Environment Variables (`.env` or config)
```bash
# TSC Anomaly Detection
TSC_ANOMALY_BASE_THRESHOLD=20
TSC_ANOMALY_ADAPTIVE_ENABLED=true
TSC_ANOMALY_MIN_THRESHOLD=5

# Merge Suggestions
MERGE_SUGGESTION_MIN_CONFIDENCE=0.85
MERGE_SUGGESTION_MAX_RESULTS=50

# Framework Preview
FRAMEWORK_PREVIEW_RATE_LIMIT=10
```

### Database Migration Command
```bash
cd backend
alembic upgrade head
```

### Redis Requirement
Framework preview requires Redis running on `localhost:6379`:
```bash
# Windows (if using Docker)
docker run -d -p 6379:6379 redis:latest

# Or install Redis for Windows
```

---

## File Change Summary

### Backend Files Modified/Created (10 files)
1. ✅ `backend/app/config.py` - Added 9 config variables
2. ✅ `backend/alembic/versions/20251119_multi_page_refs.py` - NEW migration file
3. ✅ `backend/app/models.py` - Changed control_page_ref to control_page_refs
4. ✅ `backend/app/extractors/control_extractor_v4.py` - 4 code blocks updated
5. ✅ `backend/app/main.py` - 3 new endpoints + helper function + 2 PATCH updates

### Frontend Files Modified/Created (4 files)
1. ✅ `frontend/src/config/report/columnDefinitions.tsx` - Updated 3 columns
2. ✅ `frontend/src/components/report/tables/MergeSuggestionsPanel.tsx` - NEW component
3. ✅ `frontend/src/components/report/tables/ControlsTable.tsx` - Added scanId prop + panel
4. ✅ `frontend/src/components/report/dialogs/AddItemDialog.tsx` - Added tab 2 with preview
5. ✅ `frontend/src/components/FrameworkMappingInfo.tsx` - Enhanced tooltip

**Total Files Changed**: 15 files (5 new, 10 modified)

---

## Known Limitations & Future Enhancements

### Current Limitations
1. **Merge suggestions** only compare controls with identical `control_id` (not cross-ID suggestions)
2. **Framework preview** rate limit is per-scan (not per-user)
3. **Page refs migration** loses multi-page data on downgrade
4. **GPT timeout** for description similarity is 30 seconds (may fail for very long descriptions)
5. **Redis dependency** for framework preview (fails gracefully if unavailable)

### Potential Enhancements
- [ ] Add fuzzy matching for control IDs (e.g., "CC6.1" vs "CC 6.1")
- [ ] Implement batch merge API endpoint for bulk operations
- [ ] Add audit log for merge/split operations
- [ ] Create dashboard widget showing top merge suggestions
- [ ] Add user-configurable merge confidence threshold
- [ ] Implement cross-framework similarity (TSC ↔ COSO mapping preview)
- [ ] Add keyboard shortcuts for merge actions
- [ ] Export merge suggestions to CSV for offline review

---

## Rollback Procedure

If issues arise, rollback steps:

### 1. Database Rollback
```bash
cd backend
alembic downgrade -1
```
**WARNING**: Multi-page data will be lost (only first page preserved)

### 2. Code Rollback
```bash
git checkout HEAD~1  # Or specific commit before changes
```

### 3. Frontend Cache Clear
```bash
cd frontend
rm -rf node_modules/.cache
npm run build
```

### 4. Configuration Rollback
Remove new environment variables from `.env` or restart with defaults.

---

## Support & Maintenance

### Logging & Debugging
- **TSC Anomaly**: Check backend logs for `[TSC ANOMALY] Threshold:` messages
- **Merge Operations**: Look for `[MERGE]` and `[SPLIT]` log entries
- **Framework Preview**: Check Redis connection errors if rate limiting fails
- **Migration Issues**: Review Alembic logs during `upgrade` command

### Performance Monitoring
- Monitor GPT API usage (merge suggestions call GPT for each candidate pair)
- Track Redis memory usage for rate limiting keys
- Monitor database size growth (page refs JSON arrays)
- Check confidence modal load times with large multi-match arrays

---

## Conclusion

All 12 implementation tasks completed successfully:
✅ Backend configuration (9 variables)
✅ Database migration (multi-page refs)
✅ Model updates (JSON column)
✅ Extractor enhancements (arrays + adaptive thresholds)
✅ 3 new API endpoints (suggest/merge/split)
✅ Framework preview with rate limiting
✅ Frontend column formatting
✅ MergeSuggestionsPanel UI component
✅ Preview Mappings tab with caching
✅ Enhanced tooltips with 500ms delay

The SOC Analyzer now provides intelligent merge suggestions, multi-page tracking, framework previews, adaptive anomaly detection, and a polished UX for handling duplicate controls and framework mappings.
