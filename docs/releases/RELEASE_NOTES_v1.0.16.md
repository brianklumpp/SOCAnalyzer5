# SOCAnalyzer v1.0.16 Release Notes

**Release Date**: December 12, 2024  
**Type**: Critical Bug Fix Release

## Overview

This release fixes critical database migration issues that prevented v1.0.15 from deploying successfully on fresh installations or upgrades.

## Critical Fixes

### 1. Database Migration File Missing in v1.0.15 Docker Image

**Problem**: The migration file `20251210_add_all_missing_columns.py` was not included in the v1.0.15 Docker image, causing deployments to fail with:

```
sqlalchemy.exc.ProgrammingError: column scan.company does not exist
```

**Solution**: Rebuilt Docker images with verified migration file inclusion. The migration file now exists at:
```
/app/backend/alembic/versions/20251210_add_all_missing_columns.py
```

**Verification**:
```powershell
docker run --rm --entrypoint ls socanalyzer-backend:latest -la /app/backend/alembic/versions/20251210_add_all_missing_columns.py
# Output: -rwxr-xr-x 1 root root 8129 Dec 12 01:22 ...20251210_add_all_missing_columns.py
```

### 2. Silent Migration Failures

**Problem**: The container startup script (`entrypoint.sh`) continued starting the application even when database migrations failed, leading to runtime errors that were difficult to diagnose.

**Old Behavior** (v1.0.15 and earlier):
```bash
else
    echo "  ⚠ Database migrations failed, but continuing..."
fi
# Application starts with wrong schema
```

**New Behavior** (v1.0.16):
```bash
MIGRATION_EXIT_CODE=$?
if [ $MIGRATION_EXIT_CODE -eq 0 ]; then
    echo "  ✓ Database migrations completed successfully"
else
    echo ""
    echo "========================================"
    echo "  ✗ DATABASE MIGRATION FAILED"
    echo "========================================"
    echo "Exit code: $MIGRATION_EXIT_CODE"
    echo ""
    echo "Cannot start application with incompatible database schema."
    echo "Check the migration errors above."
    echo ""
    echo "To fix manually:"
    echo "  docker compose exec backend sh -c 'cd /app/backend && alembic upgrade head'"
    echo ""
    exit 1
fi
```

**Impact**: Migration failures now:
- ✅ Display clear error messages
- ✅ Prevent application startup with wrong schema
- ✅ Provide manual fix command
- ✅ Exit with error code 1 (container restart loop visible)

## Migration Details

**Migration**: `20251210_add_all_missing_columns`  
**Parent**: `1bbe8f1675f2` (add_analyst_notes_columns)  

**Columns Added**:
- `scan.company` (VARCHAR 256)
- `scan.is_sox_vendor` (BOOLEAN)
- `control.framework_mappings` (JSONB)
- `control.primary_framework` (VARCHAR 50)
- Additional columns for report metadata

## Upgrade Instructions

### From v1.0.15 or Earlier

#### Option 1: Clean Upgrade (Recommended for Fresh Deployments)

1. **Stop containers**:
   ```powershell
   docker compose down
   ```

2. **Extract v1.0.16** over old files

3. **Import and start**:
   ```powershell
   .\IMPORT.ps1
   ```

4. **Verify migration**:
   ```powershell
   docker compose logs backend | Select-String "migration"
   # Should show: "✓ Database migrations completed successfully"
   ```

#### Option 2: Quick Fix for Existing v1.0.15 Deployments

If you need immediate relief before upgrading:

1. **Run the quick fix script**:
   ```powershell
   .\QUICKFIX_MISSING_COLUMNS.ps1
   ```

2. **Or manually**:
   ```powershell
   docker compose exec postgres psql -U soc2_analyzer -d soc2analyzer -c "ALTER TABLE scan ADD COLUMN IF NOT EXISTS company VARCHAR(256);"
   docker compose restart backend
   ```

3. **Then upgrade to v1.0.16 when convenient**

### Fresh Installation

No special steps required - migrations run automatically:

1. Extract `SOCAnalyzer-Docker-v1.0.16.zip`
2. Run `.\IMPORT.ps1`
3. Access application at https://localhost

## Verification Checklist

After deployment, verify:

- ✅ VERSION.txt shows `1.0.16`
- ✅ Backend logs show "Database migrations completed successfully"
- ✅ Application loads without errors
- ✅ Can create/view scans
- ✅ No "column does not exist" errors

**Check migration version**:
```powershell
docker compose exec postgres psql -U soc2_analyzer -d soc2analyzer -c "SELECT version_num FROM alembic_version;"
# Should show: 20251210_add_all_missing_columns
```

## Troubleshooting

### Error: "DATABASE MIGRATION FAILED"

**Cause**: Migration script encountered an error (e.g., column already exists, database locked)

**Solution**:
1. Check logs: `docker compose logs backend`
2. Run migration manually:
   ```powershell
   docker compose exec backend sh -c 'cd /app/backend && alembic upgrade head'
   ```
3. If successful, restart: `docker compose restart backend`
4. If still failing, check database state:
   ```powershell
   docker compose exec postgres psql -U soc2_analyzer -d soc2analyzer -c "\d scan"
   ```

### Container Restarts Continuously

**Cause**: Migration failing repeatedly

**Check logs**:
```powershell
docker compose logs backend --tail=50
```

**Manual fix**:
```powershell
# Stop backend to prevent restart loop
docker compose stop backend

# Check migration status
docker compose exec postgres psql -U soc2_analyzer -d soc2analyzer -c "SELECT version_num FROM alembic_version;"

# Run migration manually
docker compose run --rm backend sh -c 'cd /app/backend && alembic upgrade head'

# Start backend
docker compose start backend
```

## Technical Details

**Image Sizes**:
- Backend: 190.78 MB (includes all migration files)
- Frontend: 24.39 MB
- Postgres: 104.11 MB
- Redis: 16.47 MB
- DNS: 2.85 MB
- **Total Distribution**: 336.43 MB

**Migration File Verification**:
```powershell
# Verify migration file in image
docker run --rm --entrypoint ls socanalyzer-backend:latest -la /app/backend/alembic/versions/ | Select-String "20251210"

# Expected output:
# -rwxr-xr-x 1 root root 8129 Dec 12 01:22 20251210_add_all_missing_columns.py
```

**Entrypoint Behavior**:
```bash
# Migration runs on container startup
cd /app/backend
alembic upgrade head
MIGRATION_EXIT_CODE=$?

# Exit if migration fails (new in v1.0.16)
if [ $MIGRATION_EXIT_CODE -ne 0 ]; then
    exit 1
fi
```

## Known Issues

None at this time.

## Previous Releases

- **v1.0.15**: SOC1 framework support, legacy code cleanup (deployment broken)
- **v1.0.14**: Certificate fixes, health checks
- **v1.0.11-v1.0.13**: Initial SOC1 implementation

## Support

If you encounter issues:

1. Check logs: `docker compose logs backend frontend postgres`
2. Verify migration: `docker compose exec backend sh -c 'cd /app/backend && alembic current'`
3. Run `.\test_deployment.ps1` for automated diagnostics
4. Review `TROUBLESHOOTING.md` (if available)

## Files Included in Distribution

- `SOCAnalyzer-Docker-v1.0.16.zip` (336.43 MB)
  - `socanalyzer-backend.tar` (190.78 MB)
  - `socanalyzer-frontend.tar` (24.39 MB)
  - `postgres.tar` (104.11 MB)
  - `redis.tar` (16.47 MB)
  - `dnsmasq.tar` (2.85 MB)
  - `docker-compose.yml` (production config)
  - `IMPORT.ps1` (import script)
  - `BACKUP.ps1` (backup script)
  - `RESTORE.ps1` (restore script)
  - `test_deployment.ps1` (diagnostic script)
  - `QUICKFIX_MISSING_COLUMNS.ps1` (v1.0.15 hotfix)
  - Supporting files (certs, DNS config, env template)
