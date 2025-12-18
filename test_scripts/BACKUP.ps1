#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Backup SOCAnalyzer database
.DESCRIPTION
    Creates a timestamped backup of the PostgreSQL database.
    Run this before updating to a new version.
#>

$ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   SOCAnalyzer Database Backup" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check if Docker is running
Write-Host "[1/4] Checking Docker..." -ForegroundColor Cyan
try {
    docker version | Out-Null
    Write-Host "[OK] Docker is running`n" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker is not running!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again.`n" -ForegroundColor Yellow
    exit 1
}

# Check if postgres container is running
Write-Host "[2/4] Checking database..." -ForegroundColor Cyan
$postgresRunning = docker ps --filter "name=socanalyzer-postgres" --filter "status=running" --format "{{.Names}}"
if (-not $postgresRunning) {
    Write-Host "[ERROR] PostgreSQL container is not running!" -ForegroundColor Red
    Write-Host "Please start SOCAnalyzer first with: docker compose up -d`n" -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] Database is running`n" -ForegroundColor Green

# Create backup directory with timestamp
Write-Host "[3/4] Creating backup..." -ForegroundColor Cyan
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = ".\backups\backup_$timestamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

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

# Export database
$backupFile = Join-Path $backupDir "database.sql"
Write-Host "  Exporting to: $backupFile" -ForegroundColor Gray

docker exec socanalyzer-postgres pg_dump -U $dbUser -d $dbName > $backupFile 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Database backup failed!" -ForegroundColor Red
    Write-Host "Check if the database name and user are correct.`n" -ForegroundColor Yellow
    exit 1
}

$backupSize = [math]::Round((Get-Item $backupFile).Length / 1KB, 2)
Write-Host "[OK] Database exported: $backupSize KB`n" -ForegroundColor Green

# Create backup info file
Write-Host "[4/4] Creating backup info..." -ForegroundColor Cyan
$infoFile = Join-Path $backupDir "backup_info.txt"
$info = @"
SOCAnalyzer Database Backup
===========================

Backup Date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Database: $dbName
User: $dbUser
Size: $backupSize KB

To restore this backup:
  .\RESTORE.ps1 -BackupPath "$backupFile"

Or manually:
  docker exec -i socanalyzer-postgres psql -U $dbUser -d $dbName < "$backupFile"
"@

Set-Content -Path $infoFile -Value $info
Write-Host "[OK] Backup info saved`n" -ForegroundColor Green

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Backup Complete!" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Backup location:" -ForegroundColor Green
Write-Host "  $backupDir`n" -ForegroundColor White

Write-Host "Files created:" -ForegroundColor Yellow
Write-Host "  database.sql     ($backupSize KB)" -ForegroundColor White
Write-Host "  backup_info.txt`n" -ForegroundColor White

Write-Host "To restore this backup:" -ForegroundColor Cyan
Write-Host "  .\RESTORE.ps1 -BackupPath `"$backupFile`"`n" -ForegroundColor White

Write-Host "Safe to proceed with update!`n" -ForegroundColor Green
