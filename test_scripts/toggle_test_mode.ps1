# Quick Test Mode Toggle Script
# Easily enable/disable quick test mode for faster development cycles

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('on', 'off', 'status')]
    [string]$Action = 'status',
    
    [Parameter(Mandatory=$false)]
    [int]$MaxControls = 10
)

$envFile = "c:\Users\bklumpp\OneDrive - NANDPS\Documents\Python Scripts\SOCAnalyzer5\.env"

function Get-TestModeStatus {
    if (Test-Path $envFile) {
        $content = Get-Content $envFile -Raw
        if ($content -match 'QUICK_TEST_MODE=true') {
            $maxControls = if ($content -match 'QUICK_TEST_MAX_CONTROLS=(\d+)') { $matches[1] } else { '10' }
            Write-Host "Quick Test Mode: " -NoNewline -ForegroundColor Cyan
            Write-Host "ENABLED" -ForegroundColor Green
            Write-Host "Max Controls: " -NoNewline -ForegroundColor Cyan
            Write-Host "$maxControls" -ForegroundColor Yellow
            return $true
        }
    }
    Write-Host "Quick Test Mode: " -NoNewline -ForegroundColor Cyan
    Write-Host "DISABLED" -ForegroundColor Red
    Write-Host "(Full extraction mode - all controls)" -ForegroundColor Gray
    return $false
}

function Enable-TestMode {
    param([int]$Max = 10)
    
    $envContent = if (Test-Path $envFile) { Get-Content $envFile -Raw } else { "" }
    
    # Remove existing settings if present
    $envContent = $envContent -replace '(?m)^QUICK_TEST_MODE=.*$', ''
    $envContent = $envContent -replace '(?m)^QUICK_TEST_MAX_CONTROLS=.*$', ''
    $envContent = $envContent.Trim()
    
    # Add new settings
    $newSettings = @"

# Quick Test Mode - Extract limited controls for faster testing
QUICK_TEST_MODE=true
QUICK_TEST_MAX_CONTROLS=$Max
"@
    
    $envContent += $newSettings
    Set-Content -Path $envFile -Value $envContent -NoNewline
    
    Write-Host "`n✓ Quick Test Mode ENABLED" -ForegroundColor Green
    Write-Host "  Max Controls: $Max" -ForegroundColor Yellow
    Write-Host "`nBackend restart required for changes to take effect:" -ForegroundColor Cyan
    Write-Host "  docker restart socanalyzer-backend" -ForegroundColor White
}

function Disable-TestMode {
    if (Test-Path $envFile) {
        $envContent = Get-Content $envFile -Raw
        
        # Remove test mode settings
        $envContent = $envContent -replace '(?m)^QUICK_TEST_MODE=.*$', ''
        $envContent = $envContent -replace '(?m)^QUICK_TEST_MAX_CONTROLS=.*$', ''
        $envContent = $envContent -replace '(?m)^\s*# Quick Test Mode.*$', ''
        $envContent = $envContent.Trim()
        
        Set-Content -Path $envFile -Value $envContent -NoNewline
    }
    
    Write-Host "`n✓ Quick Test Mode DISABLED" -ForegroundColor Green
    Write-Host "  Full extraction mode (all controls)" -ForegroundColor Yellow
    Write-Host "`nBackend restart required for changes to take effect:" -ForegroundColor Cyan
    Write-Host "  docker restart socanalyzer-backend" -ForegroundColor White
}

# Main logic
Write-Host "=== Quick Test Mode Manager ===" -ForegroundColor Cyan
Write-Host ""

switch ($Action) {
    'status' {
        Get-TestModeStatus
    }
    'on' {
        Enable-TestMode -Max $MaxControls
    }
    'off' {
        Disable-TestMode
    }
}

Write-Host ""
Write-Host "Usage:" -ForegroundColor Cyan
Write-Host "  .\toggle_test_mode.ps1 status           # Check current status" -ForegroundColor Gray
Write-Host "  .\toggle_test_mode.ps1 on               # Enable test mode (10 controls)" -ForegroundColor Gray
Write-Host "  .\toggle_test_mode.ps1 on -MaxControls 20  # Enable test mode (20 controls)" -ForegroundColor Gray
Write-Host "  .\toggle_test_mode.ps1 off              # Disable test mode" -ForegroundColor Gray
