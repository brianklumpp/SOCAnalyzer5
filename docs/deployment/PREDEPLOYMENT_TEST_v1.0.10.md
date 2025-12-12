# v1.0.10 Pre-Deployment Test Checklist

## Critical: Fresh Installation Test (No .env file)

This test ensures the docker-compose.yml defaults work correctly.

### Setup
1. Extract SOCAnalyzer-Docker-v1.0.10.zip to clean directory
2. **DO NOT create .env file** (testing defaults)
3. Verify only these files exist:
   - docker-compose.yml
   - IMPORT.ps1
   - BACKUP.ps1
   - RESTORE.ps1
   - *.tar files (5 images)
   - dns/ folder

### Test Procedure

#### Step 1: Import and Start
```powershell
.\IMPORT.ps1
```

**Expected:**
- All 5 images load successfully
- Services start: postgres, redis, dns-cache, backend, frontend
- No errors in output

#### Step 2: Check Backend Startup Logs
```powershell
docker logs socanalyzer-backend
```

**Expected to see:**
```
[STARTUP] Running Alembic migrations...
Alembic upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade ... -> head
✓ Database is ready
Starting application...
```

**CRITICAL:** Must see migration logs, NOT:
```
ERROR: relation "scan" does not exist
```

#### Step 3: Verify Database Connection
```powershell
docker exec socanalyzer-backend python -c "import psycopg2; conn = psycopg2.connect('postgresql://soc2_analyzer:puntitforthewin@172.20.0.3:5432/soc2analyzer'); print('✓ Connected'); conn.close()"
```

**Expected:** `✓ Connected`

#### Step 4: Check Tables Exist
```powershell
docker exec socanalyzer-postgres psql -U soc2_analyzer -d soc2analyzer -c "\dt"
```

**Expected output should list tables:**
```
              List of relations
 Schema |       Name        | Type  |    Owner     
--------+-------------------+-------+--------------
 public | alembic_version   | table | soc2_analyzer
 public | company           | table | soc2_analyzer
 public | control           | table | soc2_analyzer
 public | cuec              | table | soc2_analyzer
 public | scan              | table | soc2_analyzer
 public | subservice_org    | table | soc2_analyzer
```

#### Step 5: Access Frontend
1. Open browser to http://localhost:3000
2. Verify homepage loads
3. Check no console errors

#### Step 6: Upload Test Report
1. Click "New Scan"
2. Upload a small test SOC2 report
3. Wait for scan to complete (~5-10 minutes)

**CRITICAL CHECK:** Scan must complete without errors

#### Step 7: Verify Results Saved
```powershell
docker exec socanalyzer-postgres psql -U soc2_analyzer -d soc2analyzer -c "SELECT id, company, scan_date FROM scan;"
```

**Expected:** Should show the scan record

#### Step 8: Check History Page
1. Navigate to History page in UI
2. Should see the completed scan
3. No 500 errors

### Success Criteria

✅ All migrations ran on first startup  
✅ All tables created automatically  
✅ Scan completed successfully  
✅ Results saved to database  
✅ History page loads with data  

### Failure Indicators

❌ "relation 'scan' does not exist" errors  
❌ Backend logs show connection refused  
❌ Tables not created  
❌ Scan completes but results not saved  
❌ History page returns 500 error  

---

## Optional: Manager Tests

### Backup Test
1. Run SOCAnalyzerManager.exe
2. Click "💾 Backup Database"
3. Verify backup created in `backups\` folder

### Restore Test
1. Click "♻ Restore Database"
2. Select the backup file created above
3. Confirm restoration
4. Verify data still present in History page

### Update Checker Test
1. Click "🔄 Check for Updates"
2. Should report "No updates available" (unless v1.0.11 exists on SharePoint)

---

## Rollback Plan

If any tests fail:
1. Stop services: `docker compose down -v`
2. DO NOT DEPLOY v1.0.10
3. Investigate root cause
4. Re-test after fix

---

## Deployment Authorization

Only deploy if **ALL** critical tests pass.

**Tested by:** __________________  
**Date:** __________________  
**Result:** ☐ PASS - Deploy  ☐ FAIL - Do not deploy  

**Notes:**
_______________________________________________
_______________________________________________
_______________________________________________
