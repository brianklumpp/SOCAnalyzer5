# Frontend Integration Testing Checklist

**Date:** December 12, 2025  
**URL:** http://localhost:3000/report/8  
**Scan:** Microsoft Corporation (168 controls, 6 deviations)

---

## Pre-Test Verification ✅

- [x] Backend running: `docker ps` shows socanalyzer-backend Up
- [x] Frontend running: `docker ps` shows socanalyzer-frontend Up  
- [x] API accessible: GET /history returns 5 scans
- [x] Scan data available: Scan ID 8 exists with controls

---

## Tab Navigation Testing

### 1. Summary Tab
- [ ] Page loads without errors
- [ ] Company name displays: "Microsoft Corporation"
- [ ] Report metadata visible (dates, auditor, type)
- [ ] Executive summary section present
- [ ] Timeline component displays
- [ ] No 404 errors in console
- [ ] Edit buttons functional

**API Endpoints Used:**
- GET /report/8
- GET /executive_summary/8

---

### 2. Controls Tab
- [ ] Tab switches successfully
- [ ] Control table loads with data
- [ ] 168 controls display correctly
- [ ] Control IDs visible (varied formats: IS-1, DS-1, etc.)
- [ ] Confidence scores display as percentages
- [ ] Duplicate detection highlighting works
- [ ] High/low confidence sections functional
- [ ] "Add Control" button present
- [ ] Edit control annotation works

**Test Operations:**
- [ ] Click control row → Details display
- [ ] Edit control note → PATCH /report/8/controls/id/{id}
- [ ] Filter by confidence → Client-side filtering
- [ ] Sort by column → React-table sorting

**API Endpoints Used:**
- GET /report/8 (controls array)
- PATCH /report/8/controls/id/{control_id}

---

### 3. CUECs Tab
- [ ] Tab switches successfully
- [ ] Table displays (may be empty - scan 8 has 0 CUECs)
- [ ] If empty, shows "No CUECs found" message
- [ ] Add CUEC button present
- [ ] No console errors

**Note:** Scan 8 has 0 CUECs - expected to show empty state

**API Endpoints Used:**
- GET /report/8 (cuecs array)

---

### 4. Subservice Organizations Tab
- [ ] Tab switches successfully
- [ ] Table displays (may be empty - scan 8 has 0 suborgs)
- [ ] If empty, shows appropriate message
- [ ] Add suborg button present
- [ ] No console errors

**Note:** Scan 8 has 0 subservice orgs - expected to show empty state

**API Endpoints Used:**
- GET /report/8 (subservice_orgs array)

---

### 5. Coverage Tab
- [ ] Tab switches successfully
- [ ] TSC donut chart renders
- [ ] COSO donut chart renders
- [ ] Coverage percentages display
- [ ] Framework criteria tables load
- [ ] Clickable criteria rows
- [ ] Tooltip/modal functionality
- [ ] No rendering errors

**Visual Elements:**
- [ ] Charts use correct colors (green/red/gray)
- [ ] Legend displays correctly
- [ ] Percentages calculate correctly
- [ ] Tables are scrollable if needed

**API Endpoints Used:**
- GET /report/8 (framework data)

---

### 6. Deviations Tab
- [ ] Tab switches successfully
- [ ] 6 deviations display correctly
- [ ] Control IDs visible (DS-1, etc.)
- [ ] Deviation descriptions show
- [ ] "Regenerate Summary" buttons work
- [ ] Edit functionality present
- [ ] Severity indicators (if present)

**Test Operations:**
- [ ] Click deviation → Details expand
- [ ] Regenerate summary → POST /report/8/deviations/{id}/regenerate
- [ ] Edit deviation → PATCH request

**API Endpoints Used:**
- GET /report/8/deviations
- POST /report/8/deviations/{control_id}/regenerate

---

### 7. Verification Tab
- [ ] Tab switches successfully
- [ ] Verification section displays
- [ ] Bad chunks shown (if any)
- [ ] JSON formatting correct
- [ ] Status indicators present

**API Endpoints Used:**
- GET /report/8 (verification data)

---

## CRUD Operations Testing

### Control Operations
- [ ] **Edit Note**: PATCH /report/8/controls/id/{id} with `{"user_note": "test"}`
- [ ] **Update Annotation**: Annotation field updates in UI
- [ ] **Recompute Frameworks**: POST /report/8/controls/{id}/recompute_frameworks
- [ ] **Ignore Control**: Mark as ignored, shows in ignored section

### CUEC Operations (if data available)
- [ ] **Edit CUEC**: PATCH /report/8/cuecs/{id}
- [ ] **Add CUEC**: POST via dialog
- [ ] **Recompute**: Framework recomputation

### Deviation Operations
- [ ] **Regenerate Summary**: POST /report/8/deviations/{id}/regenerate
- [ ] **Edit Deviation**: PATCH /report/8/deviations/{id}
- [ ] **Loading State**: Spinner shows during regeneration

---

## Error Handling

### Console Errors to Check
- [ ] No 404 errors (all API endpoints found)
- [ ] No 500 errors (no server crashes)
- [ ] No TypeScript errors
- [ ] No React warnings (key props, etc.)
- [ ] No CORS issues

### Network Tab Inspection
- [ ] All API calls return 200/201/204
- [ ] Response times acceptable (<2s for GET requests)
- [ ] Proper request headers (Content-Type: application/json)
- [ ] No failed requests

---

## UI/UX Validation

### Visual Check
- [ ] Tables render correctly (no overflow issues)
- [ ] Buttons are clickable and styled
- [ ] Modals/dialogs center properly
- [ ] Loading spinners display during operations
- [ ] Toast notifications show on success/error

### Responsive Design
- [ ] Table columns don't clip text
- [ ] Horizontal scroll works if needed
- [ ] Tab bar fits in viewport
- [ ] Dialogs are mobile-friendly (not critical for desktop app)

### Performance
- [ ] Tab switches feel instant (<100ms)
- [ ] No lag when scrolling tables
- [ ] Charts render without flickering
- [ ] Large datasets (168 controls) load smoothly

---

## Router Architecture Validation

### Verify New Router Structure Works
- [ ] All endpoints respond (no 404s from router refactoring)
- [ ] Data serialization correct (JSON structure unchanged)
- [ ] Backward compatibility maintained
- [ ] No breaking changes in API contracts

**Expected Behavior:**
- Frontend should work identically to pre-refactoring version
- All API calls should hit new routers transparently
- No changes to request/response formats

---

## GPT Flexibility Validation (Visual)

### Control ID Format Check
- [ ] Various formats display correctly (IS-1, DS-1, numeric IDs)
- [ ] No "Invalid ID" errors in UI
- [ ] Framework mappings work with varied IDs

### Control Description Rendering
- [ ] Long descriptions display (with truncation if needed)
- [ ] Special characters render correctly
- [ ] Multi-line descriptions format properly

### Framework Badges
- [ ] TSC criteria badges display
- [ ] COSO principle badges display
- [ ] Financial assertion badges (if SOC 1)
- [ ] No hardcoded format expectations

---

## Known Issues / Expected Behavior

### Scan 8 Limitations
- **0 CUECs**: CUECs tab will be empty
- **0 Subservice Orgs**: Suborgs tab will be empty
- **Executive Summary Stale**: Summary needs regeneration (marked as stale)

### Baseline Router
- **Disabled**: Baseline/validation features not accessible (models not implemented)

---

## Test Results Template

```
## Frontend Integration Test Results

**Date:** [YYYY-MM-DD]
**Tester:** [Name]
**Duration:** [X] minutes

### Summary
- Tabs Tested: [X]/7
- CRUD Operations: [X]/[Y] passed
- Console Errors: [X] found
- Overall Status: [PASS/FAIL/PARTIAL]

### Issues Found
1. [Issue description]
   - **Severity:** [Low/Medium/High]
   - **Tab:** [Tab name]
   - **Error:** [Error message]
   - **Fix:** [Action taken]

### Screenshots
[Attach screenshots of each tab]

### Recommendations
- [List any improvements or fixes needed]
```

---

## Automated Testing (Future Enhancement)

### Playwright E2E Tests (v2.1.0)
```typescript
test('Navigate all tabs without errors', async ({ page }) => {
  await page.goto('http://localhost:3000/report/8');
  
  const tabs = ['Summary', 'Controls', 'CUECs', 'Suborgs', 'Coverage', 'Deviations', 'Verification'];
  for (const tab of tabs) {
    await page.click(`text=${tab}`);
    await expect(page.locator('.error-message')).toHaveCount(0);
  }
});

test('Edit control annotation', async ({ page }) => {
  await page.goto('http://localhost:3000/report/8');
  await page.click('text=Controls');
  await page.click('.control-row:first-child');
  await page.fill('textarea[name="user_note"]', 'Test annotation');
  await page.click('button:has-text("Save")');
  await expect(page.locator('.toast-success')).toBeVisible();
});
```

---

**Status:** Manual testing in progress  
**Next:** Complete checklist and report findings
