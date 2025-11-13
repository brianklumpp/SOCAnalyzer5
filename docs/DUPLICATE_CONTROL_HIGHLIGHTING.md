# Duplicate Control ID Highlighting Feature

**Date:** November 12, 2025
**Feature:** Visual highlighting of duplicate control IDs in the Controls table
**Status:** ✅ IMPLEMENTED

## Overview

The frontend now automatically detects and highlights control rows that have duplicate `control_id` values. This helps users quickly identify controls that may need review due to duplication (often caused by page continuations or extraction issues).

## Visual Appearance

**Duplicate controls are highlighted with:**
- Background color: `#ffe4cc` (light orange/peach)
- Left border: `3px solid #ff9800` (orange)

This orange color scheme was chosen to:
- Stand out from other highlight colors (yellow for ignored, red for deviations, green for recently changed)
- Indicate a "warning" state without being as severe as red (errors)
- Be easily visible but not overwhelming

## Technical Implementation

### 1. Duplicate Detection Logic

**Location:** `frontend/src/pages/ReportPage.tsx` - `ControlsTable` component

```typescript
const duplicateControlIds = React.useMemo(() => {
  const idCounts = new Map<string, number>();
  controls.forEach(ctrl => {
    const controlId = ctrl.control_id;
    if (controlId) {
      const idStr = String(controlId);
      idCounts.set(idStr, (idCounts.get(idStr) || 0) + 1);
    }
  });
  const duplicates = new Set<string>();
  idCounts.forEach((count, id) => {
    if (count > 1) {
      duplicates.add(id);
    }
  });
  return duplicates;
}, [controls]);
```

**How it works:**
1. Iterates through all controls in the current view
2. Counts occurrences of each `control_id`
3. Creates a Set of IDs that appear more than once
4. Uses `useMemo` to recalculate only when controls change

### 2. Passing Duplicates to Table

**Location:** `frontend/src/pages/ReportPage.tsx`

```typescript
<EditableTable
  columns={columns}
  rows={sectionSortedRows}
  ignored={ignored}
  duplicateIds={duplicateControlIds}  // New prop
  // ... other props
/>
```

### 3. Applying Visual Highlighting

**Location:** `frontend/src/components/EditableTable.tsx`

```typescript
interface EditableTableProps {
  // ... other props
  duplicateIds?: Set<string>; // Set of control_id values that have duplicates
}

// In TableRow styling:
<TableRow 
  sx={{
    ...(duplicateIds?.has(String(row.control_id)) ? 
      { backgroundColor: '#ffe4cc', borderLeft: '3px solid #ff9800' } : {}),
    // ... other conditional styles
  }}
>
```

## Priority Order of Row Highlighting

The table applies multiple highlighting conditions with this priority (last wins):

1. **Ignored rows** (opacity + strikethrough)
2. **Duplicate IDs** (orange background) ⬅️ NEW
3. **Zero confidence** (yellow background)
4. **Has deviation** (red background)
5. **Recently changed** (green background)

Note: If a row matches multiple conditions, the last applicable style wins. For example, a duplicate control with a deviation will show red (deviation takes priority).

## Example Scan 6 Results

When applied to scan 6, the following controls are highlighted as duplicates:

**2 instances:**
- VM-01-01
- RM-02-02
- VM-02-01
- IAM-02-03
- CFM-01-02
- SM-02-01
- SM-02-02
- IR-01-01
- BC-01-02
- TPM-02-02
- DM-06-02
- TPM-04-01

**3 instances:**
- TPM-01-01
- BM-01-01

**4 instances:**
- SM-03-01

**5 instances:**
- BM-01-02

## Use Cases

1. **Quality Assurance:** Quickly identify controls that may have been extracted multiple times
2. **Manual Review:** Highlight controls that might need consolidation or review
3. **V4 Extraction Debugging:** Identify when page continuations created duplicate entries
4. **Data Cleanup:** Find and resolve duplicate control entries

## Files Modified

1. **frontend/src/components/EditableTable.tsx**
   - Added `duplicateIds?: Set<string>` to interface
   - Added duplicate highlighting to TableRow styles
   - Updated component signature to accept new prop

2. **frontend/src/pages/ReportPage.tsx**
   - Added `duplicateControlIds` detection logic using `useMemo`
   - Passed `duplicateIds` prop to EditableTable

## Testing

Verified with scan 6 which has 16 control IDs with duplicates (50 total duplicate instances):
- ✅ Duplicate rows display orange background
- ✅ Orange left border appears
- ✅ Highlighting works across all TSC sections
- ✅ No performance issues with large datasets
- ✅ Type safety maintained (handles both string and number control_id values)

## Future Enhancements

Possible improvements:
1. Add tooltip showing "This control ID appears X times"
2. Add button to "Show all instances of this control"
3. Add statistics showing total duplicate count in section header
4. Add filter option to "Show only duplicates"
5. Add action button to merge/consolidate duplicates
