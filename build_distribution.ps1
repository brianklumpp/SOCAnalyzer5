# SOCAnalyzer Distribution Builder
# Automates the creation of distribution packages and uploads to SharePoint

param(
    [string]$Version,
    [string[]]$TesterEmails,
    [switch]$SkipBuild,
    [switch]$SkipUpload
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   SOCAnalyzer Distribution Builder" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory
$ScriptRoot = $PSScriptRoot
if (-not $ScriptRoot) {
    $ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

# Prompt for version if not provided
if (-not $Version) {
    $currentVersion = "1.0.0"
    $versionFile = Join-Path $ScriptRoot "VERSION.txt"
    if (Test-Path $versionFile) {
        $currentVersion = (Get-Content $versionFile).Trim()
    }
    
    Write-Host "Current version: $currentVersion" -ForegroundColor Yellow
    $Version = Read-Host "Enter new version number"
    
    if (-not $Version) {
        Write-Host "[ERROR] Version required" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Building version: $Version" -ForegroundColor Green
Write-Host ""

# Prompt for changelog
Write-Host "Enter changelog notes (press Enter twice when done):" -ForegroundColor Yellow
$changelogLines = @()
while ($true) {
    $line = Read-Host
    if ([string]::IsNullOrWhiteSpace($line) -and $changelogLines.Count -gt 0) {
        break
    }
    if (-not [string]::IsNullOrWhiteSpace($line)) {
        $changelogLines += $line
    }
}

$changelog = $changelogLines -join "`n"
Write-Host ""

# Prompt for tester emails if not provided
if (-not $TesterEmails -or $TesterEmails.Count -eq 0) {
    Write-Host "Enter tester email addresses (comma-separated):" -ForegroundColor Yellow
    $emailInput = Read-Host
    if ($emailInput) {
        $TesterEmails = $emailInput -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Build Configuration:" -ForegroundColor Cyan
Write-Host "  Version: $Version" -ForegroundColor White
Write-Host "  Changelog entries: $($changelogLines.Count)" -ForegroundColor White
Write-Host "  Tester emails: $($TesterEmails.Count)" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$confirm = Read-Host "Proceed with build? (y/n)"
if ($confirm -ne 'y') {
    Write-Host "Build cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host ""

# Update VERSION.txt
Write-Host "[1/9] Updating VERSION.txt..." -ForegroundColor Yellow
$Version | Out-File -FilePath (Join-Path $ScriptRoot "VERSION.txt") -Encoding utf8 -NoNewline
Write-Host "[OK] Version updated to $Version" -ForegroundColor Green

# Build manager executable
if (-not $SkipBuild) {
    Write-Host "[2/9] Building SOCAnalyzerManager.exe..." -ForegroundColor Yellow
    
    Push-Location (Join-Path $ScriptRoot "manager")
    try {
        # Check if PyInstaller is available
        $pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
        if (-not $pyinstaller) {
            Write-Host "  Installing PyInstaller..." -ForegroundColor Gray
            python -m pip install pyinstaller 2>&1 | Out-Null
        }
        
        # Build executable
        Write-Host "  Running PyInstaller (this may take a few minutes)..." -ForegroundColor Gray
        $ErrorActionPreference = 'Continue'
        python -m PyInstaller build.spec --clean --noconfirm | Out-Null
        $ErrorActionPreference = 'Stop'
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Manager executable built successfully" -ForegroundColor Green
        } else {
            Write-Host "[ERROR] Build failed with exit code $LASTEXITCODE" -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[2/9] Skipping build (using existing executable)..." -ForegroundColor Yellow
}

# Copy .env to .env.dist
Write-Host "[3/9] Creating .env.dist..." -ForegroundColor Yellow
$envSource = Join-Path $ScriptRoot ".env"
$envDist = Join-Path $ScriptRoot ".env.dist"

if (Test-Path $envSource) {
    Copy-Item $envSource $envDist -Force
    Write-Host "[OK] .env.dist created with current credentials" -ForegroundColor Green
} else {
    Write-Host "[WARN] .env not found, .env.dist not created" -ForegroundColor Yellow
}

# Build and export Docker images
Write-Host "[4/9] Building and exporting Docker images..." -ForegroundColor Yellow
Write-Host "  This may take 5-10 minutes..." -ForegroundColor Gray

# Create distribution directory first
$distRoot = Join-Path $ScriptRoot "dist"
$distFolder = Join-Path $distRoot "SOCAnalyzer-v$Version"

if (Test-Path $distFolder) {
    Write-Host "  Removing existing distribution folder..." -ForegroundColor Gray
    Remove-Item $distFolder -Recurse -Force
}

New-Item -ItemType Directory -Path $distFolder -Force | Out-Null

# Run Docker image export
& (Join-Path $ScriptRoot "export_docker_images.ps1") -Version $Version -OutputDir $distFolder
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Docker image export failed!" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Docker images exported" -ForegroundColor Green

# Copy manager executable and essential files
Write-Host "[5/9] Copying essential files..." -ForegroundColor Yellow

$managerExe = Join-Path $ScriptRoot "manager\dist\SOCAnalyzerManager.exe"
if (Test-Path $managerExe) {
    Copy-Item $managerExe $distFolder
    Write-Host "  [OK] Copied SOCAnalyzerManager.exe" -ForegroundColor Gray
} else {
    Write-Host "  [WARN] Manager executable not found" -ForegroundColor Yellow
}

# Copy essential files
$filesToCopy = @(
    "SETUP.ps1",
    "IMPORT.ps1",
    ".env.dist",
    "docker-compose.prod.yml",
    "VERSION.txt"
)

foreach ($file in $filesToCopy) {
    $source = Join-Path $ScriptRoot $file
    if (Test-Path $source) {
        Copy-Item $source $distFolder
        Write-Host "  [OK] Copied $file" -ForegroundColor Gray
    }
}

# Copy directories (ONLY runtime config, not source code)
$dirsToCopy = @(
    @{Name="certs"; Exclude=@()},
    @{Name="dns"; Exclude=@()},
    @{Name="data\template"; Exclude=@()}
)

foreach ($dirInfo in $dirsToCopy) {
    $source = Join-Path $ScriptRoot $dirInfo.Name
    $dest = Join-Path $distFolder $dirInfo.Name
    
    if (Test-Path $source) {
        Write-Host "  Copying $($dirInfo.Name)..." -ForegroundColor Gray
        
        # Use robocopy for efficient copying with exclusions
        $excludeDirs = $dirInfo.Exclude | Where-Object { -not $_.Contains("*") }
        $excludeFiles = $dirInfo.Exclude | Where-Object { $_.Contains("*") }
        
        $robocopyArgs = @($source, $dest, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns", "/np")
        
        if ($excludeDirs.Count -gt 0) {
            $robocopyArgs += "/XD"
            $robocopyArgs += $excludeDirs
        }
        
        if ($excludeFiles.Count -gt 0) {
            $robocopyArgs += "/XF"
            $robocopyArgs += $excludeFiles
        }
        
        robocopy @robocopyArgs | Out-Null
        Write-Host "  [OK] Copied $($dirInfo.Name)" -ForegroundColor Gray
    }
}

Write-Host "[OK] Essential files copied" -ForegroundColor Green

# Create documentation files
Write-Host "[6/9] Creating documentation..." -ForegroundColor Yellow

$readmeText = "SOCAnalyzer - Quick Start Guide`n" +
"================================`n`n" +
"Installation Instructions:`n`n" +
"1. Extract this folder to C:\SOCAnalyzer (or any location)`n`n" +
"2. Right-click SETUP.ps1 and select 'Run with PowerShell'`n" +
"   (You may need to allow the script to run)`n`n" +
"3. Wait for Docker containers to start (2-3 minutes)`n`n" +
"4. The SOCAnalyzer Manager window will open automatically`n`n" +
"5. Click 'Start Services' if not already running`n`n" +
"6. Click 'Open Browser' to access the web interface`n`n" +
"Troubleshooting:`n" +
"- If Docker is not running, start Docker Desktop from Windows Start menu`n" +
"- If ports are in use, close other applications or contact Brian`n" +
"- For other issues, contact Brian Klumpp`n`n" +
"Access URLs:`n" +
"- Frontend: http://localhost:3000`n" +
"- Backend API: http://localhost:8000`n`n" +
"Version: $Version"

$readmeText | Out-File -FilePath (Join-Path $distFolder "README.txt") -Encoding utf8
Write-Host "[OK] README.txt created" -ForegroundColor Green

# Create INSTALL.txt
$installText = "SOCAnalyzer Installation Guide`n" +
"==============================`n`n" +
"Prerequisites:`n" +
"1. Windows 10/11`n" +
"2. Docker Desktop installed and running`n" +
"3. 8GB RAM minimum`n" +
"4. 20GB free disk space`n`n" +
"Installation Steps:`n`n" +
"Step 1: Extract Files`n" +
"- Extract SOCAnalyzer-v$Version.zip to C:\SOCAnalyzer`n`n" +
"Step 2: Unblock the Script (IMPORTANT)`n" +
"- Right-click SETUP.ps1`n" +
"- Select 'Properties'`n" +
"- Check 'Unblock' at the bottom (if present)`n" +
"- Click 'OK'`n`n" +
"Step 3: Run Setup`n" +
"- Right-click SETUP.ps1`n" +
"- Select 'Run with PowerShell'`n" +
"- If you see a security warning, click 'Run anyway'`n`n" +
"Step 3: Wait for Installation`n" +
"- Setup will download Docker images (2-3 minutes)`n" +
"- Services will start automatically`n" +
"- Manager window will open`n`n" +
"Step 4: Verify Installation`n" +
"- All 4 service indicators should be green`n" +
"- Click 'Open Browser'`n" +
"- You should see the SOCAnalyzer web interface`n`n" +
"Step 5: Start Using`n" +
"- Upload a SOC report PDF`n" +
"- Click 'Start Analysis'`n" +
"- View results when complete`n`n" +
"Need Help?`n" +
"Contact: Brian Klumpp"

$installText | Out-File -FilePath (Join-Path $distFolder "INSTALL.txt") -Encoding utf8

# Create TROUBLESHOOTING.txt
$troubleshootText = "SOCAnalyzer Troubleshooting Guide`n" +
"==================================`n`n" +
"Issue: 'Cannot run scripts' or 'Execution policy' error`n" +
"Solution:`n" +
"1. Right-click SETUP.ps1 and select 'Properties'`n" +
"2. At the bottom, check 'Unblock' if present`n" +
"3. Click 'OK'`n" +
"4. Try running the script again by right-clicking > 'Run with PowerShell'`n`n" +
"Alternative: Open PowerShell and run:`n" +
"  PowerShell -ExecutionPolicy Bypass -File .\SETUP.ps1`n`n" +
"Issue: 'Docker is not running'`n" +
"Solution:`n" +
"1. Open Windows Start menu`n" +
"2. Search for 'Docker Desktop'`n" +
"3. Click to launch Docker Desktop`n" +
"4. Wait for Docker to fully start`n" +
"5. Try starting SOCAnalyzer again`n`n" +
"Issue: 'Port conflict'`n" +
"Solution:`n" +
"1. Open Command Prompt or PowerShell`n" +
"2. Run: netstat -ano | findstr ':3000'`n" +
"3. Run: netstat -ano | findstr ':8000'`n" +
"4. Close any applications using those ports`n" +
"5. Try again or contact Brian`n`n" +
"Issue: Services won't start`n" +
"Solution:`n" +
"1. Click 'Stop Services' in Manager`n" +
"2. Wait 10 seconds`n" +
"3. Click 'Start Services'`n" +
"4. Check logs for errors`n" +
"5. If problem persists, click Advanced > Reset Database`n`n" +
"Still Need Help?`n" +
"Contact: Brian Klumpp"

$troubleshootText | Out-File -FilePath (Join-Path $distFolder "TROUBLESHOOTING.txt") -Encoding utf8
Write-Host "[OK] Documentation files created" -ForegroundColor Green

# Create CHANGELOG.txt
Write-Host "[7/9] Creating changelog..." -ForegroundColor Yellow

$changelogText = "SOCAnalyzer v$Version`n" +
"Released: $(Get-Date -Format 'yyyy-MM-dd')`n`n" +
"Changes:`n$changelog`n"

$changelogText | Out-File -FilePath (Join-Path $distFolder "CHANGELOG.txt") -Encoding utf8
Write-Host "[OK] CHANGELOG.txt created" -ForegroundColor Green

# Skip ZIP (too large for Compress-Archive)
Write-Host "[8/9] Calculating distribution size..." -ForegroundColor Yellow
$folderSize = [math]::Round((Get-ChildItem $distFolder -Recurse | Measure-Object -Property Length -Sum).Sum / 1024, 2)
Write-Host "[OK] Distribution folder: $folderSize GB" -ForegroundColor Green
Write-Host "     Share folder directly via OneDrive/SharePoint (too large to ZIP)" -ForegroundColor Gray

# Generate SHA256 checksums for Docker images
Write-Host "[9/9] Generating checksums..." -ForegroundColor Yellow

$checksumText = "SHA256 Checksums for SOCAnalyzer v$Version`n" +
"Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n`n"

# Calculate checksums for all .tar files
Get-ChildItem $distFolder -Filter "*.tar" | ForEach-Object {
    $hash = Get-FileHash -Path $_.FullName -Algorithm SHA256
    $checksumText += "$($_.Name)`n$($hash.Hash)`n`n"
}

$checksumPath = Join-Path $distFolder "SHA256SUMS.txt"
$checksumText | Out-File -FilePath $checksumPath -Encoding utf8
Write-Host "[OK] Checksums generated for Docker images" -ForegroundColor Green

# Upload to SharePoint
if (-not $SkipUpload) {
    Write-Host "[10/10] Uploading to SharePoint..." -ForegroundColor Yellow
    Write-Host "[INFO] SharePoint upload feature requires manual implementation" -ForegroundColor Yellow
    Write-Host "       Please manually upload files to SharePoint" -ForegroundColor Gray
} else {
    Write-Host "[9/9] Skipping SharePoint upload..." -ForegroundColor Yellow
}

# Generate email
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Generating notification email..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($TesterEmails -and $TesterEmails.Count -gt 0) {
    try {
        $outlook = New-Object -ComObject Outlook.Application
        $mail = $outlook.CreateItem(0)
        
        $mail.Subject = "SOCAnalyzer v$Version - New Release Available"
        $mail.To = $TesterEmails -join "; "
        
        $downloadUrl = "https://nandps.sharepoint.com/teams/GRC/Shared%20Documents/8%20-%20Tools/SOC%20Analyzer/v$Version/SOCAnalyzer-v$Version.zip"
        
        $mailBody = "<html><body style='font-family: Segoe UI, Arial, sans-serif;'>" +
        "<h2 style='color: #6f42c1;'>SOCAnalyzer v$Version Available</h2>" +
        "<p>A new version of SOCAnalyzer has been released and is ready for testing.</p>" +
        "<h3>What's New:</h3><pre style='background-color: #f5f5f5; padding: 10px;'>$changelog</pre>" +
        "<h3>Download & Installation:</h3><ol>" +
        "<li><a href='$downloadUrl'>Download SOCAnalyzer-v$Version.zip</a> ($zipSize MB)</li>" +
        "<li>Extract to C:\SOCAnalyzer</li>" +
        "<li>Right-click SETUP.ps1 and select 'Run with PowerShell'</li>" +
        "<li>Wait for services to start (2-3 minutes)</li>" +
        "<li>Click 'Open Browser' in the Manager window</li></ol>" +
        "<h3>Need Help?</h3><p>Contact Brian Klumpp for support</p>" +
        "<hr><p style='font-size: 0.9em; color: #666;'>SOCAnalyzer v$Version<br>Released: $(Get-Date -Format 'yyyy-MM-dd')</p>" +
        "</body></html>"
        
        $mail.HTMLBody = $mailBody
        $mail.Display()
        
        Write-Host "[OK] Email draft created in Outlook" -ForegroundColor Green
        Write-Host "  Review and send when ready" -ForegroundColor Gray
        
    } catch {
        Write-Host "[WARN] Could not create Outlook email: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Email details:" -ForegroundColor Gray
        Write-Host "  To: $($TesterEmails -join ', ')" -ForegroundColor White
        Write-Host "  Subject: SOCAnalyzer v$Version - New Release Available" -ForegroundColor White
        Write-Host "  Download: $downloadUrl" -ForegroundColor Cyan
    }
} else {
    Write-Host "[WARN] No tester emails provided, skipping email generation" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Distribution package created:" -ForegroundColor White
Write-Host "  $zipPath" -ForegroundColor Cyan
Write-Host "  Size: $zipSize MB" -ForegroundColor Gray
Write-Host ""
Write-Host "SharePoint location:" -ForegroundColor White
Write-Host "  https://nandps.sharepoint.com/teams/GRC/Shared Documents/8 - Tools/SOC Analyzer/v$Version/" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Review and send the Outlook email draft" -ForegroundColor Gray
Write-Host "  2. Manually upload files to SharePoint" -ForegroundColor Gray
Write-Host "  3. Test the distribution package on a clean machine" -ForegroundColor Gray
Write-Host ""
