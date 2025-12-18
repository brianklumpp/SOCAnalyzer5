# Docker Development Setup - CRITICAL REFERENCE

## ⚠️ READ THIS BEFORE TOUCHING DOCKER CONFIGURATION ⚠️

### Current Working Configuration

**Frontend:**
- **Target**: `dev` (Vite dev server)
- **Port**: 3000 (both host and container)
- **Image**: `socanalyzer-frontend:latest`
- **DO NOT BUILD** - Bind mounts handle code changes automatically

**Backend:**
- **Port**: 8000
- **Image**: `socanalyzer-backend:latest`
- **DO NOT BUILD** - Bind mounts handle code changes automatically

### What's Bind-Mounted (Auto-Updates)

#### Frontend
```yaml
- ./frontend/src:/app/src                    # React components, pages, etc.
- ./frontend/public:/app/public              # Static assets
- ./frontend/vite.config.ts:/app/vite.config.ts
- ./frontend/index.html:/app/index.html
- ./frontend/package.json:/app/package.json
```

#### Backend
```yaml
- ./backend/app:/app/backend/app             # Python source code
- ./backend/alembic:/app/backend/alembic     # Database migrations
- ./backend/alembic.ini:/app/backend/alembic.ini:ro
- ./.env:/app/.env                            # Environment variables
- ./data:/app/data                            # Data files
```

### How Authentication Works

**NOT nginx-based** - Authentication is handled by:
1. React app checks for token on mount
2. Backend `/auth/login` endpoint (Windows SSO or test mode)
3. Bearer token stored in localStorage
4. `api` client (from `frontend/src/api/client.ts`) includes auth header
5. All API calls must use `api` not `axios`

### Port Configuration

| Service | Container Port | Host Port | Notes |
|---------|---------------|-----------|-------|
| Frontend (Vite) | 3000 | 3000 | Dev server with HMR |
| Backend (Uvicorn) | 8000 | 8000 | FastAPI with reload |
| Postgres | 5432 | 5433 | Avoid conflict with local PG |
| Redis | 6379 | 6379 | Cache and sessions |

**Windows Port 80 Issue**: IIS/HTTP.sys often blocks port 80. That's why we use port 3000.

### Vite Configuration

**File**: `frontend/vite.config.ts` (bind-mounted)
```typescript
server: {
  host: '0.0.0.0',  // Required for Docker
  port: 3000,       // Must match docker-compose port
  proxy: {
    '/api': { target: 'http://backend:8000' },
    '/auth': { target: 'http://backend:8000' },  // REQUIRED for login/refresh
    '/ws': { target: 'ws://backend:8000', ws: true }
  }
}
```

**⚠️ CRITICAL**: Proxy configuration changes require frontend restart:
```powershell
docker-compose restart frontend
```

## 🚫 WHAT NOT TO DO

### ❌ DO NOT Build Images for Code Changes
```bash
# WRONG - Wastes time, defeats bind mounts
docker-compose build frontend
docker-compose build backend

# RIGHT - Just restart to reload
docker-compose restart frontend backend
```

### ❌ DO NOT Switch to Prod Target
```yaml
# WRONG - Breaks live updates, uses nginx on port 80
target: prod

# RIGHT - Use dev for development
target: dev
```

### ❌ DO NOT Change Port Mappings Without Updating Vite Config
```yaml
# WRONG - Port mismatch causes ERR_EMPTY_RESPONSE
ports:
  - "3000:5173"  # Vite is on 3000, not 5173!

# RIGHT - Match vite.config.ts port
ports:
  - "3000:3000"
```

### ❌ DO NOT Use axios Directly in Components
```typescript
// WRONG - No auth header, causes 401 errors
import axios from 'axios';
await axios.get('/report/123/deviations');

// RIGHT - Uses auth token from localStorage
import { api } from '../api/client';
await api.get('/report/123/deviations');
```

## ✅ CORRECT PROCEDURES

### Restart After Code Changes (If Needed)
```powershell
# For backend Python changes (usually auto-reloads via --reload)
docker-compose restart backend

# For frontend config changes (vite.config.ts, package.json)
# ⚠️ ESPECIALLY PROXY CHANGES - MUST RESTART
docker-compose restart frontend

# For bind-mounted source code (src/*) - NO RESTART NEEDED
# Vite HMR and uvicorn --reload handle it automatically
```

### Fix "Container Keeps Restarting"
```powershell
# 1. Check logs
docker logs socanalyzer-frontend
docker logs socanalyzer-backend

# 2. Common causes:
# - Port conflict (check: netstat -ano | findstr :3000)
# - Syntax error in code (check logs)
# - Missing dependency (usually happens after npm install)

# 3. If dependency issue, rebuild ONCE:
docker-compose build frontend
docker-compose up -d frontend
```

### Fix "ERR_EMPTY_RESPONSE" or "Site Won't Load"
```powershell
# 1. Verify containers are running
docker ps --filter name=socanalyzer

# 2. Check Vite is on correct port
docker logs socanalyzer-frontend | Select-String "Local"
# Should show: http://localhost:3000/

# 3. Check port mapping
docker ps --filter name=frontend --format "{{.Ports}}"
# Should show: 0.0.0.0:3000->3000/tcp

# 4. Test internal container connection
docker exec socanalyzer-frontend wget -O- http://localhost:3000
```

### Fix "No Authentication" or 401 Errors / ERR_EMPTY_RESPONSE on Login
```powershell
# 1. MOST COMMON: Frontend needs restart after adding /auth proxy
docker-compose restart frontend

# 2. Verify /auth proxy exists in vite.config.ts
cat frontend/vite.config.ts | Select-String -Pattern "auth"
# Must show: '/auth': { target: 'http://backend:8000' }

# 3. Check if using api client (not axios)
grep -r "import axios" frontend/src/components/*.tsx

# 4. Verify auth endpoints are proxied
docker exec socanalyzer-frontend cat /app/vite.config.ts | grep -A5 proxy

# 5. Check backend auth is working
curl http://localhost:8000/auth/user-info

# 6. Clear browser localStorage and re-login
# DevTools -> Application -> Local Storage -> Clear
```

## 📋 Quick Reference Commands

### Daily Development
```powershell
# Start everything
docker-compose up -d

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Restart after config change
docker-compose restart backend frontend

# Stop everything
docker-compose down

# Check status
docker-compose ps
```

### Troubleshooting
```powershell
# See what's using port 3000
netstat -ano | findstr :3000

# Check container health
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Get into container shell
docker exec -it socanalyzer-frontend sh
docker exec -it socanalyzer-backend bash

# View full logs
docker logs socanalyzer-frontend
docker logs socanalyzer-backend

# Nuclear option - full restart
docker-compose down
docker-compose up -d
```

### Database Operations
```powershell
# Run migration (inside backend container or locally)
cd backend
alembic upgrade head

# Check current version
alembic current

# Rollback one version
alembic downgrade -1
```

## 🎯 The Golden Rule

**If you're about to run `docker-compose build` for a code change:**
1. Stop
2. Remember: bind mounts exist for this reason
3. Just edit the file and let Vite/uvicorn auto-reload
4. Only build when Dockerfile, dependencies, or build target changes

## 📝 Common Mistakes Reference

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Switched to prod target | No live updates, wrong port | Change back to `dev` in docker-compose.yml |
| Port mapping wrong | ERR_EMPTY_RESPONSE | Match vite.config.ts port (3000:3000) |
| Used axios not api | 401 Unauthorized | Import api from client.ts |
| Missing /auth proxy | ERR_EMPTY_RESPONSE on login | Add to vite.config.ts + restart frontend |
| Changed proxy without restart | Auth still broken | docker-compose restart frontend |
| Built unnecessarily | Wasted 5 minutes | Just restart container |
| Port 80 conflict | Container restart loop | Use port 3000, check IIS |
| Forgot bind mount | Changes not appearing | Add volume in docker-compose.yml |

## 🔧 When You Actually Need to Build

**Only rebuild when:**
1. **Dockerfile changed** - Modified build steps, base image, etc.
2. **Dependencies changed** - Added/removed npm packages or pip requirements
3. **Build target changed** - Switched between dev/prod/other targets
4. **First time setup** - Initial image creation
5. **New team member** - They don't have images yet

**Even then, only rebuild the affected service:**
```powershell
docker-compose build frontend  # Only if frontend changed
docker-compose build backend   # Only if backend changed
```

## 📍 File Locations for Quick Reference

- **Docker compose**: `./docker-compose.yml`
- **Frontend Dockerfile**: `./frontend/Dockerfile`
- **Backend Dockerfile**: `./backend/Dockerfile`
- **Vite config**: `./frontend/vite.config.ts` (bind-mounted)
- **Nginx config**: `./frontend/nginx.conf` (only used in prod target)
- **API client**: `./frontend/src/api/client.ts` (has auth logic)
- **Backend entrypoint**: `./backend/entrypoint.sh`

## 🚀 Expected Startup Messages

**Frontend (Vite):**
```
VITE v5.4.21 ready in 272 ms
➜  Local:   http://localhost:3000/
➜  Network: http://172.20.0.6:3000/
```

**Backend (Uvicorn):**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

If you see anything else, check the logs immediately.
Using logging not logger