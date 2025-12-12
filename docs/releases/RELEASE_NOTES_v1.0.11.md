# SOCAnalyzer v1.0.11 - CRITICAL Redis Connection Fix

## Issue in v1.0.10
Backend could not connect to Redis, causing scan uploads to fail with error:
```
redis.exceptions.ConnectionError: Error -2 connecting to redis:6379. 
Name or service not known.
```

## Root Cause
The backend was configured to connect to Redis using hostname `redis://redis:6379` but Docker's internal DNS was not reliably resolving the hostname on some systems.

## Fix in v1.0.11
Changed Redis connection to use **fixed IP address** instead of hostname:
- **Old:** `SOCANALYZER_REDIS_URL: redis://redis:6379/0`
- **New:** `SOCANALYZER_REDIS_URL: redis://172.20.0.4:6379/0`

This uses the static IP address assigned to the Redis container in the Docker network, eliminating DNS resolution issues.

## Installation Instructions for v1.0.11

### Fresh Installation:
```powershell
# 1. Extract SOCAnalyzer-Docker-v1.0.11.zip
# 2. Run import script
.\IMPORT.ps1

# Should complete in 5-7 minutes
# Browser opens automatically to http://localhost:3000
```

### Upgrading from v1.0.10:
```powershell
# 1. Stop all services
docker compose down

# 2. Extract v1.0.11 and replace docker-compose.yml
# (Just the docker-compose.yml file needs updating)

# 3. Restart services
docker compose up -d
```

## Verification
After starting services, verify backend can connect to Redis:

```powershell
# Check backend logs - should NOT see Redis connection errors
docker logs socanalyzer-backend | Select-String -Pattern "redis"

# Upload a test scan - should work without 500 errors
```

## Expected Behavior
✅ Backend starts without Redis errors  
✅ Scan uploads accepted immediately  
✅ No "Name or service not known" errors  
✅ Job processing works correctly  

## Files Changed
- `docker-compose.yml` (production version)
- Version bumped to 1.0.11

## All Previous Features Retained
✅ Database credentials fix (v1.0.10)  
✅ Automated migrations on startup  
✅ One-click backup/restore/update in manager  
✅ Pre-built Docker images (fast setup)  
✅ Complete offline installation  

---

**Distribution:** SOCAnalyzer-Docker-v1.0.11.zip  
**Size:** ~367 MB  
**Critical Fix:** Redis connection uses IP address instead of hostname  
**Date:** December 11, 2025  
