#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Restore SOCAnalyzer database from backup
.DESCRIPTION
    Restores the PostgreSQL database from a backup file.
    WARNING: This will overwrite the current database!
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$BackupPath
)

$ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   SOCAnalyzer Database Restore" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check if backup file exists
Write-Host "[1/5] Checking backup file..." -ForegroundColor Cyan
if (-not (Test-Path $BackupPath)) {
    Write-Host "[ERROR] Backup file not found: $BackupPath" -ForegroundColor Red
    Write-Host "`nUsage: .\RESTORE.ps1 -BackupPath `"path\to\database.sql`"`n" -ForegroundColor Yellow
    exit 1
}
$backupSize = [math]::Round((Get-Item $BackupPath).Length / 1KB, 2)
Write-Host "[OK] Backup file found: $backupSize KB`n" -ForegroundColor Green

# Check if Docker is running
Write-Host "[2/5] Checking Docker..." -ForegroundColor Cyan
try {
    docker version | Out-Null
    Write-Host "[OK] Docker is running`n" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker is not running!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again.`n" -ForegroundColor Yellow
    exit 1
}

# Check if postgres container is running
Write-Host "[3/5] Checking database..." -ForegroundColor Cyan
$postgresRunning = docker ps --filter "name=socanalyzer-postgres" --filter "status=running" --format "{{.Names}}"
if (-not $postgresRunning) {
    Write-Host "[ERROR] PostgreSQL container is not running!" -ForegroundColor Red
    Write-Host "Please start SOCAnalyzer first with: docker compose up -d`n" -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] Database is running`n" -ForegroundColor Green

# Get database credentials from .env or use defaults
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

# Confirm restoration
Write-Host "`n[4/5] Confirm restore..." -ForegroundColor Cyan
Write-Host "WARNING: This will overwrite the current database!" -ForegroundColor Yellow
Write-Host "Backup file: $BackupPath" -ForegroundColor Yellow
Write-Host "Target database: $dbName`n" -ForegroundColor Yellow

$confirmation = Read-Host "Type 'YES' to continue"
if ($confirmation -ne "YES") {
    Write-Host "`n[CANCELLED] Restore operation cancelled.`n" -ForegroundColor Yellow
    exit 0
}

# Restore database
Write-Host "`n[5/5] Restoring database..." -ForegroundColor Cyan
Write-Host "  This may take a few minutes..." -ForegroundColor Gray

# Drop and recreate database to ensure clean restore
Write-Host "  Dropping existing database..." -ForegroundColor Gray
docker exec socanalyzer-postgres psql -U $dbUser -d postgres -c "DROP DATABASE IF EXISTS $dbName;" 2>&1 | Out-Null
docker exec socanalyzer-postgres psql -U $dbUser -d postgres -c "CREATE DATABASE $dbName;" 2>&1 | Out-Null

# Restore from backup
Write-Host "  Importing backup data..." -ForegroundColor Gray
Get-Content $BackupPath | docker exec -i socanalyzer-postgres psql -U $dbUser -d $dbName 2>&1 | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Database restore failed!" -ForegroundColor Red
    Write-Host "The database may be in an inconsistent state.`n" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Database restored successfully`n" -ForegroundColor Green

# Restart backend to clear connections
Write-Host "  Restarting backend..." -ForegroundColor Gray
docker compose restart backend | Out-Null
Start-Sleep -Seconds 3

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Restore Complete!" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Database restored from:" -ForegroundColor Green
Write-Host "  $BackupPath`n" -ForegroundColor White

Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Open browser to: http://localhost" -ForegroundColor White
Write-Host "  2. Check that your scans are visible" -ForegroundColor White
Write-Host "  3. Verify data is correct`n" -ForegroundColor White
