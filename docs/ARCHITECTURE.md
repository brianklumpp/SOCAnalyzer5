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

## Performance Notes

- **Docker PostgreSQL** uses persistent volume (`postgres_data`)
- **DNS cache** reduces corporate DNS load (caches for 1 hour)
- **Local scripts** bypass DNS using direct IP (`DATAIKU_DSS_HOST_IP`)
- **Backend** uses DNS cache for reliability

## Security Notes

- PostgreSQL password in `.env` (not in version control)
- Corporate SSL certificates in `/certs` (mounted read-only)
- Docker network isolated (172.20.0.0/16)
- Only ports 3000, 5433, 6379, 8000 exposed to host
