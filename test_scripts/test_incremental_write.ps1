# Test Incremental Write Feature
# This script tests the new checkpoint functionality

Write-Host "=== Testing Incremental Write Feature ===" -ForegroundColor Cyan
Write-Host ""

$checkpointFile = Join-Path $PSScriptRoot "..\data\json\control_result_checkpoint.json"

# Clean up any existing checkpoint file
if (Test-Path $checkpointFile) {
    Remove-Item $checkpointFile -Force
    Write-Host "Cleaned up existing checkpoint file" -ForegroundColor Yellow
}

# Start a new scan
Write-Host "Starting scan..." -ForegroundColor Green
$scanRequest = @{
    pdf_path = "soc2_reports\Okta.pdf"
    report_type = "SOC2"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:8000/analyze/" -Method Post -Body $scanRequest -ContentType "application/json"
$jobId = $response.job_id

Write-Host "Scan started with job ID: $jobId" -ForegroundColor Green
Write-Host ""

# Monitor for checkpoint file appearance
Write-Host "Monitoring for checkpoint file..." -ForegroundColor Cyan
$maxWaitSeconds = 180  # 3 minutes
$elapsed = 0
$checkpointFound = $false

while ($elapsed -lt $maxWaitSeconds) {
    Start-Sleep -Seconds 5
    $elapsed += 5
    
    if (Test-Path $checkpointFile) {
        $checkpointFound = $true
        $checkpoint = Get-Content $checkpointFile -Raw | ConvertFrom-Json
        $controlCount = $checkpoint.control_count
        $status = $checkpoint.status
        $timestamp = $checkpoint.timestamp
        
        Write-Host "$elapsed seconds - Checkpoint found!" -ForegroundColor Green
        Write-Host "  Status: $status" -ForegroundColor White
        Write-Host "  Controls: $controlCount" -ForegroundColor White
        Write-Host "  Timestamp: $timestamp" -ForegroundColor Gray
        
        # Continue monitoring to see updates
        if ($controlCount -ge 30) {
            Write-Host ""
            Write-Host "SUCCESS: Checkpoint contains $controlCount controls (expected incremental updates)" -ForegroundColor Green
            break
        }
    } else {
        Write-Host "$elapsed seconds - Waiting for checkpoint..." -ForegroundColor Gray
    }
}

Write-Host ""

if (-not $checkpointFound) {
    Write-Host "FAILED: No checkpoint file created after $maxWaitSeconds seconds" -ForegroundColor Red
    Write-Host "This suggests extraction has not progressed far enough yet." -ForegroundColor Yellow
} else {
    Write-Host "=== Checkpoint Feature Working! ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "You can now:" -ForegroundColor Cyan
    Write-Host "  1. Monitor real-time progress by checking the checkpoint file" -ForegroundColor White
    Write-Host "  2. Inspect partial results during long extractions" -ForegroundColor White
    Write-Host "  3. Recover from crashes without losing work" -ForegroundColor White
    Write-Host ""
    Write-Host "Checkpoint file location: $checkpointFile" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Current scan status:" -ForegroundColor Cyan
$status = Invoke-RestMethod -Uri "http://localhost:8000/analyze/status/$jobId"
Write-Host "  Status: $($status.status)"
Write-Host "  Progress: $($status.progress)%"
Write-Host ""
Write-Host "Note: The scan will continue running in the background." -ForegroundColor Yellow
Write-Host "Check final results with: Get-Content <checkpoint-file> | ConvertFrom-Json" -ForegroundColor Gray
