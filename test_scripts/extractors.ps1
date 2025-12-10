# PowerShell launcher for individual extractor runner
$ErrorActionPreference = "Stop"

Write-Host "Starting Individual Extractor Runner..." -ForegroundColor Cyan

# Check if virtual environment exists
if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & "venv\Scripts\Activate.ps1"
}

# Run the individual extractor script
python run_extractors.py

# Keep window open if there was an error
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nPress any key to exit..." -ForegroundColor Red
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
