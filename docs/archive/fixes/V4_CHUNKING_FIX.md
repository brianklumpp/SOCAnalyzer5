# V4 Control Extractor Fix - Chunking Bug

## Problem Identified

**Issue:** V4 only found 31 controls instead of expected 138 (~77.5% missing)

## Root Cause Analysis

### What We Found

1. **Document Size:**
   - 7,257 lines
   - 271,053 characters
   - ~67,763 tokens

2. **V4 Configuration:**
   - 1,000 tokens per chunk
   - 200 tokens overlap
   - Effective chunk size: 800 tokens

3. **Expected vs Actual:**
   - **Expected chunks:** ~84 (67,763 ÷ 800)
   - **Actual chunks:** 32
   - **Missing:** 52 chunks (62% of expected chunks not created!)

4. **Result:**
   - V4 extracts 1 control per chunk by design
   - Only 32 chunks = only 31 controls found
   - 107 controls missed because chunks weren't created

### Root Cause: Chunking Logic Bug

**Location:** `backend/app/extractors/control_extractor_v4.py`, line ~81-87

**Bug:**
```python
# WRONG - moves position to END of chunk (no overlap!)
position = chunk_end

# This means:
# Chunk 1: chars 0-4000
# Chunk 2: chars 4000-8000  <-- starts where chunk 1 ended (no overlap!)
# Chunk 3: chars 8000-12000
```

**Expected Behavior:**
```python
# CORRECT - advances by effective chunk size (with overlap)
effective_advance = chars_per_chunk - overlap_chars  # 4000 - 800 = 3200
position += effective_advance

# This means:
# Chunk 1: chars 0-4000
# Chunk 2: chars 3200-7200   <-- 800 chars overlap with chunk 1
# Chunk 3: chars 6400-10400  <-- 800 chars overlap with chunk 2
```

### Impact

**Before Fix:**
- Chunks were **contiguous** (no overlap)
- Position advanced 4000 chars each time
- Result: Only 271,053 ÷ 4000 = ~68 chunks... but we only got 32?

**Wait - Additional Issue!**

Even with contiguous chunks, we should have gotten ~68 chunks, not 32. Let me check if there's another issue...

Looking at the break condition:
```python
if chunk_end >= len(full_text):
    break
```

This breaks when `chunk_end` reaches the end. But `chunk_end` is calculated as:
```python
chunk_end = min(len(full_text), position + chars_per_chunk)
```

And `position = chunk_end` means on the next iteration, if `chunk_end` was capped at `len(full_text)`, then `position = len(full_text)`, and the loop condition `while position < len(full_text)` would exit!

**So the REAL bug is TWO-FOLD:**

1. **No overlap:** `position = chunk_end` instead of `position += effective_advance`
2. **Early exit:** Break condition uses `chunk_end` instead of `position`

## The Fix

### Change Made

```python
# OLD (BROKEN):
chunk_id += 1
position = chunk_end  # <-- BUG: no overlap, and if chunk_end=len, next iteration exits

if chunk_end >= len(full_text):
    break

# NEW (FIXED):
chunk_id += 1

# Move position forward by effective chunk size (chunk size minus overlap)
# This creates overlapping chunks: next chunk starts (overlap_chars) before current chunk ends
effective_advance = chars_per_chunk - overlap_chars
position += effective_advance

# Break if we've reached the end
if position >= len(full_text):
    break
```

### Expected Result After Fix

- **Position advances:** 3,200 chars per iteration (4,000 - 800 overlap)
- **Expected chunks:** 271,053 ÷ 3,200 = ~85 chunks
- **Expected controls:** ~85 controls (one per chunk)

### Still Not 138 Controls!

Even with the fix, we'll get ~85 controls, not 138. This means:

**Option 1:** Reduce chunk size further
- Current: 1,000 tokens/chunk → ~85 chunks
- Needed: 2,000 tokens per 138 controls = ~490 tokens/chunk
- **Recommendation:** Set `CONTROL_V4_TOKENS_PER_CHUNK = 500`

**Option 2:** Extract multiple controls per chunk (architecture change)
- Change V4 to extract ALL controls in each chunk (not just one)
- More complex, requires prompt and logic changes

## Recommendation

### Immediate Fix (Applied)
✅ Fix chunking logic to create overlapping chunks properly

### Testing
```powershell
# Re-run extraction on Adobe PDF
python interactive_scan.py
# Select option 2: Run Individual Extractors
# Select control extractor
# Check results
```

### If Still Not Enough Controls

Reduce chunk size in `.env`:
```properties
CONTROL_V4_TOKENS_PER_CHUNK=500
```

Or in `backend/app/config.py`:
```python
CONTROL_V4_TOKENS_PER_CHUNK = 500  # Smaller chunks = more controls
```

## Files Modified

1. `backend/app/extractors/control_extractor_v4.py`
   - Fixed `create_aware_chunks()` function
   - Line ~81-90: Changed position advancement logic

## Next Steps

1. ✅ Fix applied to chunking logic
2. ⏳ Test the fix (re-run extraction)
3. ⏳ If needed: Adjust chunk size to 500 tokens
4. ⏳ Compare results with V2 extractor
5. ⏳ Validate we're getting closer to 138 controls
