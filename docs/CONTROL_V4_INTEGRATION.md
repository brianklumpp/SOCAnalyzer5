# Control Extractor Integration - Complete

## ✅ Integration Complete

The **Control Extractor V4** is now fully integrated into the SOC2Analyzer pipeline!

## Configuration

Control which extractor version to use via environment variable or config:

### Option 1: Environment Variable
```bash
# Use V4 (default)
$env:CONTROL_EXTRACTOR_VERSION="v4"

# Use V2 (legacy)
$env:CONTROL_EXTRACTOR_VERSION="v2"
```

### Option 2: Direct Config Edit
Edit `backend/app/config.py` line ~1393:
```python
CONTROL_EXTRACTOR_VERSION = "v4"  # or "v2"
```

## Where It's Used

The integration is now active in:

### 1. ✅ **Interactive Script** (`interactive.ps1` → `interactive_scan.py`)
- Run all extractors
- Run single control extractor
- Automatically uses configured version

```bash
.\interactive.ps1
# Select option 6 to run Control Extractor (V4 or V2 based on config)
# Or option 10 to run all extractors
```

### 2. ✅ **Main Analysis Pipeline** (`backend/app/analyze.py`)
- Full scan with `analyze_pdf_file()`
- Uses configured version automatically

```python
from backend.app.analyze import analyze_pdf_file
analyze_pdf_file("soc2_reports/Adobe.pdf")
```

### 3. ✅ **Test Scripts** (`test_scripts/test_control_v4.py`)
```bash
# Test V4
python test_scripts/test_control_v4.py --version v4

# Test V2
python test_scripts/test_control_v4.py --version v2

# Compare
python test_scripts/test_control_v4.py --compare
```

## Files Modified

| File | Changes | Status |
|------|---------|--------|
| `config.py` | Added `CONTROL_EXTRACTOR_VERSION`, V4 constants, V4 prompt | ✅ |
| `control_extractor_v4.py` | Returns None, writes to file (like v2) | ✅ |
| `control_integration.py` | Unified interface for v2/v4 | ✅ |
| `analyze.py` | Uses integration module, reads from config | ✅ |
| `interactive_scan.py` | Uses integration module, shows version in menu | ✅ |
| `test_control_v4.py` | Updated to read from file | ✅ |

## How It Works

### Architecture
```
┌─────────────────────────────────────────┐
│   Interactive Script / analyze.py       │
│   User initiates scan                   │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│   config.CONTROL_EXTRACTOR_VERSION      │
│   → "v4" (default) or "v2"              │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│   control_integration.extract_controls()│
│   Unified interface                     │
└──────────────────┬──────────────────────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
┌─────────────────┐  ┌─────────────────┐
│ V2 Extractor    │  │ V4 Extractor    │
│ (Line-based)    │  │ (Aware-Chunk)   │
└────────┬────────┘  └────────┬────────┘
         │                    │
         └──────────┬─────────┘
                    ▼
       ┌────────────────────────────┐
       │ config.CONTROL_JSON_PATH   │
       │ {"controls": [...]}        │
       └────────────────────────────┘
```

### Data Flow
1. **User** runs interactive script or analyze.py
2. **Config** determines which version to use (v2 or v4)
3. **Integration Module** calls the appropriate extractor
4. **Extractor** writes results to `data/json/control_result.json`
5. **Pipeline** reads results from file and continues

### Output Format (Both Versions)
```json
{
  "controls": [
    {
      "control_seq": 1,
      "control_id": "CC2.1.1",
      "control_desc": "...",
      "control_tests": [...],
      "control_test_results": [...],
      "has_deviation": false,
      "control_confidence": 0.95,
      ...
    }
  ],
  "diagnostics": {
    "extractor_version": "v4",
    "total_chunks": 15,
    "controls_merged": 8,
    "avg_confidence": 0.87,
    ...
  }
}
```

## Quick Test

### Test V4 with Adobe PDF
```bash
# Set to use V4
$env:CONTROL_EXTRACTOR_VERSION="v4"

# Run interactive script
.\interactive.ps1

# Or run test directly
python test_scripts/test_control_v4.py --version v4 --max-display 10
```

### Compare V2 vs V4
```bash
# Run V2
python test_scripts/test_control_v4.py --version v2 > results_v2.txt

# Run V4
python test_scripts/test_control_v4.py --version v4 > results_v4.txt

# Compare
diff results_v2.txt results_v4.txt
```

## Benefits of V4

When you run a full scan with `CONTROL_EXTRACTOR_VERSION="v4"`, you get:

### 1. **Better Boundary Detection**
- Uses linguistic cues (control IDs, entity-voice, auditor verbs)
- Not dependent on table structure

### 2. **Continuation Handling**
- Automatically merges controls split across chunks
- Tracks source and provides merge diagnostics

### 3. **Quality Control**
- Confidence filtering (< 0.5 threshold)
- Rejected controls saved for review

### 4. **Rich Diagnostics**
```json
{
  "total_chunks": 15,
  "raw_controls_extracted": 180,
  "controls_merged": 12,
  "continuations_detected": 8,
  "controls_rejected_confidence": 5,
  "final_control_count": 163,
  "avg_confidence": 0.87,
  "deviations_found": 3,
  "processing_time_seconds": 145.2
}
```

### 5. **Token-Based Chunking**
- More consistent chunk sizes
- Better context preservation with overlap

## Migration Path

### Currently
```python
# Old direct import (still works but not recommended)
from backend.app.extractors.control_extractor_v2 import extract_controls_v2
extract_controls_v2()
```

### Now (Recommended)
```python
# Use integration module (version-agnostic)
from backend.app.extractors.control_integration import extract_controls
from backend.app import config

# Uses config.CONTROL_EXTRACTOR_VERSION automatically
extract_controls(version=config.CONTROL_EXTRACTOR_VERSION)
```

## Rollback

If you need to revert to V2:

### Quick Rollback
```bash
$env:CONTROL_EXTRACTOR_VERSION="v2"
.\interactive.ps1
```

### Permanent Rollback
Edit `backend/app/config.py` line ~1393:
```python
CONTROL_EXTRACTOR_VERSION = "v2"
```

## Next Steps

1. ✅ **Integration Complete** - All systems use unified interface
2. ⏳ **Test V4** - Run against Adobe.pdf to validate
3. ⏳ **Compare Results** - Quantify V4 improvements over V2
4. ⏳ **Production Deploy** - Set V4 as default after validation

## Summary

**Yes, when you run a full scan via the interactive script, V4 will be leveraged automatically!**

The default is now `CONTROL_EXTRACTOR_VERSION="v4"`, so:
- `.\interactive.ps1` → uses V4
- All extractors in menu → use V4
- Full analysis pipeline → uses V4

You can switch back to V2 anytime by changing the config or setting the environment variable.
