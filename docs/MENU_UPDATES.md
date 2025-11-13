# Menu Updates Summary

## Changes Made

### 1. ✅ Fixed Frontend URL Format

**Changed from:** `http://localhost:3000/report/{id}`
**Changed to:** `http://localhost:3000/app/report/{id}`

**Files updated:**
- `interactive_scan.py` - `view_reports()` function
- `interactive_scan.py` - `open_report_in_browser()` function
- `list_scans.py` - URL display

### 2. ✅ Updated Option 4: "Open Report in Browser"

**Previous behavior:** Immediately opened latest report
**New behavior:** Shows selection menu with last 9 reports

**Menu format:** `Date - Time - Company - Product`

**Example:**
```
► Select a report to open:
------------------------------------------------------------
  1. 2025-11-12 - 02:39 - Adobe Incorporated - Adobe Experience Cloud
  2. 2025-11-11 - 14:22 - Okta Inc. - Okta Identity as a Service
  3. 2025-11-10 - 09:15 - ServiceNow - ServiceNow APaaS
  ...
  10. Return to Main Menu
```

## Menu Structure Clarification

### Option 3: View Available Reports
**Purpose:** Browse all available SOC reports in detail
**Shows:** Up to 20 most recent scans
**Actions:** View full details, then optionally open in browser
**Format:** `[ID: {id}] {Product} ({PDF}) - Scanned: {date}`

### Option 4: Open Report in Browser
**Purpose:** Quick access to open a report
**Shows:** Last 9 scans (quick selection)
**Actions:** Directly opens selected report in browser
**Format:** `{Date} - {Time} - {Company} - {Product}`

## Testing Results

✅ URL format correct: `http://localhost:3000/app/report/2`
✅ Menu displays with proper format: Date - Time - Company - Product
✅ Company name fetched from database (shows "Adobe Incorporated")
✅ Browser opens successfully to correct URL
✅ Option to return to main menu works

## Implementation Details

### open_report_in_browser() Function

**New behavior:**
1. If `scan_id` provided → Opens directly (no menu)
2. If no `scan_id` → Shows selection menu

**Data fetching:**
- Queries last 9 scans from database
- For each scan, fetches associated company name
- Orders by scan ID descending (most recent first)

**Display format:**
```python
# Format: "YYYY-MM-DD - HH:MM - Company Name - Product Name"
date_str = scan.scan_date.strftime("%Y-%m-%d")
time_str = scan.scan_date.strftime("%H:%M")
product = scan.product or "Unknown Product"
company = company_name or "N/A"

label = f"{date_str} - {time_str} - {company} - {product}"
```

## Files Modified

1. **interactive_scan.py**
   - Line ~520-615: Completely rewrote `open_report_in_browser()` function
   - Added company name lookup
   - Added menu selection for 9 most recent reports
   - Updated URL format to `/app/report/{id}`
   - Line ~502: Updated URL in `view_reports()` function

2. **list_scans.py**
   - Line ~45: Updated frontend URL format
   - Line ~50: Updated quick start URL format

## How to Use

### Option 3: View Available Reports
```
python interactive_scan.py
→ Select 3
→ Browse detailed list of all reports
→ Select a report to see full details
→ Optionally open in browser
```

### Option 4: Open Report in Browser
```
python interactive_scan.py
→ Select 4
→ See quick list of 9 recent reports
→ Select number to open directly
```

### From Code (Direct Open)
```python
# Open specific scan directly
open_report_in_browser(scan_id=2)

# Show selection menu
open_report_in_browser()  # No scan_id = shows menu
```

## Architecture Alignment

This aligns with the new architecture:
- **Local scripts** run client-side (extraction, processing)
- **Docker services** handle database, API, frontend
- **DNS cache** used by Docker containers
- **PostgreSQL** on port 5433 (exposed from Docker)

All URLs now correctly point to the React router path `/app/report/{id}` as expected by the frontend application.
