# Manager Update Fix - HTTP 403 Resolution

## Problem
Manager update check was failing with **HTTP 403 Forbidden** when trying to access SharePoint URLs.

## Root Cause
SharePoint requires authentication. The manager was trying to access:
- `https://nandps.sharepoint.com/.../VERSION.txt`
- `https://nandps.sharepoint.com/.../SOCAnalyzer-Docker-v{version}.zip`

Without credentials, SharePoint returns HTTP 403.

## Solution Implemented

### Primary Method: OneDrive Sync Folder
Manager now checks OneDrive sync folder **first**:

```
%USERPROFILE%\OneDrive - NANDPS\Documents\GRC\8 - Tools\SOC Analyzer\
```

**Benefits**:
- ✅ No authentication needed (already signed into OneDrive)
- ✅ Instant access (files are local)
- ✅ Instant copy (no download time)
- ✅ Works offline if files are synced

### Fallback Method: SharePoint URL
If OneDrive folder not found, falls back to SharePoint URL (still returns 403 for now).

## Code Changes

### Version Check (_check_updates)
```python
# Try OneDrive sync folder first
onedrive_path = Path.home() / "OneDrive - NANDPS" / "Documents" / "GRC" / "8 - Tools" / "SOC Analyzer" / "VERSION.txt"
if onedrive_path.exists():
    remote_version = onedrive_path.read_text().strip()
else:
    # Fallback to SharePoint URL
    response = requests.get(self.SHAREPOINT_VERSION_URL, timeout=10)
```

### Download Update (_perform_update)
```python
# Try to copy from OneDrive first
onedrive_source = Path.home() / "OneDrive - NANDPS" / "Documents" / "GRC" / "8 - Tools" / "SOC Analyzer" / f"v{new_version}" / f"SOCAnalyzer-Docker-v{new_version}.zip"

if onedrive_source.exists():
    shutil.copy2(onedrive_source, zip_path)
else:
    # Fallback to download from SharePoint
    urllib.request.urlopen(download_url, timeout=300)
```

## For Testers

### Requirements
Your OneDrive must be syncing the GRC folder:
```
OneDrive - NANDPS\Documents\GRC\8 - Tools\SOC Analyzer\
```

### Expected Structure
```
OneDrive - NANDPS\
└── Documents\
    └── GRC\
        └── 8 - Tools\
            └── SOC Analyzer\
                ├── VERSION.txt (contains "1.0.12")
                └── v1.0.12\
                    └── SOCAnalyzer-Docker-v1.0.12.zip
```

### Testing Update Check
1. Open SOCAnalyzerManager.exe
2. Click "Check for Updates"
3. Should now show:
   - "Using OneDrive sync folder..." (if OneDrive is syncing)
   - OR "OneDrive sync not found, trying SharePoint..." (if not syncing)

### If OneDrive Not Syncing
Manager will still attempt SharePoint but get 403. Options:
1. **Sync OneDrive GRC folder** (recommended)
2. **Wait for SharePoint anonymous links** (future enhancement)
3. **Manual update** (download and extract manually)

## For Deployment

### Uploading New Versions
When uploading to SharePoint:
1. Upload ZIP to: `8 - Tools/SOC Analyzer/v{version}/`
2. Update VERSION.txt to: `{version}`
3. Wait for OneDrive sync to complete (~5 min)
4. Users with OneDrive sync will get updates automatically

### SharePoint Folder Structure
```
8 - Tools/
└── SOC Analyzer/
    ├── VERSION.txt (current version)
    ├── v1.0.10/
    │   └── SOCAnalyzer-Docker-v1.0.10.zip
    ├── v1.0.11/
    │   └── SOCAnalyzer-Docker-v1.0.11.zip
    └── v1.0.12/
        └── SOCAnalyzer-Docker-v1.0.12.zip
```

## Future Enhancements

### Option 1: SharePoint Anonymous Links
Create public sharing links that don't require authentication:
```python
SHAREPOINT_VERSION_URL = "https://nandps.sharepoint.com/:t:/r/teams/GRC/Shared%20Documents/..."
# Requires: Right-click file > Share > Copy link (with "Anyone with the link" permission)
```

### Option 2: Alternative Hosting
Host files on:
- Internal web server (IIS)
- Azure Blob Storage
- GitHub Releases (if repository is accessible)

### Option 3: Windows Authentication
Add NTLM auth support:
```python
from requests_ntlm import HttpNtlmAuth
response = requests.get(url, auth=HttpNtlmAuth(username, password))
```

## Current Status

**v1.0.12** includes the OneDrive sync fix:
- ✅ Manager checks OneDrive first
- ✅ Falls back to SharePoint (403 for now)
- ✅ Better error messages
- ✅ Works for users with OneDrive sync enabled

**Distribution**: Ready with updated manager in `SOCAnalyzer-Docker-v1.0.12.zip`

## Testing Results

### With OneDrive Sync:
```
Checking for updates...
Using OneDrive sync folder...
Remote version: 1.0.12
Local version: 1.0.12
✓ You have the latest version
```

### Without OneDrive Sync:
```
Checking for updates...
OneDrive sync not found, trying SharePoint...
✗ Failed to check updates: HTTP 403
```

Users should enable OneDrive sync for the GRC folder for automatic updates to work.
