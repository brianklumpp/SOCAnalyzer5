# Interactive Analysis Mode - Quick Start Guide

## Overview

The **Interactive Mode** provides a guided, text-based menu interface for SOC2 PDF analysis. It's designed to be the easiest way to run analyses without needing to remember command-line arguments or deal with complex workflows.

## Features

✅ **User-Friendly**: Menu-driven interface with clear prompts  
✅ **Progress Tracking**: Real-time progress bar with status updates  
✅ **Results Summary**: Formatted display of extraction results  
✅ **Guided Workflow**: Step-by-step process from file selection to browser  
✅ **No Threading**: Stable, single-process execution  

## Quick Start

### Windows PowerShell
```powershell
.\interactive.ps1
```

### Windows Command Prompt
```cmd
interactive.bat
```

### Direct Python
```bash
python interactive_scan.py
```

## Workflow

The interactive mode guides you through 6 simple steps:

### 1️⃣ Main Menu
Choose from:
- **Start New Analysis** - Begin a new scan
- **View Available Reports** - See PDFs in soc2_reports/
- **Open Report in Browser** - View latest results
- **About / Help** - Information about the tool
- **Exit** - Close the application

### 2️⃣ File Selection
- Browse available reports in `soc2_reports/` directory
- See file sizes for each report
- Option to specify a custom file path
- Navigate back to main menu

### 3️⃣ Confirmation
- Review selected file details
- Confirm before starting analysis
- Option to cancel and return

### 4️⃣ Analysis Execution
- Real-time progress bar showing completion percentage
- Status updates for each extraction phase:
  - Text extraction
  - Section analysis
  - Company/Auditor extraction
  - Control extraction (with line-by-line progress)
  - CUEC extraction
  - Subservice organizations
  - Product, dates, coverage period
- Elapsed time display

### 5️⃣ Results Summary
Comprehensive display including:
- **Company Information**: Name, parent, product, auditor
- **Extraction Counts**: Controls, CUECs, subservice orgs
- **Control Breakdown**: Status distribution, framework mapping
- **CUEC Summary**: Framework alignment counts
- **Top Subservice Organizations**: With confidence scores

### 6️⃣ Post-Analysis Options
- **Upload to Database**: One-click insertion
- **Open in Browser**: Automatically launch web interface
- Return to main menu for next analysis

## Sample Session

```
================================================================================
                        SOC2 Analyzer - Interactive Mode
================================================================================

[INFO] Welcome to the SOC2 Analysis Interactive Interface
[INFO] This wizard will guide you through the analysis process

► What would you like to do?
------------------------------------------------------------
  1. Start New Analysis
  2. View Available Reports
  3. Open Report in Browser
  4. About / Help
  5. Exit

Enter your choice: 1

================================================================================
                     SOC2 PDF Analysis - File Selection
================================================================================

[INFO] Found 6 PDF report(s)

► Select a PDF report to analyze:
------------------------------------------------------------
  1. Adobe.pdf                         (0.82 MB)
  2. Anaqua.pdf                        (0.61 MB)
  3. Okta.pdf                          (0.78 MB)
  4. SimpleLegal.pdf                   (0.71 MB)
  ...

Enter your choice: 3

================================================================================
                          Confirm Analysis
================================================================================

[INFO] Selected file: Okta.pdf
[INFO] Size: 0.78 MB

Proceed with analysis? (y/n): y

================================================================================
                          Running Analysis
================================================================================

[INFO] Analyzing: Okta.pdf
[INFO] Size: 0.78 MB

[██████████████████████████████░░░░░░░░░░] 60% | Running controls extractor...      | 02:15

... analysis completes ...

[OK] Analysis completed successfully!

================================================================================
                       Analysis Results Summary
================================================================================

► Company Information
------------------------------------------------------------
  Company Name:    Okta, Inc.
  Parent Company:  N/A
  Product:         Okta Service
  Auditor:         Deloitte & Touche LLP

► Extraction Results
------------------------------------------------------------
  Controls:               42
  CUECs:                  12
  Subservice Orgs:        5

► Database Upload
------------------------------------------------------------
Upload results to database? (y/n): y

[INFO] Saved combined results to: combined_result.json
[INFO] Inserting data into database...
[OK] Database upload completed!

Open report in browser? (y/n): y

[INFO] Opening browser to: http://localhost:8000/report/123
[OK] Browser opened successfully!

Press Enter to return to main menu...
```

## Tips

### Navigation
- Use number keys to select menu options
- Press `0` to go back when available
- Use `Ctrl+C` to exit at any time

### File Selection
- Reports in `soc2_reports/` are automatically listed
- Can specify custom path if file is elsewhere
- File sizes help identify which report to analyze

### Progress Monitoring
- Progress bar shows overall completion (0-100%)
- Status text shows current extraction phase
- Timer shows elapsed time
- Control extraction shows line-by-line progress

### Results Review
- Scroll through results summary before continuing
- Note any warnings or partial extractions
- Review confidence scores for subservice orgs

### Database Upload
- Optional but recommended for persistence
- Required for web interface viewing
- Can skip if just testing or debugging

### Browser Integration
- Automatically finds latest scan ID
- Opens report detail page
- Falls back to home page if scan not found

## Troubleshooting

### "No PDF files found"
- Ensure PDFs are in `soc2_reports/` directory
- Or use "Browse for a different file" option
- Check file extensions are `.pdf`

### Progress bar not updating
- Some extraction phases take longer
- Control extraction shows line progress
- Wait for status to change

### Database upload fails
- Check PostgreSQL is running
- Verify connection settings in `backend/app/config.py`
- Review error message for details

### Browser doesn't open
- Manually navigate to `http://localhost:8000`
- Ensure backend server is running
- Check if scan was actually saved to database

### Colors not displaying
- Use Windows Terminal for best experience
- PowerShell 5.1+ supports basic colors
- Some symbols may not render in cmd.exe

## Advantages Over Command Line

| Feature | Command Line | Interactive Mode |
|---------|-------------|------------------|
| File selection | Type full path | Browse menu |
| Progress | Text updates | Visual progress bar |
| Results | JSON files | Formatted summary |
| Database upload | Separate command | Prompted option |
| Browser launch | Manual | Automatic |
| Learning curve | Steeper | Gentler |
| Automation | Better | Not designed for it |

## When to Use Each Mode

### Use Interactive Mode When:
- ✅ Running occasional manual analyses
- ✅ Learning the tool
- ✅ Want visual feedback
- ✅ Need guided workflow
- ✅ Prefer menu navigation

### Use Command Line Mode When:
- ✅ Automating with scripts
- ✅ Batch processing multiple files
- ✅ Running in CI/CD pipeline
- ✅ Need command history
- ✅ Prefer keyboard efficiency

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1-9` | Select menu option |
| `0` | Go back (when available) |
| `y` | Yes to confirmation |
| `n` | No to confirmation |
| `Ctrl+C` | Exit immediately |
| `Enter` | Continue / Accept |

## Advanced Usage

### Custom File Paths
When selecting files, choose "Browse for a different file" and enter:
```
C:\Path\To\Your\Report.pdf
```

### Skipping Database Upload
Simply answer `n` when prompted. Results will still be in JSON files.

### Multiple Analyses
After completing an analysis, you return to the main menu. Select "Start New Analysis" to process another file.

### Viewing Previous Results
Use "Open Report in Browser" from main menu to view the most recent scan without running a new analysis.

## Integration with Other Modes

The interactive mode is fully compatible with command-line mode:

```powershell
# Mix and match:
.\interactive.ps1                    # Interactive mode
.\run_scan.ps1 Okta.pdf              # Command line mode
python interactive_scan.py           # Direct Python
```

All modes use the same:
- Extraction logic
- Database tables
- JSON output format
- Configuration settings

## Support

For issues with interactive mode:
1. Check console output for error messages
2. Verify backend dependencies are installed
3. Ensure PostgreSQL is running
4. Review `DIRECT_EXECUTION_GUIDE.md` for setup
5. Fall back to command-line mode if needed

## Summary

Interactive mode provides the **easiest** way to run SOC2 analysis with:
- No command-line arguments to remember
- Clear visual feedback
- Guided step-by-step process
- Built-in result summaries
- Automatic browser integration

Perfect for manual analysis workflows!
