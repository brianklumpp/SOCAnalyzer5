@echo off
REM Run SOC2 Analysis - Batch Wrapper
REM This script provides an easy way to run PDF analysis without the API/threading overhead

setlocal enabledelayedexpansion

REM Find Python executable (prefer venv)
set PYTHON_EXE=python
if exist ".venv\Scripts\python.exe" set PYTHON_EXE=.venv\Scripts\python.exe
if exist "venv\Scripts\python.exe" set PYTHON_EXE=venv\Scripts\python.exe
if exist "env\Scripts\python.exe" set PYTHON_EXE=env\Scripts\python.exe

REM Check if analysis script exists
if not exist "run_analysis.py" (
    echo Error: run_analysis.py not found
    exit /b 1
)

REM Check for arguments
if "%~1"=="" (
    echo SOC2 Analysis - Direct Execution (No API/Threading)
    echo ==================================================
    echo.
    echo Usage:
    echo   run_scan.bat ^<pdf-file^>        # Analyze a PDF
    echo   run_scan.bat --list-reports     # List available reports
    echo   run_scan.bat Okta.pdf           # Short form (looks in soc2_reports/)
    echo.
    echo Examples:
    echo   run_scan.bat soc2_reports\Okta.pdf
    echo   run_scan.bat Okta.pdf --verbose
    echo   run_scan.bat --list-reports
    echo.
    exit /b 0
)

REM Run the analysis with all arguments
echo Running analysis with: %PYTHON_EXE% run_analysis.py %*
echo.

%PYTHON_EXE% run_analysis.py %*

exit /b %ERRORLEVEL%
