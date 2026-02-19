# Issues Found & Fixes Required

## Issue 1: Reject Button Not Visible for Approved Objectives

**Status**: Frontend code fixed, but not rebuilt ❌

**Root Cause**: 
- Code changes were made to ReportObjectivesTab.tsx (lines 1545-1575)
- Removed `{obj.status === 'pending' && (` conditional wrapper
- But frontend container is running OLD compiled JavaScript

**Fix**:
```powershell
# Rebuild and restart frontend
cd "c:\Users\bklumpp\OneDrive - NANDPS\Documents\Python Scripts\SOCAnalyzer5"
docker-compose restart frontend
```

The frontend uses Vite which hot-reloads in development mode. If you're running in production mode, you need:
```powershell
docker-compose build frontend
docker-compose restart frontend
```

---

## Issue 2: Many Objectives ≥65% Not Auto-Approved

**Status**: Partially working ✅ / Gap extraction missing auto-approval ❌

**Current State**:
- 49 out of 50 high-confidence objectives ARE approved ✅
- Only CC1.1 (68.9% confidence) is NOT approved
- CC1.1 was extracted with method: `gpt_inferred` at 19:09:57

**Root Cause**: 
Auto-approval works during initial extraction but NOT during:
1. Gap extraction (`POST /objectives/gap-extract`)
2. Manual objective creation (`POST /objectives`)
3. Objective updates that increase confidence

**Evidence**:
```sql
-- Database shows auto-approval working
SELECT COUNT(*) as total, 
       COUNT(*) FILTER (WHERE status='approved') as approved,
       COUNT(*) FILTER (WHERE final_confidence >= 0.65) as high_conf 
FROM control_objectives WHERE scan_id = 2;

-- Result: 54 total, 49 approved, 50 high_conf
-- This means 49/50 (98%) of high-conf objectives were auto-approved!
```

**Fix Required**: Add auto-approval logic to these endpoints in `backend/app/routers/objective_router.py`:

1. After gap extraction completes
2. After manual objective creation
3. After objective update (if confidence crosses 0.65 threshold)

---

## Issue 3: Some Objectives Without Page Refs

**Status**: Actually FIXED ✅ but UX needs improvement

**Current State**:
```sql
-- Query shows NO NULL page_refs in scan_id=2
SELECT id, objective_id, line_ref, page_refs 
FROM control_objectives 
WHERE scan_id = 2 AND page_refs IS NULL;
-- Result: 0 rows
```

**The Problem**: User clicked an objective and nothing happened (no PDF navigation, no error message)

**Possible Causes**:
1. Page refs exist but are invalid (e.g., `page_refs=[]` empty array, not NULL)
2. PDF navigation silently fails without user feedback
3. User clicked objective from a DIFFERENT scan that had NULL page_refs

**Fix Required**: Add toast notification when clicking objectives without valid page_refs

Location: `frontend/src/components/report/tabs/ReportObjectivesTab.tsx`

```typescript
const handleObjectiveClick = (objectiveId: number, pageRefs: number[] | null) => {
  if (!pageRefs || pageRefs.length === 0) {
    showToast?.('This objective has no page reference', 'error');
    return;
  }
  
  // Navigate to PDF page
  const firstPage = pageRefs[0];
  // ... existing navigation code
};
```

---

## Summary of Changes Made Today

### ✅ Completed Fixes
1. **Confidence penalty for missing objective_id**: Added -0.15 penalty in calculate_multi_factor_confidence
2. **Section detection offset**: Fixed to calculate once from first section, validate all others
3. **Page refs deduplication bug**: Fixed line_ref restoration after GPT deduplication

### ⏳ Pending Actions
1. **Rebuild frontend** to see reject button changes
2. **Add auto-approval** to gap extraction and manual creation endpoints
3. **Add toast notification** for objectives without page refs
4. **Run new scan** to test all fixes comprehensively

---

## Next Steps

1. **Immediate**: Rebuild frontend
   ```powershell
   docker-compose restart frontend
   ```

2. **Then**: Add auto-approval to remaining endpoints
3. **Then**: Add toast for page ref errors
4. **Finally**: Run complete new scan to validate everything

---

**Date**: February 11, 2026
**Scan Tested**: scan_id=2 (9bc2a425...Adobe.pdf)
