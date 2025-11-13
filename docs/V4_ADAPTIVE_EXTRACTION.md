# V4 Adaptive Multi-Control Extraction

## Problem Statement

**Original Issue:** V4 was extracting only 72 controls from Adobe report instead of expected 138.

**Initial Analysis:** Thought it was a chunking bug, but chunking was working correctly (79 chunks created as expected).

**Root Cause:** V4 was designed to extract **"one control only and stop"** from each chunk, limiting it to ~1 control per chunk. Adobe has ~1.9 controls per chunk on average.

**User Insight:** "I'm hoping we're not 'backing into' the chunking approach because this is how to make it work for Adobe and not taking into account varying formats of other auditors/companies audited."

## Solution: Adaptive Multi-Control Extraction

Instead of reducing chunk size to fit Adobe specifically, **updated V4 to extract ALL controls found in each chunk**, making it adaptive to different report formats.

### Changes Made

#### 1. Updated Prompt (`backend/app/config.py`)

**OLD (Single-Control):**
```
Extract the NEXT complete control block (one control only) and stop.

Expected Output:
{
  "control_id": "...",
  "control_desc": "...",
  ...
}
```

**NEW (Multi-Control):**
```
Extract ALL complete control blocks in this chunk.

Expected Output:
{
  "controls": [
    {
      "control_id": "...",
      "control_desc": "...",
      ...
    },
    ... (repeat for each control found)
  ]
}

If only one control is found, return an array with one element.
```

Added section 8 to prompt:
```
### 8. Multiple controls in chunk
Extract ALL complete controls found in this chunk. The chunk may contain:
- Zero controls (just headers or narrative)
- One control (typical for sparse reports)
- Multiple controls (typical for dense reports like Adobe, KPMG)
- Partial control (starts but doesn't complete - mark as continuation)
```

#### 2. Updated Parser (`backend/app/extractors/control_extractor_v4.py`)

**Function:** `parse_control_json()`

**Changes:**
- Returns `List[Dict]` instead of `Dict`
- Handles both formats for backward compatibility:
  - New: `{"controls": [...]}`
  - Old: `{...}` (single control object)

```python
# Handle both old format (single control) and new format (array)
if "controls" in parsed:
    # New format: {"controls": [...]}
    controls = parsed["controls"]
else:
    # Old format (backwards compatibility): single control object
    controls = [parsed]
```

#### 3. Updated Extraction Loop

**Function:** `extract_control_with_cot()`

**Changes:**
- Returns `List[Dict]` instead of `Dict`
- Processes multiple controls from single chunk
- Logs count: "Extracted {len(controls)} control(s)"

**Main Loop:**
```python
# OLD:
for chunk in chunks:
    control = extract_control_with_cot(chunk)
    if control:
        raw_controls.append(control)

# NEW:
for chunk in chunks:
    controls_from_chunk = extract_control_with_cot(chunk)
    if controls_from_chunk:
        raw_controls.extend(controls_from_chunk)
```

## Adaptive Behavior

The extractor now automatically adapts to different report formats:

| Report Type | Controls/Chunk | Behavior |
|-------------|----------------|----------|
| **Sparse** (e.g., some Big 4) | 0.5-1.0 | Extracts 1 control, sets continuation for splits |
| **Balanced** (most reports) | 1.0-1.5 | Extracts 1-2 controls per chunk |
| **Dense** (Adobe, KPMG) | 1.5-2.5 | Extracts 2-3 controls per chunk |
| **Very Dense** | 2.5+ | Extracts 3+ controls, uses continuations |

### Chunk Size Remains Optimal

**500 tokens/chunk with 100 token overlap:**
- Works for sparse reports (doesn't miss controls)
- Works for dense reports (extracts multiple)
- Overlapping ensures split controls are caught
- Not hardcoded for any specific auditor format

## Expected Results

### Adobe Report (Dense Format)

**Previous (Single-Control):**
- 79 chunks → 79 controls → 72 after merging/filtering
- **Coverage: 52% of target**

**Now (Multi-Control):**
- 79 chunks → ~120-150 controls → ~130-140 after merging/filtering
- **Coverage: 95-100% of target** ✅

### Other Report Formats

**Sparse Report (0.8 controls/chunk):**
- Will extract 1 control per chunk where present
- Sets continuation for split controls
- No performance degradation

**Very Dense Report (3 controls/chunk):**
- Will extract all 3 controls per chunk
- May need more continuation merging
- Still captures all controls

## Backward Compatibility

✅ **Parser handles both response formats:**
- Old single-control format: `{...}`
- New multi-control format: `{"controls": [...]}`

✅ **Continuation merging still works:**
- Merges split controls across chunks
- No changes needed to merge logic

✅ **All other extractors unchanged:**
- V2 control extractor unaffected
- Other extractors (company, product, etc.) unchanged

## Key Design Principles

1. **Adaptive, not prescriptive** - Doesn't assume control density
2. **Format-agnostic** - Works with any auditor format
3. **Overlap for safety** - Ensures split controls aren't missed
4. **Continuation handling** - Merges controls that span chunks
5. **Confidence filtering** - Rejects low-quality extractions

## Testing Recommendations

### Test 1: Adobe Report (Dense)
```
Expected: ~130-150 controls (up from 72)
Target: 138 controls
Coverage: Should achieve 95-100%
```

### Test 2: Different Auditor (if available)
```
Expected: Matches control count regardless of density
Should adapt automatically to format
```

### Test 3: Sparse Report (if available)
```
Expected: No degradation from previous version
Should still extract all controls correctly
```

## Files Modified

1. **`backend/app/config.py`** (Lines 1390-1480)
   - Updated `CONTROL_EXTRACTION_PROMPT_V4`
   - Changed from "one control only" to "ALL controls"
   - Added multi-control output format
   - Added section 8 on adaptive behavior
   - Reverted chunk size to 500 tokens (was temporarily 250)

2. **`backend/app/extractors/control_extractor_v4.py`**
   - `parse_control_json()`: Returns `List[Dict]` instead of `Dict`
   - `extract_control_with_cot()`: Returns `List[Dict]`, processes multiple controls
   - Main loop: Uses `extend()` instead of `append()`
   - Added backward compatibility for old format

## Success Metrics

✅ **Fixes Adobe extraction** - Should get ~138 controls instead of 72
✅ **Maintains flexibility** - Works with any report format
✅ **No performance regression** - Same number of API calls (79 chunks)
✅ **Backward compatible** - Old format still works
✅ **Future-proof** - Adapts to new auditor formats automatically

## Next Steps

1. **Run V4 extraction on Adobe report**
   - Should extract ~130-150 controls
   - Compare with V2 results for validation

2. **Test with other report formats**
   - Verify adaptive behavior works
   - Ensure no regression on sparse reports

3. **Monitor diagnostics**
   - Check controls per chunk average
   - Verify continuation merging still works
   - Review confidence scores

4. **Compare with V2**
   - V4 should match or exceed V2 control count
   - V4 should maintain high confidence scores
   - Processing time should be similar
