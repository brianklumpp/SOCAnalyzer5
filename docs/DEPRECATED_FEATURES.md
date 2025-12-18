# Deprecated Features & Removed Code

**Last Updated**: 2025-12-14

This document tracks features that have been intentionally removed or deprecated to prevent accidental reintroduction.

---

## ❌ REMOVED: Legacy Framework Mapping Columns (v2.1.0)

### What Was Removed
Individual database columns for TSC and COSO mappings:
- `control_tsc_id` (VARCHAR 128)
- `control_coso_id` (VARCHAR 128)
- `control_tsc_similarity` (DOUBLE PRECISION)
- `control_coso_similarity` (DOUBLE PRECISION)
- `control_tsc_confidence_pct` (DOUBLE PRECISION)
- `control_coso_confidence_pct` (DOUBLE PRECISION)
- `control_closest_framework` (VARCHAR)
- `control_tsc_section` (VARCHAR)
- `control_coso_section` (VARCHAR)
- `control_tsc_mappings` (JSON)
- `control_coso_mappings` (JSON)

Similar legacy fields removed from `cuec` table:
- `cuec_tsc_id` (VARCHAR 128)
- `cuec_coso_id` (VARCHAR 128)
- `cuec_tsc_similarity` (DOUBLE PRECISION)
- `cuec_coso_similarity` (DOUBLE PRECISION)
- `cuec_tsc_confidence_pct` (DOUBLE PRECISION)
- `cuec_coso_confidence_pct` (DOUBLE PRECISION)
- `cuec_closest_framework` (VARCHAR)
- `cuec_framework_alignment` (VARCHAR)
- `cuec_framework_alignment_id` (VARCHAR 128)
- `cuec_tsc_mappings` (JSON)
- `cuec_coso_mappings` (JSON)

### Why They Were Removed
These columns created a **hardcoded, non-extensible** schema that only supported TSC and COSO frameworks. The system needed to support:
- SOC 1 financial assertions (COSO)
- Multiple international frameworks (ISAE 3402, etc.)
- Custom frameworks
- Multiple mappings per control

### ✅ Replacement: Unified Framework System
**Use Instead**:
- `framework_mappings` (JSON) - Stores ALL framework mappings in one flexible structure
- `primary_framework` (VARCHAR 64) - Best matching framework name
- `primary_criterion_id` (VARCHAR 128) - Best matching criterion ID  
- `primary_confidence` (FLOAT) - Confidence score of best match

**Schema Example**:
```json
{
  "framework_mappings": {
    "TSC": [{"id": "CC6.1", "confidence": 0.95, "reasoning": "..."}],
    "COSO": [{"id": "Control Activities", "confidence": 0.87}],
    "FINANCIAL_ASSERTIONS": [{"id": "EO1", "confidence": 0.92}]
  },
  "primary_framework": "TSC",
  "primary_criterion_id": "CC6.1", 
  "primary_confidence": 0.95
}
```

### If You See Errors About These Columns
**DO NOT** add them back to the database schema!

**DO** update the code to use `framework_mappings` instead.

### Files That Should NOT Reference These Columns
- `backend/app/models.py` - Control/CUEC model definitions
- `backend/app/config.py` - TABLE_FIELD_MAP["control"] and TABLE_FIELD_MAP["cuec"]
- `backend/app/explicit_sql_insert.py` - INSERT statements
- `backend/app/extractors/control_extractor.py` - Control extraction logic
- `backend/app/extractors/cuec_extractor.py` - CUEC extraction logic
- `frontend/src/hooks/report/useFrameworkCoverage.ts` - Framework coverage calculation
- `frontend/src/components/CuecDetailsModal.tsx` - CUEC detail display
- `frontend/src/components/report/tables/CuecsTable.tsx` - CUEC table display
- `frontend/src/services/report/dataTransformations.ts` - Data transformations
- Any API endpoints that serialize controls or CUECs

### Known Remaining References (To Be Cleaned Up)
Check these files for stale references that need updating:
- `backend/app/main.py` - Lines ~2829-2835, ~4008, ~4031
- `backend/app/services/executive_summary_service.py` - Line ~102
- `backend/app/services/framework_mapping_service.py` - Line ~89
- `backend/app/services/merge_service.py` - Lines ~110-111
- `backend/app/extractors/control_extractor_combined.py` - Line ~1158

---

## When Adding New Framework Mappings

**✅ CORRECT Approach**:
```python
# Add to framework_mappings JSON
control.framework_mappings = {
    "TSC": [{"id": "CC6.1", "confidence": 0.95}],
    "NEW_FRAMEWORK": [{"id": "NF-1.2", "confidence": 0.88}]
}
control.primary_framework = "TSC"
control.primary_criterion_id = "CC6.1"
control.primary_confidence = 0.95
```

**❌ WRONG Approach** (DON'T DO THIS):
```python
# Don't try to use individual columns - they don't exist!
control.control_tsc_id = "CC6.1"  # ❌ Column removed
control.control_coso_id = "CA"     # ❌ Column removed
```

---

## Emergency Recovery

If you accidentally added these columns back:

```sql
-- Remove them again:
ALTER TABLE control 
  DROP COLUMN IF EXISTS control_tsc_id,
  DROP COLUMN IF EXISTS control_coso_id,
  DROP COLUMN IF EXISTS control_tsc_similarity,
  DROP COLUMN IF EXISTS control_coso_similarity,
  DROP COLUMN IF EXISTS control_tsc_confidence_pct,
  DROP COLUMN IF EXISTS control_coso_confidence_pct;
```

And update code to use `framework_mappings` instead.
