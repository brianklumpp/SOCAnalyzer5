#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Sync DEV database to PROD server
.DESCRIPTION
    Backs up the DEV database and restores it to PROD server (10.74.214.9)
    This will overwrite all data in PROD with DEV data.
#>

$ErrorActionPreference = "Stop"

# Configuration
$DEV_BACKUP_FILE = "dev_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').sql"
$PROD_SERVER = "10.74.214.9"
$PROD_PATH = "C:\Apps\SOCAnalyzer"

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Database Sync: DEV → PROD" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Backup DEV database
Write-Host "[1/5] Backing up DEV database..." -ForegroundColor Yellow
docker exec socanalyzer-postgres pg_dump -U soc2_analyzer -d soc2analyzer --clean --if-exists > $DEV_BACKUP_FILE
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to backup DEV database" -ForegroundColor Red
    exit 1
}
Write-Host "✅ DEV backup created: $DEV_BACKUP_FILE" -ForegroundColor Green
Write-Host ""

# Step 2: Copy backup to PROD server
Write-Host "[2/5] Copying backup to PROD server..." -ForegroundColor Yellow
Copy-Item $DEV_BACKUP_FILE "\\$PROD_SERVER\c$\Apps\SOCAnalyzer\$DEV_BACKUP_FILE"
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to copy backup to PROD" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Backup copied to PROD" -ForegroundColor Green
Write-Host ""

# Step 3: Stop PROD backend (to close DB connections)
Write-Host "[3/5] Stopping PROD backend..." -ForegroundColor Yellow
Invoke-Command -ComputerName $PROD_SERVER -ScriptBlock {
    cd C:\Apps\SOCAnalyzer
    docker-compose -f docker-compose.prod.yml stop backend
}
Write-Host "✅ PROD backend stopped" -ForegroundColor Green
Write-Host ""

# Step 4: Restore backup to PROD database
Write-Host "[4/5] Restoring backup to PROD database..." -ForegroundColor Yellow
Invoke-Command -ComputerName $PROD_SERVER -ScriptBlock {
    param($BackupFile)
    cd C:\Apps\SOCAnalyzer
    Get-Content $BackupFile | docker exec -i socanalyzer-postgres psql -U soc2_analyzer -d soc2analyzer
} -ArgumentList $DEV_BACKUP_FILE
Write-Host "✅ Database restored to PROD" -ForegroundColor Green
Write-Host ""

# Step 5: Start PROD backend
Write-Host "[5/5] Starting PROD backend..." -ForegroundColor Yellow
Invoke-Command -ComputerName $PROD_SERVER -ScriptBlock {
    cd C:\Apps\SOCAnalyzer
    docker-compose -f docker-compose.prod.yml start backend
}
Write-Host "✅ PROD backend started" -ForegroundColor Green
Write-Host ""

# Cleanup
Write-Host "Cleaning up backup file..." -ForegroundColor Yellow
Remove-Item $DEV_BACKUP_FILE
Invoke-Command -ComputerName $PROD_SERVER -ScriptBlock {
    param($BackupFile)
    Remove-Item "C:\Apps\SOCAnalyzer\$BackupFile"
} -ArgumentList $DEV_BACKUP_FILE
Write-Host "✅ Cleanup complete" -ForegroundColor Green
Write-Host ""

Write-Host "=====================================" -ForegroundColor Green
Write-Host "✅ Database sync complete!" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green
Write-Host ""
Write-Host "PROD database now matches DEV schema and data." -ForegroundColor Cyan
