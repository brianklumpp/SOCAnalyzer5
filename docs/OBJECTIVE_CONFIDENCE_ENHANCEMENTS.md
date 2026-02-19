# Objective Confidence Scoring Enhancements

**Date**: January 2025  
**Status**: ✅ Implemented  
**Migration**: `7db38ce025c3` - Add confidence_metadata field

## Overview

Comprehensive upgrade to the objective confidence scoring system with 6 major improvements:

1. **TSC-Based Keywords** - Enhanced vocabulary with Trust Services Criteria language patterns
2. **Rebalanced Weights** - Reduced GPT reliance, increased format/alignment emphasis  
3. **ID Pattern Penalties** - 50% reduction for missing/outlier IDs based on super majority detection
4. **Audit Trail Metadata** - Comprehensive JSON confidence_metadata field with factor breakdown
5. **Validation Persistence** - GPT validation adjustments saved to confidence_metadata
6. **Configurable Penalties** - Three new config constants for ID penalty thresholds

## 1. TSC-Based Keywords (`config.py`)

**Problem**: Generic keywords like "control objective" missed TSC-specific language.

**Solution**: Replaced `OBJECTIVE_PATTERN_KEYWORDS` with 20+ TSC criteria patterns:

```python
OBJECTIVE_PATTERN_KEYWORDS = {
    'tsc_entity_patterns': [
        'the entity demonstrates', 'the entity identifies', 'the entity implements',
        'the entity establishes', 'the entity maintains', 'the entity communicates',
        'the entity evaluates', 'the entity selects', 'the entity monitors'
    ],
    'tsc_outcome_patterns': [
        'reasonable assurance', 'criteria are met', 'objectives are achieved',
        'system description', 'service commitments', 'system requirements'
    ],
    'trust_services_refs': [
        'common criteria', 'trust services criteria', 'TSC', 'COSO principle',
        'confidentiality criteria', 'availability criteria', 'privacy criteria'
    ],
    # ... additional categories
}
```

**Impact**: Better detection of legitimate objectives in audit reports.

---

## 2. Rebalanced Confidence Weights (`config.py`)

**Before**:
```python
OBJECTIVE_CONFIDENCE_WEIGHTS = {
    'keyword': 0.25,
    'distance': 0.20,
    'gpt_opinion': 0.30,  # Too high
    'alignment': 0.15,    # Too low
    'format': 0.10        # Too low
}
```

**After**:
```python
OBJECTIVE_CONFIDENCE_WEIGHTS = {
    'keyword': 0.25,      # Unchanged
    'distance': 0.20,     # Unchanged
    'gpt_opinion': 0.15,  # ⬇️ Reduced 50% (30→15)
    'alignment': 0.20,    # ⬆️ Increased 33% (15→20)
    'format': 0.20        # ⬆️ Doubled (10→20)
}
```

**Rationale**: 
- GPT can be inconsistent; reduce reliance
- Format clarity (numbering, structure) is objective and reliable
- Alignment with controls is strong validation signal

---

## 3. ID Pattern Penalties (`config.py`, `objective_extractor.py`)

**New Configuration**:
```python
# Penalty applied when objective ID is missing but super majority have IDs
OBJECTIVE_ID_MISSING_PENALTY = 0.50  # 50% reduction

# Penalty applied when ID format differs from dominant pattern
OBJECTIVE_ID_OUTLIER_PENALTY = 0.50  # 50% reduction

# Threshold for "super majority" (80% = 0.80)
OBJECTIVE_ID_SUPERMAJORITY_THRESHOLD = 0.80
```

**New Functions**:
- `_calculate_id_penalties()` - Detects missing/outlier ID scenarios
- `_analyze_id_patterns()` - Groups IDs by structural pattern (CC., C., ALPHA-NUM-NUM, etc.)
- `_extract_id_pattern()` - Extracts pattern from individual ID

**Penalty Logic**:
1. **Missing ID Penalty**: If 80%+ of objectives have IDs but this one doesn't → -50%
2. **Outlier Pattern Penalty**: If 80%+ follow pattern "CC." but this uses "SO-1-2" → -50%

**Supported Patterns**:
- **TSC**: `CC.` (CC1.1), `C.` (C1.1), `A.` (A1.1), `P.` (P1.1), `PI.` (PI1.1), `Conf.` (Conf1.1)
- **Custom**: `ALPHA-NUM-NUM` (SO-1-2), `ALPHA.NUM.NUM` (IM.1.2), `ALPHANUM` (OBJ001)

**Example**:
```
Scan has 12 objectives:
  - 10 use pattern "CC." (CC1.1, CC2.1, etc.) = 83% super majority
  - 1 uses "SO-1-2" (ALPHA-NUM-NUM pattern) → PENALTY: -50%
  - 1 has no ID → PENALTY: -50% (missing when majority have IDs)
```

---

## 4. Confidence Metadata Audit Trail (`models.py`, `objective_extractor.py`)

**Database Schema** (`models.py`):
```python
class ControlObjective(Base):
    # ... existing fields ...
    confidence_metadata = Column(JSON)  # NEW: Comprehensive audit trail
```

**JSON Structure**:
```json
{
  "method": "5-factor",
  "calculated_at": "2025-01-20T15:30:45.123456",
  "factor_scores": {
    "keyword_confidence": 0.85,
    "distance_confidence": 0.90,
    "gpt_confidence": 0.75,
    "alignment_confidence": 0.80,
    "format_confidence": 0.95
  },
  "weighted_contributions": {
    "keyword_contribution": 0.2125,  // 0.85 * 0.25
    "distance_contribution": 0.18,   // 0.90 * 0.20
    "gpt_contribution": 0.1125,      // 0.75 * 0.15
    "alignment_contribution": 0.16,  // 0.80 * 0.20
    "format_contribution": 0.19      // 0.95 * 0.20
  },
  "weights_used": {
    "keyword": 0.25,
    "distance": 0.20,
    "gpt_opinion": 0.15,
    "alignment": 0.20,
    "format": 0.20
  },
  "adjustments": [
    {
      "type": "id_pattern_outlier",
      "penalty_multiplier": 0.50,
      "reason": "ID format 'ALPHA-NUM-NUM' differs from dominant 'CC.' (10/12 = 83%)",
      "applied_at": "2025-01-20T15:30:45.234567"
    }
  ]
}
```

**Benefits**:
- **Auditability**: Full breakdown of confidence calculation
- **Debugging**: Identify why confidence is low/high
- **Validation**: Verify weights were applied correctly
- **History**: Track adjustments (penalties, boosts)
- **UI Display**: Can show factor breakdown in frontend tooltips

---

## 5. Validation Confidence Persistence

**Updated**: `calculate_multi_factor_confidence()` signature:
```python
def calculate_multi_factor_confidence(
    objective: Dict[str, Any],
    extracted_text: str,
    line_ref: Optional[int] = None,
    all_objectives: Optional[List[Dict[str, Any]]] = None  # NEW
) -> Tuple[float, str, Dict[str, Any]]:  # Returns metadata now
```

**Call Sites Updated**:
1. `_score_objectives_for_selection()` - Passes `all_objectives=objectives` for penalty analysis
2. `extract_objectives_from_pdf()` - Passes `all_objectives=objectives` during extraction
3. `update_alignment_confidence()` - Passes `all_objectives=None` (no penalties in recalc)

**Metadata Saved**: `confidence_metadata` field populated on:
- Initial objective extraction
- Manual objective creation (future enhancement)
- Validation adjustments (future enhancement)

---

## 6. Validation Confidence Adjustments (Future)

**Planned**: Update `_validate_objectives_batch()` to:
1. Adjust `gpt_confidence` based on GPT validation
2. Recalculate `final_confidence` with new GPT score
3. Add validation adjustment to `confidence_metadata.adjustments`:
   ```json
   {
     "type": "gpt_validation_adjustment",
     "original_gpt_confidence": 0.75,
     "adjusted_gpt_confidence": 0.85,
     "reason": "GPT validation confirmed objective matches TSC criteria",
     "applied_at": "2025-01-20T16:00:00.000000"
   }
   ```
4. Persist updated `confidence_metadata` to database

**Status**: ⏳ Pending implementation

---

## Migration Details

**File**: `backend/alembic/versions/7db38ce025c3_add_objective_confidence_metadata_field_.py`

**Applied**: ✅ January 2025

**Changes**:
- Added `confidence_metadata` column to `control_objectives` table (type: JSON)
- No data migration needed (existing rows will have NULL, populated on next scan)

**Rollback** (if needed):
```bash
cd backend
alembic downgrade -1
```

---

## Testing Recommendations

### Unit Tests
```python
# Test ID penalty logic
def test_id_penalty_missing_supermajority():
    objectives = [
        {'objective_id': 'CC1.1'}, {'objective_id': 'CC1.2'},
        {'objective_id': 'CC1.3'}, {'objective_id': 'CC1.4'},
        {'objective_id': ''}  # Missing ID
    ]
    penalties = _calculate_id_penalties('', objectives)
    assert len(penalties) == 1
    assert penalties[0][1] == 0.50  # 50% penalty

def test_id_penalty_outlier_pattern():
    objectives = [
        {'objective_id': 'CC1.1'}, {'objective_id': 'CC1.2'},
        {'objective_id': 'CC2.1'}, {'objective_id': 'CC2.2'},
        {'objective_id': 'SO-1-2'}  # Outlier pattern
    ]
    penalties = _calculate_id_penalties('SO-1-2', objectives)
    assert len(penalties) == 1
    assert 'differs from dominant' in penalties[0][2]
```

### Integration Tests
1. **Scan with TSC objectives** - Verify keyword confidence high (0.7-0.9)
2. **Scan with missing IDs** - Verify 50% penalty applied when super majority present
3. **Scan with mixed patterns** - Verify outlier penalties applied correctly
4. **Confidence metadata** - Verify JSON structure populated with all fields

### Manual Testing
```bash
.\test_scripts\run_scan.ps1 soc2_reports\Okta.pdf
# Check database:
SELECT objective_id, final_confidence, confidence_metadata 
FROM control_objectives 
WHERE scan_id = (SELECT MAX(id) FROM scan);
```

---

## Configuration Reference

### New Constants (`config.py`)

| Constant | Value | Purpose |
|----------|-------|---------|
| `OBJECTIVE_ID_MISSING_PENALTY` | `0.50` | Penalty when ID missing (50% reduction) |
| `OBJECTIVE_ID_OUTLIER_PENALTY` | `0.50` | Penalty when ID pattern outlier (50%) |
| `OBJECTIVE_ID_SUPERMAJORITY_THRESHOLD` | `0.80` | Threshold for "super majority" (80%) |

### Updated Weights

| Factor | Old Weight | New Weight | Change |
|--------|-----------|-----------|--------|
| `keyword` | 0.25 | 0.25 | ➡️ Unchanged |
| `distance` | 0.20 | 0.20 | ➡️ Unchanged |
| `gpt_opinion` | 0.30 | 0.15 | ⬇️ -50% |
| `alignment` | 0.15 | 0.20 | ⬆️ +33% |
| `format` | 0.10 | 0.20 | ⬆️ +100% |

### Enhanced Keywords

**Categories**: 4 → 6  
**Total Patterns**: 8 → 25+  
**Focus**: Generic → TSC-specific language

---

## Impact Summary

✅ **Improved Accuracy**: TSC language patterns increase keyword confidence for legitimate objectives  
✅ **Better Auditability**: `confidence_metadata` provides full calculation breakdown  
✅ **Reduced Noise**: ID penalties lower confidence for malformed/missing identifiers  
✅ **Balanced Scoring**: Reduced GPT reliance in favor of objective metrics (format, alignment)  
✅ **Configurable**: All thresholds adjustable via config constants  
✅ **Database Migration**: Clean schema upgrade with no data loss  

---

## Related Documentation

- [CONTROL_OBJECTIVE_WORKFLOW.md](CONTROL_OBJECTIVE_WORKFLOW.md) - Complete extraction pipeline
- [5_FACTOR_CONFIDENCE_IMPLEMENTATION.md](5_FACTOR_CONFIDENCE_IMPLEMENTATION.md) - Original confidence system design
- [GPT_MODEL_CONFIG.md](GPT_MODEL_CONFIG.md) - Model selection and Dataiku integration

---

## Future Enhancements

### Item 7: ConfidenceWeights Table Extension
**Goal**: Allow org-specific overrides of objective confidence weights (like controls currently have)

**Implementation**:
- Add `objective_enabled` boolean to `confidence_weights` table
- Update `objective_extractor.py` to check for org-specific weights before using defaults
- Create admin UI for managing objective weight overrides

### Item 8: Validation Adjustment Tracking
**Goal**: Track GPT validation boost/penalty in metadata

**Implementation**:
- Update `_validate_objectives_batch()` to modify `gpt_confidence` and `confidence_metadata`
- Add `validation_adjustment` key to metadata JSON with before/after scores
- Persist updated metadata to database after validation

---

## Questions?

Contact: [Ben Klumpp](mailto:bklumpp@example.com)  
Last Updated: January 20, 2025
