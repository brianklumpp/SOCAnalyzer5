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

# Start backend (FastAPI) on all interfaces for WebSocket compatibility (FORCE SINGLE WORKER for debugging)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1" -WorkingDirectory "$PSScriptRoot"

# Start frontend (React, production build)
# Start-Process powershell -ArgumentList "-NoExit", "-Command", "npx serve -s build" -WorkingDirectory "$PSScriptRoot\frontend"

Write-Host "Backend is starting in new PowerShell window."
