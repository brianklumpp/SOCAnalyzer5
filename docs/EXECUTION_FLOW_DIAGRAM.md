# SOC Analyzer Scan Pipeline Execution Flow

## Overview
This document maps the complete execution flow of the scan pipeline with dependencies and sequencing.

## Execution Phases

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: File Upload & Preprocessing                            │
├─────────────────────────────────────────────────────────────────┤
│ 1. PDF Upload                                                   │
│ 2. Text Extraction (extract_text_from_pdf)                      │
│ 3. Section Detection (find_section_candidates)                  │
│    └─> Writes: section_results.json                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: Prerequisites (Sequential)                             │
├─────────────────────────────────────────────────────────────────┤
│ 4. Company Extraction (extract_company_from_report)             │
│    ├─ Depends on: section_results.json                         │
│    └─> Writes: company_result.json                             │
│                                                                  │
│ 5. Logo Fetching (fetch_company_logo)                           │
│    ├─ Depends on: company_result.json (needs domain)           │
│    └─> Writes: company_logo.png                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Phase 3: Metadata Extraction (Parallel if enabled)              │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐ │
│ │ 6. Auditor      │  │ 7. Product      │  │ 8. Report Date   │ │
│ │    Extraction   │  │    Extraction   │  │    Extraction    │ │
│ ├─────────────────┤  ├─────────────────┤  ├──────────────────┤ │
│ │ Depends on:     │  │ Depends on:     │  │ Depends on:      │ │
│ │ • sections      │  │ • sections      │  │ • sections       │ │
│ │ • company name  │  │                 │  │                  │ │
│ │   (exclusion)   │  │                 │  │                  │ │
│ └─────────────────┘  └─────────────────┘  └──────────────────┘ │
│                                                                  │
│ ┌─────────────────────────────────────┐                        │
│ │ 9. Coverage Period Extraction        │                        │
│ ├─────────────────────────────────────┤                        │
│ │ Depends on: sections                 │                        │
│ └─────────────────────────────────────┘                        │
│                                                                  │
│ ⚠️  CRITICAL: Auditor extraction MUST run after company         │
│              extraction completes (not in same parallel batch)  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Phase 4: Control Extraction (Parallel if enabled)               │
├─────────────────────────────────────────────────────────────────┤
│ 10. Control Extraction (extract_controls_parallel)              │
│     ├─ Depends on: section_results.json                        │
│     ├─ Input: Control_Descriptions section boundaries          │
│     ├─ Internal parallelism: chunks processed concurrently     │
│     └─> Writes: control_result.json                            │
│                                                                  │
│ 11. Framework Mapping (map_controls_to_frameworks_batch)        │
│     ├─ Depends on: control_result.json                         │
│     ├─ Maps controls to: TSC, COSO, NIST, ISO, PCI, HIPAA      │
│     └─> Updates: control_result.json (adds framework_mappings) │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Phase 5: Post-Control Parallel                                  │
├─────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────┐  ┌───────────────────────────────┐│
│ │ 12. CUEC Extraction      │  │ 13. Subservice Orgs           ││
│ ├──────────────────────────┤  ├───────────────────────────────┤│
│ │ Depends on: sections     │  │ Depends on: sections          ││
│ │ Extracts:                │  │ Extracts:                     ││
│ │ • CUECs                  │  │ • Third-party orgs            ││
│ │ • Complementary controls │  │ Filters with GPT to remove    ││
│ │                          │  │ false positives               ││
│ └──────────────────────────┘  └───────────────────────────────┘│
│                                                                  │
│ ℹ️  These can run in parallel - no dependency on controls       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Phase 6: Finalization                                            │
├─────────────────────────────────────────────────────────────────┤
│ 14. Combine Results (combine_all_results)                       │
│     ├─ Merges all JSON outputs                                 │
│     └─> Writes: combined_result.json                           │
│                                                                  │
│ 15. Database Insertion (explicit_sql_insert)                    │
│     └─ Inserts into PostgreSQL                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Dependency Matrix

| Extractor | Depends On | Required Files | Can Run in Parallel With |
|-----------|------------|----------------|--------------------------|
| Text Extraction | PDF file | - | - |
| Section Detection | Text file | output.txt | - |
| Company Extraction | Sections | section_results.json | - |
| Logo Fetching | Company | company_result.json | - |
| Auditor Extraction | Sections, Company | section_results.json, company_result.json | Product, Report Date, Coverage Period |
| Product Extraction | Sections | section_results.json | Auditor, Report Date, Coverage Period |
| Report Date Extraction | Sections | section_results.json | Auditor, Product, Coverage Period |
| Coverage Period Extraction | Sections | section_results.json | Auditor, Product, Report Date |
| Control Extraction | Sections | section_results.json | - |
| Framework Mapping | Controls | control_result.json | - |
| CUEC Extraction | Sections | section_results.json | Subservice Orgs |
| Subservice Orgs Extraction | Sections | section_results.json | CUEC |

## Parallel Execution Modes

### Mode 1: ENABLE_PARALLEL_METADATA_EXTRACTION=true (Default)
- Auditor, Product, Report Date, Coverage Period run concurrently
- Uses IntelligentTaskExecutor with ThreadPoolExecutor
- Progress tracker provides real-time updates

### Mode 2: ENABLE_PARALLEL_CONTROL_EXTRACTION=true
- Control extraction chunks processed concurrently
- Speeds up large reports with 100+ controls

### Mode 3: Sequential Fallback
- If executor unavailable or parallel mode disabled
- Runs extractors one at a time
- Slower but more reliable for debugging

## Error Handling

### Partial Failures
When some metadata extractors succeed and others fail:
1. Job continues with successful extractors
2. `extraction_partial=true` flag set in Redis
3. Failed extractors logged in `extraction_failures` array
4. Frontend shows warning indicator

### Complete Failures
When entire phase fails:
1. Job status set to "failed"
2. Error logged with full traceback
3. Checkpoint saved for resume capability
4. User notified in UI

## Checkpointing System

### Checkpoint File Location
`data/jobs/{user_id}/{job_id}/checkpoint.json`

### Checkpoint Content
```json
{
  "completed": ["control_extraction", "framework_mapping"],
  "checklist": [...]
}
```

### Resume Logic
1. Check if checkpoint exists
2. Skip completed extractors
3. Resume from last successful step
4. Maintain all job-specific paths

## Code Locations

| Phase | Function | File | Lines |
|-------|----------|------|-------|
| Text Extraction | `extract_text_from_pdf` | pdf_handler.py | ~1200 |
| Section Detection | `find_section_candidates` | pdf_handler.py | ~900 |
| Company Extraction | `extract_company_from_report` | company.py | 54-180 |
| Logo Fetching | `fetch_company_logo` | analyze.py | ~1150 |
| Parallel Metadata | `run_metadata_extractors_parallel` | analyze.py | 110-380 |
| Sequential Fallback | `_run_metadata_extractors_sequential` | analyze.py | 381-470 |
| Control Extraction | `extract_controls_parallel` | control_extractor.py | ~800 |
| Framework Mapping | `map_controls_to_frameworks_batch` | mapper.py | ~200 |
| Main Pipeline | `analyze_pdf_file` | analyze.py | 554-1820 |

## Configuration Options

| Config Variable | Default | Impact |
|-----------------|---------|--------|
| `ENABLE_PARALLEL_METADATA_EXTRACTION` | true | Runs 4 metadata extractors concurrently |
| `ENABLE_PARALLEL_CONTROL_EXTRACTION` | true | Chunks controls for parallel processing |
| `ENABLE_CHECKPOINT_SYSTEM` | true | Allows job resume after crashes |
| `MAX_PARALLEL_WORKERS` | 5 | Thread pool size for parallel execution |

## Troubleshooting

### Job Skips Extractors
- Check `ENABLE_PARALLEL_METADATA_EXTRACTION` setting
- Verify executor is instantiated
- Check logs for "falling back to sequential"

### Metadata Not Showing in UI
- Progress tracker may not be updating Redis
- Check browser console for WebSocket messages
- Verify `identified_entities` in job state

### Job Hangs
- Check for infinite loops in pause/resume logic
- Verify all extractors return (don't hang indefinitely)
- Check Redis connection for job state updates

### Partial Failures Not Logged
- Ensure `extraction_partial` flag is set
- Check `extraction_failures` array in Redis
- Verify logger level is INFO or DEBUG

## Recent Improvements (December 2025)

1. **Sequential Fallback Fixed** - Now properly passes `job_paths` and `job_id` to all extractors
2. **Checkpoint Tracking Added** - Parallel metadata extractors now saved to checkpoint
3. **Partial Failure Detection** - System distinguishes between complete success, partial failure, and complete failure
4. **Dependency Documentation** - Code comments clarify company→auditor dependency
5. **Unused Code Removed** - Eliminated confusing `metadata_parallel_steps` array

## Performance Metrics

Typical execution times for a 100-page SOC 2 report:

| Phase | Sequential | Parallel | Speedup |
|-------|-----------|----------|---------|
| Text + Sections | 15s | 15s | N/A |
| Company + Logo | 8s | 8s | N/A |
| Metadata (4 extractors) | 32s | 12s | 2.7x |
| Control Extraction | 120s | 45s | 2.7x |
| Framework Mapping | 25s | 25s | N/A |
| CUEC + Subservice | 30s | 18s | 1.7x |
| **Total** | **230s** | **123s** | **1.9x** |
