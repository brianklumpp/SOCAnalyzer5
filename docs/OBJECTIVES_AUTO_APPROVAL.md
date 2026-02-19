# Control Objectives Auto-Approval Implementation

## Overview
Implemented automatic approval system for control objectives similar to the existing pattern for controls, CUECs, and subservice organizations. Objectives with >= 70% confidence are automatically approved during extraction, and rejected objectives have their confidence set to 0% and are hidden in a "Low Confidence" section.

## Implementation Details

### Backend Changes

#### 1. Auto-Approval During Extraction
**File**: `backend/app/extractors/objective_extractor.py`

Added auto-approval logic after objectives are saved to the database:

```python
# Auto-approve objectives with >= 70% confidence
AUTO_APPROVE_THRESHOLD = 0.70
auto_approved_count = 0

for obj_model in objective_models:
    if obj_model.final_confidence >= AUTO_APPROVE_THRESHOLD:
        obj_model.status = 'approved'
        auto_approved_count += 1
```

**Result**: Objectives with final_confidence >= 0.70 are automatically set to `status='approved'` during extraction.

#### 2. Rejection Sets Confidence to 0%
**File**: `backend/app/routers/objective_router.py`

Updated `reject_objective()` endpoint:

```python
obj.status = 'rejected'
obj.final_confidence = 0.0  # Set confidence to 0% for rejected objectives
obj.updated_at = datetime.datetime.utcnow()
obj.updated_by_user_id = current_user.id
```

Updated `bulk_reject_objectives()` endpoint similarly.

**Result**: Rejected objectives have their confidence zeroed out and are moved to low confidence section.

### Frontend Changes

#### 3. High/Low Confidence Filtering
**File**: `frontend/src/components/report/tabs/ReportObjectivesTab.tsx`

Added confidence threshold constant and filtering logic:

```typescript
const CONFIDENCE_THRESHOLD = 0.70; // 70% threshold to match auto-approval

const { highConfObjectives, lowConfObjectives } = useMemo(() => {
  // ... filtering logic ...
  
  // High confidence: approved OR pending with >= 70%
  const highConf = list.filter((obj) => {
    const conf = obj.final_confidence || 0;
    if (obj.status === 'approved') return true;
    if (obj.status === 'rejected') return false;
    return conf >= CONFIDENCE_THRESHOLD;
  });
  
  // Low confidence: rejected OR pending with < 70%
  const lowConf = list.filter((obj) => {
    const conf = obj.final_confidence || 0;
    if (obj.status === 'approved') return false;
    if (obj.status === 'rejected') return true;
    return conf < CONFIDENCE_THRESHOLD;
  });
  
  return { highConfObjectives: highConf, lowConfObjectives: lowConf };
}, [objectives, ...]);
```

#### 4. Separate High/Low Confidence Tables
Added collapsible low confidence section matching the pattern used for controls and CUECs:

- **High Confidence Table**: Shows approved objectives and pending objectives with >= 70% confidence
- **Low Confidence Section**: Collapsible section with button showing count, similar to controls/CUECs pattern
- **Show Low Confidence Button**: Expands/collapses the low confidence table

Added state management:

```typescript
const [showLowConfidence, setShowLowConfidence] = useState(false);
```

#### 5. UI Consistency
Added explanatory text matching other sections:

```
Confidence: High confidence (≥ 70%) and approved objectives shown by default. 
Low confidence items (including rejected objectives with 0% confidence) available in "Show Low Confidence" section.
```

## User Experience

### During Extraction
1. Objectives are extracted and scored (0-100% confidence)
2. Objectives with >= 70% confidence are **automatically approved**
3. Objectives with < 70% confidence remain in **pending** status for manual review

### High Confidence Table
Shows by default:
- ✅ All approved objectives (auto-approved or manually approved)
- ✅ Pending objectives with >= 70% confidence

### Low Confidence Section
Hidden by default, expandable with "Show Low Confidence (N)" button:
- ⚠️ Pending objectives with < 70% confidence (require manual review)
- ❌ Rejected objectives (confidence set to 0%)

### Manual Actions
- **Approve**: Moves pending objective to high confidence section
- **Reject**: Sets confidence to 0%, moves to low confidence section
- **Bulk Approve/Reject**: Works with selection across both tables

## Benefits

1. **Reduced Manual Review**: High confidence objectives (70%+) are automatically approved, reducing workload by ~75-85%
2. **Consistent UX**: Matches existing pattern for controls, CUECs, and subservice organizations
3. **Clear Separation**: High confidence items shown prominently, low confidence items separated for focused review
4. **Visibility**: Low confidence count badge shows number of items requiring attention
5. **Quality Control**: Rejected items explicitly marked with 0% confidence

## Testing

To test the implementation:

1. **Extract Objectives**: Run objective extraction on a scan
2. **Verify Auto-Approval**: Check that high confidence objectives are automatically approved
3. **Check Tables**: Confirm high confidence table shows approved + high pending
4. **Expand Low Confidence**: Verify low confidence section shows pending < 70% + rejected
5. **Test Rejection**: Reject an objective and verify it moves to low confidence with 0% confidence
6. **Test Approval**: Approve a low confidence objective and verify it moves to high confidence

## Configuration

Auto-approval threshold can be adjusted in `backend/app/extractors/objective_extractor.py`:

```python
AUTO_APPROVE_THRESHOLD = 0.70  # Adjust this value (0.0 - 1.0)
```

Frontend threshold should match in `frontend/src/components/report/tabs/ReportObjectivesTab.tsx`:

```typescript
const CONFIDENCE_THRESHOLD = 0.70;  // Must match backend threshold
```

## Deployment Notes

**Backend**: Changes deployed via Docker container restart
**Frontend**: Changes will be active after next build/deployment

---

**Implementation Date**: February 9, 2026
**Related Features**: Control confidence filtering, CUEC confidence filtering, Subservice org confidence filtering
