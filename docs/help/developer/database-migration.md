# Database Migration Guide

## Overview

This guide covers the completed migration from local PostgreSQL to Docker PostgreSQL, ensuring all data flows through a single containerized database.

## Migration Complete

The architecture migration was successfully completed with these changes:

### 1. Docker PostgreSQL Exposure
- **Internal:** Docker backend uses `postgres:5432` (internal network)
- **External:** Local scripts connect via `localhost:5433`

### 2. Database Configuration
Updated `.env` file to point to Docker PostgreSQL:
```bash
# Before:
DATABASE_URL_ASYNC=postgresql+asyncpg://postgres:postgres@localhost:5432/soc2analyzer

# After:
DATABASE_URL_ASYNC=postgresql+asyncpg://postgres:postgres@localhost:5433/soc2analyzer
```

### 3. Local PostgreSQL Handling
Windows PostgreSQL service should be stopped to avoid confusion:

```powershell
# Run as Administrator:
.\stop_local_postgres.ps1
```

This will:
- Stop the `postgresql-x64-17` service
- Disable it from auto-starting
- Free up port 5432
- Prevent database confusion

## Current Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LOCAL MACHINE                        │
│                                                          │
│  Python Scripts (interactive_scan.py)                   │
│         │                                                │
│         ├─→ Extract PDF (local CPU)                     │
│         ├─→ Call Dataiku GPT (via DNS fallback)        │
│         └─→ Save to localhost:5433 ──────┐              │
│                                           │              │
│  Browser (localhost:3000) ───────────┐   │              │
│                                       ↓   ↓              │
└───────────────────────────────────────────────────────┬─┘
                                                         │
┌────────────────────────────────────────────────────────┼─┐
│                    DOCKER NETWORK                      │ │
│                                                         │ │
│  ┌──────────────┐      ┌──────────────┐               │ │
│  │   Frontend   │      │   Backend    │               │ │
│  │   (React)    │──────┤   (FastAPI)  │               │ │
│  │  Port 3000   │      │  Port 8000   │               │ │
│  └──────────────┘      └──────┬───────┘               │ │
│                               │                        │ │
│  ┌──────────────┐      ┌──────┴───────┐               │ │
│  │  DNS Cache   │      │  PostgreSQL  │←──────────────┘ │
│  │  172.20.0.2  │      │  Port 5432   │                 │
│  └──────────────┘      │  (internal)  │                 │
│                        │  Port 5433   │                 │
│  ┌──────────────┐      │  (external)  │                 │
│  │    Redis     │      └──────────────┘                 │
│  │  Port 6379   │                                       │
│  └──────────────┘                                       │
└──────────────────────────────────────────────────────────┘
```

## Benefits

### ✅ Consistency
- All data in ONE database (Docker PostgreSQL)
- No confusion about which database has what data
- Frontend always shows ALL scans

### ✅ Production-Ready
- Database, backend, frontend all containerized
- Easy to deploy to production environment
- DNS cache reduces corporate DNS load
- Persistent data volumes

### ✅ Performance
- Local scripts use local CPU for extraction
- Docker services always running, no startup time
- Persistent database (survives container restarts)

### ✅ Development Friendly
- Run scripts locally (no need to enter container)
- Hot-reload for backend/frontend development
- Easy to test and debug

## Verification

### Check Database Connection

**From local scripts:**
```powershell
python list_scans.py
# Should show all scans in Docker database
```

**From backend API:**
```powershell
curl http://localhost:8000/scans
```

**From frontend:**
```
Open browser: http://localhost:3000
Should see all scans on analyzer page
```

### Verify Ports

```powershell
netstat -ano | Select-String "5432|5433"
# Should only see:
# - 5432: LISTENING (Docker internal)
# - 5433: LISTENING (Docker external)
# No local PostgreSQL on 5432
```

### Check Docker Services

```powershell
docker ps
# Should show:
# - socanalyzer-postgres
# - socanalyzer-backend
# - socanalyzer-frontend
# - socanalyzer-redis
# - socanalyzer-dns-cache
```

## Database Operations

### Backup Database

```powershell
# Backup to SQL file
docker exec -t socanalyzer-postgres pg_dump -U postgres soc2analyzer > backup.sql

# Backup to custom format (compressed)
docker exec -t socanalyzer-postgres pg_dump -U postgres -Fc soc2analyzer > backup.dump
```

### Restore Database

```powershell
# Restore from SQL file
docker exec -i socanalyzer-postgres psql -U postgres soc2analyzer < backup.sql

# Restore from custom format
docker exec -i socanalyzer-postgres pg_restore -U postgres -d soc2analyzer < backup.dump
```

### Reset Database

```powershell
# Drop and recreate (WARNING: destroys all data)
docker exec socanalyzer-postgres psql -U postgres -c "DROP DATABASE soc2analyzer;"
docker exec socanalyzer-postgres psql -U postgres -c "CREATE DATABASE soc2analyzer;"

# Restart backend to recreate tables
docker compose restart backend
```

### Access Database Console

```powershell
# Connect to PostgreSQL shell
docker exec -it socanalyzer-postgres psql -U postgres -d soc2analyzer

# Run queries
SELECT scan_id, company_name, product, scan_date FROM scans ORDER BY scan_id;
```

## Migrating Old Data

If you have data in the old local PostgreSQL that you want to migrate:

### 1. Backup Old Database

```powershell
# Backup from local PostgreSQL (if still running)
pg_dump -U postgres -h localhost -p 5432 soc2analyzer > old_local_backup.sql
```

### 2. Restore to Docker PostgreSQL

```powershell
# Import into Docker database
docker exec -i socanalyzer-postgres psql -U postgres soc2analyzer < old_local_backup.sql
```

### 3. Verify Migration

```powershell
# Check scan count
docker exec socanalyzer-postgres psql -U postgres -d soc2analyzer -c "SELECT COUNT(*) FROM scans;"

# List all scans
python list_scans.py
```

## Troubleshooting

### Can't connect to database

**Check Docker container:**
```powershell
docker ps | Select-String postgres
# Should show socanalyzer-postgres running
```

**Check port exposure:**
```powershell
docker port socanalyzer-postgres
# Should show: 5432/tcp -> 0.0.0.0:5433
```

**Test connection:**
```powershell
python -c "from backend.app.database import async_engine; print('OK')"
```

### Both PostgreSQL instances running

```powershell
netstat -ano | Select-String "5432|5433"
# Should only see Docker ports (5433 external, 5432 internal)
# If you see local PostgreSQL on 5432, stop it:
.\stop_local_postgres.ps1
```

### Database tables missing

```powershell
# Restart backend to recreate tables
docker compose restart backend

# Or manually run migrations
docker exec socanalyzer-backend alembic upgrade head
```

### Old scans not visible in frontend

**Cause:** Data still in local PostgreSQL, not Docker PostgreSQL

**Solution:** Migrate old data (see "Migrating Old Data" section above)

## Files Modified

1. **docker-compose.yml**
   - Exposed PostgreSQL port: `5433:5432`
   - Updated default credentials to match `.env`

2. **.env**
   - Updated database URLs to use port 5433
   - Added comments explaining local vs Docker

3. **New Helper Scripts:**
   - `stop_local_postgres.ps1` - Stop Windows PostgreSQL
   - `check_scan_28.py` - Database verification tool
   - `upload_last_scan.py` - Upload JSON to database

## Success Criteria

✅ Docker containers running (postgres, backend, frontend, redis, dns-cache)  
✅ Local scripts connect to Docker PostgreSQL (port 5433)  
✅ Backend API returns data  
✅ Frontend displays reports  
✅ Local PostgreSQL stopped (port 5432 free)  
✅ New scans appear in frontend immediately  

## Further Reading

- See **Architecture > Database Schema** for table structure
- See **Architecture > Backend Services** for database connection details
- See **Troubleshooting > Common Errors** for database issues
