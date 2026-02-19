# SOCAnalyzer5 - AI Coding Agent Instructions

## System Architecture

**3-service Docker architecture** on Windows with PowerShell management:
- **Backend** (`172.20.0.5:8000`) - FastAPI + SQLAlchemy async, GPT extraction via Dataiku DSS
- **Frontend** (`localhost:3000`) - React + Material-UI, connects to backend API
- **PostgreSQL** (`172.20.0.3:5432`, exposed as `localhost:5433`) - Audit data storage
- **Redis** (`172.20.0.4:6379`) - Job queues and progress tracking
- **DNS Cache** (`172.20.0.2`) - Corporate DNS caching for Dataiku connections

**Key network detail**: Local Python scripts connect to Docker Postgres via `localhost:5433`. Backend uses internal network (`postgres:5432`).

## Critical Workflows

### Development Mode
```powershell
# Start all services (no rebuild)
docker-compose up -d

# Run scan directly (PREFERRED - no threading issues)
.\test_scripts\run_scan.ps1 soc2_reports\Okta.pdf

# Interactive wizard (TUI mode)
.\test_scripts\interactive.ps1

# Run migrations
cd backend && alembic upgrade head
```

**IMPORTANT**: The FastAPI background threading approach is **deprecated** (Nov 2025). Use direct script execution via `run_scan.ps1` or `interactive.ps1` instead.

### Database Migrations
```powershell
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

Models live in `backend/app/models.py`. Always verify migrations before deploying.

## GPT Integration (Critical Pattern)

**Model Configuration**: Code uses logical name `"gpt-5"` but **actually runs `gpt-4o`** via Dataiku mapping:
- Set in `.env`: `DATAIKU_LLM_GPT5=azureopenai:Azure-OpenAI-Prod:gpt-4o`
- Configured in `backend/app/config.py` via `DATAIKU_CATALOG_MAP`
- Default model: `config.DEFAULT_GPT_MODEL = "gpt-5"` (resolves to gpt-4o)
- Framework mapping uses: `config.FRAMEWORK_MAPPING_MODEL = "gpt-4o-mini"` (faster/cheaper)

**Always use**: `from backend.app.gpt_client import call_gpt` - handles Dataiku routing, retries, SSL certs, cost tracking.

### Dataiku DSS Integration Details

**Connection Pattern** (`backend/app/gpt_client.py`):
- Uses `dataikuapi.DSSClient` to connect to Dataiku's LLM catalog
- Connection caching via `_DSS_CACHE` dict (client, project, llm instances)
- DNS fallback: Overrides `socket.getaddrinfo()` globally to route corporate hostname to IP
- SSL: Corporate CA bundle at `/certs/corp-ca-bundle.pem` set via `REQUESTS_CA_BUNDLE`
- Excludes Docker internal hostnames (`redis`, `postgres`, `localhost`) from custom DNS

**Retry Strategy**:
```python
_with_retries(func, retries=3, base_delay_seconds=1.0)
# Exponential backoff with jitter
# Logs all errors (timeouts, 502 Bad Gateway, etc.)
# Updates Redis job status on retry attempts
# Re-raises last exception after retries exhausted
```

**Response Parsing** (`extract_json_from_response()`):
- 4-pattern extraction: markdown code blocks (```json), brace extraction, bracket extraction
- Handles GPT responses with extra text before/after JSON
- Raises `ValueError` with first 200 chars on parse failure

**Cost Tracking** (`backend/app/gpt_tracker.py`):
- Logs all calls to `data/logs/gpt_calls.log` when `LOG_GPT_REQUESTS=true`
- JSON Lines format with timestamp, model, prompt/response sizes, usage tokens
- Optional sampling via `LOG_GPT_SAMPLE_RATE` (0.0-1.0)
- Context propagation via `contextvars` for job_id/extractor tracking

## Extraction System (Core Pattern)

**V4 Control Extractor** (`backend/app/extractors/control_extractor.py`) uses **AWARE-CHUNK** architecture:
- Token-based chunks (1000 tokens/chunk, 200 overlap) replace line-based approach
- Chain-of-Thought prompting with 7-step reasoning for boundary detection
- Automatic continuation merging across chunks
- 5-factor confidence scoring (keyword, distance, GPT, alignment, format)
- Rejects extractions with confidence < 0.5

**Key extractors**:
- `control_extractor.py` - Controls extraction (V4 is default)
- `objective_extractor.py` - Multi-factor confidence scoring for objectives
- `cuec_extractor.py` - User Entity Controls  
- `management_response_extractor.py` - Auditor responses

**Test pattern**: `python test_scripts/test_control_v4.py --version v4 --max-display 10`

## Framework Mapping (Performance Critical)

**Batched mode** (default, 6-7x speedup):
- `config.BATCH_ALL_FRAMEWORKS_IN_ONE_CALL = True`
- Maps all 7 frameworks in **single API call** per control (218 calls vs 1,526)
- Uses `gpt-4o-mini` by default (97% cost reduction)
- Function: `map_control_to_all_frameworks_batched()` in `backend/app/frameworks/mapper.py`

**Fallback**: Set to `False` for sequential mode (legacy, slower but more granular).

## Database Schema Patterns

**Multi-table structure** with cascading deletes:
- `scan` - Main report metadata (report_type: SOC1/SOC2/COMBINED, as_of_date, executive_summary)
- `control` - Extracted controls (has_deviation, control_confidence, framework mappings in JSON)
- `cuec` - User Entity Controls
- `control_objectives` - Strategic goals (5-factor confidence: keyword, distance, GPT, alignment, format)
- `subservice_org` - Sub-service organizations
- `management_response` - Auditor responses

**Key relationships**: `scan.id` → `control.scan_id` (ON DELETE CASCADE). Always use `scan_id` in queries.

## API Routing Conventions

**Router structure** (`backend/app/routers/`):
- All routers use async handlers: `async def endpoint(db: AsyncSession = Depends(get_db))`
- Authentication: `current_user: User = Depends(get_current_active_user)`
- Admin-only: `Depends(require_admin)`
- Path pattern: `/api/{resource}` - registered in `backend/app/main.py`

**Key routers**: `control_router.py`, `objective_router.py`, `scan_router.py`, `baseline_router.py`

## Frontend Architecture (React + Material-UI)

**Tech Stack**:
- React 18 with TypeScript
- Material-UI v7 (`@mui/material`, `@mui/x-data-grid`)
- Native `fetch` API (no axios) with custom `FetchClient` class
- Context API for state: `AuthContext`, `SplitViewContext`
- React Router for navigation

**API Client Pattern** (`frontend/src/api/client.ts`):
```typescript
// Always uses relative URLs - nginx proxy handles routing
api.get('/api/scans')  // NOT http://localhost:8000/api/scans
// Automatic token refresh on 401 via refreshTokenCallback
// 120s timeout default (configurable per request)
// Authorization: Bearer {token} auto-injected from AuthContext
```

**Component Conventions**:
- Material-UI `Box` for layout with sx props: `<Box sx={{ display: 'flex', gap: 2 }}>`
- `DataGrid` from `@mui/x-data-grid` for tables (virtualized, sortable, filterable)
- `Typography` for text with variants: `h4`, `h5`, `body1`, `body2`
- `Button` with `variant`: `contained`, `outlined`, `text`
- Icon imports: `import { Add, Edit, Delete } from '@mui/icons-material'`

**State Management**:
- AuthContext: JWT token storage (localStorage), user profile, role checks (`isAdmin`)
- Session timeout warning component (`SessionTimeoutWarning`) checks every 30s
- No Redux - Context API + local state only

**Key Patterns**:
- Pages in `frontend/src/pages/` (e.g., `ReportPage.tsx`, `ValidationPage.tsx`)
- Reusable components in `frontend/src/components/`
- API calls in `frontend/src/api/` or inline with async/await
- Type definitions in `frontend/src/types/`

## Testing & Debugging

**Test scripts** (`test_scripts/`):
- `run_scan.ps1` - Direct execution wrapper (preferred)
- `test_control_v4.py` - V4 extractor validation
- `test_deployment.ps1` - Full integration test suite
- `socanalyzer.ps1` - Docker service management (start/stop/status/rebuild)

**Debug patterns**:
```sql
-- Check extraction quality
SELECT status, COUNT(*), AVG(final_confidence) 
FROM control_objectives WHERE scan_id = X GROUP BY status;

-- Find zero-confidence extractions
SELECT * FROM control_objectives 
WHERE scan_id = X AND final_confidence = 0.0;
```

## Error Handling Patterns

**GPT Call Failures**:
- 3 retries with exponential backoff (1s, 2s, 4s + jitter)
- Specific handling: Timeouts (900s default), 502 Bad Gateway (service unavailable)
- Redis job status updated with error messages: `status: "extracting controls (GPT timeout - retrying 2/3)"`
- Last exception re-raised after retries exhausted
- Logged to both standard logger and optional GPT calls log

**Database Errors**:
- AsyncPG connection pooling (10 connections, 20 overflow, 30s timeout)
- Pre-ping enabled (`DB_POOL_PRE_PING=true`) to detect stale connections
- Migrations run on startup if `RUN_MIGRATIONS_ON_START=true`
- Cascade deletes: Deleting `scan` removes all related `control`, `cuec`, `objective` rows

**Frontend Error Handling**:
- `ErrorBoundary` component catches React render errors
- API 401 errors → automatic token refresh → retry → redirect to /login if fails
- Network errors → user-facing toast/snackbar notifications
- Validation errors → inline form field errors

## Configuration Patterns

**Environment-driven** (`.env` file):
- `DATABASE_URL_ASYNC` - AsyncPG connection string (required)
- `DATAIKU_DSS_HOST`, `DATAIKU_DSS_API_KEY` - GPT access via Dataiku
- `DATAIKU_DSS_HOST_IP` - Direct IP fallback for DNS issues (bypasses corporate DNS)
- `DATAIKU_CA_BUNDLE=/certs/corp-ca-bundle.pem` - Corporate SSL certs
- `LOG_GPT_REQUESTS=true` - Enable GPT call logging to `data/logs/gpt_calls.log`
- `LOG_GPT_SAMPLE_RATE=0.1` - Sample 10% of calls (reduces log volume)
- `HTTP_REQUEST_TIMEOUT=900` - 15 minutes for large GPT requests

**Runtime config** (`backend/app/config.py` - 4100+ lines):
- Feature flags: `BATCH_ALL_FRAMEWORKS_IN_ONE_CALL`, `CONTROL_V4_ENABLED`
- Model mappings: `DATAIKU_CATALOG_MAP`, `DEFAULT_GPT_MODEL`
- Timeouts: `FRAMEWORK_MAPPING_TIMEOUT_SECONDS = 45`, `DATAIKU_TIMEOUT = 900`
- Pool settings: `DB_POOL_SIZE=10`, `DB_MAX_OVERFLOW=20`, `DB_POOL_TIMEOUT=30`

## Project-Specific Conventions

1. **Async everywhere**: All DB operations use AsyncSession. Never use sync models in routers.
2. **Multi-factor confidence**: Objective/control extraction uses weighted average (keyword 0.25, distance 0.20, GPT 0.30, alignment 0.15, format 0.10).
3. **Corporate network**: DNS cache required for Dataiku access. Health checks verify connectivity.
4. **SOC1 vs SOC2**: Use `report_type` enum (SOC1, SOC2, COMBINED) and `as_of_date` for Type 1 reports.
5. **PowerShell-first**: All automation uses `.ps1` scripts. Frontend uses `npm` commands.
6. **No API threading**: Deprecated due to stability issues. Use direct script execution.
7. **Framework mapping optimization**: Always use batched mode unless debugging specific framework issues.

## Key Files Reference

- `backend/app/analyze.py` - Main scan orchestrator (932 lines)
- `backend/app/models.py` - SQLAlchemy schema (488 lines)
- `backend/app/config.py` - All configuration (4148 lines)
- `docker-compose.yml` - Service definitions with fixed IPs
- `docs/CONTROL_V4_QUICKSTART.md` - V4 extractor guide
- `docs/CONTROL_OBJECTIVE_WORKFLOW.md` - Complete extraction pipeline

## Documentation

**Extensive docs/** folder with:
- `ARCHITECTURE.md` - Network topology, database connections
- `GPT_MODEL_CONFIG.md` - Model naming vs actual models (gpt-5 → gpt-4o)
- `FRAMEWORK_MAPPING_OPTIMIZATION.md` - 6-7x speedup implementation
- `DEPLOYMENT_CHECKLIST.md` - Production deployment steps
- `CONTROL_OBJECTIVE_WORKFLOW.md` - 390-line extraction guide

**Read these first** when working on extractors, GPT integration, or performance issues.
