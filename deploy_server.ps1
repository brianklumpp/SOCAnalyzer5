# SOCAnalyzer Production Server Deployment Script
param(
    [string]$GitRepo = "https://github.com/brianklumpp/SOCAnalyzer5.git",
    [string]$Branch = "refactor/v2.0.0-cleanup",
    [string]$InstallPath = "C:\Apps\SOCAnalyzer",
    [switch]$UseExistingDB
)

Clear-Host
Write-Host "SOCAnalyzer Production Deployment" -ForegroundColor Cyan
Write-Host "Repository: $GitRepo" -ForegroundColor Gray
Write-Host "Branch: $Branch" -ForegroundColor Gray
Write-Host ""

# Prerequisites
Write-Host "[1/7] Checking prerequisites..." -ForegroundColor Yellow
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "  Git not found!" -ForegroundColor Red
    exit 1
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "  Docker not found!" -ForegroundColor Red
    exit 1
}
Write-Host "   Prerequisites met" -ForegroundColor Green

# Clone or update
Write-Host "`n[2/7] Getting source code..." -ForegroundColor Yellow
if (Test-Path $InstallPath\.git) {
    Push-Location $InstallPath
    git pull origin $Branch
    Write-Host "   Repository updated" -ForegroundColor Green
}
elseif (Test-Path $InstallPath) {
    Write-Host "  Path exists but not a git repo. Remove $InstallPath first." -ForegroundColor Red
    exit 1
}
else {
    git clone -b $Branch $GitRepo $InstallPath
    Push-Location $InstallPath
    Write-Host "   Repository cloned" -ForegroundColor Green
}
# Check frontend directory (separate git repo)
Write-Host "  Checking frontend..." -ForegroundColor Gray
if (-not (Test-Path .\frontend\Dockerfile)) {
    Write-Host "  ! Frontend source code missing" -ForegroundColor Red
    Write-Host "    The frontend is a separate Git repository." -ForegroundColor Yellow
    Write-Host "    Please copy the frontend folder from your development machine or:" -ForegroundColor Yellow
    Write-Host "    1. Clone from: https://github.com/brianklumpp/SOCAnalyzer5-Frontend.git" -ForegroundColor Gray
    Write-Host "    2. Place in: $InstallPath\frontend" -ForegroundColor Gray
    Write-Host "" -ForegroundColor Yellow
    Pop-Location
    exit 1
}
else {
    Write-Host "  ✓ Frontend present" -ForegroundColor Green
}
# Configure .env
Write-Host "`n[3/7] Configuring environment..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    @"
POSTGRES_DB=soc2analyzer
POSTGRES_USER=soc2_analyzer
POSTGRES_PASSWORD=ChangeThisPassword123!
DATABASE_URL=postgresql://soc2_analyzer:ChangeThisPassword123!@postgres:5432/soc2analyzer
REDIS_URL=redis://redis:6379/0
OPENAI_API_KEY=your_openai_api_key_here
NODE_ENV=production
BACKEND_URL=http://backend:8000
FRONTEND_URL=http://localhost:3000
SECRET_KEY=change_this_secret
ALLOWED_ORIGINS=*
"@ | Out-File -FilePath ".env" -Encoding UTF8
    Write-Host "   .env created - EDIT WITH YOUR SETTINGS!" -ForegroundColor Yellow
    Read-Host "Press Enter after editing .env"
}
else {
    Write-Host "   .env exists" -ForegroundColor Green
}

# Database backup
Write-Host "`n[4/7] Database preparation..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path "database_backup" -Force -ErrorAction SilentlyContinue | Out-Null
$backups = Get-ChildItem "database_backup\*.sql" -ErrorAction SilentlyContinue
if ($backups.Count -gt 0) {
    Write-Host "   Found backup: $($backups[0].Name)" -ForegroundColor Green
}
elseif (-not $UseExistingDB) {
    Write-Host "  ! No backup found - will use fresh database" -ForegroundColor Yellow
}

# Stop services
Write-Host "`n[5/7] Stopping existing services..." -ForegroundColor Yellow
docker compose -f docker-compose.prod.yml down 2>$null
Write-Host "   Stopped" -ForegroundColor Green

# Build
Write-Host "`n[6/7] Building Docker images (5-10 minutes)..." -ForegroundColor Yellow
docker compose -f docker-compose.prod.yml build
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Build failed!" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "   Build complete" -ForegroundColor Green

# Start
Write-Host "`n[7/7] Starting services..." -ForegroundColor Yellow
docker compose -f docker-compose.prod.yml up -d postgres
Start-Sleep -Seconds 10

if ((-not $UseExistingDB) -and ($backups.Count -gt 0)) {
    Write-Host "  Restoring database..." -ForegroundColor Gray
    Get-Content $backups[0].FullName | docker exec -i socanalyzer-postgres psql -U soc2_analyzer -d soc2analyzer 2>$null
}

docker compose -f docker-compose.prod.yml up -d
Start-Sleep -Seconds 5

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Deployment Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "`nAccess at: http://localhost:3000" -ForegroundColor Cyan
Write-Host "`nUseful commands:" -ForegroundColor Yellow
Write-Host "  Logs:    docker compose -f docker-compose.prod.yml logs -f"
Write-Host "  Stop:    docker compose -f docker-compose.prod.yml down"
Write-Host "  Restart: docker compose -f docker-compose.prod.yml restart"
Write-Host ""

Pop-Location
