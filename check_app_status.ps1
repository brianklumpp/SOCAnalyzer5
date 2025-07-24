# SOC Analyzer Hung Detection Script
param(
    [string]$ScanId = ""
)

Write-Host "🔍 SOC Analyzer Status Check" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# 1. Check backend process
$pythonProcs = Get-Process python* -ErrorAction SilentlyContinue
if ($pythonProcs) {
    Write-Host "✅ Backend Process: RUNNING" -ForegroundColor Green
    $pythonProcs | ForEach-Object {
        $cpu = if ($_.CPU) { [math]::Round($_.CPU, 2) } else { 0 }
        $memory = [math]::Round($_.WorkingSet / 1MB, 1)
        Write-Host "   PID: $($_.Id) | CPU: $($cpu)s | Memory: $($memory)MB" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ Backend Process: NOT RUNNING" -ForegroundColor Red
}

# 2. Check recent log activity
Write-Host "`n📋 Recent Log Activity:" -ForegroundColor Cyan
$recentLogs = Get-ChildItem data\logs\*.log | Where-Object {$_.Length -gt 0 -and $_.LastWriteTime -gt (Get-Date).AddMinutes(-10)} | Sort-Object LastWriteTime -Descending
if ($recentLogs) {
    $recentLogs | ForEach-Object {
        Write-Host "   $($_.Name): $($_.LastWriteTime.ToString('HH:mm:ss'))" -ForegroundColor Green
    }
} else {
    Write-Host "   ⚠️  No log activity in last 10 minutes" -ForegroundColor Yellow
}

# 3. Check status API if scan ID provided
if ($ScanId) {
    Write-Host "`n🌐 API Status Check:" -ForegroundColor Cyan
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/analyze/status/$ScanId" -Method GET -TimeoutSec 5
        $status = $response.Content | ConvertFrom-Json
        Write-Host "   Status: $($status.status)" -ForegroundColor Green
        Write-Host "   Progress: $($status.progress)%" -ForegroundColor Green
    } catch {
        Write-Host "   ❌ API not responding" -ForegroundColor Red
    }
}

# 4. Check for stuck control extraction
$controlLog = "data\logs\control_extractor_v2.log"
if (Test-Path $controlLog) {
    $lastControlActivity = (Get-Item $controlLog).LastWriteTime
    $timeSinceControl = (Get-Date) - $lastControlActivity
    if ($timeSinceControl.TotalMinutes -gt 5) {
        Write-Host "`n⚠️  Control extraction may be hung (no activity for $([math]::Round($timeSinceControl.TotalMinutes, 1)) minutes)" -ForegroundColor Yellow
    }
}

# 5. Overall assessment
Write-Host "`n🎯 Assessment:" -ForegroundColor Cyan
$backendRunning = $pythonProcs -ne $null
$recentActivity = $recentLogs -ne $null

if ($backendRunning -and $recentActivity) {
    Write-Host "   ✅ System appears HEALTHY" -ForegroundColor Green
} elseif ($backendRunning -and -not $recentActivity) {
    Write-Host "   ⚠️  System may be HUNG (process running but no activity)" -ForegroundColor Yellow
} else {
    Write-Host "   ❌ System appears DOWN" -ForegroundColor Red
}

Write-Host "`nUsage: .\check_app_status.ps1 -ScanId 'your-scan-id'" -ForegroundColor Gray 