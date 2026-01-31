# Quick Start: Testing Control Objectives Integration

## Prerequisites
- Backend server running
- Frontend development server running
- At least one SOC 2 report uploaded and analyzed
- Admin user account for full testing

## Step-by-Step Testing Guide

### 1. Initial Setup ✓
```bash
# Terminal 1: Start backend (if not running)
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Start frontend (if not running)
cd frontend
npm start
```

### 2. Navigate to Report Page
1. Open browser: `http://localhost:3000`
2. Login with admin credentials
3. Navigate to a report from the history

### 3. Test Objectives Caching (Performance Check)
**What to Check:**
- Open browser DevTools → Network tab
- Reload the report page
- Look for API calls:
  - ✅ Should see: `GET /api/scans/{id}/objectives` (once)
  - ✅ Should see: `GET /api/scans/{id}/objectives/controls` (once)
  - ❌ Should NOT see: Multiple objective API calls per control

**Expected Behavior:**
- Objectives fetched once on page load
- Data cached in ReportPage state
- No N+1 query problem

### 4. Test Admin Permissions
**As Admin User:**
1. Navigate to "Controls" tab
2. ✅ Verify "Manage Objectives" button is visible in tab label
3. Click the button
4. ✅ Verify ObjectivesModal opens

**As Non-Admin User:**
1. Logout and login as regular user
2. Navigate to "Controls" tab
3. ✅ Verify "Manage Objectives" button is HIDDEN
4. ✅ Verify objectives still visible in "Control Objective" column

### 5. Test Objectives Management Modal
1. Click "Manage Objectives" button (as admin)
2. Test search: Type objective text → results filter
3. Test status filter: Select "Pending", "Approved", "Rejected"
4. Test confidence filter: Adjust min/max sliders
5. Click an objective to select
6. Click "Approve" → status changes to "approved"
7. Select multiple objectives
8. Click "Bulk Approve" → all selected approved
9. Click "Extract Objectives" → extraction job triggered
10. Click "Map Objectives" → mapping UI appears
11. Close modal → verify refresh triggered

**Expected API Calls:**
- `POST /api/scans/{id}/objectives/{objective_id}/approve`
- `POST /api/scans/{id}/objectives/bulk-approve`
- `POST /api/scans/{id}/objectives/extract`
- `GET /api/scans/{id}/objectives` (on refresh)

### 6. Test Objective Coverage Tab
1. Click on "Objective Coverage" tab (Tab 6)
2. ✅ Verify statistics dashboard shows:
   - Total objectives count
   - Approved/Pending/Rejected counts
   - Average confidence score
   - Coverage percentage
3. ✅ Verify objectives listed with controls
4. Click a control name
5. ✅ Verify ControlDetailsModal opens
6. ✅ Verify mapping confidence badges visible
7. ✅ Verify primary objective indicators (star icon)

### 7. Test Controls Table Integration
1. Navigate to "Controls" tab
2. Scroll to "Control Objective" column (may need to scroll right)
3. ✅ Verify column is visible
4. ✅ Verify objectives display for mapped controls
5. ✅ Verify confidence badges show correct colors:
   - 🟢 Green: High confidence (≥85%)
   - 🟡 Yellow: Medium confidence (≥70%)
   - 🔴 Red: Low confidence (<70%)
6. ✅ Verify unmapped controls show empty cell
7. Test low confidence section:
   - Click "Show Low Confidence"
   - ✅ Verify objectives also appear in low confidence controls

### 8. Test Data Refresh
1. Open ObjectivesModal
2. Approve/reject some objectives
3. Close modal
4. ✅ Verify changes reflected in:
   - Controls table (objective column)
   - Objective Coverage tab (statistics)
5. ✅ Verify no manual page refresh needed

### 9. Test Loading States
1. Navigate to a report with many controls
2. Watch the Controls tab on load
3. ✅ Verify objective column doesn't show stale data
4. ✅ Verify loading completes before displaying objectives

### 10. Test Error Handling
1. Stop backend server
2. Navigate to report page
3. ✅ Verify error is caught silently (no crash)
4. ✅ Verify objectives column shows empty (no data)
5. Restart backend server
6. Refresh page
7. ✅ Verify objectives load correctly

## Performance Benchmarks

### Before Integration
- **API Calls**: N (one per control)
- **Load Time**: 10-15 seconds (50 controls)
- **Network Traffic**: High

### After Integration (Expected)
- **API Calls**: 2 (one for objectives, one for mappings)
- **Load Time**: 1-2 seconds (50 controls)
- **Network Traffic**: Low

**Measure Performance:**
1. Open DevTools → Network tab
2. Count API calls to `/objectives` endpoints
3. Measure "Finish" time in network tab
4. ✅ Should see ~80-90% improvement

## Common Issues & Fixes

### Issue: "Manage Objectives" button not visible
**Cause**: User not admin  
**Fix**: Login with admin account or check `is_admin` flag in user table

### Issue: Objectives not displaying in table
**Cause**: Objectives not extracted yet  
**Fix**: Click "Extract Objectives" in ObjectivesModal

### Issue: Modal not opening
**Cause**: JavaScript error or missing import  
**Fix**: Check browser console for errors, verify all imports present

### Issue: Coverage tab empty
**Cause**: No objectives or no mappings created  
**Fix**: Extract objectives and map them to controls first

### Issue: Performance still slow
**Cause**: Cached data not being used  
**Fix**: Verify `objectiveMappings` prop passed to ControlsTable

## Success Criteria ✅

All tests pass if:
- ✅ Only 2 API calls for objectives per scan load
- ✅ "Manage Objectives" button visible to admins only
- ✅ ObjectivesModal opens and functions correctly
- ✅ Objective Coverage tab displays data
- ✅ Control Objective column shows mapped objectives
- ✅ Confidence badges render with correct colors
- ✅ Data refreshes automatically on modal close
- ✅ No TypeScript errors in console
- ✅ No runtime errors in browser console
- ✅ Load time improved by 80-90%

## Next Steps

After successful testing:
1. ✅ Mark integration as complete
2. 📝 Update user documentation
3. 🎓 Train users on objectives feature
4. 🚀 Deploy to production
5. 📊 Monitor performance metrics

---

**Testing Date**: _________  
**Tester**: _________  
**Status**: ⬜ Pending  /  ⬜ In Progress  /  ⬜ Complete  
**Issues Found**: _________
