# Batch Edit Mode

Efficiently edit multiple records at once in Controls, CUECs, or Subservice Organizations tabs.

## What is Batch Edit?

Batch Edit mode allows you to make the same change across multiple rows simultaneously without editing each row individually. Perfect for:

- Updating confidence scores for similar controls
- Changing framework mappings in bulk
- Adding annotations to multiple records
- Correcting systematic extraction errors

## How to Use

### 1. Enable Batch Edit Mode

Click the **"Enable Batch Edit"** toggle at the top of any table (Controls, CUECs, or Subservice Orgs tab).

**Note:** For tables with 50+ rows, there's a brief loading delay as the system prepares the interface.

### 2. Select Rows

- Click checkboxes next to rows you want to edit
- Use "Select All" checkbox in header to select all visible rows
- Selected rows are highlighted

### 3. Edit Common Fields

When rows are selected, a **batch edit panel** appears at the bottom showing:

- Number of selected rows
- Editable fields available for batch update
- Current values (if consistent across selection)

### 4. Make Changes

Type new values in the batch edit fields:
- **Text fields**: Enter new value (applied to all selected)
- **Dropdowns**: Select new option (applied to all selected)
- **Confidence**: Enter new confidence score (0.0-1.0)

### 5. Apply Changes

Click **"Apply to Selected"** button to save changes to all selected rows.

### 6. Disable Batch Edit

Click the **"Disable Batch Edit"** toggle when finished to return to normal view.

## Available Fields

### Controls Tab

Batch editable fields:
- **Control Confidence** - Adjust quality score (0.0-1.0)
- **TSC Framework** - Change Trust Services Criteria mapping
- **COSO Framework** - Change COSO principle mapping
- **Deviation Status** - Mark as deviation or not
- **Annotation** - Add notes or comments

### CUECs Tab

Batch editable fields:
- **CUEC Confidence** - Adjust quality score
- **Framework Alignment** - Change TSC/COSO mapping
- **Annotation** - Add notes

### Subservice Orgs Tab

Batch editable fields:
- **Confidence** - Adjust quality score
- **Annotation** - Add notes

## Performance Considerations

### Table Size Warnings

**50-100 rows:**
- Brief loading spinner (50ms delay)
- "Preparing X rows for batch editing..."
- Normal performance

**100+ rows:**
- Warning tooltip appears
- "Large table - batch edit may be slow"
- Consider filtering data first

**200+ rows:**
- Noticeable delay when enabling
- Frontend memory usage increases
- May experience lag with rapid edits

### Optimization Tips

1. **Filter before batch editing**
   - Use search/filter to reduce visible rows
   - Enable batch edit on filtered subset

2. **Work in batches**
   - Edit 50-100 rows at a time
   - Disable and re-enable between batches

3. **Avoid rapid toggling**
   - Enable once, make all edits, then disable
   - Toggling frequently causes re-rendering

## Common Use Cases

### 1. Boosting Low Confidence Controls

**Scenario:** Manual review confirms low confidence controls are accurate.

**Steps:**
1. Filter controls with confidence 0.50-0.74
2. Enable Batch Edit
3. Select verified controls
4. Set confidence to 0.85
5. Apply changes

### 2. Bulk TSC Reassignment

**Scenario:** Multiple controls should map to CC6.1 instead of CC6.2.

**Steps:**
1. Search for "CC6.2" in TSC column
2. Enable Batch Edit
3. Select all incorrect mappings
4. Change TSC to "CC6.1"
5. Apply changes

### 3. Adding Annotations

**Scenario:** Mark controls requiring executive review.

**Steps:**
1. Enable Batch Edit
2. Select relevant controls
3. Add annotation: "Executive review needed"
4. Apply changes

### 4. Flagging Deviations

**Scenario:** Identify all deviations for a specific control area.

**Steps:**
1. Filter controls by TSC section (e.g., "CC7")
2. Enable Batch Edit
3. Select controls with deviations
4. Set deviation status = true
5. Apply changes

## Troubleshooting

### Batch Edit Button Disabled

**Cause:** No editable fields in current view

**Solution:** Ensure you're in a tab with editable data (Controls, CUECs, Subservice Orgs)

### Changes Not Saving

**Cause:** Network error or validation failure

**Solution:**
- Check browser console for errors
- Verify field values are valid
- Ensure required fields are not empty
- Try editing fewer rows at once

### Browser Freezing/Slow

**Cause:** Too many rows selected

**Solution:**
- Disable batch edit and refresh page
- Filter data to reduce row count
- Edit in smaller batches (< 100 rows)
- Increase Node.js memory if self-hosting

### Selection Not Working

**Cause:** Batch edit not fully enabled

**Solution:**
- Wait for loading spinner to complete
- Disable and re-enable batch edit
- Refresh page if problem persists

## Technical Details

### Memory Management

The frontend uses an increased Node.js heap size (8GB) to handle large tables:

```javascript
// docker-compose.yml
NODE_OPTIONS: "--max-old-space-size=8192"
```

### Loading Mechanism

For tables with 50+ rows, batch edit initialization includes:

```javascript
if (rowCount >= 50) {
  setBatchEditLoading(true);
  await sleep(50); // Allow UI to render spinner
  // Initialize batch edit state
  setBatchEditLoading(false);
}
```

### Change Tracking

Batch edits are tracked in component state:

```javascript
const [batchChanges, setBatchChanges] = useState({});

// Apply to all selected rows
selectedRows.forEach(rowId => {
  applyChanges(rowId, batchChanges);
});
```

## Best Practices

### Before Enabling Batch Edit

✅ **Filter data** - Reduce visible rows
✅ **Save current work** - Commit any pending single edits
✅ **Plan changes** - Know what fields you'll update

### While in Batch Edit Mode

✅ **Select carefully** - Double-check selection before applying
✅ **Apply incrementally** - Don't select all 200+ rows at once
✅ **Verify changes** - Spot check a few rows after applying

### After Batch Editing

✅ **Disable mode** - Return to normal view
✅ **Verify results** - Review updated rows
✅ **Check confidence** - Ensure scores make sense

### What to Avoid

❌ **Don't** enable on 200+ row tables without filtering
❌ **Don't** make critical changes without verification
❌ **Don't** rapidly toggle batch edit on/off
❌ **Don't** edit required fields in batch (may cause validation errors)

## See Also

- [Controls Tab](#controls-tab) - Control data management
- [Common Errors](#common-errors) - Troubleshooting batch edit issues
- [Performance Tips](#performance) - Optimizing large table handling
