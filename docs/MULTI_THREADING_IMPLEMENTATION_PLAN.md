# Multi-Threading & Scan Queue Implementation Plan v2.1.0

**Created:** December 14, 2025  
**Target Release:** v2.1.0  
**Status:** 🟡 In Progress

---

## Executive Summary

### Goals

1. **Performance:** 40-60% faster scan completion through intelligent parallel extraction
2. **UX:** Modern scan queue interface supporting multiple concurrent scans
3. **Reliability:** Bounded resource usage with adaptive throttling (no runaway threads)
4. **Visibility:** Real-time progress tracking with granular updates (every 2 controls, every 4 mappings)

### Key Deliverables

- ✅ Intelligent multi-threading executor with circuit breaker & throttling
- 🔄 Scan queue manager with priority scheduling
- 🔄 Refactored UI with active scan grid + completed scan history
- 🔄 Enhanced progress tracking (phase-level + entity detection)
- 🔄 Batch upload support (queue 10+ reports for overnight processing)

### Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Scan Duration (150 controls) | ~10-12 min | ~5-7 min | Avg completion time |
| Control Extraction Rate | 12-15/min | 25-30/min | Controls extracted/min |
| Framework Mapping Rate | 8-10/min | 20-25/min | Controls mapped/min |
| Progress Update Frequency | ~10-15 updates | 50+ updates | Updates per scan |
| Concurrent Scans | 1 | 5+ queued | Active + queued jobs |
| CPU Utilization (peak) | 40-50% | 65-75% | System monitoring |
| Memory Usage | ~500MB | <1GB | Backend container |

---

## Implementation Timeline

| Phase | Component | Duration | Status | Start | End |
|-------|-----------|----------|--------|-------|-----|
| 1.1 | Intelligent Executor | 1 day | ✅ Complete | Dec 14 | Dec 14 |
| 1.2 | Scan Queue Manager | 1 day | 🟡 In Progress | Dec 14 | Dec 15 |
| 1.3 | Progress Tracker | 1 day | 🔴 Not Started | Dec 16 | Dec 16 |
| 2.1 | Parallel Chunk Extraction | 1 day | 🔴 Not Started | Dec 17 | Dec 17 |
| 2.2 | Parallel Framework Mapping | 1 day | 🔴 Not Started | Dec 18 | Dec 18 |
| 2.3 | Parallel Metadata Extraction | 1 day | 🔴 Not Started | Dec 19 | Dec 19 |
| 3.1 | ActiveScanCard UI | 2 days | 🔴 Not Started | Dec 20 | Dec 21 |
| 3.2 | QueueControls UI | 1 day | 🔴 Not Started | Dec 22 | Dec 22 |
| 3.3 | PhaseProgress UI | 1 day | 🔴 Not Started | Dec 23 | Dec 23 |
| 3.4 | CompletionSummary UI | 1 day | 🔴 Not Started | Dec 24 | Dec 24 |
| 4 | Backend Integration | 2-3 days | 🔴 Not Started | Dec 25 | Dec 27 |
| 5 | Testing & Optimization | 2-3 days | 🔴 Not Started | Dec 28 | Dec 30 |
| 6 | Documentation & Deployment | 1-2 days | 🔴 Not Started | Dec 31 | Jan 1 |

**Total Duration:** 14-18 days  
**Target Release:** January 1-5, 2026

---

## Phase 1: Multi-Threading Infrastructure

### 1.1 Intelligent Task Executor ✅ COMPLETE

**File:** `backend/app/threading/intelligent_executor.py`

**Features Implemented:**
- `IntelligentTaskExecutor` - Bounded thread pool with semaphore control
- `CircuitBreaker` - Failure detection & graceful degradation
- `AdaptiveThrottler` - CPU/memory monitoring with exponential backoff
- `TaskPriority` enum - Priority queue for task scheduling
- `TaskMetrics` - Real-time performance tracking

**Configuration:**
```python
max_workers = 4              # Concurrent threads (semaphore limit)
target_cpu_percent = 70      # Throttle threshold
target_memory_percent = 80   # Memory limit
task_timeout_seconds = 300   # 5 min per task
```

---

### 1.2 Scan Queue Manager 🟡 IN PROGRESS

**File:** `backend/app/threading/scan_queue.py`

**Features:**
- FIFO queue with priority override
- Pause/resume capability
- Redis-backed persistence
- Batch upload support
- Position tracking
- Automatic progression

**Queue States:**
```python
QUEUED = "queued"       # Waiting to start
RUNNING = "running"     # Currently processing
PAUSED = "paused"       # User paused queue
COMPLETED = "completed" # Finished successfully
FAILED = "failed"       # Extraction failed
CANCELLED = "cancelled" # User cancelled
```

**Redis Keys:**
```
scan_queue:active           # Sorted set: {job_id: priority}
scan_queue:current          # String: currently running job_id
scan_queue:paused           # Boolean: queue pause state
scan_queue:stats            # Hash: total queued/completed/failed
scan_queue:scan:{job_id}    # Hash: scan metadata
```

**New API Endpoints:**
```
POST   /analyze/batch              # Upload multiple PDFs
GET    /analyze/queue               # Get queue status + all scans
POST   /analyze/queue/pause         # Pause queue processing
POST   /analyze/queue/resume        # Resume queue
POST   /analyze/queue/prioritize    # Change scan priority
DELETE /analyze/queue/{job_id}      # Remove from queue/cancel
GET    /analyze/active              # Get all active scans
```

---

### 1.3 Enhanced Progress Tracker 🔴 NOT STARTED

**File:** `backend/app/threading/progress_tracker.py`

**Enhanced Progress Model:**
```python
{
    "job_id": "uuid",
    "status": "running",
    "overall_progress": 45,
    "current_phase": "control_extraction",
    "queue_position": 1,
    
    "phases": {
        "prerequisites": { ... },
        "metadata": {
            "identified_entities": {
                "company": {"name": "Acme", "logo_url": "...", "detected_at": ...},
                "auditor": {...},
                "product": {...},
                "report_date": {...},
                "coverage_period": {...}
            }
        },
        "content_extraction": {
            "extractors": {
                "controls": {
                    "extracted_count": 68,
                    "estimated_total": 150,
                    "mapped_count": 52,
                    "extraction_rate": 22.6,
                    "mapping_rate": 17.3
                }
            }
        }
    },
    
    "stats": {
        "elapsed_seconds": 223,
        "estimated_remaining_seconds": 178,
        "current_memory_mb": 450,
        "current_cpu_percent": 65
    },
    
    "completion": {
        "summary": { ... },
        "next_steps": [ ... ]
    }
}
```

**Update Frequency:**
- ⚡ **Immediate:** Entity detection (company, auditor, logo, dates)
- 🔄 **Every 2 controls:** Extraction progress update
- 🔄 **Every 4 mappings:** Framework mapping progress update
- 🔄 **Every chunk:** Chunk completion
- 📊 **Every 5 seconds:** CPU/memory stats
- ✅ **On completion:** Final summary

---

## Phase 2: Control Extractor Parallelization

### 2.1 Parallel Chunk Extraction 🔴 NOT STARTED

**File:** `backend/app/control_extractor_v4.py` (modify)

**Strategy:**
- Chunk size: 50-100 lines (configurable)
- Max concurrent chunks: 4 (semaphore-limited)
- Thread-safe result merging
- Progress updates every 2 controls

**Performance Target:** 25-30 controls/min (vs 12-15 sequential)

---

### 2.2 Parallel Framework Mapping 🔴 NOT STARTED

**File:** `backend/app/framework_mapper.py` (modify)

**Nested Parallelism:**
- Outer: 4 controls mapped concurrently
- Inner: 3 frameworks per control (TSC, COSO, ISAE3402)
- Total: Up to 12 concurrent GPT calls
- Progress updates every 4 mappings

**Performance Target:** 20-25 mappings/min (vs 8-10 sequential)

---

### 2.3 Parallel Metadata Extraction 🔴 NOT STARTED

**File:** `backend/app/analyze.py` (modify)

**Strategy:**
- 5 extractors run concurrently (company, auditor, product, dates)
- Results update UI immediately when detected
- Async logo fetch (non-blocking)

**Performance Target:** ~15-20s (vs 35-50s sequential)

---

## Phase 3: Scan Queue UI Redesign

### 3.1 Component Architecture

**New Components:**
```
frontend/src/components/analyzer/
├── UploadSection.tsx (extracted from AnalyzerPage)
├── ActiveScansGrid.tsx (NEW - active scan queue)
├── ActiveScanCard.tsx (NEW - in-progress scan card)
├── QueueControls.tsx (NEW - pause/resume/batch upload)
├── CompletedScansGrid.tsx (refactored VirtualHistoryGrid)
└── CompletedScanCard.tsx (renamed from HistoryCard)

frontend/src/components/progress/
├── PhaseProgress.tsx (NEW - phase-level progress bar)
├── EntityBadge.tsx (NEW - company/auditor/date badges)
├── ExtractionStats.tsx (NEW - controls/mappings counters)
└── CompletionSummary.tsx (NEW - scan complete banner)
```

**Page Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  AppBar (Solidigm branding)                              │
├─────────────────────────────────────────────────────────┤
│  Upload Section                                          │
│  [Drag & Drop Zone] [Batch Upload Button]               │
├─────────────────────────────────────────────────────────┤
│  Queue Controls                                          │
│  [Pause/Resume] [Clear Completed] [Export Queue]        │
├─────────────────────────────────────────────────────────┤
│  Active Scans (Grid - 2 columns)                        │
│  ┌─────────────────┐  ┌─────────────────┐              │
│  │ Scan Card       │  │ Scan Card       │              │
│  │ [Running]       │  │ [Queued #2]     │              │
│  │ Progress: 45%   │  │ Position: 2/5   │              │
│  └─────────────────┘  └─────────────────┘              │
├─────────────────────────────────────────────────────────┤
│  Completed Scans (Virtualized Grid)                     │
│  [Filter] [Sort] [Search]                               │
│  ┌─────────────────┐  ┌─────────────────┐              │
│  │ History Card    │  │ History Card    │              │
│  └─────────────────┘  └─────────────────┘              │
└─────────────────────────────────────────────────────────┘
```

### 3.2 ActiveScanCard Design

**Card States:**
1. **Queued:** Grey colors, queue position badge, estimated start time
2. **Running:** Vibrant colors, animated progress bars, real-time stats
3. **Paused:** Orange colors, progress frozen
4. **Completing:** Pulsing animation, "Finalizing..." label
5. **Failed:** Red colors, error message, retry option

**Features:**
- Real-time progress bars
- Entity badges (company, auditor, dates)
- Extraction stats (68/150 controls, 52/68 mapped)
- CPU/memory monitoring
- Elapsed/remaining time
- Actions: Pause, Cancel, Prioritize, Remove
- Confetti animation on completion

---

## Phase 4: Backend Integration

### Modifications Required:

1. **analyze.py:**
   - Import executor & queue
   - Phase 2: Parallel metadata extraction
   - Phase 3: Parallel control extraction
   - Phase 3: Parallel framework mapping
   - Add completion summary

2. **control_extractor_v4.py:**
   - Add `extract_controls_parallel()` function
   - Parallel chunk processing
   - Progress callbacks every 2 controls

3. **scan_router.py:**
   - Add 6 new endpoints (batch, queue, pause, resume, prioritize, active)

---

## Phase 5: Testing & Optimization

### Test Coverage:
- Backend: 70%+ coverage
- Frontend: 60%+ coverage

### Critical Tests:
- Executor: Semaphore limits, circuit breaker, throttling
- Queue: FIFO ordering, priority override, pause/resume
- Parallel Extraction: 4 chunks concurrent, no duplicates
- UI: Card updates, batch upload, completion animation

### Performance Benchmarks:
- 50-control report: Compare sequential vs parallel
- 150-control report: Target < 7 minutes
- 300-control report: Stress test
- 5-report batch: Overnight scenario
- 10-report batch: Weekend scenario

---

## Phase 6: Documentation & Deployment

### Documentation:
- `README.md` - Feature overview
- `docs/ARCHITECTURE.md` - Executor & queue diagrams
- `docs/API.md` - New endpoints
- `CHANGELOG.md` - v2.1.0 release notes
- `docs/PARALLEL_EXTRACTION.md` - How it works
- `docs/SCAN_QUEUE.md` - Queue management guide

### Configuration:
```python
# backend/app/config.py
ENABLE_PARALLEL_EXTRACTION = True
MAX_WORKER_THREADS = 4
ENABLE_ADAPTIVE_THROTTLING = True
TARGET_CPU_PERCENT = 70
TARGET_MEMORY_PERCENT = 80
PROGRESS_UPDATE_FREQUENCY_CONTROLS = 2
PROGRESS_UPDATE_FREQUENCY_MAPPINGS = 4
MAX_QUEUED_SCANS = 50
```

### Deployment:
1. Tag release: `v2.1.0`
2. Build Docker images
3. Run migrations (if any)
4. Backup database
5. Deploy to staging
6. Smoke tests
7. Deploy to production
8. Monitor for 24 hours

**Rollback:** Set `ENABLE_PARALLEL_EXTRACTION=false`

---

## Risk Assessment

| Risk | Severity | Mitigation | Fallback |
|------|----------|------------|----------|
| GPT Rate Limits | 🔴 High | Exponential backoff, respect 429s | Reduce to 2-3 workers |
| Memory Pressure | 🟡 Medium | Adaptive throttling monitors usage | Sequential if >90% |
| Thread Safety | 🟡 Medium | Redis locks, semaphore control | Single-threaded mode |
| Chunk Boundaries | 🟡 Medium | Break at paragraphs | Sequential if >5% dups |
| UI Performance | 🟢 Low | Debounce updates (1/sec max) | Reduce update frequency |
| Queue Persistence | 🟢 Low | Redis-backed with TTL | In-memory queue |

---

## Key Design Decisions

### User Requirements Applied:
1. ✅ Progress updates: **Every 2 controls + every 4 mappings**
2. ✅ Logo fetch: **Async** (shows when ready)
3. ✅ Queue priorities: **Yes** (urgent scans can jump ahead)
4. ✅ Threading: **Aggressive** (control chunk parallelism)
5. ✅ Executive summary: **Manual/user-initiated only**
6. ✅ Completion notification: **UI only** (no email yet)

### Architecture Choices:
- **HTTP polling** (keep existing reliable mechanism)
- **Redis-backed queue** (survives backend restart)
- **Semaphore limits** (prevent runaway threads)
- **Circuit breaker** (graceful degradation on failures)
- **Adaptive throttling** (backs off at 70% CPU / 80% memory)

---

## Success Criteria

### Must Have (Release Blockers):
- ✅ Scan duration reduced by 40%+ (< 7 min for 150 controls)
- ✅ No CPU spikes > 80%
- ✅ No memory usage > 1GB
- ✅ Progress updates every 2 controls
- ✅ Entities show immediately when detected
- ✅ Queue UI displays active + queued scans
- ✅ Batch upload supports 10+ PDFs
- ✅ Pause/resume queue works
- ✅ No regressions

### Nice to Have (Future):
- 🎯 Concurrent scan processing (2-3 at once) - v2.2.0
- 🎯 Scan scheduling - v2.2.0
- 🎯 Email notifications - v2.2.0
- 🎯 Scan templates - v2.2.0
- 🎯 Queue analytics dashboard - v2.2.0
- 🎯 Pattern learning from feedback - v2.3.0

---

**Plan Version:** 1.0  
**Last Updated:** December 14, 2025  
**Next Review:** After Phase 1 completion
