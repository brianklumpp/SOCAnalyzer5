# Interactive SOC2 Analysis Launcher
# Provides a guided TUI for SOC2 PDF analysis

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Find Python executable (prefer venv)
function Get-PythonExe {
    $candidates = @(
        (Join-Path $ScriptDir ".venv\Scripts\python.exe"),
        (Join-Path $ScriptDir "venv\Scripts\python.exe"),
        (Join-Path $ScriptDir "env\Scripts\python.exe"),
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
$InteractiveScript = Join-Path $ScriptDir "interactive_scan.py"

# Check if script exists
if (-not (Test-Path $InteractiveScript)) {
    Write-Error "Interactive script not found: $InteractiveScript"
    exit 1
}

# Check for Windows Terminal (better color support)
$useWindowsTerminal = $false
if (Get-Command wt -ErrorAction SilentlyContinue) {
    $useWindowsTerminal = $true
}

# Enable ANSI color support in PowerShell
if ($host.UI.SupportsVirtualTerminal) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  SOC2 Analyzer - Interactive Mode                            " -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "Starting interactive analysis wizard..." -ForegroundColor Green
Write-Host ""

# Run the interactive script
& $PythonExe $InteractiveScript

exit $LASTEXITCODE
