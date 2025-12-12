# SOCAnalyzer v1.0.17 Release Notes

**Release Date**: December 12, 2024  
**Type**: Feature Enhancement

## Overview

This release adds the ability to manually edit Control IDs in the frontend, addressing cases where the extractor misses or incorrectly identifies control IDs.

## New Features

### Editable Control ID Column

**Problem Solved**: Previously, when the extractor missed or incorrectly identified a control ID, there was no way to manually correct it in the UI.

**Solution**: The Control ID column is now fully editable, allowing users to:
- Add missing control IDs that the extractor failed to detect
- Correct misidentified control IDs
- Update control IDs as needed for reporting purposes

**How to Use**:
1. Navigate to the Controls tab in any scan
2. Click the Edit button (pencil icon) on any row
3. The Control ID field now shows an editable text input
4. Modify the control ID as needed
5. Click Save to persist the change

**Technical Details**:
- Backend now accepts `control_id` updates in both PATCH endpoints
- Frontend column marked as `editable: true`
- Changes persist immediately to database
- Existing tooltip and clickable link functionality preserved in view mode

## Changes Made

### Backend (`backend/app/main.py`)

Added control_id editing support to both PATCH endpoints:

**Endpoint 1**: `/report/{scan_id}/controls/{control_id}`
**Endpoint 2**: `/report/{scan_id}/controls/id/{control_db_id}`

```python
# Allow editing control_id
if "control_id" in data:
    ctrl.control_id = data["control_id"]
```

### Frontend (`frontend/src/config/report/columnDefinitions.tsx`)

Changed Control ID column from non-editable to editable:

```tsx
{ 
  key: "control_id", 
  label: "Control ID", 
  width: 80,
  editable: true,  // Changed from false
  render: (row: any) => onOpenControlModal ? (
    <ControlTooltip control={row} onClick={() => onOpenControlModal(row)}>
      <span style={{ cursor: 'pointer', textDecoration: 'underline', color: '#1976d2' }}>
        {row.control_id || 'N/A'}
      </span>
    </ControlTooltip>
  ) : (row.control_id || 'N/A')
}
```

### Version

Updated `VERSION.txt` to `1.0.17`

## Upgrade Instructions

### From v1.0.16 or Earlier

**Option 1: Clean Upgrade** (Recommended)

1. Stop containers:
   ```powershell
   docker compose down
   ```

2. Extract v1.0.17 over old files

3. Import and start:
   ```powershell
   .\IMPORT.ps1
   ```

**Option 2: In-Place Upgrade**

No special migration steps required. Simply:
1. Load new images: `.\IMPORT.ps1`
2. Restart containers: `docker compose up -d`

### Fresh Installation

No special steps required:
1. Extract `SOCAnalyzer-Docker-v1.0.17.zip`
2. Run `.\IMPORT.ps1`
3. Access application at https://localhost

## Verification

After deployment, verify the feature works:

1. Open any scan with controls
2. Click Edit on a control row
3. Verify Control ID shows as an editable text field (not just a label)
4. Modify a control ID and save
5. Refresh the page and verify the change persisted

## User Interface

**View Mode** (default):
- Control ID displays as clickable link with blue underline
- Clicking opens control detail tooltip/modal
- No changes to existing functionality

**Edit Mode** (when editing a row):
- Control ID displays as editable text input field
- Users can type new values
- Saving updates the database

## Technical Notes

### API Changes

Both PATCH endpoints now accept `control_id` in the request body:

```bash
# Example: Update control ID
curl -X PATCH http://localhost:5001/report/123/controls/id/456 \
  -H "Content-Type: application/json" \
  -d '{"control_id": "NEW-ID-001"}'
```

### Database Impact

- No schema changes required
- Existing `control.control_id` column is used
- No data migration needed

### Backward Compatibility

✅ **Fully backward compatible**
- View mode behavior unchanged
- Existing controls not affected
- API endpoints accept but don't require control_id

## Known Issues

None at this time.

## Future Enhancements

Potential improvements for future releases:
1. **Validation**: Add regex validation for control ID format
2. **Bulk Edit**: Allow editing multiple control IDs at once
3. **Auto-suggest**: Suggest control IDs based on existing patterns
4. **Audit Trail**: Track control_id changes in confidence_calc field

## Previous Releases

- **v1.0.16**: Database migration fixes, fail-fast migrations
- **v1.0.15**: SOC1 framework support, legacy code cleanup
- **v1.0.14**: Certificate fixes, health checks

## Support

If you encounter issues:
1. Check that you're editing via the Edit button (not just clicking the cell)
2. Verify changes save by refreshing the page
3. Check browser console for errors
4. Review backend logs: `docker compose logs backend`

## Files Included in Distribution

- `SOCAnalyzer-Docker-v1.0.17.zip` (336.43 MB)
  - Backend with control_id editing support
  - Frontend with editable Control ID column
  - All standard supporting files and scripts

## Summary

v1.0.17 addresses a common user request by making Control IDs editable, providing flexibility when the automated extractor misses or misidentifies control identifiers. This small but important change improves the user experience and reduces manual workarounds.
