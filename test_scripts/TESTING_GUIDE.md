# Testing Guide: Framework Mapping Integration

## Overview

This guide covers testing the unified extractor system with dynamic framework mapping across SOC1, SOC2, and COMBINED report types.

## Prerequisites

1. **Backend Running**: Ensure FastAPI backend is running on http://localhost:8000
   ```powershell
   cd backend
   python -m uvicorn app.main:app --reload
   ```

2. **Frontend Running** (optional, for UI validation): http://localhost:3000
   ```powershell
   cd frontend
   npm start
   ```

3. **Database Running**: PostgreSQL with migrations applied
   ```powershell
   cd backend
   alembic upgrade head
   ```

4. **Test Reports**: Have SOC1 and SOC2 PDF reports ready in appropriate directories

## Test Suite

### 1. Framework Registry Test (Quick Validation)

**Purpose**: Verify framework registry is properly configured and frameworks load correctly.

**Command**:
```powershell
python test_scripts\test_framework_mapping.py --registry
```

**Expected Output**:
- ✓ Loaded 10 frameworks (TSC, COSO, FINANCIAL_ASSERTIONS, COSO_ICFR, ISAE3402, CSAE3416, AAF0106, GS007, ISO27001, NIST)
- ✓ SOC1: 6 frameworks loaded
- ✓ SOC2: 4 frameworks loaded
- ✓ COMBINED: 10 frameworks loaded

**Pass Criteria**: All frameworks load without errors

---

### 2. SOC2 Report Extraction Test

**Purpose**: Verify SOC2 reports extract with TSC/COSO/ISO27001/NIST frameworks.

#### Option A: Using Interactive Tool (Recommended)
```powershell
python interactive_scan.py
```
1. Choose "Start New Analysis"
2. Select a SOC2 report (e.g., from `soc2_reports/` folder)
3. Confirm report type detection (should detect SOC2)
4. Wait for extraction to complete
5. Note the scan ID from results

#### Option B: Using Auto-Detection Test
```powershell
python test_scripts\test_auto_detection.py "soc2_reports\YourReport.pdf"
```

**Validation**:
```powershell
# After extraction, test framework mappings
python test_scripts\test_framework_mapping.py --latest
```

**Expected Results**:
- ✓ Report Type: SOC2
- ✓ Frameworks Used: TSC, COSO (ISO27001, NIST if applicable)
- ✓ 80%+ controls have framework mappings
- ✓ Primary framework set for each control
- ✓ No unexpected frameworks (like FINANCIAL_ASSERTIONS)
- ✓ CUECs have framework mappings

**Pass Criteria**:
- Framework validation passes
- No SOC1-specific frameworks appear
- Average 1-2 frameworks per control
- No critical issues reported

---

### 3. SOC1 Report Extraction Test

**Purpose**: Verify SOC1 reports extract with Financial Assertions/COSO ICFR/ISAE 3402 frameworks.

#### Using Interactive Tool
```powershell
python interactive_scan.py
```
1. Choose "Start New Analysis"
2. Select a SOC1 report (e.g., from `soc1_reports/` folder)
3. Confirm report type detection (should detect SOC1)
4. Wait for extraction to complete
5. Note the scan ID

#### Using Auto-Detection Test
```powershell
python test_scripts\test_auto_detection.py "soc1_reports\YourReport.pdf"
```

**Validation**:
```powershell
python test_scripts\test_framework_mapping.py --latest
```

**Expected Results**:
- ✓ Report Type: SOC1
- ✓ Frameworks Used: FINANCIAL_ASSERTIONS, COSO_ICFR (ISAE3402, CSAE3416, AAF0106, or GS007 if applicable)
- ✓ 80%+ controls have framework mappings
- ✓ Primary framework typically FINANCIAL_ASSERTIONS or COSO_ICFR
- ✓ No SOC2-specific frameworks (like TSC)
- ✓ CUECs use SOC1 keywords ("management's assertion", "financial reporting", etc.)

**Pass Criteria**:
- Framework validation passes
- No SOC2-specific frameworks appear
- Financial assertions properly mapped
- CUEC keywords appropriate for SOC1

---

### 4. Multi-Scan Regression Test

**Purpose**: Validate framework mappings across multiple recent scans.

**Command**:
```powershell
# Test 5 most recent scans
python test_scripts\test_framework_mapping.py --all-recent 5
```

**Expected Results**:
- Summary shows passed/failed for each scan
- Each scan uses frameworks appropriate for its report type
- Consistent mapping patterns across similar report types

**Pass Criteria**: All tested scans pass validation

---

### 5. Database Verification Test

**Purpose**: Verify framework mappings are correctly stored in database.

**SQL Queries**:
```sql
-- Connect to database
psql -U postgres -d soc2analyzer

-- Check recent scans and their report types
SELECT id, company_name, report_type, created_at 
FROM scans 
ORDER BY created_at DESC 
LIMIT 10;

-- Check framework mappings for latest scan (replace 123 with actual scan_id)
SELECT 
    control_id,
    primary_framework,
    jsonb_object_keys(framework_mappings) as framework,
    framework_mappings
FROM controls 
WHERE scan_id = 123
LIMIT 10;

-- Count controls by primary framework for a scan
SELECT 
    primary_framework,
    COUNT(*) as control_count
FROM controls
WHERE scan_id = 123
GROUP BY primary_framework
ORDER BY control_count DESC;

-- Check CUEC framework mappings
SELECT 
    cuec_id,
    cuec_description,
    framework_mappings
FROM cuecs
WHERE scan_id = 123
LIMIT 5;

-- Verify framework_mappings column type
SELECT 
    column_name, 
    data_type 
FROM information_schema.columns 
WHERE table_name = 'controls' 
  AND column_name IN ('framework_mappings', 'primary_framework', 'primary_criterion_id', 'primary_confidence');
```

**Expected Results**:
- `framework_mappings` column is JSONB type
- Contains nested JSON like `{"TSC": [{"criterion_id": "CC6.1", "confidence": 0.85}], "COSO": [...]}`
- `primary_framework` is populated (e.g., "TSC" or "FINANCIAL_ASSERTIONS")
- `primary_criterion_id` contains the top-confidence criterion
- CUECs also have `framework_mappings` populated

---

### 6. Frontend UI Validation

**Purpose**: Verify multi-framework mappings display correctly in web UI.

**Steps**:
1. Open browser to http://localhost:3000
2. Navigate to latest scan report
3. Check "Controls" tab

**What to Verify**:
- [ ] Controls show multiple framework mappings (not just TSC/COSO)
- [ ] Primary framework is highlighted/indicated
- [ ] Confidence scores display for each framework
- [ ] SOC1 reports show Financial Assertions
- [ ] SOC2 reports show TSC
- [ ] Framework badges/tags render correctly
- [ ] Coverage charts reflect multiple frameworks

**Note**: Frontend updates may be needed to properly display multi-framework data. Check with frontend team if issues arise.

---

## Test Scenarios by Report Type

### SOC2 Expected Behavior
```
Report Type: SOC2
Frameworks:  TSC (primary), COSO, ISO27001*, NIST*
Keywords:    availability, integrity, confidentiality, processing integrity, privacy
Prompt:      SOC2 control extraction prompt
Mapping:     map_control_to_frameworks_dynamic() with SOC2 frameworks
```

### SOC1 Expected Behavior
```
Report Type: SOC1
Frameworks:  FINANCIAL_ASSERTIONS (primary), COSO_ICFR, ISAE3402*, CSAE3416*, AAF0106*, GS007*
Keywords:    financial reporting, management's assertion, ICFR
Prompt:      SOC2 control extraction prompt (unified)
Mapping:     map_control_to_frameworks_dynamic() with SOC1 frameworks
             Optional: Batch assertion mapping if enabled
```

### COMBINED Expected Behavior
```
Report Type: COMBINED
Frameworks:  All 10 frameworks loaded
Mapping:     Controls map to relevant frameworks from both SOC1 and SOC2 sets
```

\* Framework usage depends on report content and jurisdiction

---

## Troubleshooting

### Issue: No Framework Mappings Found
**Symptoms**: test_framework_mapping.py reports 0% coverage

**Possible Causes**:
1. Framework mapping code didn't execute during extraction
2. Database migration not applied (framework_mappings column missing)
3. Extraction used old/cached code

**Solutions**:
```powershell
# Check database schema
psql -U postgres -d soc2analyzer -c "\d controls"

# Re-run migration if needed
cd backend
alembic upgrade head

# Clear Python cache and restart backend
Remove-Item -Recurse -Force backend\app\__pycache__
Remove-Item -Recurse -Force backend\app\extractors\__pycache__
Remove-Item -Recurse -Force backend\app\frameworks\__pycache__
```

### Issue: Wrong Frameworks for Report Type
**Symptoms**: SOC2 report shows FINANCIAL_ASSERTIONS, or SOC1 shows TSC

**Possible Causes**:
1. Report type not correctly passed to extractor
2. Framework loader not using report_type parameter
3. Hardcoded framework lists in extractors

**Solutions**:
```powershell
# Check logs for report type
Get-Content data\logs\control_extractor.log | Select-String "report_type"

# Verify framework loading
python -c "from backend.app.frameworks import get_available_frameworks; print(get_available_frameworks('SOC1').keys())"
```

### Issue: Extraction Fails
**Symptoms**: Error during extraction, no results

**Solutions**:
```powershell
# Check backend logs
Get-Content backend\app\logs\*.log -Tail 50

# Check extraction logs
Get-Content data\logs\control_extractor.log -Tail 100

# Test GPT connectivity
python test_scripts\check_llm_catalog.py
```

---

## Success Criteria Summary

✅ **Framework Registry**: All 10 frameworks load correctly for appropriate report types

✅ **SOC2 Extraction**: 
- Uses TSC, COSO, ISO27001, NIST
- No SOC1-specific frameworks
- 80%+ framework mapping coverage

✅ **SOC1 Extraction**:
- Uses FINANCIAL_ASSERTIONS, COSO_ICFR, ISAE3402/CSAE3416/AAF0106/GS007
- No SOC2-specific frameworks
- 80%+ framework mapping coverage
- CUECs use SOC1 keywords

✅ **Database Storage**:
- framework_mappings column is JSONB
- Contains nested multi-framework data
- primary_framework populated

✅ **UI Display** (optional):
- Multi-framework mappings visible
- Framework selection works
- Coverage charts accurate

---

## Quick Test Commands

```powershell
# Full test sequence
python test_scripts\test_framework_mapping.py --registry          # 1. Verify registry
python interactive_scan.py                                        # 2. Upload SOC2 report
python test_scripts\test_framework_mapping.py --latest            # 3. Validate mappings
python test_scripts\test_auto_detection.py "soc1_reports\X.pdf"  # 4. Upload SOC1 report
python test_scripts\test_framework_mapping.py --latest            # 5. Validate SOC1
python test_scripts\test_framework_mapping.py --all-recent 5     # 6. Regression test
```

---

## Reporting Issues

When reporting test failures, include:
1. Command that failed
2. Full error output
3. Scan ID being tested
4. Report type (SOC1/SOC2/COMBINED)
5. Relevant log snippets from:
   - `data/logs/control_extractor.log`
   - `data/logs/cuec_extractor.log`
   - `backend/app/logs/app.log`

---

**Last Updated**: 2025-01-06
**Status**: Ready for testing
