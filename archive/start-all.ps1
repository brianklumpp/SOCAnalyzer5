<#
Windows PowerShell script to start backend (FastAPI) and optionally the local frontend (static build via 'serve').

Usage: Right-click and 'Run with PowerShell' or run in a PowerShell terminal.

Behavior:
- Starts Redis via Docker if available (can be skipped).
- Starts backend on http://localhost:8000.
- Starts local frontend (serving ./frontend/build) only if a Dockerized frontend is NOT already running.
    - Docker Compose maps the containerized frontend to http://localhost:3000.
    - Local 'serve' uses port 3001 by default (overridable).

Environment variables:
- SOCANALYZER_SKIP_REDIS=1
    Skip starting Redis via Docker.
- SOCANALYZER_FORCE_DOCKER=1
    Treat Docker as available even if basic checks fail.
- SOCANALYZER_SKIP_LOCAL_FRONTEND=1
    Always skip starting the local 'serve' frontend (use the Dockerized frontend on port 3000).
- SOCANALYZER_FRONTEND_PORT=PORT
    Port for local 'serve' (default: 3001) when local frontend is started.

Notes:
- To avoid double frontends, this script auto-detects a running Docker frontend container (socanalyzer-frontend) and skips local 'serve'.
- Stop the containerized frontend if you prefer using the local 'serve' instance instead.
#>
# Windows PowerShell script to start both backend (FastAPI) and frontend (React)
# Usage: Right-click and 'Run with PowerShell' or run in a PowerShell terminal




# Start Redis (using Docker, if available). Handle missing Docker Desktop gracefully.
Write-Host "Starting Redis server using Docker (if available)..."
# Opt-outs/overrides via env vars
if ($env:SOCANALYZER_SKIP_REDIS -eq '1') {
    Write-Host "Skipping Redis startup by request (SOCANALYZER_SKIP_REDIS=1)." -ForegroundColor Yellow
    $canUseDocker = $false
} else {
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
$canUseDocker = $false
if ($null -eq $dockerCmd) {
    Write-Host "Docker CLI not found. Skipping Redis startup. Backend will run without Redis; background analyze jobs will be unavailable." -ForegroundColor Yellow
} else {
    # Prefer a lightweight check that also works under most configurations
    $null = & docker ps -a 2>$null
    if ($LASTEXITCODE -eq 0) {
        $canUseDocker = $true
        $serverVersion = (& docker version --format '{{.Server.Version}}' 2>$null)
        if ($LASTEXITCODE -eq 0 -and $serverVersion) {
            Write-Host "Docker server detected (version $serverVersion)."
        } else {
            Write-Host "Docker server detected."
        }
    } else {
        Write-Host "Docker Desktop is not reachable. Skipping Redis startup. If Docker Desktop is open, ensure the engine is running and the current user has access to Docker." -ForegroundColor Yellow
    }
}
}

if ($env:SOCANALYZER_FORCE_DOCKER -eq '1') {
    Write-Host "Forcing Docker usage (SOCANALYZER_FORCE_DOCKER=1)."
    $canUseDocker = $true
}

if ($canUseDocker) {
    try {
        $redisContainer = docker ps -a --filter "name=socanalyzer-redis" --format "{{.Names}}"
        $redisRunning = docker ps --filter "name=socanalyzer-redis" --filter "status=running" --format "{{.Names}}"
        if ($redisRunning) {
            Write-Host "Redis container already running."
        } elseif ($redisContainer) {
            Write-Host "Redis container exists but is not running. Starting it..."
            docker start socanalyzer-redis | Out-Null
            if ($LASTEXITCODE -eq 0) { Write-Host "Redis container started." } else { Write-Host "Failed to start existing Redis container." -ForegroundColor Yellow }
        } else {
            Write-Host "Launching new Redis container..."
            docker run -d --name socanalyzer-redis -p 6379:6379 redis | Out-Null
            if ($LASTEXITCODE -eq 0) { Write-Host "Redis container created and started." } else { Write-Host "Failed to create Redis container. Continuing without Redis." -ForegroundColor Yellow }
        }
        # Optional: wait a moment and verify container is running
        Start-Sleep -Seconds 1
        $redisRunning = docker ps --filter "name=socanalyzer-redis" --filter "status=running" --format "{{.Names}}"
        if (-not $redisRunning) {
            Write-Host "Redis container is not reported as running. Background jobs may be unavailable." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Encountered an error while managing Redis container. Continuing without Redis." -ForegroundColor Yellow
    }
}

# Start backend (FastAPI) in a new window
$activate = Join-Path $PSScriptRoot ".venv\\Scripts\\Activate.ps1"
if (Test-Path $activate) {
    $backendCmd = '& .\\.venv\\Scripts\\Activate.ps1; $env:PYTHONIOENCODING = ''utf-8''; python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1'
} else {
    $backendCmd = '$env:PYTHONIOENCODING = ''utf-8''; python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1'
}
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCmd -WorkingDirectory "$PSScriptRoot"

# Prepare and (optionally) start frontend (React, production build) in another new window
$frontendDir = Join-Path $PSScriptRoot "frontend"
$buildIndex = Join-Path $frontendDir "build\index.html"

# Decide whether to skip local frontend if Dockerized frontend is running or if explicitly requested
$skipLocalFrontend = $false
if ($env:SOCANALYZER_SKIP_LOCAL_FRONTEND -eq '1') {
    $skipLocalFrontend = $true
    Write-Host "Skipping local frontend per SOCANALYZER_SKIP_LOCAL_FRONTEND=1" -ForegroundColor Yellow
} elseif ($canUseDocker) {
    try {
        $feRunning = docker ps --filter "name=socanalyzer-frontend" --filter "status=running" --format "{{.Names}}"
        if ($feRunning) {
            $skipLocalFrontend = $true
            Write-Host "Detected Dockerized frontend container '$feRunning' running. Skipping local 'serve' to avoid duplicate frontends (3000 vs 3001)." -ForegroundColor Yellow
        }
    } catch {
        # ignore docker errors here
    }
}

if (-not $skipLocalFrontend) {
    # If build is missing, install deps and build once
    if (-not (Test-Path $buildIndex)) {
        Write-Host "Frontend build not found. Installing dependencies and creating production build..."
        if (Test-Path (Join-Path $frontendDir "package-lock.json")) {
            Start-Process powershell -Wait -ArgumentList "-NoExit", "-Command", "npm ci" -WorkingDirectory $frontendDir | Out-Null
        } else {
            Start-Process powershell -Wait -ArgumentList "-NoExit", "-Command", "npm install" -WorkingDirectory $frontendDir | Out-Null
        }
        Start-Process powershell -Wait -ArgumentList "-NoExit", "-Command", "npm run build" -WorkingDirectory $frontendDir | Out-Null
    }

    # Choose port (default 3001). Allow override via env SOCANALYZER_FRONTEND_PORT
    $frontendPort = if ($env:SOCANALYZER_FRONTEND_PORT) { [int]$env:SOCANALYZER_FRONTEND_PORT } else { 3001 }
    Write-Host "Starting local frontend on http://localhost:$frontendPort (serving ./frontend/build via 'serve')"
    # Ensure 'serve' is available (installed as devDependency). If node_modules missing, run a quick install.
    if (-not (Test-Path (Join-Path $frontendDir "node_modules\serve\package.json"))) {
        Write-Host "Installing frontend dev dependencies (including 'serve')..."
        if (Test-Path (Join-Path $frontendDir "package-lock.json")) {
            Start-Process powershell -Wait -ArgumentList "-NoExit", "-Command", "npm ci" -WorkingDirectory $frontendDir | Out-Null
        } else {
            Start-Process powershell -Wait -ArgumentList "-NoExit", "-Command", "npm install" -WorkingDirectory $frontendDir | Out-Null
        }
    }
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "npm run serve:prod -- -l $frontendPort" -WorkingDirectory $frontendDir
} else {
    Write-Host "Local frontend not started (Dockerized frontend is active or skip requested)."
}

Write-Host "Backend started in a separate PowerShell window."
