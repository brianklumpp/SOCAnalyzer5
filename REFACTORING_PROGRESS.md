# ReportPage Refactoring Progress

## Status: IN PROGRESS (Phase 1: Foundation)

### Completed

1. **Directory Structure** ✅
   - Created `frontend/src/hooks/report/`
   - Created `frontend/src/components/report/tabs/`
   - Created `frontend/src/components/report/tables/`
   - Created `frontend/src/components/report/dialogs/`
   - Created `frontend/src/services/report/`
   - Created `frontend/src/config/report/`

2. **Configuration Files** ✅
   - `config/report/constants.ts` - API URLs and confidence threshold

3. **Custom Hooks** ✅ (ALL COMPLETE - 5/5)
   - ✅ `hooks/report/useTabNavigation.ts` (52 lines) - Tab state, keyboard nav, scroll position tracking
   - ✅ `hooks/report/useReportData.ts` (42 lines) - Report data fetching and loading state
   - ✅ `hooks/report/useExecutiveSummary.ts` (58 lines) - Executive summary operations
   - ✅ `hooks/report/useResourceCRUD.ts` (499 lines) - Generic CRUD for suborgs/cuecs/controls
   - ✅ `hooks/report/useFrameworkCoverage.ts` (237 lines) - TSC/COSO coverage calculations with memoization

4. **Service Layer** ✅
   - ✅ `services/report/dataTransformations.ts` (117 lines) - Pure transformation functions

5. **TSC Configuration** ✅
   - ✅ `config/report/tscCriteria.ts` (74 lines) - TSC criteria and section mappings

### Remaining Work

#### Phase 3: Column Definitions (COMPLETE) ✅

1. **config/report/columnDefinitions.tsx** (240 lines) ✅
   - cuecColumns with 17 fields (9 main + 8 hidden)
   - controlColumns with 25 fields (11 main + 14 hidden)
   - subserviceOrgColumns with 10 fields (4 main + 6 hidden)
   - Includes render functions for framework mappings and confidence tooltips
   - Default visible column exports for each table

#### Phase 4: Table Components (COMPLETE) ✅

1. **components/report/tables/CuecsTable.tsx** (183 lines) ✅
   - Wrapped with React.memo for performance
   - High confidence and collapsible low confidence sections
   - Recompute button with loading state
   - Confidence percentage formatting
   - Accept props: highConfCuecs, lowConfCuecs, ignored, onIgnore, onConfirm, onEdit, onBatchEdit, onRecompute

2. **components/report/tables/ControlsTable.tsx** (178 lines) ✅
   - Wrapped with React.memo for performance
   - Duplicate control ID detection
   - Confidence tooltip/modal integration
   - Similarity percentage formatting
   - Accept props: controls, ignored, onEdit, onBatchEdit, onRecompute, onIgnore, onConfirm, onOpenConfidenceModal

3. **components/report/tables/SuborgsTable.tsx** (90 lines) ✅
   - Wrapped with React.memo for performance
   - Duplicate name detection and highlighting
   - Confidence percentage formatting
   - Accept props: subOrgs, ignored, onIgnore, onConfirm, onEdit, onBatchEdit

#### Phase 5: Tab Components (ALMOST COMPLETE - 5/6) ⏳

1. **ReportControlsTab.tsx** (106 lines) ✅
   - High confidence controls table
   - Low confidence controls section (collapsible)
   - Add control dialog integration

2. **ReportCuecsTab.tsx** (72 lines) ✅
   - High confidence CUECs table
   - Low confidence CUECs section
   - Add CUEC dialog integration

3. **ReportSuborgsTab.tsx** (131 lines) ✅
   - Duplicate name warning
   - High/low confidence sections
   - Add suborg dialog integration

4. **ReportVerificationTab.tsx** (95 lines) ✅
   - VerificationSection integration
   - Bad chunks display (JSON formatted)

5. **ReportCoverageTab.tsx** (436 lines) ✅
   - TSC/COSO donut charts with 4-category breakdown
   - Interactive criteria tables with tooltips
   - Control/CUEC mapping info
   - Deviation highlighting
   - Clickable CUEC links to modal

6. **ReportSummaryTab.tsx** (~400-450 lines) ⏳ REMAINING
   - Overview section with editable fields
   - Executive summary with regeneration
   - Key stats display
   - Timeline component
   - Will reference Coverage tab for charts (moved there)

4. **ReportSuborgsTab.tsx** (~100 lines)
   - High confidence suborgs table
   - Low confidence suborgs section
   - Add suborg dialog integration
   - Duplicate warning display

5. **ReportCoverageTab.tsx** (~300 lines)
   - Move TSC/COSO charts from Summary tab
   - Framework criteria tables
   - Coverage percentage displays

6. **ReportVerificationTab.tsx** (~100 lines)
   - VerificationSection component
   - Bad chunks display
   - Status indicators

#### Phase 6: Dialog Component (Est. 2-3 hours)

1. **components/report/dialogs/AddItemDialog.tsx**
   - Generic dialog accepting type prop ('suborg' | 'cuec' | 'control')
   - Field configuration based on type
   - Form validation
   - Confidence prefill logic
   - Replaces 250 LOC of duplicated dialog code

#### Phase 7: Main ReportPage Refactor (Est. 4-5 hours)

1. **Transform ReportPage.tsx**
   - Remove all extracted code
   - Import all hooks
   - Import all tab components
   - Import dialogs
   - Create simple orchestrator structure (~300 lines)
   - Wire up all props and state
   - Test all functionality

#### Phase 8: Testing & Validation (Est. 4-6 hours)

1. **Unit Tests**
   - Test all custom hooks
   - Test service functions
   - Test data transformations

2. **Integration Tests**
   - Test tab navigation
   - Test CRUD operations
   - Test keyboard shortcuts

3. **Manual Testing**
   - Test all existing functionality
   - Verify no regressions
   - Test performance improvements
   - Validate in Docker build

### Total Estimated Effort
- **25-35 hours** of focused development time
- Recommended approach: Complete one phase at a time
- Test after each phase before proceeding

### Current Blockers
- Need to extract useResourceCRUD (most complex, touches 15+ handlers)
- Need to extract column definitions (referenced throughout)
- Need to carefully preserve all existing functionality

### Next Steps
1. Complete useResourceCRUD.ts hook
2. Complete useFrameworkCoverage.ts hook
3. Extract service functions to services/report/
4. Extract column definitions to config/report/
5. Then proceed with component extraction

### Notes
- This is a production system - proceed carefully
- Test thoroughly after each extraction
- Keep git commits granular for easy rollback
- Consider feature branch workflow
- Original ReportPage.tsx: 2,974 lines
- Target ReportPage.tsx: ~300 lines (90% reduction)
