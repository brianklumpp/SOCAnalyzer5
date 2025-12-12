# SOCAnalyzer Distribution - Quick Reference

## For You (Brian)

### Testing Locally
```powershell
.\test_manager.ps1
```

### Building New Version
```powershell
.\build_distribution.ps1
```

### Manual Build (skip prompts)
```powershell
.\build_distribution.ps1 -Version "1.0.1" `
    -TesterEmails "user1@example.com","user2@example.com","user3@example.com"
```

### Build Without Upload
```powershell
.\build_distribution.ps1 -SkipUpload
```

### Build Without Recompiling Exe
```powershell
.\build_distribution.ps1 -SkipBuild
```

## Files You Created

| File | Purpose |
|------|---------|
| `manager/socanalyzer_manager.py` | Desktop GUI application (556 lines) |
| `manager/requirements.txt` | Python dependencies for manager |
| `manager/build.spec` | PyInstaller build configuration |
| `SETUP.ps1` | Installation script for testers |
| `build_distribution.ps1` | Packaging utility with SharePoint upload |
| `VERSION.txt` | Current version number |
| `test_manager.ps1` | Test manager without building |

## SharePoint Location

**Upload URL**: https://nandps.sharepoint.com/teams/GRC/Shared Documents/8 - Tools/SOC Analyzer/

**Update check URL**: https://nandps.sharepoint.com/teams/GRC/Shared%20Documents/8%20-%20Tools/SOC%20Analyzer/VERSION.txt

## Manager Features

- ✅ Service status indicators (4 services)
- ✅ Start/Stop/Restart buttons
- ✅ Open browser button
- ✅ Check for updates (manual)
- ✅ Real-time log viewer
- ✅ Port conflict detection
- ✅ Docker availability check
- ✅ System tray support
- ✅ Reset database (Advanced menu)
- ✅ Health checks

## Error Messages for Testers

**Docker not running**:
> "Docker is not running. Please start Docker from your Windows Start menu and try again."

**Port conflict**:
> "Port conflict. Close other applications and try again or contact Brian."

## Tester Instructions

1. Download ZIP from SharePoint link in email
2. Extract to C:\SOCAnalyzer
3. Right-click SETUP.ps1 → Run with PowerShell
4. Wait 2-3 minutes for installation
5. Manager opens automatically
6. Click "Start Services"
7. Click "Open Browser"

## Distribution Contents

- SOCAnalyzerManager.exe (30-35MB)
- All source code (backend/ and frontend/)
- Docker configuration (docker-compose.yml)
- Full credentials (.env.dist - NO sanitization)
- Corporate certificates (certs/)
- DNS config (dns/)
- Excel templates (data/template/)
- Documentation (README, INSTALL, TROUBLESHOOTING)

## What Gets Uploaded to SharePoint

Per version folder (`v1.0.0/`):
- SOCAnalyzer-v1.0.0.zip
- VERSION.txt
- SHA256SUMS.txt
- CHANGELOG.txt

Parent folder:
- VERSION.txt (for update checks)

## Credentials Included (Not Sanitized)

✅ DATAIKU_DSS_API_KEY = actual key
✅ OPENAI_API_KEY = actual key  
✅ POSTGRES_PASSWORD = puntitforthewin
✅ All Dataiku model mappings
✅ All logging configurations

## Update Workflow

1. You run `build_distribution.ps1`
2. Script uploads to SharePoint
3. Script creates Outlook email draft
4. You review and send email
5. Testers click "Check for Updates" in Manager
6. They see update notification
7. They contact you or download from email
8. They extract over existing installation
9. They run SETUP.ps1 (preserves data)

## Troubleshooting

**Manager won't build**:
```powershell
cd manager
pip install -r requirements.txt
pip install pyinstaller
pyinstaller build.spec --clean
```

**SharePoint upload fails**:
- Check you're on corporate network/VPN
- Check Windows authentication is working
- Manually upload from `dist/` folder

**Email won't generate**:
- Check Outlook is installed
- Manually copy email details from script output

**Docker not detected**:
- Ensure Docker Desktop is running
- Try restarting Docker Desktop
- Check `docker version` in PowerShell

## Contact

All issues, questions, or feedback: **Brian Klumpp**
