# Architecture Setup Guide

## System Architecture

### 🖥️ Local (Client-Side)
**Purpose:** Development, script execution, CPU-intensive operations

**Components:**
- Interactive scan script (`interactive_scan.py`)
- Test scripts (`test_scripts/`)
- Extraction processes (V4 control extractor)
- GPT API calls (through Dataiku DSS)

**Configuration:**
- Connects to Docker PostgreSQL via `localhost:5433`
- Uses `DATAIKU_DSS_HOST_IP` for direct IP connection (bypasses DNS)
- Certificates in `/certs` for corporate SSL

### 🐳 Docker (Server-Side)
**Purpose:** Production-ready services, database, API, frontend

**Components:**
1. **PostgreSQL** (`socanalyzer-postgres`)
   - Port: `5433` (external) → `5432` (internal)
   - Database: `soc2analyzer`
   - User: `soc2_analyzer`
   - Stores all scan results, controls, CUECs, etc.

2. **DNS Cache** (`socanalyzer-dns-cache`)
   - IP: `172.20.0.2` (internal)
   - Caches corporate DNS queries (e.g., `dataiku-dss.corp.nandps.com`)
   - Reduces load on corporate DNS servers

3. **Redis** (`socanalyzer-redis`)
   - Port: `6379`
   - Used for job queues and caching

4. **Backend API** (`socanalyzer-backend`)
   - Port: `8000`
   - FastAPI + Uvicorn
   - Connects to PostgreSQL via internal network (`postgres:5432`)
   - Uses DNS cache for corporate resolution

5. **Frontend** (`socanalyzer-frontend`)
   - Port: `3000` (external) → `80` (internal)
   - React application
   - Queries backend API

## Network Architecture

```
Local Machine (Windows)
├─ Python Scripts → localhost:5433 → Docker PostgreSQL
└─ Browser → localhost:3000 → Docker Frontend
                └─ → localhost:8000 → Docker Backend
                            └─ → postgres:5432 (internal)

Docker Network (172.20.0.0/16)
├─ 172.20.0.2 → DNS Cache
├─ 172.20.0.3 → PostgreSQL
├─ 172.20.0.4 → Redis
├─ 172.20.0.5 → Backend API
└─ Frontend (dynamic IP)
```

## Setup Steps

### 1. Stop Local PostgreSQL (One-Time)

**Run as Administrator:**
```powershell
.\stop_local_postgres.ps1
```

This will:
- Stop the Windows PostgreSQL service
- Disable it from starting on boot
- Free up system resources

### 2. Start Docker Services

```powershell
docker-compose up -d
```

**Wait for services:**
```powershell
docker-compose ps
```

All services should show "Up" or "healthy" status.

### 3. Verify Connectivity

**Test local script → Docker PostgreSQL:**
```powershell
python list_scans.py
```

**Test backend API:**
```powershell
curl http://localhost:8000/history
```

**Test frontend:**
Open browser: `http://localhost:3000`

### 4. Run Interactive Script

```powershell
python interactive_scan.py
# OR
.\interactive.ps1
```

The script will:
- Connect to Docker PostgreSQL on port 5433
- Save all results to Docker database
- Automatically appear in frontend

## Environment Variables (.env)

### Database Connection
```properties
POSTGRES_DB=soc2analyzer
POSTGRES_USER=soc2_analyzer
POSTGRES_PASSWORD=puntitforthewin

# Local scripts use port 5433 (Docker exposed port)
DATABASE_URL_ASYNC=postgresql+asyncpg://soc2_analyzer:puntitforthewin@localhost:5433/soc2analyzer
DATABASE_URL_SYNC=postgresql://soc2_analyzer:puntitforthewin@localhost:5433/soc2analyzer
```

### DNS Configuration
```properties
# Docker backend uses DNS cache (172.20.0.2)
# Local scripts use direct IP to bypass DNS
DATAIKU_DSS_HOST=https://dataiku-dss.corp.nandps.com/
DATAIKU_DSS_HOST_IP=10.249.93.32
```

## Data Flow

### Scan Workflow
1. **User runs** `interactive_scan.py` (local)
2. **Script extracts** text from PDF (local CPU)
3. **Script calls** Dataiku GPT API (direct IP: 10.249.93.32)
4. **Script saves** results to Docker PostgreSQL (localhost:5433)
5. **Frontend queries** backend API (localhost:8000)
6. **Backend queries** PostgreSQL (internal postgres:5432)
7. **User views** report in browser (localhost:3000)

### DNS Resolution
- **Docker containers:** Use DNS cache (172.20.0.2) → Corporate DNS
- **Local scripts:** Use `DATAIKU_DSS_HOST_IP` → Direct IP (no DNS)

## Troubleshooting

### "Port 5433 already in use"
```powershell
# Check what's using port 5433
netstat -ano | Select-String "5433"

# Kill the process or change Docker port in docker-compose.yml
```

### "Cannot connect to PostgreSQL"
```powershell
# Verify Docker PostgreSQL is running
docker ps | Select-String "postgres"

# Check logs
docker logs socanalyzer-postgres

# Test connection
docker exec socanalyzer-postgres psql -U soc2_analyzer -d soc2analyzer -c "SELECT 1;"
```

### "Frontend shows 404 for scan"
```powershell
# Verify scan exists in Docker database
python list_scans.py

# Check backend can access it
curl http://localhost:8000/report/{scan_id}

# Restart backend if needed
docker-compose restart backend
```

### "Local PostgreSQL keeps starting"
```powershell
# Re-run as Administrator
.\stop_local_postgres.ps1

# Verify disabled
Get-Service postgresql-x64-17
```

## Backup and Restore

### Backup Docker Database
```powershell
docker exec socanalyzer-postgres pg_dump -U soc2_analyzer -d soc2analyzer -F c -f /tmp/backup.dump
docker cp socanalyzer-postgres:/tmp/backup.dump ./database_backup/backup_$(Get-Date -Format 'yyyyMMdd').dump
```

### Restore to Docker Database
```powershell
docker cp ./database_backup/backup.dump socanalyzer-postgres:/tmp/backup.dump
docker exec socanalyzer-postgres pg_restore -U soc2_analyzer -d soc2analyzer -c /tmp/backup.dump
```

## Maintenance

### View Logs
```powershell
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f postgres
```

### Update Images
```powershell
docker-compose pull
docker-compose up -d --build
```

### Clean Up
```powershell
# Stop all services
docker-compose down

# Remove volumes (deletes database!)
docker-compose down -v

# Remove all unused Docker resources
docker system prune -a
```

## URLs Reference

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | `http://localhost:3000` | Main UI |
| Backend API | `http://localhost:8000` | REST API |
| API Docs | `http://localhost:8000/docs` | Swagger UI |
| PostgreSQL | `localhost:5433` | Database (local access) |
| Redis | `localhost:6379` | Cache |

## Backend Architecture (v2.0.0)

### Modular Router Structure

The backend has been refactored into a modular architecture with **9 specialized routers** and **3 service modules**:

#### Router Modules (`backend/app/routers/`)

1. **scan_router.py** (650 lines, 10 endpoints + WebSocket)
   - PDF upload and analysis orchestration
   - Job management and progress tracking
   - WebSocket for real-time updates
   - Endpoints: `/analyze/`, `/analyze/cancel/{job_id}`, `/analyze/status/{job_id}`, etc.

2. **report_router.py** (412 lines, 7 endpoints)
   - Report CRUD operations
   - PDF and Excel export
   - Full report payload with controls/CUECs/suborgs
   - Endpoints: `/report/{scan_id}`, `/report/{scan_id}/pdf`, `/report/{scan_id}/export_excel`, etc.

3. **control_router.py** (615 lines, 14 endpoints)
   - Control CRUD operations
   - Merge, split, and duplicate management
   - Framework mapping (TSC/COSO/etc.)
   - Endpoints: `/report/{scan_id}/controls/{control_id}`, `/merge`, `/split`, `/suggest_merges`, etc.

4. **cuec_router.py** (215 lines, 4 endpoints)
   - CUEC (Complementary User Entity Control) operations
   - Framework mapping
   - Endpoints: `/report/{scan_id}/cuecs/{cuec_id}`, `/recompute_frameworks`, etc.

5. **suborg_router.py** (97 lines, 2 endpoints)
   - Subservice organization updates
   - Confidence normalization
   - Endpoints: `/report/{scan_id}/suborgs/id/{suborg_id}`, `/report/{scan_id}/suborgs/name/{name}`, etc.

6. **deviation_router.py** (227 lines, 6 endpoints)
   - Deviation management
   - AI-powered deviation summarization
   - Batch regeneration with progress tracking
   - Endpoints: `/report/{scan_id}/deviations`, `/regenerate_summary`, `/create`, etc.

7. **executive_summary_router.py** (117 lines, 3 endpoints)
   - Executive summary generation
   - Staleness tracking and regeneration
   - Endpoints: `/report/{scan_id}/executive_summary`, `/regenerate`, etc.

8. **baseline_router.py** (361 lines, 12 endpoints)
   - Baseline creation and comparison
   - Validation workflows
   - Pattern learning and review queue
   - Endpoints: `/baseline/create`, `/verify/{scan_id}`, `/patterns/review-queue`, etc.

9. **config_router.py** (326 lines, 16 endpoints)
   - Settings CRUD
   - Runtime configuration introspection
   - Help system
   - Docker container control
   - Endpoints: `/settings`, `/config/runtime`, `/help/index`, `/docker/status`, etc.

#### Service Modules (`backend/app/services/`)

1. **scan_service.py** (3 functions)
   - `mark_executive_summary_stale()` - Track data changes requiring summary regeneration
   - `update_scan_gpt_fields()` - Update GPT usage metrics
   - `add_gpt_usage()` - Track detailed GPT call information

2. **merge_service.py** (~735 lines, 7 functions)
   - `automated_cleanup()` - Auto-merge high-confidence duplicates
   - `penalize_incomplete_controls()` - Apply penalties to incomplete controls
   - `detect_duplicate_type()` - Classify duplicate relationships (IDENTICAL/CRITERIA_VARIANT/TEST_VARIANT/AMBIGUOUS)
   - `suggest_control_merges()` - Generate merge suggestions with confidence scoring
   - `merge_controls_action()` - Execute control merge with intelligent primary selection
   - `split_control()` - Undo merge and restore original confidence

3. **excel_export.py** (ExcelExportService)
   - Excel template generation for reports

#### Utility Modules (`backend/app/utils/`)

1. **redis_helpers.py**
   - `get_job()`, `set_job()`, `del_job()` - Redis job management
   - `_get_redis()` - Connection pool singleton (max_connections=20)

### Import Strategy

All routers are registered in `main.py`:

```python
from .routers import (
    scan_router, report_router, control_router, cuec_router,
    suborg_router, deviation_router, executive_summary_router,
    baseline_router, config_router
)

app.include_router(scan_router.router, tags=["scan"])
app.include_router(report_router.router, tags=["report"])
# ... etc
```

### Benefits

- **Modularity**: Each router handles a specific domain
- **Maintainability**: ~3,000 lines extracted from monolithic main.py
- **Testability**: Routers can be tested independently
- **Clear separation**: Business logic in service layer, HTTP handling in routers

## Performance Notes

- **Docker PostgreSQL** uses persistent volume (`postgres_data`)
- **DNS cache** reduces corporate DNS load (caches for 1 hour)
- **Local scripts** bypass DNS using direct IP (`DATAIKU_DSS_HOST_IP`)
- **Backend** uses DNS cache for reliability
- **Redis connection pooling** (20 connections) for 20-30% performance gain
- **8 database indexes** for optimized queries on large scans

## Security Notes

- PostgreSQL password in `.env` (not in version control)
- Corporate SSL certificates in `/certs` (mounted read-only)
- Docker network isolated (172.20.0.0/16)
- Only ports 3000, 5433, 6379, 8000 exposed to host
