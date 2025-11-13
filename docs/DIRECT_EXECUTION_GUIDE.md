# Reverting from API Approach to Direct Execution

## Overview

This document explains the reversion from the FastAPI-based background job approach back to direct Python script execution for SOC2 PDF analysis.

## Why the Change?

The API-based approach introduced several stability issues:

1. **Threading Problems**: Background threads causing hanging processes
2. **High CPU Usage**: Thread management overhead and potential race conditions
3. **Resource Leaks**: Threads not being properly cleaned up
4. **Complexity**: Additional layers (FastAPI, Redis job queue, WebSocket) adding failure points

## What Changed?

### Before (API Approach)
```
User → Web Upload → FastAPI Endpoint → Background Thread → analyze_pdf_file() → Redis Job Queue → Database
                                      ↓
                                   Watchdog Thread
                                   Progress Updates
                                   WebSocket Broadcasting
```

### After (Direct Approach)
```
User → run_analysis.py → analyze_pdf_file() → Database
                        ↓
                   Console Progress
                   Simple Callbacks
```

## New Usage

### Method 1: Interactive Mode (Easiest - Recommended for New Users)

**Launch the Interactive TUI:**
```powershell
# PowerShell
.\interactive.ps1

# Or Command Prompt
interactive.bat

# Or Python directly
python interactive_scan.py
```

**Interactive Features:**
- 📁 **File Selection**: Browse and select from available reports
- 📊 **Progress Tracking**: Real-time progress bar with status updates
- 📋 **Results Summary**: Formatted display of extraction results
- 💾 **Database Upload**: Optional one-click database insertion
- 🌐 **Browser Launch**: Automatically open the report in your browser

**Workflow:**
1. Select a PDF from the list (or browse for a file)
2. Confirm and start analysis
3. Watch real-time progress with status updates
4. Review comprehensive results summary
5. Choose to upload to database
6. Optionally open report in browser

### Method 2: Command Line Scripts (For Automation)

**PowerShell (Windows):**
```powershell
# List available reports
.\run_scan.ps1 -ListReports

# Analyze a specific PDF
.\run_scan.ps1 soc2_reports\Okta.pdf

# With verbose logging
.\run_scan.ps1 Okta.pdf -Verbose

# Skip database insertion
.\run_scan.ps1 Okta.pdf -NoDbInsert
```

**Batch File (Windows):**
```cmd
# List available reports
run_scan.bat --list-reports

# Analyze a specific PDF
run_scan.bat soc2_reports\Okta.pdf

# With verbose logging
run_scan.bat Okta.pdf --verbose
```

### Method 3: Direct Python Execution (Most Flexible)

```bash
# List available reports
python run_analysis.py --list-reports

# Analyze a specific PDF
python run_analysis.py soc2_reports/Okta.pdf

# With verbose logging
python run_analysis.py soc2_reports/Okta.pdf --verbose

# Skip database insertion
python run_analysis.py soc2_reports/Okta.pdf --no-db-insert

# Custom output directory
python run_analysis.py soc2_reports/Okta.pdf --output-dir custom/path
```

## Benefits of Direct Approach

1. **Stability**: No threading issues, no race conditions
2. **Simplicity**: Single-process execution, easier to debug
3. **Transparency**: Console output shows real-time progress
4. **Resource Efficiency**: No background threads consuming CPU
5. **Reliability**: No Redis dependency for job tracking
6. **Debugging**: Easier to trace issues with direct execution

## What Happens to the Web Interface?

The web interface (FastAPI backend) is still available for:
- Viewing existing scan results
- Managing reports
- Accessing the database
- Other non-analysis endpoints

However, the `/analyze/` endpoint is now **disabled** and will return an error message directing users to the direct script approach.

## Re-enabling the API Approach (Not Recommended)

If you absolutely need to re-enable the API-based analysis (despite stability issues), you can:

1. Edit `backend/app/main.py`
2. Find the `@app.post("/analyze/")` endpoint (around line 1041)
3. Uncomment the original code
4. Comment out the deprecation message

**However**, be aware that you'll likely encounter:
- Hanging processes
- High CPU usage
- Threading-related instability

## Migration Guide

### If You Were Using the Web UI Upload

**Old Way:**
1. Start backend server
2. Navigate to web interface
3. Upload PDF
4. Wait for background job
5. Poll for completion

**New Way:**
1. Place PDF in `soc2_reports/` directory (or use any path)
2. Run: `.\run_scan.ps1 YourFile.pdf`
3. Watch console for real-time progress
4. Results automatically inserted into database

### If You Were Using the API Programmatically

**Old Way:**
```python
# Upload file to /analyze/
response = requests.post("http://localhost:8000/analyze/", files={"file": pdf_file})
job_id = response.json()["job_id"]

# Poll for completion
while True:
    status = requests.get(f"http://localhost:8000/analyze/status/{job_id}").json()
    if status["done"]:
        break
    time.sleep(5)
```

**New Way:**
```python
from backend.app.analyze import analyze_pdf_file
from backend.app.explicit_sql_insert import insert_extracted_data

# Direct function call (no API, no threading)
results = analyze_pdf_file(
    "soc2_reports/Okta.pdf",
    progress_callback=lambda p, s: print(f"{p}% - {s}"),
    checklist_callback=lambda c: print(c)
)

# Insert into database
summary = insert_extracted_data("data/json/combined_result.json")
```

## File Locations

After running analysis, results are available in:

```
data/
├── json/
│   ├── combined_result.json      # All results combined
│   ├── section_results.json      # Section analysis
│   ├── control_result.json       # Extracted controls
│   ├── cuec_result.json          # Extracted CUECs
│   ├── company_result.json       # Company info
│   ├── auditor_result.json       # Auditor info
│   ├── product_result.json       # Product info
│   ├── report_date_result.json   # Report dates
│   ├── coverage_period_result.json # Coverage periods
│   └── subservice_orgs_result.json # Subservice orgs
├── output/
│   └── output.txt                # Extracted PDF text
└── logs/
    ├── control_extractor_v2.log  # Control extraction logs
    ├── cuec_extractor.log        # CUEC extraction logs
    └── ... (other extractor logs)
```

## Troubleshooting

### "Module not found" errors
Make sure you're running from the project root directory and have installed dependencies:
```bash
pip install -r backend/requirements.txt
```

### Database connection errors
Ensure PostgreSQL is running and connection settings in `backend/app/config.py` are correct.

### "PDF file not found"
- Use absolute paths, or
- Place PDFs in `soc2_reports/` and use just the filename, or
- Use `--list-reports` to see available files

### Want more details during execution
Use the `--verbose` or `-v` flag to enable DEBUG-level logging.

## Performance Comparison

| Metric | API Approach | Direct Approach |
|--------|-------------|----------------|
| CPU Usage | High (threading overhead) | Normal |
| Memory | Higher (multiple threads) | Lower |
| Stability | Prone to hanging | Stable |
| Debugging | Difficult (async logs) | Easy (sequential) |
| Setup | Complex (Redis, workers) | Simple (just Python) |

## Questions?

If you encounter issues with the direct approach, check:
1. Python environment is activated
2. All dependencies are installed
3. PostgreSQL is running
4. File paths are correct
5. Log files in `data/logs/` for detailed error messages

## Reverting This Change

If you need to go back to the API approach (again, not recommended), you can:

1. Restore the original `/analyze/` endpoint in `backend/app/main.py`
2. Delete or rename `run_analysis.py`, `run_scan.ps1`, `run_scan.bat`
3. Continue using the web interface

However, you'll likely encounter the same threading issues that prompted this change.
