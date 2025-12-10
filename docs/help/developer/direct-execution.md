# Direct Execution Guide

## Overview

SOC Analyzer supports direct Python script execution for stability and simplicity, replacing the previous FastAPI-based background job approach.

## Why Direct Execution?

The API-based approach had several issues:
1. **Threading Problems** - Background threads causing hanging processes
2. **High CPU Usage** - Thread management overhead
3. **Resource Leaks** - Threads not being properly cleaned up
4. **Complexity** - Additional layers (FastAPI, Redis, WebSocket) adding failure points

## Execution Methods

### Method 1: Interactive Mode (Recommended)

**Launch the Interactive TUI:**
```powershell
# PowerShell
.\interactive.ps1

# Or Command Prompt
interactive.bat

# Or Python directly
python interactive_scan.py
```

**Features:**
- 📁 File browser for PDF selection
- 📊 Real-time progress bar
- 📋 Formatted results summary
- 💾 One-click database upload
- 🌐 Automatic browser launch

**Workflow:**
1. Select PDF from list
2. Confirm and start analysis
3. Watch real-time progress
4. Review results summary
5. Upload to database (optional)
6. Open report in browser

### Method 2: PowerShell Script

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

### Method 3: Direct Python

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

## Interactive Mode Features

### Main Menu Options
1. **Start New Analysis** - Begin a new scan
2. **View Available Reports** - Browse PDFs in soc2_reports/
3. **Open Report in Browser** - View latest results
4. **About / Help** - Information about the tool
5. **Exit** - Close application

### Progress Tracking
- Real-time progress bar (0-100%)
- Status updates for each phase:
  - Text extraction
  - Section analysis
  - Company/Auditor extraction
  - Control extraction (with line-by-line progress)
  - CUEC extraction
  - Subservice organizations
  - Product, dates, coverage period
- Elapsed time display

### Results Summary
After extraction, see:
- **Company Information** - Name, parent, product, auditor
- **Extraction Counts** - Controls, CUECs, subservice orgs
- **Control Breakdown** - Status distribution, framework mapping
- **CUEC Summary** - Framework alignment counts
- **Top Subservice Organizations** - With confidence scores

### Post-Analysis Options
- Upload to database (one-click)
- Open in browser (automatic)
- Return to main menu

## Benefits of Direct Approach

| Aspect | Direct Execution | API Approach |
|--------|------------------|--------------|
| **Stability** | No threading issues | Prone to hanging |
| **Simplicity** | Single-process | Complex async |
| **Transparency** | Console output | Background jobs |
| **Resources** | Low CPU | High CPU |
| **Dependencies** | None (Redis optional) | Redis required |
| **Debugging** | Easy to trace | Difficult async logs |

## Output Locations

Results are saved to:

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
```bash
pip install -r backend/requirements.txt
```

### Database connection errors
- Ensure PostgreSQL is running
- Check connection settings in `backend/app/config.py`
- Verify `.env` has correct `DATABASE_URL_ASYNC`

### "PDF file not found"
- Use absolute paths, or
- Place PDFs in `soc2_reports/` directory
- Use `--list-reports` to see available files

### Want more details
Use `--verbose` or `-v` flag for DEBUG-level logging

### Progress bar not updating
- Some phases take longer
- Control extraction shows line-by-line progress
- Wait for status to change

## When to Use Each Mode

### Use Interactive Mode When:
- Running occasional manual analyses
- Learning the tool
- Want visual feedback
- Need guided workflow
- Prefer menu navigation

### Use Command Line Mode When:
- Automating with scripts
- Batch processing multiple files
- Running in CI/CD pipeline
- Need command history
- Prefer keyboard efficiency

## Programmatic Usage

For custom scripts:

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
print(f"Inserted scan ID: {summary['scan_id']}")
```

## Performance Comparison

| Metric | API Approach | Direct Approach |
|--------|--------------|-----------------|
| CPU Usage | High (threading) | Normal |
| Memory | Higher (threads) | Lower |
| Stability | Prone to hanging | Stable |
| Debugging | Difficult (async) | Easy (sequential) |
| Setup | Complex (Redis) | Simple (Python) |

## Re-enabling API Approach (Not Recommended)

If absolutely needed:
1. Edit `backend/app/main.py`
2. Find `/analyze/` endpoint (around line 1041)
3. Uncomment original code
4. Comment out deprecation message

**Warning:** You'll likely encounter hanging processes and high CPU usage.

## Further Reading

- See **Interactive Mode** for detailed menu walkthrough
- See **Troubleshooting > Common Errors** for issue resolution
- See **Architecture > Backend Services** for extraction pipeline details
