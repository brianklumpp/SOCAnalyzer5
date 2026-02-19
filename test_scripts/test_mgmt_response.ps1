# Quick test script for management response regeneration endpoint
# Usage: .\test_mgmt_response.ps1

$scan_id = 2
$control_id = 3990

# Get auth token from browser localStorage (you'll need to paste it here)
# To get token: Open browser dev tools -> Application -> Local Storage -> Copy 'token' value
$token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxNzY2NjYxMzE1LCJ0eXBlIjoicmVmcmVzaCJ9.VrN4AOpVoVXrCqYYpgCt5J1h5NpqA0ksnDVbKtBIOLg"  # Replace with actual token from browser localStorage

Write-Host "Testing management response regeneration..." -ForegroundColor Cyan
Write-Host "Scan ID: $scan_id, Control ID: $control_id" -ForegroundColor Yellow

try {
    $headers = @{
        "Authorization" = "Bearer $token"
        "Content-Type" = "application/json"
    }
    
    $url = "http://localhost:8000/report/$scan_id/deviations/$control_id/regenerate-management-response"
    
    Write-Host "`nCalling: POST $url" -ForegroundColor Gray
    
    $response = Invoke-RestMethod -Uri $url -Method POST -Headers $headers -ErrorAction Stop
    
    Write-Host "`n✅ SUCCESS!" -ForegroundColor Green
    Write-Host "Response:" -ForegroundColor White
    $response | ConvertTo-Json -Depth 5
    
} catch {
    Write-Host "`n❌ ERROR!" -ForegroundColor Red
    Write-Host "Status: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Red
    Write-Host "Message: $($_.Exception.Message)" -ForegroundColor Red
    
    if ($_.ErrorDetails.Message) {
        Write-Host "Details:" -ForegroundColor Yellow
        Write-Host $_.ErrorDetails.Message
    }
}

Write-Host "`nCheck backend logs with:" -ForegroundColor Cyan
Write-Host 'docker logs socanalyzer-backend --since 10s' -ForegroundColor Gray
