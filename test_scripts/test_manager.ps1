# Test the manager application locally
# Run this script to test the manager without building the exe

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$managerDir = Join-Path $ScriptRoot "manager"

Push-Location $managerDir

Write-Host "Installing manager dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt

Write-Host ""
Write-Host "Launching SOCAnalyzer Manager..." -ForegroundColor Green
python socanalyzer_manager.py

Pop-Location
