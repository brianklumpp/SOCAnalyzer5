#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Export Docker images for distribution
.DESCRIPTION
    Builds Docker images and exports them as .tar files for distribution.
    This allows testers to import pre-built images instead of building from source.
#>

param(
    [string]$Version = "1.0.12",
    [string]$OutputDir = ".\dist\SOCAnalyzer-v$Version"
)

$ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Docker Image Export for Distribution" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Version: $Version" -ForegroundColor Yellow
Write-Host "Output: $OutputDir`n" -ForegroundColor Yellow

# Create output directory if it doesn't exist
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# Step 1: Pull public images
Write-Host "[1/9] Pulling public images..." -ForegroundColor Cyan
$publicImages = @("postgres:15-alpine", "redis:7-alpine", "strm/dnsmasq:latest")
foreach ($image in $publicImages) {
    Write-Host "  Pulling $image..." -ForegroundColor Gray
    docker pull $image | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to pull $image" -ForegroundColor Red
        exit 1
    }
}
Write-Host "[OK] Public images pulled`n" -ForegroundColor Green

# Step 2: Build custom images
Write-Host "[2/9] Building custom Docker images..." -ForegroundColor Cyan
Write-Host "  This may take 5-10 minutes..." -ForegroundColor Gray
docker compose build
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Docker build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Images built successfully`n" -ForegroundColor Green

# Step 3: Tag images with version
Write-Host "[3/9] Tagging images..." -ForegroundColor Cyan
docker tag socanalyzer5-backend:latest socanalyzer-backend:$Version
docker tag socanalyzer5-frontend:latest socanalyzer-frontend:$Version
Write-Host "[OK] Images tagged`n" -ForegroundColor Green

# Step 4: Export postgres image
Write-Host "[4/9] Exporting postgres image..." -ForegroundColor Cyan
$postgresTar = Join-Path $OutputDir "postgres.tar"
docker save postgres:15-alpine -o $postgresTar
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Postgres export failed!" -ForegroundColor Red
    exit 1
}
$postgresSize = [math]::Round((Get-Item $postgresTar).Length / 1MB, 2)
Write-Host "[OK] Postgres exported: $postgresSize MB`n" -ForegroundColor Green

# Step 5: Export redis image
Write-Host "[5/9] Exporting redis image..." -ForegroundColor Cyan
$redisTar = Join-Path $OutputDir "redis.tar"
docker save redis:7-alpine -o $redisTar
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Redis export failed!" -ForegroundColor Red
    exit 1
}
$redisSize = [math]::Round((Get-Item $redisTar).Length / 1MB, 2)
Write-Host "[OK] Redis exported: $redisSize MB`n" -ForegroundColor Green

# Step 6: Export dnsmasq image
Write-Host "[6/9] Exporting dnsmasq image..." -ForegroundColor Cyan
$dnsTar = Join-Path $OutputDir "dnsmasq.tar"
docker save strm/dnsmasq:latest -o $dnsTar
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Dnsmasq export failed!" -ForegroundColor Red
    exit 1
}
$dnsSize = [math]::Round((Get-Item $dnsTar).Length / 1MB, 2)
Write-Host "[OK] Dnsmasq exported: $dnsSize MB`n" -ForegroundColor Green

# Step 7: Export backend image
Write-Host "[7/9] Exporting backend image..." -ForegroundColor Cyan
$backendTar = Join-Path $OutputDir "socanalyzer-backend.tar"
docker save socanalyzer-backend:$Version -o $backendTar
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Backend export failed!" -ForegroundColor Red
    exit 1
}
$backendSize = [math]::Round((Get-Item $backendTar).Length / 1MB, 2)
Write-Host "[OK] Backend exported: $backendSize MB`n" -ForegroundColor Green

# Step 8: Export frontend image
Write-Host "[8/9] Exporting frontend image..." -ForegroundColor Cyan
$frontendTar = Join-Path $OutputDir "socanalyzer-frontend.tar"
docker save socanalyzer-frontend:$Version -o $frontendTar
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Frontend export failed!" -ForegroundColor Red
    exit 1
}
$frontendSize = [math]::Round((Get-Item $frontendTar).Length / 1MB, 2)
Write-Host "[OK] Frontend exported: $frontendSize MB`n" -ForegroundColor Green

# Step 9: Copy supporting files
Write-Host "[9/9] Copying supporting files..." -ForegroundColor Cyan

# Copy production docker-compose.yml (without dev volume mounts)
Copy-Item -Path "docker-compose.prod.yml" -Destination (Join-Path $OutputDir "docker-compose.yml") -Force
Write-Host "  [OK] Copied docker-compose.yml (production)" -ForegroundColor Gray

# Copy .env.dist
if (Test-Path ".env") {
    Copy-Item -Path ".env" -Destination (Join-Path $OutputDir ".env.dist") -Force
    Write-Host "  [OK] Copied .env.dist" -ForegroundColor Gray
} else {
    Write-Host "  [WARN] .env not found, skipping" -ForegroundColor Yellow
}

# Copy VERSION.txt
Set-Content -Path (Join-Path $OutputDir "VERSION.txt") -Value $Version
Write-Host "  [OK] Created VERSION.txt" -ForegroundColor Gray

# Copy dns config
if (Test-Path "dns") {
    Copy-Item -Path "dns" -Destination $OutputDir -Recurse -Force
    Write-Host "  [OK] Copied dns config" -ForegroundColor Gray
}

# Copy certs directory with certificate bundle
$certsDir = Join-Path $OutputDir "certs"
if (-not (Test-Path $certsDir)) {
    New-Item -ItemType Directory -Path $certsDir -Force | Out-Null
}
$certFile = Join-Path $PSScriptRoot "certs\corp-ca-bundle.pem"
if (Test-Path $certFile) {
    Copy-Item $certFile $certsDir -Force
    Write-Host "  [OK] Copied certificate bundle" -ForegroundColor Gray
} else {
    Write-Host "  [OK] Created certs directory (no cert file found)" -ForegroundColor Gray
}

# Copy installation and management scripts
Copy-Item -Path "IMPORT.ps1" -Destination $OutputDir -Force
Write-Host "  [OK] Copied IMPORT.ps1" -ForegroundColor Gray

Copy-Item -Path "BACKUP.ps1" -Destination $OutputDir -Force
Write-Host "  [OK] Copied BACKUP.ps1" -ForegroundColor Gray

Copy-Item -Path "RESTORE.ps1" -Destination $OutputDir -Force
Write-Host "  [OK] Copied RESTORE.ps1" -ForegroundColor Gray

Copy-Item -Path "UPDATE.txt" -Destination $OutputDir -Force
Write-Host "  [OK] Copied UPDATE.txt" -ForegroundColor Gray

# Copy test script
Copy-Item -Path "test_deployment.ps1" -Destination $OutputDir -Force
Write-Host "  [OK] Copied test_deployment.ps1" -ForegroundColor Gray

# Create README.txt
$readmeContent = @"
SOCAnalyzer v$Version - Quick Start Guide
========================================

INSTALLATION (First Time):
1. Extract all files to C:\SOCAnalyzer (or your preferred location)
2. Right-click IMPORT.ps1 > Run with PowerShell
   OR open PowerShell and run: .\IMPORT.ps1
3. Wait 5-7 minutes for setup to complete
4. Browser will open automatically to http://localhost:3000

DAILY USE:
- Double-click SOCAnalyzerManager.exe to start/stop services
- Or use PowerShell: docker compose up -d (start) / docker compose down (stop)

FEATURES:
- Backup Database: Click backup button in manager or run .\BACKUP.ps1
- Restore Database: Click restore button in manager or run .\RESTORE.ps1
- Check for Updates: Click update button in manager (fully automated)

REQUIREMENTS:
- Docker Desktop installed and running
- Windows 10/11 with PowerShell 5.1+
- 4GB RAM minimum, 8GB recommended

TESTING YOUR DEPLOYMENT:
Run the deployment test to verify everything is working:
  .\test_deployment.ps1          # Run all health checks
  .\test_deployment.ps1 -Verbose # Detailed output

TROUBLESHOOTING:
- If services won't start: docker compose down; docker compose up -d
- Check logs: docker compose logs backend
- Verify Docker running: docker version
- Run deployment test: .\test_deployment.ps1

SUPPORT:
Contact your SOCAnalyzer administrator

"@
Set-Content -Path (Join-Path $OutputDir "README.txt") -Value $readmeContent
Write-Host "  [OK] Created README.txt" -ForegroundColor Gray

Write-Host "[OK] Supporting files copied`n" -ForegroundColor Green

Write-Host "Creating distribution ZIP..." -ForegroundColor Cyan
$zipPath = ".\dist\SOCAnalyzer-Docker-v$Version.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

# Compress the directory
Compress-Archive -Path "$OutputDir\*" -DestinationPath $zipPath -CompressionLevel Optimal -Force
$zipSize = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host "[OK] ZIP created: $zipSize MB`n" -ForegroundColor Green

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Export Complete!" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Distribution package created:" -ForegroundColor Green
Write-Host "  Location: $zipPath" -ForegroundColor White
Write-Host "  Size: $zipSize MB`n" -ForegroundColor White

Write-Host "Image sizes:" -ForegroundColor Yellow
Write-Host "  Postgres: $postgresSize MB" -ForegroundColor White
Write-Host "  Redis:    $redisSize MB" -ForegroundColor White
Write-Host "  DNS:      $dnsSize MB" -ForegroundColor White
Write-Host "  Backend:  $backendSize MB" -ForegroundColor White
Write-Host "  Frontend: $frontendSize MB" -ForegroundColor White
$totalSize = [math]::Round($postgresSize + $redisSize + $dnsSize + $backendSize + $frontendSize, 2)
Write-Host "  Total:    $totalSize MB`n" -ForegroundColor White

Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Upload $zipPath to SharePoint" -ForegroundColor White
Write-Host "  2. Send testers the download link" -ForegroundColor White
Write-Host "  3. Testers extract and run: .\IMPORT.ps1`n" -ForegroundColor White
