# SOC 1 Implementation Deployment Checklist

## Pre-Deployment Validation

### Backend Tests
- [ ] Run database migration: `cd backend && alembic upgrade head`
- [ ] Verify schema: Check `report_type`, `as_of_date`, `financial_assertions`, `framework_category` columns exist
- [ ] Test SOC 1 extractor: `python test_scripts/test_control_extraction.py --report soc1_reports/CitiDirect.pdf`
- [ ] Test combined extractor: `python test_scripts/test_control_extraction.py --report soc1_reports/Azure+Dynamics365.pdf`
- [ ] Verify FIFO baseline cleanup: Create 21+ baselines, confirm oldest deleted

### Frontend Tests
- [ ] Build frontend: `cd frontend && npm run build`
- [ ] Test report type selector on upload page
- [ ] Upload SOC 1 PDF, verify "SOC1" type selected and as_of_date extracted
- [ ] Verify FinancialAssertionBadges render on report page
- [ ] Verify FrameworkBadge displays correct category
- [ ] Navigate to `/validation` page, test baseline creation
- [ ] Test baseline comparison with regression detection UI

### API Tests
- [ ] Test POST /analyze with report_type=SOC1
- [ ] Test GET /report/{scan_id} - verify financial_assertions and framework_category in response
- [ ] Test POST /baseline/create - confirm baseline file created in soc1_reports/baselines/
- [ ] Test POST /baseline/compare - verify delta calculation and regression detection
- [ ] Test GET /baseline/list - confirm baselines sorted by created_at desc
- [ ] Test DELETE /baseline/{id} - confirm file removed

### CI/CD Tests
- [ ] Run workflow manually: GitHub Actions → soc1-validation → Run workflow
- [ ] Verify test results artifact uploaded
- [ ] Check PR comment integration (create test PR)
- [ ] Test Slack notification (temporarily break extraction)
- [ ] Confirm nightly schedule configured (2 AM UTC)

## Deployment Steps

### 1. Database Migration
```powershell
cd backend
alembic upgrade head
# Expected output: Running upgrade ... -> 33a1ce8acc7a, add soc1 support columns
```

### 2. Backend Deployment
```powershell
# Stop backend service
Stop-Process -Name "python" -ErrorAction SilentlyContinue

# Install dependencies
pip install -r backend/requirements.txt

# Start backend
.\start-backend.ps1
# Verify: http://localhost:8000/docs shows new baseline endpoints
```

### 3. Frontend Deployment
```powershell
cd frontend

# Install dependencies
npm install

# Build production bundle
npm run build

# Deploy build/ to web server or test locally
npm start
# Verify: Navigate to http://localhost:3000/validation
```

### 4. Environment Configuration
```powershell
# Ensure .env or environment variables set:
# DATABASE_URL=postgresql://user:pass@localhost:5432/socanalyzer
# LLM_PROVIDER=dataiku
# DATAIKU_DSS_HOST=<host>
# DATAIKU_API_KEY=<key>
```

### 5. Baseline Directory Setup
```powershell
# Ensure baseline directory exists with proper permissions
New-Item -Path "soc1_reports/baselines" -ItemType Directory -Force
# Verify write access
Test-Path "soc1_reports/baselines" -PathType Container
```

### 6. GitHub Actions Secrets
Configure in GitHub repo settings → Secrets and variables → Actions:
- [ ] `DATAIKU_DSS_HOST` - Dataiku API host
- [ ] `DATAIKU_API_KEY` - Dataiku API key
- [ ] `SLACK_WEBHOOK_URL` - Slack incoming webhook for notifications

### 7. Initial Baseline Creation
```powershell
# Process 3 test reports
python test_scripts/run_validation_tests.py --output validation_results.json

# Create initial baselines via UI:
# 1. Navigate to http://localhost:3000/validation
# 2. Select each completed scan
# 3. Click "Create Baseline"
# 4. Add reviewer notes: "Initial production baseline"
```

## Post-Deployment Verification

### Smoke Tests
- [ ] Upload Okta.pdf (SOC 2) → Verify report_type=SOC2, v4 extractor used
- [ ] Upload CitiDirect.pdf (SOC 1) → Verify report_type=SOC1, v4_soc1 extractor used
- [ ] Upload Azure+Dynamics365.pdf (Combined) → Verify report_type=COMBINED, combined extractor used
- [ ] Check financial assertions populated for SOC 1 controls
- [ ] Check framework_category set correctly (SOC1/SOC2/COMBINED/AMBIGUOUS)

### Baseline Workflow Test
1. [ ] Create baseline from validated SOC 1 scan
2. [ ] Reprocess same PDF
3. [ ] Compare to baseline - verify no regressions
4. [ ] Manually edit control in DB to simulate regression
5. [ ] Compare again - verify regression detected

### CI/CD Workflow Test
1. [ ] Create feature branch
2. [ ] Make trivial change (e.g., update README)
3. [ ] Open pull request
4. [ ] Verify workflow runs automatically
5. [ ] Check PR comment with test results
6. [ ] Merge PR

### Performance Validation
- [ ] SOC 1 extraction time: Expected 60-120 seconds for 50 controls
- [ ] Baseline comparison: <5 seconds for 100 control comparison
- [ ] Database query performance: Check scan list query <2 seconds

## Rollback Plan

### If Critical Issues Arise
```powershell
# 1. Revert database migration
cd backend
alembic downgrade -1

# 2. Restore previous code version
git checkout <previous-commit-hash>

# 3. Rebuild frontend
cd frontend
npm run build

# 4. Restart services
.\start-backend.ps1
```

### Partial Rollback (Keep Infrastructure)
If only prompt tuning needed:
1. Keep schema and API changes
2. Revert prompts in `backend/app/config.py`:
   - `CONTROL_EXTRACTION_PROMPT_V4_SOC1`
   - `CUEC_KEYWORDS_SOC1`
3. Test with 3 SOC 1 reports
4. Adjust keywords/threshold as needed

## Monitoring

### Key Metrics to Watch
- [ ] Extraction success rate: Target >95%
- [ ] Average control count per report: SOC 1 ~40-80, SOC 2 ~50-120
- [ ] Financial assertion accuracy: Target >90% (manual review)
- [ ] AMBIGUOUS control rate: Target <10%
- [ ] PARTIAL_EXTRACTION rate: Target <5%
- [ ] CI/CD test pass rate: Target 100%

### Logging
Monitor these log files:
- `backend_recent.log` - Backend errors
- `data/logs/auditor_extractor.log` - Extraction issues
- `data/logs/control_extractor.log` - Control parsing failures
- GitHub Actions workflow runs - CI/CD test results

### Alerts to Configure
1. **High AMBIGUOUS Rate**: >15% of controls flagged as AMBIGUOUS
2. **Baseline Regression**: Any CI/CD workflow failure
3. **Extraction Failures**: >5% of scans fail to complete
4. **Long Processing Times**: >180 seconds for typical report

## Success Criteria

### Functional
- ✅ All 3 report types (SOC1/SOC2/COMBINED) extract successfully
- ✅ Financial assertions mapped for SOC 1 controls with >85% accuracy
- ✅ Framework category assigned correctly (manual validation)
- ✅ Baseline comparison detects intentional regressions
- ✅ CI/CD workflow passes on main branch

### Performance
- ✅ SOC 1 extraction: <120 seconds for 50 controls
- ✅ Combined extraction: <150 seconds for 80 controls
- ✅ Baseline comparison: <10 seconds
- ✅ Database migration: <30 seconds

### User Experience
- ✅ Report type selector intuitive on upload page
- ✅ Financial assertion badges render clearly
- ✅ Validation page provides clear comparison view
- ✅ Baseline creation straightforward (<3 clicks)

## Sign-Off

**Deployed By**: _________________
**Date**: _________________
**Production URL**: _________________
**Baseline Count**: _________ baselines created
**Test Results**: All CI/CD tests passing ✅

**Notes**:
_______________________________________________
_______________________________________________
_______________________________________________
