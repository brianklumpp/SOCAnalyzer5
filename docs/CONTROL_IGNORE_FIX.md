# Control Ignore Functionality Fix

**Date:** November 12, 2025
**Issue:** Clicking IGNORE on a control showed "saved" message but nothing happened
**Status:** ✅ RESOLVED

## Problem

When clicking the IGNORE button on a control row in the frontend:
- Toast notification showed "Control saved"
- No visible change occurred (row didn't get strikethrough, confidence didn't change to 0)
- Backend was not being called
- The ignore action appeared to do nothing

## Root Cause

The `ControlsTable` component had a local `handleIgnore` function that was not properly connected to the parent's `ignoreRow` function:

```typescript
// OLD - Broken implementation
const handleIgnore = (row: any, idx: number, type: string) => {
  const newRow = { ...row, confidence: 0, cuec_confidence: 0, control_confidence: 0 };
  onEdit(newRow, idx);  // This only updates local state, doesn't call backend
};
```

**Issues:**
1. `ControlsTable` component was missing an `onIgnore` prop in its interface
2. Parent component (`ReportPage`) wasn't passing the `ignoreRow` function
3. Local `handleIgnore` only called `onEdit` which doesn't trigger the backend API
4. No visual feedback because the backend wasn't updating the confidence to 0

## Solution

### 1. Added `onIgnore` prop to ControlsTable

**File:** `frontend/src/pages/ReportPage.tsx`

```typescript
interface ControlsTableProps {
  controls: Control[];
  ignored: Set<number>;
  setIgnored: React.Dispatch<React.SetStateAction<any>>;
  onEdit: (row: Control, idx: number) => void;
  onBatchEdit?: (changes: { [rowIdx: number]: any }, sectionRows: any[]) => void;
  onRecompute: (row: any) => Promise<void>;
  onIgnore?: (row: any) => void;  // NEW PROP
}
```

### 2. Updated component signature to accept onIgnore

```typescript
export function ControlsTable({ 
  controls, 
  ignored, 
  setIgnored, 
  onEdit, 
  onBatchEdit, 
  onRecompute, 
  onIgnore  // NEW PARAMETER
}: ControlsTableProps) {
```

### 3. Updated handleIgnore to call parent's onIgnore

```typescript
// NEW - Working implementation
const handleIgnore = (row: any, idx: number, type: string) => {
  if (onIgnore) {
    onIgnore(row);  // Call parent's ignoreRow function
  } else {
    // Fallback to old behavior if onIgnore not provided
    const newRow = { ...row, confidence: 0, cuec_confidence: 0, control_confidence: 0 };
    onEdit(newRow, idx);
  }
};
```

### 4. Pass ignoreRow function from parent

```typescript
<ControlsTable
  controls={filteredHighConfControls}
  ignored={ignored.controls}
  setIgnored={setIgnored}
  onEdit={(row, idx) => handleEditControl(row, idx)}
  onBatchEdit={(changes: any, sectionRows: any[]) => handleBatchEditControls(changes, sectionRows)}
  onRecompute={handleRecomputeControl}
  onIgnore={(row) => ignoreRow(row, 'controls')}  // NEW LINE
/>
```

## How ignoreRow Works

The parent component's `ignoreRow` function (lines 900-970):

1. **Builds the API endpoint:**
   ```typescript
   endpoint = row.id != null
     ? `${API_URL}${selectedScanId}/controls/id/${encodeURIComponent(row.id)}`
     : `${API_URL}${selectedScanId}/controls/${encodeURIComponent(row.control_id)}`;
   ```

2. **Prepares update payload:**
   ```typescript
   updateData = {
     control_confidence: 0,
     confidence_calc: (row.confidence_calc || '') + '; Manually ignored in UI - confidence set to 0'
   };
   ```

3. **Calls backend API:**
   ```typescript
   await api.patch(endpoint, updateData);
   ```

4. **Updates UI state:**
   - Adds control to ignored set
   - Optimistically updates report state
   - Shows success toast

5. **Visual feedback:**
   - Row gets strikethrough styling
   - Opacity reduced to 0.4
   - Confidence shows as 0%

## Testing

Created test script: `test_scripts/test_ignore_functionality.py`

**Test Results:**
```
✓ Found test control (CC1.3, DB ID 1533, confidence: 67.5%)
✓ PATCH successful - control ignored
✓ Updated control retrieved: New confidence = 0.0
✅ Control successfully ignored (confidence = 0)
✓ Control restored to original confidence
```

## Files Modified

1. **frontend/src/pages/ReportPage.tsx**
   - Added `onIgnore?: (row: any) => void;` to `ControlsTableProps` interface
   - Added `onIgnore` parameter to component signature
   - Updated `handleIgnore` to call parent's `onIgnore`
   - Passed `onIgnore={(row) => ignoreRow(row, 'controls')}` to both high and low confidence tables

## Expected Behavior After Fix

1. Click IGNORE button on a control row
2. Backend API called with `control_confidence: 0`
3. Success toast appears: "Control ignored"
4. Row immediately shows:
   - Strikethrough text
   - Reduced opacity (0.4)
   - Confidence = 0%
5. Row moves to "Low Confidence" section (confidence < 89%)
6. Can be restored by editing confidence back to > 0

## Deployment

1. Frontend rebuilt: `npm run build`
2. Frontend container restarted: `docker-compose restart frontend`
3. Changes are immediately effective
4. No backend changes required

## Related Components

**Other tables that have working ignore:**
- CUECs table (already working)
- Subservice Orgs table (already working)

**Why they work:**
They properly pass `onIgnore` or `onIgnoreRow` props from parent to child components.
