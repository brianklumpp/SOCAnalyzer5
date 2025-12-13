# Endpoint Cleanup Plan - Remove Duplicates from main.py

## Problem

**Duplicate Endpoints**: 37+ endpoints exist in BOTH `main.py` AND the routers, causing:
- Code duplication and maintenance burden
- Confusion about which implementation is active (routers override main.py)
- main.py still at 7,282 lines despite router extraction

## Root Cause

During Week 2 refactoring, endpoints were **copied** to routers but **not removed** from main.py. The routers are registered first (lines 275-299), so they override main.py endpoints.

## Verification Strategy

**Test which implementation is active:**
```powershell
# Check if router endpoints are active
Invoke-RestMethod -Uri "http://localhost:8000/report/8" -Method Get
# If this works and returns data, routers are active

# Temporary test: Comment out router registration
# If endpoints still work, main.py versions are active (should NOT be the case)
```

## Cleanup Tasks

### Phase 1: Report Router Endpoints (PRIORITY 1)

**In Router (`report_router.py`):** 6 endpoints
- ✅ GET /report/{scan_id}
- ✅ GET /pdf/{scan_id}
- ✅ GET /export/excel/{scan_id}
- ✅ GET /report/{scan_id}/pdf
- ✅ PATCH /report/{scan_id}/overview
- ✅ GET /report/{scan_id}/reload_text (renamed from /reload_extracted_text)

**Remove from main.py:**
- [ ] Line 522: @app.get("/report/{scan_id}")
- [ ] Line 857: @app.get("/report/{scan_id}/pdf")
- [ ] Line 3706: @app.post("/report/{scan_id}/reload_extracted_text")
- [ ] Line 3754: @app.patch("/report/{scan_id}/overview")

**Note:** Some endpoints may have minor differences - verify logic is identical before deleting

### Phase 2: Control Router Endpoints (PRIORITY 1)

**In Router (`control_router.py`):** 14 endpoints
- ✅ PATCH /report/{scan_id}/controls/annotation/{control_id} (router format)
- ✅ PATCH /report/{scan_id}/controls/{control_id}
- ✅ PATCH /report/{scan_id}/controls/id/{control_db_id}
- ✅ POST /report/{scan_id}/cleanup
- ✅ GET /report/{scan_id}/controls/suggest-merges
- ✅ POST /report/{scan_id}/controls/merge
- ✅ POST /report/{scan_id}/controls/{control_db_id}/split
- ✅ POST /report/{scan_id}/controls/link
- ✅ DELETE /report/{scan_id}/controls/{control_id}/unlink
- ✅ POST /report/{scan_id}/controls/dismiss-merge
- ✅ GET /report/{scan_id}/controls/duplicate-groups
- ✅ POST /report/{scan_id}/controls/{control_db_id}/recompute_frameworks
- ✅ POST /report/{scan_id}/controls/batch_recompute
- ✅ POST /report/{scan_id}/controls/preview_mappings (router: preview_mappings vs main: preview-frameworks)

**Remove from main.py:**
- [ ] Line 3812: @app.patch("/report/{scan_id}/controls/{control_id}/annotation")
- [ ] Line 3827: @app.patch("/report/{scan_id}/controls/{control_id}")
- [ ] Line 3922: @app.patch("/report/{scan_id}/controls/id/{control_db_id}")
- [ ] Line 4278: @app.post("/report/{scan_id}/cleanup")
- [ ] Line 4429: @app.get("/report/{scan_id}/controls/suggest-merges")
- [ ] Line 4620: @app.post("/report/{scan_id}/controls/merge")
- [ ] Line 4788: @app.post("/report/{scan_id}/controls/{control_db_id}/split")
- [ ] Line 4862: @app.post("/report/{scan_id}/controls/link_instances") (router: /link)
- [ ] Line 5019: @app.post("/report/{scan_id}/controls/unlink_instance/{control_id}")
- [ ] Line 5115: @app.post("/report/{scan_id}/controls/dismiss_merge_suggestion")
- [ ] Line 5188: @app.get("/report/{scan_id}/controls/duplicate_groups")
- [ ] Line 5574: @app.post("/report/{scan_id}/controls/id/{control_db_id}/recompute_frameworks")
- [ ] Line 5733: @app.post("/report/{scan_id}/preview-frameworks")
- [ ] Line 5864: @app.post("/report/{scan_id}/controls/batch_recompute_frameworks")

### Phase 3: Deviation Router Endpoints (PRIORITY 1)

**In Router (`deviation_router.py`):** 6 endpoints
- ✅ GET /report/{scan_id}/deviations
- ✅ PATCH /report/{scan_id}/deviations/{control_id}
- ✅ POST /report/{scan_id}/deviations/{control_id}/regenerate
- ✅ POST /report/{scan_id}/deviations/regenerate_all
- ✅ GET /report/{scan_id}/deviations/regenerate_progress
- ✅ POST /report/{scan_id}/deviations/create (main: /deviation)

**Remove from main.py:**
- [ ] Line 897: @app.get("/report/{scan_id}/deviations")
- [ ] Line 943: @app.patch("/control/{control_id}/deviation-summary")
- [ ] Line 974: @app.post("/control/{control_id}/regenerate-deviation-summary")
- [ ] Line 996: @app.post("/report/{scan_id}/deviations/regenerate-all")
- [ ] Line 1037: @app.get("/report/{scan_id}/deviations/regenerate-progress")
- [ ] Line 1068: @app.post("/report/{scan_id}/deviation")

### Phase 4: CUEC Router Endpoints (PRIORITY 2)

**In Router (`cuec_router.py`):** Check what endpoints exist

**Remove from main.py:**
- [ ] Line 5237: @app.patch("/report/{scan_id}/cuecs/{cuec_id}/annotation")
- [ ] Line 5247: @app.patch("/report/{scan_id}/cuecs/{cuec_id}")
- [ ] Line 5312: @app.patch("/report/{scan_id}/cuecs/tsc/{cuec_tsc_id}")
- [ ] Line 5382: @app.post("/report/{scan_id}/cuecs/{cuec_id}/recompute_frameworks")
- [ ] Line 7037: @app.post("/report/{scan_id}/cuecs")

### Phase 5: Suborg Router Endpoints (PRIORITY 2)

**In Router (`suborg_router.py`):** Check what endpoints exist

**Remove from main.py:**
- [ ] Line 1148: @app.patch("/report/{scan_id}/suborgs/id/{suborg_id}")
- [ ] Line 1169: @app.patch("/report/{scan_id}/suborgs/{suborg_name}")
- [ ] Line 6823: @app.patch("/report/{scan_id}/suborgs/{suborg_id}/annotation")
- [ ] Line 6833: @app.patch("/report/{scan_id}/suborgs/id/{suborg_id}") (duplicate?)
- [ ] Line 6893: @app.patch("/report/{scan_id}/suborgs/{suborg_name}") (duplicate?)
- [ ] Line 6984: @app.post("/report/{scan_id}/suborgs")

### Phase 6: Executive Summary Endpoints (PRIORITY 3)

**Note:** executive_summary_router.py is currently disabled (line 293)

**Remove from main.py AFTER router is fixed and enabled:**
- [ ] Line 3367: @app.get("/executive_summary/{scan_id}")
- [ ] Line 3671: @app.post("/executive_summary/{scan_id}")
- [ ] Line 3692: @app.patch("/executive_summary/{scan_id}")

### Phase 7: Remaining Report Endpoints (PRIORITY 4)

**Not yet in routers - keep in main.py for now:**
- Line 3215: @app.delete("/report/{scan_id}") - Consider adding to report_router
- Line 7083: @app.post("/report/{scan_id}/controls") - Consider adding to control_router
- Line 7138: @app.post("/report/{scan_id}/extract-entity") - Specialized, may stay
- Line 7496: @app.post("/report/{scan_id}/migrate_framework_mappings") - Admin/migration, may stay
- Line 3206: @app.get("/report_diag/{scan_id}") - Diagnostic, keep in main

## Testing Strategy

For EACH endpoint removal:

1. **Verify router has endpoint**:
```powershell
Select-String -Path backend/app/routers/*_router.py -Pattern "endpoint_path"
```

2. **Compare implementations**:
- Read router version
- Read main.py version
- Verify logic is identical or router version is correct

3. **Test endpoint works BEFORE deletion**:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/endpoint" -Method GET/POST/PATCH
```

4. **Remove from main.py** (comment out first, then delete after testing)

5. **Test endpoint still works AFTER deletion**:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/endpoint" -Method GET/POST/PATCH
```

6. **Restart backend if needed**:
```powershell
docker compose restart backend
```

## Expected Results

- **main.py**: Reduce from 7,282 lines to ~4,000 lines (45% reduction)
- **Duplicates removed**: 30+ endpoints
- **Code clarity**: Single source of truth for each endpoint
- **Maintainability**: Changes only need to be made in one place

## Risks & Mitigation

**Risk:** Router implementation differs from main.py implementation
- **Mitigation:** Compare implementations before deletion, test each endpoint

**Risk:** Frontend breaks due to API changes
- **Mitigation:** Use FRONTEND_TESTING_CHECKLIST.md to validate after cleanup

**Risk:** Deleting wrong code
- **Mitigation:** Use git commits for each phase, easy rollback

## Success Criteria

- [ ] All duplicate endpoints removed from main.py
- [ ] Backend starts without errors
- [ ] All API endpoints respond correctly
- [ ] Frontend testing passes (all 7 tabs work)
- [ ] main.py under 5,000 lines
- [ ] Git history shows clear incremental progress

---

**Next Action:** Start with Phase 1 (Report Router) - verify and remove 4 duplicate endpoints
