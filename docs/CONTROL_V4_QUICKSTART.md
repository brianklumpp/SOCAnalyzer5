# Quick Start: Control Extractor V4

## What's New?
**AWARE-CHUNK + Chain-of-Thought** architecture replaces the old line-based approach with:
- 🧩 **Smart Chunks**: Token-based segments that know their position and can signal incomplete controls
- 🧠 **Chain-of-Thought**: 7-step reasoning embedded in the prompt for better boundary detection
- 🔗 **Continuation Handling**: Automatically merges controls split across chunks
- ⚖️ **Confidence Filtering**: Rejects low-quality extractions (< 0.5 threshold)
- 📊 **Rich Diagnostics**: 10+ metrics about extraction quality

## Quick Test

```bash
# Test V4 on current document
python test_scripts/test_control_v4.py --version v4

# Show first 10 controls
python test_scripts/test_control_v4.py --version v4 --max-display 10

# Compare V2 vs V4
python test_scripts/test_control_v4.py --compare
```

## Usage in Code

```python
from backend.app.extractors.control_integration import extract_controls

# Use V4 (default)
result = extract_controls(version="v4")

# Access results
controls = result["controls"]           # List of extracted controls
diagnostics = result["diagnostics"]     # Extraction metrics
rejected = result["rejected_controls"]  # Low-confidence controls

# Print summary
print(f"Extracted {len(controls)} controls")
print(f"Average confidence: {diagnostics['avg_confidence']:.2f}")
print(f"Merged {diagnostics['controls_merged']} continuations")
```

## Key Metrics

The V4 extractor returns comprehensive diagnostics:

```python
{
  "total_chunks": 15,                    # Number of chunks processed
  "raw_controls_extracted": 180,         # Total extracted before merge
  "controls_merged": 12,                 # Number merged due to continuation
  "continuations_detected": 8,           # Chunks with continuation=true
  "controls_after_merge": 168,           # After merging
  "controls_rejected_confidence": 5,     # Below threshold
  "final_control_count": 163,            # Final output
  "avg_confidence": 0.87,                # Average confidence score
  "deviations_found": 3,                 # Controls with deviations
  "processing_time_seconds": 145.2       # Total time
}
```

## Configuration

Adjust settings in `backend/app/config.py`:

```python
# Chunk size (default: 1000 tokens ≈ 4000 chars)
CONTROL_V4_TOKENS_PER_CHUNK = 1000

# Overlap (default: 200 tokens ≈ 800 chars)
CONTROL_V4_OVERLAP_TOKENS = 200

# Confidence threshold (default: 0.5)
CONTROL_V4_MIN_CONFIDENCE = 0.5

# Save rejected controls for review
CONTROL_V4_SAVE_REJECTED = True
```

## Output Structure

Each control includes:

```json
{
  "control_seq": 1,
  "control_id": "CC2.1.1",
  "control_desc": "The company implements...",
  "control_tests": ["Inspected...", "Tested..."],
  "control_test_results": ["No exceptions noted"],
  "has_deviation": false,
  "deviation_desc": "",
  "additional_references": [],
  "end_line": 142,
  "control_confidence": 0.95,
  "control_gpt_conf_justification": "Complete control with ID, description, tests, and results",
  "continuation": false,
  "chunk_id": 3,
  "source_start_line": 125
}
```

## Files

- **config.py** - V4 configuration constants and prompt
- **control_extractor_v4.py** - Full implementation
- **control_integration.py** - Unified v2/v4 interface
- **test_control_v4.py** - Test harness
- **CONTROL_EXTRACTOR_V4_SUMMARY.md** - Detailed documentation

## Support

For detailed architecture info, see `CONTROL_EXTRACTOR_V4_SUMMARY.md`
