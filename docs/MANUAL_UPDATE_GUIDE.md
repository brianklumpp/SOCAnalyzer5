# Manual Update Guide - SOCAnalyzer v1.0.12

## Overview

SOCAnalyzer Manager now supports **three update methods** to ensure all users can update regardless of their network configuration or OneDrive sync status:

1. **Automatic Update (OneDrive Sync)** - Fastest, no authentication required
2. **Automatic Update (SharePoint Fallback)** - May require authentication
3. **Manual Update** - Always works, user selects downloaded ZIP file

## Update Methods

### Method 1: Automatic Update (OneDrive Sync)

**Requirements**: OneDrive GRC folder synced to local machine

**Path**: `%USERPROFILE%\OneDrive - NANDPS\Documents\GRC\8 - Tools\SOC Analyzer\`

**How to use**:
1. Open SOCAnalyzerManager.exe
2. Click "⬇ Check for Updates"
3. If update available, click "Update Now"
4. Manager will copy from OneDrive sync folder (instant)

**Advantages**:
- No authentication required
- Instant (local file copy, not download)
- Works offline if OneDrive synced

**Limitations**:
- Only works if you have OneDrive GRC folder syncing
- Must be on corporate network or VPN

---

### Method 2: Automatic Update (SharePoint)

**Requirements**: Network access to SharePoint, may need authentication

**URL**: SharePoint GRC folder

**How to use**:
1. Open SOCAnalyzerManager.exe
2. Click "⬇ Check for Updates"
3. If OneDrive sync not found, falls back to SharePoint
4. May prompt for authentication
5. Downloads ZIP from SharePoint

**Advantages**:
- Works without OneDrive sync
- Direct download from source

**Limitations**:
- Requires authentication
- May fail with HTTP 403 if credentials not cached
- Requires active network connection

---

### Method 3: Manual Update ⭐ NEW IN v1.0.12

**Requirements**: Downloaded ZIP file only

**How to use**:

1. **Obtain the ZIP file**:
   - Download from SharePoint manually
   - Receive via email
   - Copy from USB drive
   - Any method that gets you `SOCAnalyzer-Docker-vX.X.X.zip`

2. **Save to Downloads folder** (or anywhere accessible):
   ```
   C:\Users\<username>\Downloads\SOCAnalyzer-Docker-v1.0.12.zip
   ```

3. **Run manual update**:
   - Open SOCAnalyzerManager.exe
   - Click "📦 Manual Update" button
   - File picker opens (defaults to Downloads folder)
   - Select the downloaded ZIP file
   - Manager extracts version from filename
   - Confirm update dialog shows:
     - Filename
     - Detected version
     - Current version
     - Update steps
   - Click "Yes" to proceed

4. **Update process** (automatic):
   - ✓ Backup database
   - ✓ Stop services
   - ✓ Extract update files
   - ✓ Update VERSION.txt
   - ✓ Restart services
   - ✓ Health check backend

**Advantages**:
- ⭐ **Always works** - no network/auth required
- ⭐ **Works offline** - once ZIP downloaded
- ⭐ **Works for all users** - no OneDrive/SharePoint needed
- ⭐ **Flexible delivery** - email, USB, download, etc.

**Limitations**:
- Requires manual ZIP download first
- User must select correct file

---

## Version Detection

The manual update feature automatically extracts version numbers from ZIP filenames:

**Supported patterns**:
- `SOCAnalyzer-Docker-v1.0.12.zip` → Version: 1.0.12
- `SOCAnalyzer-v1.0.12.zip` → Version: 1.0.12
- `v1.0.12.zip` → Version: 1.0.12

**Note**: If version cannot be extracted from filename, it will be marked as "unknown" but update will still proceed.

---

## Troubleshooting

### "Failed to check for updates: HTTP 403"

**Cause**: SharePoint authentication failed, OneDrive sync folder not found

**Solution**: Use Method 3 (Manual Update)
1. Download ZIP manually from SharePoint via browser
2. Use "📦 Manual Update" button
3. Select downloaded ZIP file

### "Invalid File" Error

**Cause**: Selected file is not a valid SOCAnalyzer ZIP

**Solution**: Ensure filename contains version number (e.g., `v1.0.12`)

### Update Fails During Extraction

**Cause**: ZIP file corrupted or incomplete

**Solution**: 
1. Download ZIP again
2. Verify file size (should be ~367 MB)
3. Try manual update again

### Services Don't Restart

**Cause**: Docker not running or port conflicts

**Solution**:
1. Check Docker Desktop is running
2. Check logs in manager
3. Use "🔄 Restart All" button
4. Check port conflicts (5432, 6379, 8000, 3000)

---

## For Beta Testers

**Recommended approach**:

1. **First, try automatic update**:
   ```
   Click "⬇ Check for Updates"
   ```
   - If you have OneDrive sync → Works instantly
   - If SharePoint auth works → Downloads update

2. **If automatic fails**:
   ```
   Use "📦 Manual Update"
   ```
   - Download ZIP from provided link/email
   - Click "📦 Manual Update"
   - Select downloaded ZIP
   - Confirm and wait

3. **Report issues**:
   - Which method worked for you?
   - Any errors encountered?
   - How long did update take?

---

## Technical Details

### Update Process (All Methods)

1. **Database Backup**:
   - Runs `BACKUP.ps1`
   - Creates timestamped backup in `database_backup/`
   - Includes all scan data, reports, controls

2. **Service Shutdown**:
   - Stops all Docker containers gracefully
   - `docker-compose -f docker-compose.prod.yml down`

3. **File Extraction**:
   - Extracts ZIP to temporary folder
   - Copies files (preserves `data/` directory)
   - Updates `VERSION.txt`

4. **Service Startup**:
   - Loads updated Docker images
   - Starts services: postgres → redis → backend → frontend
   - Waits for backend health check

5. **Verification**:
   - Checks backend API responds
   - Verifies services running
   - Displays success message

### Files Preserved During Update

**Not overwritten**:
- `data/` - All scan data, JSON files, logs, outputs
- `database_backup/` - Your database backups
- `certs/` - Custom certificates

**Overwritten**:
- Docker images (.tar files)
- `docker-compose.yml`
- Scripts (.ps1, .bat, .py)
- Manager executable
- Backend/frontend code

---

## FAQ

**Q: Which update method should I use?**

A: Try automatic first. If it fails, use manual update - it always works.

**Q: Is my data safe during updates?**

A: Yes. Database is backed up first, and `data/` directory is never overwritten.

**Q: Can I update while scans are running?**

A: No. Complete or pause scans first, then update.

**Q: How long does update take?**

A: 
- Automatic (OneDrive): ~3-5 minutes
- Automatic (SharePoint): ~5-10 minutes (download time)
- Manual: ~3-5 minutes (once ZIP downloaded)

**Q: What if update fails?**

A: Your data is safe (backed up). Use "🔄 Restart All" to restore services. Contact support if issues persist.

**Q: Do I need admin rights?**

A: No. Docker Desktop needs admin, but update process doesn't.

---

## Version History

### v1.0.12 - Manual Update Feature
- ✅ Added "📦 Manual Update" button
- ✅ File picker for ZIP selection
- ✅ Automatic version extraction from filename
- ✅ Works offline after ZIP download
- ✅ No authentication required

### v1.0.11 - OneDrive Priority
- ✅ OneDrive sync folder as primary source
- ✅ SharePoint as fallback
- ✅ Certificate error handling

---

## Support

**Issues**: Report to GRC team with:
- Update method attempted
- Error messages from manager logs
- Screenshot if helpful

**Logs**: Found in manager's log window during update process
