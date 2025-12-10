# Controls Tab

## Overview

The Controls Tab provides a comprehensive interface for viewing, editing, and managing all extracted controls from a SOC report.

## Features

### Data Table
Displays all controls with key information:
- **Control ID**: Unique identifier
- **Description**: Control description (truncated in table)
- **Test Procedure**: How the control was tested
- **Test Results**: Outcome of testing
- **TSC Criteria**: Trust Services Criteria alignment
- **COSO Criteria**: COSO 2013 alignment
- **Confidence**: Extraction confidence score
- **Has Deviation**: Exception indicator
- **Pages**: Source page references

### Inline Editing
Click any cell to edit:
1. Click cell to enter edit mode
2. Modify the value
3. Press Enter or click outside to save
4. Changes save automatically to database

### Sorting & Filtering
- **Sort**: Click column headers
- **Filter**: Use search box for text filtering
- **Multi-column**: Hold Shift for multi-sort

### Batch Edit Mode
Edit multiple controls at once:
1. Click "Batch Edit" button
2. Select controls using checkboxes
3. Choose field to edit
4. Enter new value
5. Apply to all selected controls

See [Batch Edit Mode](#batch-edit) for details.

### Duplicate Instance Handling
Controls with duplicate instances show:
- **Blue Background**: Visual indicator
- **Chain Link Icon**: Instance marker
- **Instance Badge**: "Instance X of Y"
- **Link/Unlink Actions**: Manage relationships

### Merge Suggestions
Access control merge recommendations:
1. Click "Suggest Merges" button
2. Review side-by-side comparisons
3. Choose action:
   - **Ignore**: Hide temporarily
   - **Dismiss**: Permanently reject
   - **Link**: Mark as duplicate instances
   - **Merge**: Combine into single control

## Column Details

### Control ID
- Format varies by auditor (e.g., CC6.1, EL-06-02)
- Click to sort alphabetically
- Used for cross-referencing

### Description
- Full control description text
- Truncated in table view
- Click cell to expand and edit

### Test Procedure
- Details how control was tested
- May include sample sizes
- Can be edited for clarification

### Test Results
- Outcome of testing
- Typically "No exceptions noted"
- Deviations highlighted

### TSC Criteria
- Comma-separated list
- Editable dropdown selection
- Affects coverage calculations

### COSO Criteria
- Comma-separated principle numbers
- Editable dropdown selection
- Maps to COSO components

### Confidence
- 0-100% score
- Based on 6-factor system:
  1. GPT confidence (22.5%)
  2. Pattern match (18%)
  3. Structure (18%)
  4. Framework (18%)
  5. Deviation (13.5%)
  6. ID format (10%)

### Has Deviation
- Boolean flag
- Automatically detected
- Manual override available

### Deviation Description
- Details of exceptions
- Only populated when has_deviation = true
- Critical for audit follow-up

## Actions

### Export
Export controls to Excel or PDF:
1. Click "Export" button
2. Choose format
3. Select columns
4. Download file

### Delete
Remove controls:
1. Select control(s)
2. Click "Delete" button
3. Confirm action
4. Cannot be undone

### Refresh
Reload data from database:
- Click "Refresh" button
- Useful after bulk operations
- Clears local cache

## Best Practices

1. **Review Confidence Scores**: Focus on controls < 70%
2. **Validate Criteria**: Ensure TSC/COSO mappings accurate
3. **Check Deviations**: Verify all exceptions documented
4. **Use Batch Edit**: Efficient for repetitive updates
5. **Regular Exports**: Backup data periodically
