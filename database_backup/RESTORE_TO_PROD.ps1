#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Restore database backup to PROD
.DESCRIPTION
    Run this script ON THE PROD SERVER to restore the database
#>

$ErrorActionPreference = "Stop"

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Restoring Database to PROD" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Stop backend
Write-Host "[1/3] Stopping backend..." -ForegroundColor Yellow
docker-compose -f docker-compose.prod.yml stop backend
Write-Host "✅ Backend stopped" -ForegroundColor Green
Write-Host ""

# Step 2: Restore database
Write-Host "[2/3] Restoring database..." -ForegroundColor Yellow
Get-Content database_backup\prod_sync.sql | docker exec -i socanalyzer-postgres psql -U soc2_analyzer -d soc2analyzer
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to restore database" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Database restored" -ForegroundColor Green
Write-Host ""

# Step 3: Start backend
Write-Host "[3/3] Starting backend..." -ForegroundColor Yellow
docker-compose -f docker-compose.prod.yml start backend
Write-Host "✅ Backend started" -ForegroundColor Green
Write-Host ""

Write-Host "=====================================" -ForegroundColor Green
Write-Host "✅ Database restore complete!" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green
