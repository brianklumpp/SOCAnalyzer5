# Control Objective Mapping Workflow

## Overview
This document describes the enhanced control objective mapping workflow implemented to ensure data quality and proper workflow integration.

## Key Changes Implemented

### 1. Confidence Threshold for Auto-Mapping (65%)
**Location**: `backend/app/extractors/objective_extractor.py:1788`

Only objectives with `final_confidence >= 0.65` are automatically mapped during pipeline extraction.

```python
objectives = db_session.query(ControlObjective).filter(
    ControlObjective.scan_id == scan_id,
    ControlObjective.final_confidence >= 0.65
).all()
```

**Rationale**: Low-confidence objectives should be manually reviewed and approved before mapping.

---

### 2. Mapping Timing: After Gap Extraction
**Location**: `backend/app/main.py:1449-1530`

**Previous Flow**:
1. Extract objectives (90%)
2. Map objectives → controls (95%)
3. Gap extraction (98%)
4. Complete (100%)

**New Flow**:
1. Extract objectives (90%)
2. Gap extraction (95%) - finds missing objectives
3. Map ALL objectives → controls (98%) - includes gap-extracted ones
4. Complete (100%)

**Rationale**: Gap extraction can discover additional objectives that need to be mapped. Mapping must happen after ALL objectives are identified.

---

### 3. Rejection Unmaps Controls
**Location**: `backend/app/routers/objective_router.py:616-621`

When an objective's status is changed to "rejected", all associated control mappings are automatically deleted.

```python
elif status_value == "rejected":
    await db.execute(
        delete(ControlObjectiveMapping).where(
            ControlObjectiveMapping.objective_id == objective_id
        )
    )
```

**Rationale**: Rejected objectives should not remain mapped to controls.

---

### 4. Approval Triggers Mapping Signal
**Location**: `backend/app/routers/objective_router.py:625-630`

When a low-confidence objective is approved, the update response includes `needs_mapping: true`.

```python
return {
    "status": "success",
    "message": f"Objective {objective_id} updated successfully",
    "objective": objective_data,
    "needs_mapping": status_value == "approved" and old_status != "approved"
}
```

**Frontend Integration Required**:
- When `needs_mapping: true` is received, call mapping endpoint
- Show progress indicator during mapping
- Endpoint: `POST /report/{scan_id}/objectives/map`

---

## Workflow Summary

### Automatic Pipeline Flow
1. ✅ **Extract objectives** from report
2. ✅ **Gap extraction** finds missing objectives
3. ✅ **Auto-map** only objectives with confidence >= 65%
4. ⏸️ Low-confidence objectives remain unmapped (status: "pending")

### Manual Review Flow
1. User reviews low-confidence objective
2. **Option A: Approve**
   - Status → "approved"
   - Backend returns `needs_mapping: true`
   - Frontend calls mapping endpoint
   - Progress indicator shown during mapping
   - Objective now mapped to relevant controls
3. **Option B: Reject**
   - Status → "rejected"
   - All existing mappings automatically deleted
   - Objective excluded from reports

### Manual Mapping Trigger
- Endpoint: `POST /report/{scan_id}/objectives/map`
- Supports `force=true` to re-map all objectives
- Returns job status for progress tracking

---

## Database Schema

### ControlObjective Table
- `objective_id` (TEXT) - Normalized ID (e.g., "CC1.1")
- `normalized_objective_id` (TEXT) - Same as objective_id
- `original_objective_id` (TEXT) - Original extracted ID
- `final_confidence` (FLOAT) - 0.0 to 1.0
- `status` (TEXT) - "pending", "approved", "rejected"

### ControlObjectiveMapping Table
- `objective_id` (FK → ControlObjective)
- `control_id` (FK → Control)
- `match_score` (FLOAT) - Confidence of the mapping
- `match_method` (TEXT) - How mapping was determined

---

## Testing Checklist

### Scenario 1: High-Confidence Objective
1. ✅ Extract objectives (some >= 65%, some < 65%)
2. ✅ Verify high-confidence ones auto-mapped after gap extraction
3. ✅ Verify low-confidence ones NOT auto-mapped

### Scenario 2: Approve Low-Confidence Objective
1. ✅ Find objective with confidence < 65% (status: "pending")
2. ✅ Approve objective via UI
3. ⏸️ Frontend receives `needs_mapping: true`
4. ⏸️ Frontend calls mapping endpoint
5. ⏸️ Progress indicator shown
6. ⏸️ Objective now mapped to controls

### Scenario 3: Reject Objective
1. ✅ Find objective that has existing control mappings
2. ✅ Reject objective via UI
3. ✅ Verify all mappings deleted from ControlObjectiveMapping table

### Scenario 4: Gap Extraction Creates Objective
1. ✅ Gap extraction finds missing objective
2. ✅ New objective created with confidence score
3. ✅ If confidence >= 65%, auto-mapped during pipeline
4. ✅ If confidence < 65%, requires manual approval before mapping

---

## Frontend Integration TODO

### 1. Mapping Progress Indicator
When approval triggers mapping, show:
- Progress bar (reuse existing job progress UI)
- Status: "Mapping objective to controls..."
- Poll mapping job status until complete

### 2. Handle `needs_mapping` Response
```javascript
const response = await updateObjectiveStatus(objectiveId, "approved");
if (response.needs_mapping) {
  // Trigger mapping
  const mappingJob = await triggerMapping(scanId);
  // Show progress indicator
  showMappingProgress(mappingJob.job_id);
}
```

### 3. Mapping Endpoint Integration
```javascript
async function triggerMapping(scanId) {
  return await fetch(`/report/${scanId}/objectives/map`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  });
}
```

---

## Benefits

1. **Data Quality**: Only high-confidence objectives auto-mapped
2. **User Control**: Low-confidence objectives require manual review
3. **Correct Timing**: Mapping happens after ALL objectives identified (including gaps)
4. **Clean State**: Rejected objectives automatically unmapped
5. **User Feedback**: Progress indicators for long-running mapping operations

---

## Related Files

- `backend/app/extractors/objective_extractor.py` - Mapping logic + confidence filter
- `backend/app/routers/objective_router.py` - Update endpoint + rejection unmapping
- `backend/app/main.py` - Pipeline flow + timing
- `backend/app/models/models.py` - Database schema
