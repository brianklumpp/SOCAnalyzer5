# Run SOC2 Analysis - PowerShell Wrapper
# This script provides an easy way to run PDF analysis without the API/threading overhead

param(
    [Parameter(Position=0)]
    [string]$PdfPath,
    
    [Parameter()]
    [switch]$ListReports,
    
    [Parameter()]
    [switch]$Verbose,
    
    [Parameter()]
    [switch]$NoDbInsert,
    
    [Parameter()]
    [string]$OutputDir = "data/json"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Find Python executable (prefer venv)
function Get-PythonExe {
    $candidates = @(
        Join-Path $ScriptDir ".venv\Scripts\python.exe",
        Join-Path $ScriptDir "venv\Scripts\python.exe",
        Join-Path $ScriptDir "env\Scripts\python.exe",
        "python"
    )
    
    foreach ($exe in $candidates) {
        if (Test-Path $exe -ErrorAction SilentlyContinue) {
            return $exe
        }
    }
    
    return "python"
}

$PythonExe = Get-PythonExe
$AnalysisScript = Join-Path $ScriptDir "run_analysis.py"

# Check if analysis script exists
if (-not (Test-Path $AnalysisScript)) {
    Write-Error "Analysis script not found: $AnalysisScript"
    exit 1
}

# Build command arguments
$args = @($AnalysisScript)

if ($ListReports) {
    $args += "--list-reports"
} elseif ($PdfPath) {
    $args += $PdfPath
} else {
    Write-Host "SOC2 Analysis - Direct Execution (No API/Threading)"
    Write-Host "=================================================="
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  .\run_scan.ps1 <pdf-file>               # Analyze a PDF"
    Write-Host "  .\run_scan.ps1 -ListReports             # List available reports"
    Write-Host "  .\run_scan.ps1 Okta.pdf                 # Short form (looks in soc2_reports/)"
    Write-Host "  .\run_scan.ps1 -Verbose                 # Enable debug logging"
    Write-Host "  .\run_scan.ps1 -NoDbInsert              # Skip database insertion"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\run_scan.ps1 soc2_reports\Okta.pdf"
    Write-Host "  .\run_scan.ps1 Okta.pdf -Verbose"
    Write-Host "  .\run_scan.ps1 -ListReports"
    Write-Host ""
    exit 0
}

if ($Verbose) {
    $args += "--verbose"
}

if ($NoDbInsert) {
    $args += "--no-db-insert"
}

if ($OutputDir -ne "data/json") {
    $args += "--output-dir", $OutputDir
}

# Run the analysis
Write-Host "Running analysis with: $PythonExe $($args -join ' ')" -ForegroundColor Cyan
Write-Host ""

& $PythonExe @args

exit $LASTEXITCODE
