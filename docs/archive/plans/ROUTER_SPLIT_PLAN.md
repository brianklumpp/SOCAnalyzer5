# v2.0.0 Router Split Implementation Plan

## Status: IN PROGRESS - Week 2

This document tracks the router modularization effort for v2.0.0.

## Overview
- **Current:** main.py = 7,488 lines with 100+ endpoints
- **Target:** 8 router modules + 3 service modules
- **Approach:** Extract endpoints maintaining identical API paths

---

## Router Modules (backend/app/routers/)

### 1. scan_router.py - Scan/Analysis Operations
**Lines in main.py:** ~1852-2830
**Endpoints:**
- POST /analyze/ (analyze_pdf_bg)
- POST /analyze/cancel/{job_id} (cancel_analysis_job)
- POST /analyze/confirm_report_type/{job_id} (confirm_report_type)
- GET /analyze/status/{job_id} (get_job_status)
- GET /analyze/status_min/{job_id} (get_job_status_min)
- GET /analyze/result/{job_id} (get_job_result)
- POST /analyze/finalize/{job_id} (finalize_job_from_disk)
- POST /analyze/resume/{job_id} (resume_extractors)
- GET /analyze/partial/{job_id} (get_partial_controls)
- WebSocket /ws/progress (websocket_progress)

### 2. report_router.py - Report CRUD
**Lines in main.py:** ~486-861
**Endpoints:**
- GET /report/{scan_id} (get_report)
- GET /report/{scan_id}/pdf (get_pdf)
- GET /report/{scan_id}/excel (export_excel)
- GET /report/{scan_id}/report_pdf (get_report_pdf)
- GET /report/{scan_id}/deviations (get_deviations)
- PATCH /report/{scan_id}/overview (patch_report_overview)
- GET /report/{scan_id}/reload_text (reload_extracted_text)

### 3. control_router.py - Control Operations
**Lines in main.py:** ~3770-5149
**Endpoints:**
- PATCH /report/{scan_id}/controls/annotation/{control_id} (patch_control_annotation)
- PATCH /report/{scan_id}/controls/{control_id} (patch_control)
- PATCH /report/{scan_id}/controls/id/{control_db_id} (patch_control_by_id)
- POST /report/{scan_id}/cleanup (trigger_cleanup)
- GET /report/{scan_id}/suggest_merges (suggest_control_merges)
- POST /report/{scan_id}/merge_controls (merge_controls)
- POST /report/{scan_id}/split_control/{control_db_id} (split_control)
- POST /report/{scan_id}/link_controls (link_control_instances)
- DELETE /report/{scan_id}/unlink_control/{control_id} (unlink_control_instance)
- POST /report/{scan_id}/dismiss_merge (dismiss_merge_suggestion)
- GET /report/{scan_id}/duplicate_groups (get_duplicate_groups)
- POST /report/{scan_id}/controls/{control_db_id}/recompute_frameworks (recompute_control_frameworks)
- POST /report/{scan_id}/controls/batch_recompute (batch_recompute_control_frameworks)
- POST /report/{scan_id}/controls/preview_mappings (preview_framework_mappings)

### 4. cuec_router.py - CUEC Operations  
**Lines in main.py:** ~5198-5343
**Endpoints:**
- PATCH /report/{scan_id}/cuecs/annotation/{cuec_id} (patch_cuec_annotation)
- PATCH /report/{scan_id}/cuecs/{cuec_id} (patch_cuec)
- PATCH /report/{scan_id}/cuecs/tsc/{cuec_tsc_id} (patch_cuec_by_tsc)
- POST /report/{scan_id}/cuecs/{cuec_id}/recompute_frameworks (recompute_cuec_frameworks)

### 5. suborg_router.py - Subservice Org Operations
**Lines in main.py:** ~1112-1158
**Endpoints:**
- PATCH /report/{scan_id}/suborg/id/{suborg_id} (patch_suborg_by_id)
- PATCH /report/{scan_id}/suborg/name/{suborg_name} (patch_suborg_by_name)

### 6. deviation_router.py - Deviation Operations
**Lines in main.py:** ~907-1032
**Endpoints:**
- PATCH /report/{scan_id}/deviations/{control_id} (update_deviation_summary)
- POST /report/{scan_id}/deviations/{control_id}/regenerate (regenerate_deviation_summary)
- POST /report/{scan_id}/deviations/regenerate_all (regenerate_all_deviation_summaries)
- GET /report/{scan_id}/deviations/regenerate_progress (get_regenerate_progress)
- POST /report/{scan_id}/deviations/create (create_deviation)

### 7. baseline_router.py - Validation/Baseline Operations
**Endpoints:**
- POST /baseline/create
- GET /baseline/list
- GET /baseline/{baseline_id}
- POST /baseline/compare
- DELETE /baseline/{baseline_id}
- POST /report/{scan_id}/verify (trigger_verification)
- GET /report/{scan_id}/verification_status (get_verification_status)
- POST /report/{scan_id}/learn_patterns (learn_patterns)
- GET /patterns/review_queue (get_pattern_review_queue)
- POST /patterns/review/{review_id}/approve (approve_pattern_merge)
- POST /patterns/review/{review_id}/reject (reject_pattern_merge)
- GET /patterns/org/{organization} (get_organization_patterns)

### 8. config_router.py - Settings/Config/Utility
**Lines in main.py:** ~2840-3101, 290-329
**Endpoints:**
- GET /settings (get_settings)
- POST /settings (update_settings)
- GET /runtime_config (get_runtime_config)
- GET /budget_snapshot (get_budget_snapshot)
- POST /toggle_quick_test_mode (toggle_quick_test_mode)
- GET /help (get_help_index)
- GET /help/{topic_id} (get_help_content)
- GET /docker/status (docker_status)
- POST /docker/stop/{container} (docker_stop)
- POST /docker/restart/{container} (docker_restart)
- POST /docker/start/{container} (docker_start)
- GET /history (get_history)
- GET /estimate_time (estimate_processing_time)
- GET /scan/{scan_id}/progress (get_scan_progress)
- GET /framework_criteria (get_framework_criteria)
- GET /confidence_weights (get_global_confidence_weights)

### 9. executive_summary_router.py - Executive Summary Operations
**Lines in main.py:** ~3324-3664
**Endpoints:**
- GET /report/{scan_id}/executive_summary (get_executive_summary)
- POST /report/{scan_id}/executive_summary/regenerate (regenerate_executive_summary)
- PATCH /report/{scan_id}/executive_summary (patch_executive_summary)

---

## Service Modules (backend/app/services/)

### 1. merge_service.py - Control Merging Logic
**Functions to extract:**
- automated_cleanup() (~line 3971)
- penalize_incomplete_controls() (~line 4175)
- suggest_control_merges() (~line 4388)
- merge_controls() (~line 4580)

### 2. scan_service.py - Scan Lifecycle
**Functions to extract:**
- update_scan_gpt_fields() (~line 3235)
- add_gpt_usage() (~line 3257)
- mark_executive_summary_stale() (~line 125)

### 3. deviation_service.py - Deviation Summarization
**Already exists:** backend/app/post_processors/deviation_summarizer.py
**Action:** Verify integration

---

## Utility Modules (backend/app/utils/)

### redis_helpers.py - Redis Job Management
**Functions to extract:**
- get_job() (~line 1158)
- set_job() (~line 1173)
- del_job() (~line 1178)
- _get_redis() (~line 1183) [ALREADY REFACTORED with connection pool]

### decorators.py - Common Decorators
**To create:**
- @database_error_handler decorator for consistent error handling

### data_helpers.py - Data Transformation
**To create:**
- parse_page_refs()
- normalize_confidence()
- get_data_path()

---

## Implementation Steps

### Phase 1: Create Router Scaffolding ✅
- [x] Create directories (routers/, services/, utils/)

### Phase 2: Extract Utilities (Week 2, Day 1)
- [ ] Create utils/redis_helpers.py
- [ ] Create utils/decorators.py
- [ ] Create utils/data_helpers.py
- [ ] Update imports in main.py

### Phase 3: Extract Services (Week 2, Day 1-2)
- [ ] Create services/merge_service.py
- [ ] Create services/scan_service.py
- [ ] Verify services/deviation_service.py integration
- [ ] Update imports in main.py

### Phase 4: Create Routers (Week 2, Day 2-3)
- [ ] scan_router.py
- [ ] report_router.py
- [ ] control_router.py
- [ ] cuec_router.py
- [ ] suborg_router.py
- [ ] deviation_router.py
- [ ] baseline_router.py
- [ ] config_router.py
- [ ] executive_summary_router.py

### Phase 5: Register Routers (Week 2, Day 3)
- [ ] Add app.include_router() calls in main.py
- [ ] Remove old endpoint functions from main.py
- [ ] Keep only core app setup, middleware, and shared functions

### Phase 6: Update Documentation (Week 2, Day 3-4)
- [ ] Update docs/ARCHITECTURE.md with router structure
- [ ] Add endpoint→router mapping table
- [ ] Document service layer

### Phase 7: Testing (Week 2, Day 4)
- [ ] Docker rebuild: docker compose down && docker compose build
- [ ] Test all API endpoints via frontend
- [ ] Verify no import errors

---

## Progress Tracking

**Current Status:** Phase 1 Complete
**Last Updated:** 2025-12-12
**Estimated Completion:** Week 2, Day 4
