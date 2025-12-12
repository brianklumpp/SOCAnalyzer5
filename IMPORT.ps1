#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Import and start SOCAnalyzer from pre-built Docker images
.DESCRIPTION
    This script loads pre-built Docker images and starts all services.
    No building required - everything is ready to run!
#>

$ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   SOCAnalyzer Quick Start" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check if Docker is running
Write-Host "[1/8] Checking Docker..." -ForegroundColor Cyan
try {
    docker version | Out-Null
    Write-Host "[OK] Docker is running`n" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker is not running!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again.`n" -ForegroundColor Yellow
    exit 1
}

# Check for required files
Write-Host "[2/8] Checking files..." -ForegroundColor Cyan
$requiredFiles = @(
    "postgres.tar",
    "redis.tar",
    "dnsmasq.tar",
    "socanalyzer-backend.tar",
    "socanalyzer-frontend.tar",
    "docker-compose.yml"
)

foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
        Write-Host "[ERROR] Missing file: $file" -ForegroundColor Red
        Write-Host "Please ensure all files were extracted from the ZIP.`n" -ForegroundColor Yellow
        exit 1
    }
}
Write-Host "[OK] All required files found`n" -ForegroundColor Green

# Load postgres image
Write-Host "[3/8] Loading postgres image..." -ForegroundColor Cyan
Write-Host "  This may take 1-2 minutes..." -ForegroundColor Gray
docker load -i postgres.tar
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to load postgres image!" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Postgres image loaded`n" -ForegroundColor Green

# Load redis image
Write-Host "[4/8] Loading redis image..." -ForegroundColor Cyan
docker load -i redis.tar
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to load redis image!" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Redis image loaded`n" -ForegroundColor Green

# Load dnsmasq image
Write-Host "[5/8] Loading dnsmasq image..." -ForegroundColor Cyan
docker load -i dnsmasq.tar
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to load dnsmasq image!" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] DNS cache image loaded`n" -ForegroundColor Green

# Load backend image
Write-Host "[6/8] Loading backend image..." -ForegroundColor Cyan
Write-Host "  This may take 2-3 minutes..." -ForegroundColor Gray
docker load -i socanalyzer-backend.tar
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to load backend image!" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Backend image loaded`n" -ForegroundColor Green

# Load frontend image
Write-Host "[7/8] Loading frontend image..." -ForegroundColor Cyan
docker load -i socanalyzer-frontend.tar
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to load frontend image!" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Frontend image loaded`n" -ForegroundColor Green

# Configure environment
Write-Host "[8/8] Starting services..." -ForegroundColor Cyan

# Create .env if it doesn't exist
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.dist") {
        Copy-Item ".env.dist" ".env"
        Write-Host "  Created .env from template" -ForegroundColor Gray
    } else {
        Write-Host "  [WARN] No .env file found, using defaults" -ForegroundColor Yellow
    }
}

# Create data directories
$dataDirs = @("data\json", "data\logs", "data\output", "data\tmp")
foreach ($dir in $dataDirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

# Start services
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to start services!" -ForegroundColor Red
    Write-Host "`nTry running: docker compose logs" -ForegroundColor Yellow
    exit 1
}

# Wait for services to be healthy
Write-Host "  Waiting for services to start..." -ForegroundColor Gray
Start-Sleep -Seconds 10

# Check service status
$services = docker compose ps --format json | ConvertFrom-Json
$allRunning = $true
foreach ($service in $services) {
    if ($service.State -ne "running") {
        $allRunning = $false
        Write-Host "  [WARN] $($service.Service) is $($service.State)" -ForegroundColor Yellow
    }
}

if ($allRunning) {
    Write-Host "[OK] All services started successfully`n" -ForegroundColor Green
} else {
    Write-Host "[WARN] Some services may not be ready yet`n" -ForegroundColor Yellow
}

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   SOCAnalyzer is Ready!" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Access the application at:" -ForegroundColor Green
Write-Host "  http://localhost`n" -ForegroundColor White

Write-Host "Useful commands:" -ForegroundColor Yellow
Write-Host "  Check status:  docker compose ps" -ForegroundColor White
Write-Host "  View logs:     docker compose logs -f" -ForegroundColor White
Write-Host "  Stop:          docker compose down" -ForegroundColor White
Write-Host "  Restart:       docker compose restart`n" -ForegroundColor White

Write-Host "If you see any errors, run:" -ForegroundColor Cyan
Write-Host "  docker compose logs backend" -ForegroundColor White
Write-Host "  docker compose logs frontend`n" -ForegroundColor White

Write-Host "Opening browser..." -ForegroundColor Gray
Start-Sleep -Seconds 2
Start-Process "http://localhost"
