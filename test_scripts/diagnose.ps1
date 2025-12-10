# SOCAnalyzer Diagnostic and Recovery Script
# Run this when the system stalls or Docker becomes unresponsive

Write-Host "================================" -ForegroundColor Cyan
Write-Host "SOCAnalyzer Diagnostic & Recovery" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Docker status
Write-Host "[1/6] Checking Docker Desktop status..." -ForegroundColor Yellow
$dockerProcs = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
if ($dockerProcs) {
    $totalCPU = ($dockerProcs | Measure-Object -Property CPU -Sum).Sum
    $totalMem = ($dockerProcs | Measure-Object -Property WorkingSet64 -Sum).Sum / 1MB
    Write-Host "  Docker Desktop CPU time: $([math]::Round($totalCPU/60, 1)) minutes" -ForegroundColor White
    Write-Host "  Docker Desktop Memory: $([math]::Round($totalMem, 0)) MB" -ForegroundColor White
    
    if ($totalCPU -gt 600) {
        Write-Host "  ⚠ WARNING: Docker Desktop has high CPU usage - may be unstable" -ForegroundColor Red
    }
} else {
    Write-Host "  ✗ Docker Desktop is not running!" -ForegroundColor Red
}
Write-Host ""

# 2. Check extraction files
Write-Host "[2/6] Checking extraction progress..." -ForegroundColor Yellow
$resultFiles = Get-ChildItem "data\json\*result*.json" -ErrorAction SilentlyContinue
if ($resultFiles) {
    $latest = $resultFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Write-Host "  Latest extraction activity: $($latest.LastWriteTime)" -ForegroundColor White
    
    $nonZeroFiles = $resultFiles | Where-Object {$_.Length -gt 100}
    Write-Host "  Files with data: $($nonZeroFiles.Count) / $($resultFiles.Count)" -ForegroundColor White
    
    foreach ($file in $nonZeroFiles) {
        $sizeKB = [math]::Round($file.Length / 1KB, 1)
        Write-Host "    - $($file.Name): $sizeKB KB" -ForegroundColor Gray
    }
} else {
    Write-Host "  No extraction files found" -ForegroundColor Gray
}
Write-Host ""

# 3. Check checkpoint
Write-Host "[3/6] Checking checkpoint status..." -ForegroundColor Yellow
$checkpoint = Get-Content "data\output\_extraction_checkpoint.json" -Raw -ErrorAction SilentlyContinue
if ($checkpoint) {
    $checkpointData = $checkpoint | ConvertFrom-Json
    Write-Host "  Checkpoint timestamp: $([DateTimeOffset]::FromUnixTimeSeconds($checkpointData.timestamp).LocalDateTime)" -ForegroundColor White
    Write-Host "  Completed extractors: $($checkpointData.completed -join ', ')" -ForegroundColor White
} else {
    Write-Host "  No checkpoint file found" -ForegroundColor Gray
}
Write-Host ""

# 4. Try to get container status
Write-Host "[4/6] Checking Docker containers..." -ForegroundColor Yellow
try {
    $containers = docker ps --format "{{.Names}}\t{{.Status}}" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $containers | ForEach-Object {
            Write-Host "  $_" -ForegroundColor White
        }
    } else {
        Write-Host "  ✗ Cannot communicate with Docker - API error" -ForegroundColor Red
    }
} catch {
    Write-Host "  ✗ Docker command failed: $_" -ForegroundColor Red
}
Write-Host ""

# 5. Check backend logs (if possible)
Write-Host "[5/6] Attempting to retrieve backend logs..." -ForegroundColor Yellow
try {
    $logs = docker logs socanalyzer-backend --tail 10 2>$null
    if ($LASTEXITCODE -eq 0 -and $logs) {
        Write-Host "  Last 10 log lines:" -ForegroundColor White
        $logs | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    } else {
        Write-Host "  ✗ Cannot retrieve logs - Docker unresponsive" -ForegroundColor Red
    }
} catch {
    Write-Host "  ✗ Log retrieval failed" -ForegroundColor Red
}
Write-Host ""

# 6. Recommendations
Write-Host "[6/6] Recommendations:" -ForegroundColor Yellow
Write-Host ""

$needsRestart = $false
if ($totalCPU -gt 600) {
    Write-Host "  ⚠ Docker Desktop is consuming excessive CPU" -ForegroundColor Red
    $needsRestart = $true
}

try {
    docker ps 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ⚠ Docker API is not responding" -ForegroundColor Red
        $needsRestart = $true
    }
} catch {
    $needsRestart = $true
}

if ($needsRestart) {
    Write-Host ""
    Write-Host "  RECOMMENDED ACTION: Restart Docker Desktop" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  To restart:" -ForegroundColor White
    Write-Host "    1. Right-click Docker Desktop icon in system tray" -ForegroundColor Gray
    Write-Host "    2. Select 'Restart Docker Desktop'" -ForegroundColor Gray
    Write-Host "    3. Wait 30-60 seconds for it to fully restart" -ForegroundColor Gray
    Write-Host "    4. Run: .\socanalyzer.ps1 start" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Or use PowerShell:" -ForegroundColor White
    Write-Host "    Stop-Process -Name 'Docker Desktop' -Force" -ForegroundColor Gray
    Write-Host "    Start-Sleep -Seconds 5" -ForegroundColor Gray
    Write-Host "    Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'" -ForegroundColor Gray
    Write-Host "    Start-Sleep -Seconds 30" -ForegroundColor Gray
    Write-Host "    docker-compose up -d" -ForegroundColor Gray
} else {
    Write-Host "  ✓ System appears healthy - no action needed" -ForegroundColor Green
}

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
