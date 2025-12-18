#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Package and upload SOCAnalyzer deployment to SharePoint
.DESCRIPTION
    Creates a complete deployment package with Docker images, database backup,
    source code, and configuration, then uploads to SharePoint.
#>

param(
    [string]$SharePointSite = "https://nandps.sharepoint.com/teams/GRC",
    [string]$DocumentLibrary = "Shared Documents/8 - Tools/SOC Analyzer",
    [string]$Version = "1.0.13"
)

$ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   SOCAnalyzer SharePoint Deployment" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$StagingDir = ".\dist\SOCAnalyzer-SharePoint-$timestamp"

Write-Host "Version: $Version" -ForegroundColor Yellow
Write-Host "SharePoint: $SharePointSite" -ForegroundColor Yellow
Write-Host "Library: $DocumentLibrary" -ForegroundColor Yellow
Write-Host "Staging: $StagingDir`n" -ForegroundColor Yellow

# Check prerequisites
Write-Host "[1/8] Checking prerequisites..." -ForegroundColor Cyan

# Check Docker
try {
    docker version | Out-Null
    Write-Host "  ✓ Docker is running" -ForegroundColor Green
}
catch {
    Write-Host "  ✗ Docker is not running!" -ForegroundColor Red
    exit 1
}

# Check if containers are running
$postgresRunning = docker ps --filter "name=socanalyzer-postgres" --filter "status=running" --format "{{.Names}}"
if (-not $postgresRunning) {
    Write-Host "  ✗ PostgreSQL container not running!" -ForegroundColor Red
    Write-Host "    Start with: docker compose up -d" -ForegroundColor Yellow
    exit 1
}
Write-Host "  ✓ PostgreSQL is running" -ForegroundColor Green

# Check for PnP PowerShell module
if (-not (Get-Module -ListAvailable -Name "PnP.PowerShell")) {
    Write-Host "  ! PnP.PowerShell module not found" -ForegroundColor Yellow
    Write-Host "    Installing PnP.PowerShell..." -ForegroundColor Gray
    try {
        Install-Module -Name PnP.PowerShell -Scope CurrentUser -Force -AllowClobber
        Write-Host "  ✓ PnP.PowerShell installed" -ForegroundColor Green
    }
    catch {
        Write-Host "  ✗ Failed to install PnP.PowerShell" -ForegroundColor Red
        Write-Host "    Run manually: Install-Module -Name PnP.PowerShell -Scope CurrentUser" -ForegroundColor Yellow
        exit 1
    }
}
else {
    Write-Host "  ✓ PnP.PowerShell is available" -ForegroundColor Green
}

Write-Host ""

# Create staging directory
Write-Host "[2/8] Creating staging directory..." -ForegroundColor Cyan
if (Test-Path $StagingDir) {
    Remove-Item -Path $StagingDir -Recurse -Force
}
New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null

$dockerImagesDir = Join-Path $StagingDir "docker_images"
$databaseDir = Join-Path $StagingDir "database"
$sourceDir = Join-Path $StagingDir "source"
$dataDir = Join-Path $StagingDir "data"
$docsDir = Join-Path $StagingDir "docs"

New-Item -ItemType Directory -Path $dockerImagesDir -Force | Out-Null
New-Item -ItemType Directory -Path $databaseDir -Force | Out-Null
New-Item -ItemType Directory -Path $sourceDir -Force | Out-Null
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
New-Item -ItemType Directory -Path $docsDir -Force | Out-Null

Write-Host "  ✓ Staging directories created" -ForegroundColor Green
Write-Host ""

# Export Docker images
Write-Host "[3/8] Exporting Docker images..." -ForegroundColor Cyan
Write-Host "  This may take 5-10 minutes..." -ForegroundColor Gray

$images = @(
    @{Name = "socanalyzer5-frontend"; File = "frontend.tar" },
    @{Name = "socanalyzer5-backend"; File = "backend.tar" },
    @{Name = "postgres:15-alpine"; File = "postgres.tar" },
    @{Name = "redis:7-alpine"; File = "redis.tar" }
)

foreach ($img in $images) {
    Write-Host "  Exporting $($img.Name)..." -ForegroundColor Gray
    $outputPath = Join-Path $dockerImagesDir $img.File
    docker save -o $outputPath $img.Name 2>&1 | Out-Null
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ✗ Failed to export $($img.Name)" -ForegroundColor Red
        exit 1
    }
    
    $size = [math]::Round((Get-Item $outputPath).Length / 1MB, 2)
    Write-Host "    Saved: $size MB" -ForegroundColor Gray
}

Write-Host "  ✓ Docker images exported" -ForegroundColor Green
Write-Host ""

# Backup database
Write-Host "[4/8] Backing up database..." -ForegroundColor Cyan

# Get credentials from .env
$dbName = "soc2analyzer"
$dbUser = "soc2_analyzer"

if (Test-Path ".env") {
    $envContent = Get-Content ".env" -Raw
    if ($envContent -match 'POSTGRES_DB=([^\r\n]+)') {
        $dbName = $Matches[1]
    }
    if ($envContent -match 'POSTGRES_USER=([^\r\n]+)') {
        $dbUser = $Matches[1]
    }
}

Write-Host "  Database: $dbName" -ForegroundColor Gray
Write-Host "  User: $dbUser" -ForegroundColor Gray

$backupFile = Join-Path $databaseDir "soc2analyzer_backup.sql"
docker exec socanalyzer-postgres pg_dump -U $dbUser -d $dbName > $backupFile 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Database backup failed!" -ForegroundColor Red
    exit 1
}

$dbSize = [math]::Round((Get-Item $backupFile).Length / 1KB, 2)
Write-Host "  ✓ Database backed up: $dbSize KB" -ForegroundColor Green
Write-Host ""

# Copy source code
Write-Host "[5/8] Copying source code..." -ForegroundColor Cyan

$sourceFolders = @("backend", "frontend", "scripts", "docs")
foreach ($folder in $sourceFolders) {
    if (Test-Path $folder) {
        Write-Host "  Copying $folder..." -ForegroundColor Gray
        Copy-Item -Path $folder -Destination $sourceDir -Recurse -Force
    }
}

# Copy important files
Write-Host "  Copying configuration files..." -ForegroundColor Gray
$importantFiles = @(
    "docker-compose.yml",
    "docker-compose.prod.yml",
    ".env",
    "requirements.txt",
    "package.json",
    "VERSION.txt",
    "CHANGELOG.md"
)

foreach ($file in $importantFiles) {
    if (Test-Path $file) {
        Copy-Item -Path $file -Destination $sourceDir -Force
    }
}

Write-Host "  ✓ Source code copied" -ForegroundColor Green
Write-Host ""

# Copy data folder
Write-Host "[6/8] Copying data folder..." -ForegroundColor Cyan
if (Test-Path ".\data") {
    Write-Host "  Copying data folder (excluding logs)..." -ForegroundColor Gray
    
    $dataSubfolders = @("json", "template", "output")
    foreach ($subfolder in $dataSubfolders) {
        $sourcePath = ".\data\$subfolder"
        if (Test-Path $sourcePath) {
            $destPath = Join-Path $dataDir $subfolder
            Copy-Item -Path $sourcePath -Destination $destPath -Recurse -Force
        }
    }
    
    Write-Host "  ✓ Data folder copied (logs excluded)" -ForegroundColor Green
}
else {
    Write-Host "  ! No data folder found, skipping..." -ForegroundColor Yellow
}
Write-Host ""

# Create deployment documentation
Write-Host "[7/8] Creating deployment documentation..." -ForegroundColor Cyan

# Create deployment guide
$deploymentContent = "SOCAnalyzer Deployment Package`n"
$deploymentContent += "================================`n"
$deploymentContent += "Version: $Version`n"
$deploymentContent += "Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n`n"
$deploymentContent += "CONTENTS`n"
$deploymentContent += "--------`n"
$deploymentContent += "1. docker_images/     - Docker images (.tar files)`n"
$deploymentContent += "2. database/          - PostgreSQL database backup`n"
$deploymentContent += "3. source/            - Complete source code and configuration`n"
$deploymentContent += "4. data/              - Data folder with templates and outputs`n"
$deploymentContent += "5. docs/              - This deployment guide`n`n"
$deploymentContent += "DEPLOYMENT STEPS`n"
$deploymentContent += "----------------`n`n"
$deploymentContent += "1. Install Rancher Desktop`n"
$deploymentContent += "   Download from https://rancherdesktop.io/`n"
$deploymentContent += "   Enable Dockerd (moby) runtime`n`n"
$deploymentContent += "2. Create Application Folder`n"
$deploymentContent += "   New-Item -Path C:\Apps\SOCAnalyzer -ItemType Directory -Force`n`n"
$deploymentContent += "3. Download from SharePoint`n"
$deploymentContent += "   Navigate to: Shared Documents/8 - Tools/SOC Analyzer`n`n"
$deploymentContent += "4. Run Quick Start Script`n"
$deploymentContent += "   .\QUICK_START.ps1`n`n"
$deploymentContent += "SUPPORT`n"
$deploymentContent += "-------`n"
$deploymentContent += "Contact: GRC Team`n"
$deploymentContent += "SharePoint: https://nandps.sharepoint.com/teams/GRC`n"

$deploymentContent | Out-File -FilePath (Join-Path $docsDir "DEPLOYMENT_GUIDE.txt") -Encoding UTF8

# Create quick start script
$quickStartContent = "#!/usr/bin/env pwsh`n"
$quickStartContent += "`$ErrorActionPreference = 'Stop'`n`n"
$quickStartContent += "Write-Host '========================================' -ForegroundColor Cyan`n"
$quickStartContent += "Write-Host '   SOCAnalyzer Quick Deployment' -ForegroundColor Cyan`n"
$quickStartContent += "Write-Host '========================================' -ForegroundColor Cyan`n`n"
$quickStartContent += "Write-Host '[1/5] Importing Docker images...' -ForegroundColor Cyan`n"
$quickStartContent += "docker load -i docker_images/frontend.tar`n"
$quickStartContent += "docker load -i docker_images/backend.tar`n"
$quickStartContent += "docker load -i docker_images/postgres.tar`n"
$quickStartContent += "docker load -i docker_images/redis.tar`n`n"
$quickStartContent += "Write-Host '[2/5] Copying source files...' -ForegroundColor Cyan`n"
$quickStartContent += "Copy-Item -Path source\* -Destination . -Recurse -Force`n`n"
$quickStartContent += "Write-Host '[3/5] Starting PostgreSQL...' -ForegroundColor Cyan`n"
$quickStartContent += "docker compose up -d postgres`n"
$quickStartContent += "Start-Sleep -Seconds 10`n`n"
$quickStartContent += "Write-Host '[4/5] Restoring database...' -ForegroundColor Cyan`n"
$quickStartContent += "Get-Content database\soc2analyzer_backup.sql | docker exec -i socanalyzer-postgres psql -U soc2_analyzer -d soc2analyzer`n`n"
$quickStartContent += "Write-Host '[5/5] Starting all services...' -ForegroundColor Cyan`n"
$quickStartContent += "docker compose up -d`n`n"
$quickStartContent += "Write-Host 'Deployment complete!' -ForegroundColor Green`n"
$quickStartContent += "Write-Host 'Access at: http://localhost:3000' -ForegroundColor Cyan`n"

$quickStartContent | Out-File -FilePath (Join-Path $StagingDir "QUICK_START.ps1") -Encoding UTF8

# Create README
$readmeContent = "# SOCAnalyzer Deployment Package`n`n"
$readmeContent += "Version: $Version`n"
$readmeContent += "Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n`n"
$readmeContent += "## Quick Start`n`n"
$readmeContent += "1. Copy this entire folder to your Windows Server`n"
$readmeContent += "2. Run: .\QUICK_START.ps1`n"
$readmeContent += "3. Configure Windows Firewall`n"
$readmeContent += "4. Access at: http://SERVER_IP:3000`n`n"
$readmeContent += "## Documentation`n`n"
$readmeContent += "See docs/DEPLOYMENT_GUIDE.txt for detailed instructions.`n`n"
$readmeContent += "## Support`n`n"
$readmeContent += "GRC Team - https://nandps.sharepoint.com/teams/GRC`n"

$readmeContent | Out-File -FilePath (Join-Path $StagingDir "README.md") -Encoding UTF8

Write-Host "  ✓ Documentation created" -ForegroundColor Green
Write-Host ""

# Upload to SharePoint
Write-Host "[8/8] Uploading to SharePoint..." -ForegroundColor Cyan
Write-Host "  Connecting to SharePoint..." -ForegroundColor Gray

try {
    # Connect to SharePoint
    Connect-PnPOnline -Url $SharePointSite -Interactive
    
    # Create deployment folder name
    $deploymentTS = Get-Date -Format 'yyyyMMdd_HHmmss'
    $deploymentFolderName = "SOCAnalyzer_v${Version}_$deploymentTS"
    $targetPath = "$DocumentLibrary/$deploymentFolderName"
    
    Write-Host "  Creating folder: $deploymentFolderName..." -ForegroundColor Gray
    
    # Get all files to upload
    $allFiles = Get-ChildItem -Path $StagingDir -Recurse -File
    $fileCount = $allFiles.Count
    $uploaded = 0
    
    Write-Host "  Uploading $fileCount files (this may take 10-20 minutes)..." -ForegroundColor Gray
    
    foreach ($file in $allFiles) {
        $uploaded++
        $relativePath = $file.FullName.Substring($StagingDir.Length + 1)
        $targetFolder = Split-Path -Parent $relativePath
        
        if ($targetFolder) {
            $fullTargetPath = "$targetPath/$($targetFolder -replace '\\', '/')"
        }
        else {
            $fullTargetPath = $targetPath
        }
        
        # Upload file
        try {
            Add-PnPFile -Path $file.FullName -Folder $fullTargetPath -ErrorAction Stop | Out-Null
            
            if ($uploaded % 10 -eq 0 -or $uploaded -eq $fileCount) {
                Write-Progress -Activity "Uploading to SharePoint" -Status "$uploaded of $fileCount files" -PercentComplete (($uploaded / $fileCount) * 100)
            }
        }
        catch {
            Write-Host "    Warning: Failed to upload $relativePath" -ForegroundColor Yellow
        }
    }
    
    Write-Progress -Activity "Uploading to SharePoint" -Completed
    
    Write-Host "  ✓ Upload complete!" -ForegroundColor Green
    Write-Host ""
    
    Write-Host "✓ Deployment package available at SharePoint!" -ForegroundColor Green
    Write-Host "  Navigate to: Shared Documents > 8 - Tools > SOC Analyzer > $deploymentFolderName" -ForegroundColor Cyan
    
    # Disconnect
    Disconnect-PnPOnline
    
}
catch {
    Write-Host "  ✗ SharePoint upload failed!" -ForegroundColor Red
    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Package is available locally at:" -ForegroundColor Yellow
    Write-Host "  $StagingDir" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Manual upload options:" -ForegroundColor Yellow
    Write-Host "  1. Copy folder to OneDrive/SharePoint sync location" -ForegroundColor Gray
    Write-Host "  2. Use SharePoint web interface (drag and drop)" -ForegroundColor Gray
    Write-Host "  3. Check PnP.PowerShell permissions and try again" -ForegroundColor Gray
    exit 1
}

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Deployment Package Complete" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$totalSize = [math]::Round((Get-ChildItem -Path $StagingDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB, 2)

Write-Host "Package Details:" -ForegroundColor Yellow
Write-Host "  Total Size: $totalSize GB" -ForegroundColor White
Write-Host "  Files: $fileCount" -ForegroundColor White
Write-Host "  Location: SharePoint GRC Team Site" -ForegroundColor White
Write-Host "  Path: 8 - Tools > SOC Analyzer" -ForegroundColor White
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Share SharePoint link with deployment team" -ForegroundColor White
Write-Host "  2. On target server, download and run QUICK_START.ps1" -ForegroundColor White
Write-Host "  3. Configure Windows Firewall for port 3000" -ForegroundColor White
Write-Host ""

# Cleanup option
$cleanup = Read-Host "Delete local staging folder? (y/N)"
if ($cleanup -eq 'y' -or $cleanup -eq 'Y') {
    Remove-Item -Path $StagingDir -Recurse -Force
    Write-Host "✓ Staging folder cleaned up`n" -ForegroundColor Green
}
else {
    Write-Host "✓ Local copy retained at: $StagingDir`n" -ForegroundColor Gray
}
