# Windows PowerShell script to start both backend (FastAPI) and frontend (React)
# Usage: Right-click and 'Run with PowerShell' or run in a PowerShell terminal




# Start Redis (using Docker, if not already running)
Write-Host "Starting Redis server using Docker (if not already running)..."
$redisContainer = docker ps -a --filter "name=socanalyzer-redis" --format "{{.Names}}"
$redisRunning = docker ps --filter "name=socanalyzer-redis" --filter "status=running" --format "{{.Names}}"
if ($redisRunning) {
    Write-Host "Redis container already running."
} elseif ($redisContainer) {
    Write-Host "Redis container exists but is not running. Starting it..."
    docker start socanalyzer-redis | Out-Null
    Write-Host "Redis container started."
} else {
    Write-Host "Launching new Redis container..."
    docker run -d --name socanalyzer-redis -p 6379:6379 redis | Out-Null
    Write-Host "Redis container created and started."
}

# Start backend (FastAPI) in a new window
$activate = Join-Path $PSScriptRoot ".venv\\Scripts\\Activate.ps1"
if (Test-Path $activate) {
    $backendCmd = '& .\\.venv\\Scripts\\Activate.ps1; $env:PYTHONIOENCODING = ''utf-8''; python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1'
} else {
    $backendCmd = '$env:PYTHONIOENCODING = ''utf-8''; python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1'
}
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCmd -WorkingDirectory "$PSScriptRoot"

# Prepare and start frontend (React, production build) in another new window
$frontendDir = Join-Path $PSScriptRoot "frontend"
$buildIndex = Join-Path $frontendDir "build\index.html"

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

# Use a fixed port to avoid interactive prompts if 3000 is in use by a dev server
$frontendPort = 3001
Write-Host "Starting frontend on http://localhost:$frontendPort (serving ./frontend/build via 'serve' 14.2.5)"
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

Write-Host "Backend and frontend started in separate PowerShell windows."
