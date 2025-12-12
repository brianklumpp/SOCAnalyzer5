# CRITICAL FIX - Redis Connection Issue

## Problem
Backend cannot connect to Redis because services were started with incomplete network configuration.

## Root Cause
Services may have been started before the correct docker-compose.yml was in place, so containers are running without proper network setup.

## Solution - COMPLETE RESTART

Run these commands **in order**:

```powershell
# 1. STOP AND REMOVE all containers and networks
docker compose down

# 2. VERIFY everything is stopped
docker ps -a | findstr socanalyzer

# If you see any socanalyzer containers, remove them:
docker rm -f socanalyzer-backend socanalyzer-frontend socanalyzer-postgres socanalyzer-redis socanalyzer-dns-cache

# 3. REPLACE docker-compose.yml with the new one
# (Copy docker-compose-SEND-TO-TESTER.yml to docker-compose.yml)

# 4. START services with correct configuration
docker compose up -d

# 5. VERIFY all services on correct network
docker inspect socanalyzer-backend | findstr -i "networkmode\|ipaddress"
docker inspect socanalyzer-redis | findstr -i "networkmode\|ipaddress"

# You should see:
# - NetworkMode: socanalyzer_socanalyzer-network
# - Backend IP: 172.20.0.5
# - Redis IP: 172.20.0.4
```

## Why This Happens
Docker containers remember their network configuration from when they were first created. Just stopping and restarting doesn't change the network - you must **remove** the containers (`docker compose down`) and recreate them.

## Expected Output After Fix
```
✓ Backend should connect to Redis successfully
✓ Scan uploads should work
✓ No "Name or service not known" errors
```

## If Still Failing
Check the network exists:
```powershell
docker network ls | findstr socanalyzer
```

Should show: `socanalyzer_socanalyzer-network`

If missing, the docker-compose.yml wasn't applied correctly.
