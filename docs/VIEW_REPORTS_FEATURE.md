# View Reports Feature

## Overview
Added a new "View Available Reports" option to the interactive script that allows users to:
1. See all available scans in the database (up to 20 most recent)
2. Select a specific scan to view details
3. Open the selected report in the browser

## What Was Added

### 1. New Function: `view_reports()`
**Location:** `interactive_scan.py` (before `open_report_in_browser()`)

**Features:**
- Loads up to 20 most recent scans from the database
- Displays them in an interactive menu with:
  - Scan ID
  - Product name
  - PDF filename (if available)
  - Scan date
- Allows selection of a specific report
- Shows detailed information about the selected scan:
  - Product
  - PDF File
  - Scan Date
  - Report Date
  - Auditor
  - Coverage period
  - Frontend URL
  - API URL
- Prompts to open the report in browser (default: Yes)

### 2. Updated Function: `open_report_in_browser()`
**Fixed Issues:**
- Changed `Scan.scan_id` to `Scan.id` (correct field name)
- Now works with both:
  - Specific scan ID (when passed as parameter)
  - Latest scan ID (when no parameter provided)

### 3. Menu Integration
**Main Menu Options:**
1. Start New Analysis
2. Run Individual Extractors
3. **View Available Reports** ← NEW
4. Open Report in Browser
5. About / Help
6. Exit

## How to Use

### From Main Menu:
1. Run `python interactive_scan.py` or `.\interactive.ps1`
2. Select option **3: View Available Reports**
3. Browse the list of scans
4. Select a scan to view details
5. Choose to open in browser (press Enter for Yes)

### Example Flow:
```
================================================================================
                              Available Reports
================================================================================

[INFO] Loading reports from database...

Found 28 report(s)

Select a report to open:
  1. [ID: 28] Adobe Experience Cloud - Scanned: 2025-11-12 17:31
  2. [ID: 27] Adobe Experience Cloud - Scanned: 2025-11-12 01:51
  3. [ID: 26] Adobe Experience Cloud (Adobe.pdf) - Scanned: 2025-11-05 00:53
  ...
  29. Return to Main Menu

Enter your choice: 1

================================================================================
                         Report Details - Scan ID 28
================================================================================

Product: Adobe Experience Cloud
PDF File: N/A
Scan Date: 2025-11-12 17:31:44.454066
Report Date: 2023-11-21
Auditor: Unknown
Coverage: None to None

Frontend URL: http://localhost:3000/report/28
API URL: http://localhost:8000/report/28

Open this report in browser? (Y/n): [Press Enter]
```

## URLs Generated

### Frontend (React App):
```
http://localhost:3000/report/{scan_id}
```

### Backend API:
```
http://localhost:8000/report/{scan_id}
```

## Related Files
- `interactive_scan.py` - Updated with new feature
- `list_scans.py` - Standalone script to list scans (created earlier)

## Dependencies
- Async database connection (`app.database.get_db()`)
- SQLAlchemy models (`app.models.Scan`)
- Existing menu infrastructure (`display_menu()`, `prompt_yes_no()`)

## Notes
- Shows up to 20 most recent scans (can be adjusted if needed)
- Gracefully handles database errors
- Uses the new `prompt_yes_no()` helper with default 'y'
- Compatible with existing workflow
