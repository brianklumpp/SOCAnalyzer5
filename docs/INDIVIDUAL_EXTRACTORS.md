# Individual Extractor Mode

## Overview

The interactive script now includes an **Individual Extractor Runner** that allows you to run extractors one at a time for better debugging and control.

## How to Use

1. **Launch the interactive script:**
   ```powershell
   .\interactive.ps1
   ```

2. **Select option 2** from the main menu:
   ```
   2. Run Individual Extractors
   ```

3. **Choose which extractor to run:**
   - Company Extractor
   - Auditor Extractor  
   - Product Extractor
   - Report Date Extractor
   - Coverage Period Extractor
   - Control Extractor (v2)
   - CUEC Extractor
   - Subservice Orgs Extractor
   - Run All Extractors (Sequential)

## Features

### ✅ Individual Control
- Run one extractor at a time
- See immediate results after each extraction
- Full error messages with tracebacks

### ✅ Sequential Mode
- Run all extractors in order
- Option to continue or stop after failures
- Summary report at the end

### ✅ Immediate Feedback
- Each extractor shows:
  - Execution status
  - Results summary
  - Key metrics (counts, confidence scores, etc.)

### ✅ Error Handling
- Full stack traces for debugging
- Option to continue after errors
- Clear error messages

## Prerequisites

The individual extractor mode requires:
- ✅ PDF text file (`data/pdf_extracted_text.txt`)
- ✅ Section results (`data/json/section_results.json`)

These are created during the initial analysis workflow (Option 1).

## Example Usage

### Running Subservice Orgs Extractor Only

1. Launch interactive script: `.\interactive.ps1`
2. Select: `2. Run Individual Extractors`
3. Select: `8. Subservice Orgs Extractor`
4. View results immediately
5. See any errors with full details

### Running All Extractors Sequentially

1. Launch interactive script: `.\interactive.ps1`
2. Select: `2. Run Individual Extractors`
3. Select: `9. Run All Extractors (Sequential)`
4. Watch each extractor run in order
5. See summary at the end

## Benefits Over Full Analysis

| Full Analysis | Individual Extractors |
|--------------|----------------------|
| All-or-nothing | Run specific extractors |
| Limited error visibility | Full error tracebacks |
| Can't skip failures | Continue after errors |
| Progress bar only | Detailed results per extractor |

## Troubleshooting

### "Missing required files"
- Run a full analysis first (Option 1) to create the prerequisite files
- Or ensure `data/pdf_extracted_text.txt` and `data/json/section_results.json` exist

### Extractor fails with error
- Read the full traceback shown
- Check the specific log file in `data/logs/`
- Review configuration in `.env`

### No results displayed
- Check if the JSON output file was created
- Look for errors in the traceback
- Verify the PDF text contains relevant content

## Tips

1. **Start with simpler extractors** (Company, Auditor, Product) to verify setup
2. **Run Subservice Orgs individually** when debugging that specific extractor
3. **Use sequential mode** for complete re-runs after config changes
4. **Check logs** in `data/logs/` for detailed execution info

## Related Files

- `interactive_scan.py` - Main interactive script
- `interactive.ps1` - PowerShell launcher
- `run_extractors.py` - Standalone individual extractor script (deprecated)
- `.env` - Configuration file
