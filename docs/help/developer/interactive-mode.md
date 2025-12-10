# Interactive Mode Guide

## Overview

Interactive Mode provides a guided, text-based menu interface for SOC2 PDF analysis with real-time progress tracking and formatted results display.

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

## Features

✅ **User-Friendly** - Menu-driven interface with clear prompts  
✅ **Progress Tracking** - Real-time progress bar with status updates  
✅ **Results Summary** - Formatted display of extraction results  
✅ **Guided Workflow** - Step-by-step from file selection to browser  
✅ **No Threading** - Stable, single-process execution  
✅ **Individual Extractors** - Run specific extractors for testing/debugging  

## Main Menu

### Option 1: Start New Analysis
Full scan of a PDF report:
1. Select PDF from list or browse
2. Confirm and start analysis
3. Watch real-time progress
4. Review results summary
5. Optional database upload
6. Optional browser launch

### Option 2: Run Individual Extractors
Run specific extractors for testing:
- Company Information
- Auditor Information
- Product Information
- Report Date
- Coverage Period
- Control Extractor (V4 or V2)
- CUEC Extractor
- Subservice Organizations
- Section Analysis
- All Extractors

### Option 3: View Available Reports
Browse existing scans in database:
- Lists all scans with company, product, date
- Select to view details
- Open in browser

### Option 4: Open Report in Browser
Automatically launch web interface:
- Finds latest scan
- Opens browser to report detail page
- Falls back to home page if not found

### Option 5: About / Help
Information about the tool:
- Version info
- GPT model configuration
- Architecture overview
- Credits

## Workflow Example

```
================================================================================
                        SOC2 Analyzer - Interactive Mode
================================================================================

[INFO] Welcome to the SOC2 Analysis Interactive Interface

► What would you like to do?
------------------------------------------------------------
  1. Start New Analysis
  2. Run Individual Extractors
  3. View Available Reports
  4. Open Report in Browser
  5. About / Help
  6. Exit

Enter your choice: 1

================================================================================
                     SOC2 PDF Analysis - File Selection
================================================================================

[INFO] Found 6 PDF report(s)

► Select a PDF report to analyze:
------------------------------------------------------------
  1. Adobe.pdf                         (0.82 MB)
  2. Okta.pdf                          (0.78 MB)
  ...

Enter your choice: 2

[INFO] Selected file: Okta.pdf
Proceed with analysis? (y/n): y

================================================================================
                          Running Analysis
================================================================================

[██████████████████████████████░░░░░░░░░░] 60% | Extracting controls...      | 02:15

... analysis completes ...

[OK] Analysis completed successfully!

================================================================================
                       Analysis Results Summary
================================================================================

► Company Information
------------------------------------------------------------
  Company Name:    Okta, Inc.
  Product:         Okta Service
  Auditor:         Deloitte & Touche LLP

► Extraction Results
------------------------------------------------------------
  Controls:               42
  CUECs:                  12
  Subservice Orgs:        5

Upload results to database? (y/n): y
[OK] Database upload completed!

Open report in browser? (y/n): y
[INFO] Opening browser...
```

## Progress Tracking

### Progress Bar
```
[██████████████████████████████░░░░░░░░░░] 60% | Status message | 02:15
```

Shows:
- Visual progress bar (0-100%)
- Current status text
- Elapsed time

### Extraction Phases

1. **Text extraction** (5%)
2. **Section analysis** (15%)
3. **Company/Auditor extraction** (25%)
4. **Control extraction** (35-75%) - with line-by-line progress
5. **CUEC extraction** (80%)
6. **Subservice organizations** (85%)
7. **Product, dates, coverage period** (90%)
8. **Framework mapping** (95%)
9. **Complete** (100%)

## Individual Extractors

Useful for:
- **Testing** - Test single extractor after changes
- **Debugging** - Isolate issues to specific extractor
- **Development** - Rapid iteration on extractor logic
- **Partial Runs** - Re-run only failed extractors

### Example: Testing Control Extractor

```
► Select Extractor:
------------------------------------------------------------
  1. Company Information
  ...
  6. Control Extractor
  ...

Enter your choice: 6

[INFO] Running Control Extractor (v4)
[INFO] Processing 170 chunks...
[OK] Extracted 163 controls
[INFO] Average confidence: 0.87
[INFO] 5 controls rejected (< 0.5 confidence)

Run another extractor? (y/n): n
```

## Results Summary

After extraction, see comprehensive stats:

### Company Information
- Company name
- Parent company (if applicable)
- Product/service name
- Auditor name and location

### Extraction Counts
- Total controls
- Total CUECs
- Total subservice organizations
- Controls with deviations

### Control Breakdown
- By TSC category (CC, A, CA, PI)
- By status (Operating Effectively, With Deviation)
- Framework mapping coverage

### CUEC Summary
- TSC alignment counts
- COSO alignment counts
- Top CUECs by control count

### Top Subservice Organizations
- Organization name
- Confidence score
- Number of controls

## Tips

### Navigation
- Use number keys for menu selections
- Press `0` to go back when available
- Use `Ctrl+C` to exit at any time

### File Selection
- PDFs in `soc2_reports/` are listed automatically
- Can specify custom path for files elsewhere
- File sizes help identify which report

### Progress Monitoring
- Progress bar shows overall completion
- Status text shows current phase
- Timer shows elapsed time
- Control extraction shows detailed line progress

### Results Review
- Scroll through summary before continuing
- Note warnings or partial extractions
- Review confidence scores

### Database Upload
- Optional but recommended for persistence
- Required for web interface viewing
- Can skip for testing/debugging

### Browser Integration
- Automatically finds latest scan ID
- Opens report detail page
- Falls back to home page if scan not found

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1-9` | Select menu option |
| `0` | Go back |
| `y` | Yes |
| `n` | No |
| `Ctrl+C` | Exit immediately |
| `Enter` | Continue/Accept |

## Advanced Usage

### Custom File Paths
Select "Browse for a different file" and enter full path:
```
C:\Path\To\Your\Report.pdf
```

### Skipping Database Upload
Answer `n` when prompted. Results saved to JSON files.

### Multiple Analyses
After completion, return to main menu for next analysis.

### Viewing Previous Results
Use "View Available Reports" to see all scans without running new analysis.

## Troubleshooting

### "No PDF files found"
- Ensure PDFs in `soc2_reports/` directory
- Or use "Browse for different file" option
- Check file extensions are `.pdf`

### Progress bar not updating
- Some phases take longer
- Control extraction shows line progress
- Wait for status change

### Database upload fails
- Check PostgreSQL running
- Verify connection in `backend/app/config.py`
- Review error message

### Browser doesn't open
- Manually navigate to `http://localhost:3000`
- Ensure backend running
- Check scan saved to database

### Colors not displaying
- Use Windows Terminal for best experience
- PowerShell 5.1+ supports basic colors
- Some symbols may not render in cmd.exe

## Comparison with Command Line

| Feature | Command Line | Interactive Mode |
|---------|-------------|------------------|
| File selection | Type full path | Browse menu |
| Progress | Text updates | Visual progress bar |
| Results | JSON files | Formatted summary |
| Database upload | Separate command | Prompted option |
| Browser launch | Manual | Automatic |
| Learning curve | Steeper | Gentler |
| Automation | Better | Not designed for |

## When to Use

### Use Interactive Mode When:
- Running occasional manual analyses
- Learning the tool
- Want visual feedback
- Need guided workflow
- Testing individual extractors

### Use Command Line When:
- Automating with scripts
- Batch processing multiple files
- Running in CI/CD pipeline
- Need command history
- Prefer keyboard efficiency

## Integration

Interactive mode is fully compatible with command-line mode:

```powershell
# Mix and match:
.\interactive.ps1                    # Interactive
.\run_scan.ps1 Okta.pdf              # Command line
python interactive_scan.py           # Direct Python
```

All modes use:
- Same extraction logic
- Same database tables
- Same JSON output format
- Same configuration settings

## Further Reading

- See **Direct Execution Guide** for command-line options
- See **V4 Extraction Architecture** for extractor details
- See **GPT Model Configuration** for model setup
- See **Troubleshooting > Common Errors** for issues
