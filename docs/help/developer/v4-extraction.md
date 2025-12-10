# Control Extractor V4 - Architecture

## Overview

Control Extractor V4 uses **AWARE-CHUNK + Chain-of-Thought (CoT)** architecture for SOC 2 control extraction with improved accuracy and continuation handling.

## Key Features

### 1. Token-Based Aware Chunking
Chunks "know" they're part of a sequence and can signal incomplete controls:
```python
CONTROL_V4_TOKENS_PER_CHUNK = 500    # ~500 tokens per chunk
CONTROL_V4_OVERLAP_TOKENS = 100      # ~100 token overlap
```

### 2. Chain-of-Thought Reasoning
Embedded in prompt with 7 parsing strategies:
1. Ignore structural noise (headers, principles)
2. Detect control boundaries (IDs, entity-voice, auditor verbs)
3. Classify sentences by role (description, test, result)
4. Deviation detection (explicit mentions)
5. Boundary sanity (stop at new sections)
6. Confidence scoring (0.9-1.0 complete, 0.3-0.59 partial)
7. Continuation flag (incomplete at chunk end)

### 3. Continuation Handling
Three merge criteria for controls split across chunks:
- Previous control has `continuation: true`
- Consecutive control_ids match
- Adjacent line ranges (within 5 lines)

### 4. Confidence Filtering
```python
CONTROL_V4_MIN_CONFIDENCE = 0.5      # Threshold for keeping controls
CONTROL_V4_SAVE_REJECTED = True      # Save rejected controls for review
```

## Architecture Comparison

| Feature | V2 (Legacy) | V4 (New) |
|---------|-------------|----------|
| **Chunking** | Line-based (160 lines) | Token-based (~500 tokens) |
| **Overlap** | 40 lines + 8 tail guard | 100 tokens |
| **Metadata** | None | chunk_id, start_line, end_line, hints |
| **Prompt Style** | Multi-field (8 rules) | Single-control (7 strategies) |
| **Continuation** | Implicit (overlap) | Explicit (flag + merge) |
| **Filtering** | None | Confidence threshold (0.5) |
| **Diagnostics** | Basic | Comprehensive (10+ metrics) |
| **Validation** | None | Post-merge schema check |

## Configuration

Configure V4 in `backend/app/config.py`:

```python
# Control which version to use
CONTROL_EXTRACTOR_VERSION = "v4"  # or "v2" for legacy

# V4 Parameters
CONTROL_V4_TOKENS_PER_CHUNK = 500
CONTROL_V4_OVERLAP_TOKENS = 100
CONTROL_V4_MIN_CONFIDENCE = 0.5
CONTROL_V4_SAVE_REJECTED = True
```

## Testing V4

### Quick Test
```powershell
# Test V4 extractor
python test_scripts/test_control_v4.py --version v4 --max-display 10

# Compare V2 vs V4
python test_scripts/test_control_v4.py --compare
```

### Via Interactive Mode
```powershell
.\interactive.ps1
# Select option 6: Run Control Extractor
# V4 is used automatically if configured
```

## Output Format

V4 produces rich diagnostics:

```json
{
  "controls": [...],
  "diagnostics": {
    "extractor_version": "v4",
    "total_chunks": 170,
    "raw_controls_extracted": 180,
    "controls_merged": 12,
    "continuations_detected": 8,
    "controls_after_merge": 168,
    "controls_rejected_confidence": 5,
    "final_control_count": 163,
    "avg_confidence": 0.87,
    "deviations_found": 3,
    "processing_time_seconds": 145.2
  }
}
```

## Chunking Fix (November 2025)

**Issue:** V4 initially extracted only 31 controls instead of 138

**Root Cause:** Position advanced to end of chunk instead of overlapping
```python
# WRONG:
position = chunk_end  # No overlap, early exit

# CORRECT:
effective_advance = chars_per_chunk - overlap_chars
position += effective_advance  # Properly overlapping
```

**Result:** Fixed chunking now creates 170 chunks (was 32), covering entire document.

## Expected Improvements

### 1. Boundary Detection
- **V2:** Relies on table structure and GPT-inferred breakpoints
- **V4:** Uses linguistic cues (control IDs, entity-voice, auditor verbs)

### 2. Continuation Handling
- **V2:** Implicit via overlap (may miss or duplicate)
- **V4:** Explicit flag + intelligent merge (tracks source)

### 3. Quality Control
- **V2:** No filtering (all extractions kept)
- **V4:** Confidence threshold (< 0.5 rejected with reasoning)

### 4. Observability
- **V2:** Basic logging
- **V4:** Comprehensive diagnostics + rejected control tracking

## Rollback to V2

If needed, revert to legacy extractor:

```python
# In config.py:
CONTROL_EXTRACTOR_VERSION = "v2"
```

Or via environment variable:
```powershell
$env:CONTROL_EXTRACTOR_VERSION = "v2"
```

## Files Modified

- `backend/app/config.py` - V4 configuration constants + prompt
- `backend/app/extractors/control_extractor_v4.py` - Full V4 implementation (~700 lines)
- `backend/app/extractors/control_integration.py` - Unified v2/v4 interface
- `backend/app/analyze.py` - Uses integration module
- `test_scripts/test_control_v4.py` - Test harness

## Performance

**API Call Reduction:**
- V2: 175 controls × 3 GPT + 175×2 embeddings = ~875 calls
- V4: 175 controls × 3 GPT = 525 calls (no embeddings)
- **Result:** ~40% fewer API calls

## Further Reading

- See **GPT Model Configuration** for model setup
- See **Direct Execution Guide** for running extractors standalone
- See **Troubleshooting > Common Errors** for extraction issues
