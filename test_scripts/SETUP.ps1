# SOCAnalyzer Installation Script
# Automatically sets up SOCAnalyzer for first-time use

param(
    [switch]$SkipDockerCheck
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   SOCAnalyzer Installation Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory
$ScriptRoot = $PSScriptRoot
if (-not $ScriptRoot) {
    $ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

# Check Docker Desktop
if (-not $SkipDockerCheck) {
    Write-Host "[1/7] Checking Docker Desktop..." -ForegroundColor Yellow
    
    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCmd) {
        Write-Host "[X] Docker not found." -ForegroundColor Red
        Write-Host ""
        Write-Host "Docker Desktop is required to run SOCAnalyzer." -ForegroundColor Red
        Write-Host "Please install Docker Desktop from:" -ForegroundColor Yellow
        Write-Host "  https://www.docker.com/products/docker-desktop" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "After installing, restart this script." -ForegroundColor Yellow
        exit 1
    }
    
    try {
        $null = docker version --format '{{.Server.Version}}' 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Docker Desktop is running" -ForegroundColor Green
        } else {
            throw "Docker not running"
        }
    } catch {
        Write-Host "[X] Docker Desktop is not running." -ForegroundColor Red
        Write-Host ""
        Write-Host "Please start Docker Desktop from your Windows Start menu and try again." -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "[1/7] Skipping Docker check..." -ForegroundColor Yellow
}

# Copy .env.dist to .env
Write-Host "[2/7] Setting up environment configuration..." -ForegroundColor Yellow

$envDist = Join-Path $ScriptRoot ".env.dist"
$envFile = Join-Path $ScriptRoot ".env"

if (Test-Path $envDist) {
    if (Test-Path $envFile) {
        Write-Host "  .env already exists, skipping..." -ForegroundColor Gray
    } else {
        Copy-Item $envDist $envFile
        Write-Host "[OK] Created .env from .env.dist" -ForegroundColor Green
    }
} else {
    Write-Host "[WARN] .env.dist not found, skipping..." -ForegroundColor Yellow
}

# Validate certificate bundle
Write-Host "[3/7] Checking certificate bundle..." -ForegroundColor Yellow

$certPath = Join-Path $ScriptRoot "certs\corp-ca-bundle.pem"
if (Test-Path $certPath) {
    Write-Host "[OK] Certificate bundle found" -ForegroundColor Green
} else {
    Write-Host "[WARN] Corporate CA bundle not found at:" -ForegroundColor Yellow
    Write-Host "  $certPath" -ForegroundColor Gray
    Write-Host "  Some features may not work without corporate certificates." -ForegroundColor Yellow
}

# Create data directories
Write-Host "[4/7] Creating data directories..." -ForegroundColor Yellow

$dataDirs = @("data\json", "data\logs", "data\output", "data\tmp")
foreach ($dir in $dataDirs) {
    $fullPath = Join-Path $ScriptRoot $dir
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
        Write-Host "  Created $dir" -ForegroundColor Gray
    }
}
Write-Host "[OK] Data directories ready" -ForegroundColor Green

# Pull and build Docker images
Write-Host "[5/7] Pulling and building Docker images (this may take several minutes)..." -ForegroundColor Yellow

Push-Location $ScriptRoot
try {
    Write-Host "  Pulling base images..." -ForegroundColor Gray
    $pullResult = docker compose pull 2>&1 | Out-String
    
    Write-Host "  Building backend service..." -ForegroundColor Gray
    $buildResult = docker compose build backend 2>&1 | Out-String
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Docker images ready" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Some images may not have built correctly" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] Error with images: $_" -ForegroundColor Yellow
} finally {
    Pop-Location
}

# Start Docker Compose services
Write-Host "[6/7] Starting SOCAnalyzer services..." -ForegroundColor Yellow

Push-Location $ScriptRoot
try {
    Write-Host "  Stopping any existing services..." -ForegroundColor Gray
    docker compose down 2>&1 | Out-Null
    
    Write-Host "  Starting services (will build backend if needed)..." -ForegroundColor Gray
    docker compose up -d --build 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Services started" -ForegroundColor Green
        
        # Wait for backend health
        Write-Host "  Waiting for backend to be healthy (timeout: 30s)..." -ForegroundColor Gray
        
        $timeout = 30
        $elapsed = 0
        $healthy = $false
        
        while ($elapsed -lt $timeout) {
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
                if ($response.StatusCode -eq 200) {
                    $healthy = $true
                    break
                }
            } catch {
                # Still waiting
            }
            
            Start-Sleep -Seconds 2
            $elapsed += 2
            Write-Host "." -NoNewline -ForegroundColor Gray
        }
        
        Write-Host ""
        
        if ($healthy) {
            Write-Host "[OK] Backend is healthy and ready" -ForegroundColor Green
        } else {
            Write-Host "[WARN] Backend health check timed out (services may still be starting)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[X] Error starting services (exit code: $LASTEXITCODE)" -ForegroundColor Red
        Write-Host "  Run 'docker compose logs' to see details" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "[X] Error starting services: $_" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}

# Launch manager
Write-Host "[7/7] Launching SOCAnalyzer Manager..." -ForegroundColor Yellow

$managerExe = Join-Path $ScriptRoot "SOCAnalyzerManager.exe"
if (Test-Path $managerExe) {
    Start-Process $managerExe
    Write-Host "[OK] Manager launched" -ForegroundColor Green
} else {
    Write-Host "[WARN] Manager executable not found, skipping..." -ForegroundColor Yellow
    Write-Host "  You can access the frontend at: http://localhost:3000" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Installation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "SOCAnalyzer is now running." -ForegroundColor Green
Write-Host ""
Write-Host "Access the application at:" -ForegroundColor White
Write-Host "  http://localhost:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Use the SOCAnalyzer Manager to control services." -ForegroundColor White
Write-Host ""

# Pause to show results
if (-not $SkipDockerCheck) {
    Write-Host "Press any key to exit..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
}
