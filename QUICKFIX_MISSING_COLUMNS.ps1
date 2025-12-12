#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Quick fix for missing database columns in v1.0.15
.DESCRIPTION
    If you're seeing "column scan.company does not exist" errors,
    run this script ONCE to add the missing columns manually.
    
    This is a temporary fix until you upgrade to v1.0.16.
#>

$ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Quick Fix: Add Missing Columns" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "This script adds missing database columns for v1.0.15." -ForegroundColor Yellow
Write-Host "Only run this if you see 'column scan.company does not exist' errors.`n" -ForegroundColor Yellow

$confirm = Read-Host "Continue? (y/n)"
if ($confirm -ne 'y') {
    Write-Host "`nCancelled." -ForegroundColor Red
    exit 0
}

Write-Host "`n[1/2] Adding missing scan.company column..." -ForegroundColor Cyan
docker compose exec postgres psql -U soc2_analyzer -d soc2analyzer -c "ALTER TABLE scan ADD COLUMN IF NOT EXISTS company VARCHAR(256);"

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to add column!" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Column added`n" -ForegroundColor Green

Write-Host "[2/2] Restarting backend..." -ForegroundColor Cyan
docker compose restart backend

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to restart backend!" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Backend restarted`n" -ForegroundColor Green

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Fix Complete!" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "The application should now work correctly." -ForegroundColor Green
Write-Host "This is a temporary fix - please upgrade to v1.0.16 when available.`n" -ForegroundColor Yellow
