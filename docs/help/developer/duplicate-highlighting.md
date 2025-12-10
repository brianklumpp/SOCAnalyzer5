# Duplicate Control Highlighting

## Overview

The frontend automatically detects and visually highlights control rows that have duplicate `control_id` values, helping users quickly identify controls that may need review.

## Visual Appearance

**Duplicate controls are highlighted with:**
- Background color: `#ffe4cc` (light orange/peach)
- Left border: `3px solid #ff9800` (orange)

This orange color scheme:
- Stands out from other highlight colors (yellow for ignored, red for deviations, green for recently changed)
- Indicates a "warning" state without being as severe as red
- Is easily visible but not overwhelming

## How It Works

### Detection Logic

The system counts occurrences of each `control_id` in the current view:

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

**Process:**
1. Iterates through all controls in current view
2. Counts occurrences of each `control_id`
3. Creates a Set of IDs that appear more than once
4. Uses `useMemo` to recalculate only when controls change

### Applying Highlights

The duplicate IDs are passed to the `EditableTable` component:

```typescript
<EditableTable
  columns={columns}
  rows={sectionSortedRows}
  ignored={ignored}
  duplicateIds={duplicateControlIds}  // New prop
  // ... other props
/>
```

In the table, rows are styled conditionally:

```typescript
<TableRow 
  sx={{
    ...(duplicateIds?.has(String(row.control_id)) ? 
      { backgroundColor: '#ffe4cc', borderLeft: '3px solid #ff9800' } : {}),
    // ... other conditional styles
  }}
>
```

## Priority Order of Highlighting

Multiple highlighting conditions are applied with this priority (last wins):

1. **Ignored rows** (opacity + strikethrough)
2. **Duplicate IDs** (orange background) ⬅️
3. **Zero confidence** (yellow background)
4. **Has deviation** (red background)
5. **Recently changed** (green background)

If a row matches multiple conditions, the last applicable style wins. For example, a duplicate control with a deviation will show red (deviation takes priority).

## Common Duplicate Scenarios

### 1. Page Continuations
Controls split across pages may be extracted multiple times:
```
SM-03-01 (page 15, lines 450-470)
SM-03-01 (page 16, lines 471-490)
```

### 2. Table Headers
Control ID repeated as table header:
```
BM-01-01 (actual control)
BM-01-01 (table header row)
```

### 3. Extraction Boundaries
V4 extraction chunks may overlap and extract the same control:
```
TPM-01-01 (chunk 5)
TPM-01-01 (chunk 6 overlap)
```

## Use Cases

1. **Quality Assurance** - Quickly identify controls extracted multiple times
2. **Manual Review** - Highlight controls that might need consolidation
3. **V4 Extraction Debugging** - Identify when page continuations created duplicates
4. **Data Cleanup** - Find and resolve duplicate control entries

## Handling Duplicates

### Manual Resolution

1. **Review instances** - Click on each duplicate to review content
2. **Compare details** - Check if description, tests, results differ
3. **Keep best instance** - Keep the most complete version
4. **Delete others** - Delete partial or incomplete instances
5. **Or merge** - Use batch edit to consolidate information

### Automatic Merging (V4)

V4 extractor has continuation handling to automatically merge controls:

```python
# Three merge criteria:
# 1. Previous control has continuation: true
# 2. Consecutive control_ids match
# 3. Adjacent line ranges (within 5 lines)
```

This reduces duplicates but doesn't eliminate them entirely.

### Database-Level Deduplication

For bulk cleanup, use database queries:

```sql
-- Find all duplicate control IDs
SELECT control_id, COUNT(*) as count
FROM controls
WHERE scan_id = 6
GROUP BY control_id
HAVING COUNT(*) > 1
ORDER BY count DESC;

-- Keep highest confidence instance, delete others
DELETE FROM controls c1
WHERE EXISTS (
  SELECT 1 FROM controls c2
  WHERE c2.control_id = c1.control_id
  AND c2.scan_id = c1.scan_id
  AND c2.control_confidence > c1.control_confidence
  AND c2.id > c1.id
);
```

## Statistics

When applied to scan 6, the following controls were highlighted as duplicates:

**2 instances (12 control IDs):**
- VM-01-01, RM-02-02, VM-02-01, IAM-02-03, CFM-01-02, SM-02-01, SM-02-02, IR-01-01, BC-01-02, TPM-02-02, DM-06-02, TPM-04-01

**3 instances (2 control IDs):**
- TPM-01-01, BM-01-01

**4 instances (1 control ID):**
- SM-03-01

**5 instances (1 control ID):**
- BM-01-02

**Total:** 16 unique control IDs with duplicates, 50 total duplicate instances

## Files Modified

1. **frontend/src/components/EditableTable.tsx**
   - Added `duplicateIds?: Set<string>` to interface
   - Added duplicate highlighting to TableRow styles
   - Updated component signature to accept new prop

2. **frontend/src/pages/ReportPage.tsx**
   - Added `duplicateControlIds` detection logic using `useMemo`
   - Passed `duplicateIds` prop to EditableTable

## Future Enhancements

Possible improvements:

1. **Tooltip** - Show "This control ID appears X times" on hover
2. **Show All Instances** - Button to view all instances side-by-side
3. **Statistics** - Total duplicate count in section header
4. **Filter** - Option to "Show only duplicates"
5. **Auto-merge** - Action button to automatically merge duplicates
6. **Comparison View** - Diff view showing differences between instances

## Related Features

- **Confidence Filtering** - V4 extractor filters low-confidence controls (< 0.5)
- **Continuation Handling** - V4 automatically merges some split controls
- **Batch Edit** - Edit multiple controls at once (including duplicates)
- **Ignored Controls** - Mark duplicates as ignored if they're false positives

## Further Reading

- See **V4 Extraction Architecture** for continuation handling details
- See **Features > Controls Tab** for manual editing workflow
- See **Features > Batch Edit Mode** for bulk operations
- See **Troubleshooting > Common Errors** for extraction issues
