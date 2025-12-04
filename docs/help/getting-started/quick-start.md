# Quick Start Guide

Get up and running with SOC Analyzer in just a few minutes.

## Prerequisites

- Docker and Docker Compose installed
- At least 8GB RAM available
- SOC 1 or SOC 2 audit report (PDF format)
- OpenAI API key (for GPT extraction)

## Installation

### 1. Start the System

```powershell
# Navigate to project directory
cd SOCAnalyzer5

# Start all services
.\socanalyzer.ps1 start
```

This will start:
- Frontend (http://localhost:3000)
- Backend API (http://localhost:8000)
- PostgreSQL database
- Redis cache

### 2. Access the Web Interface

Open your browser and navigate to: **http://localhost:3000**

## Your First Analysis

### Step 1: Upload a Report

1. Click **"New Scan"** or **"Upload Report"** button
2. Select your SOC 1/2 PDF file
3. Enter scan details:
   - **Company Name**: The audited organization
   - **Report Type**: SOC 1 Type II or SOC 2 Type II
   - **Report Date**: Date of the audit report
4. Click **"Upload and Analyze"**

### Step 2: Monitor Progress

The system will process your report in several stages:

```
Uploading PDF (10-30s)
    ↓
Extracting Controls (2-5 min)
    ↓
Extracting CUECs (1-2 min)
    ↓
Extracting Subservice Orgs (1-2 min)
    ↓
Framework Mapping (1-2 min)
    ↓
Automated Cleanup (30s)
    ↓
Complete ✓
```

Progress updates appear in real-time via WebSocket.

### Step 3: Review Extracted Data

Once complete, you'll see multiple tabs:

#### Controls Tab
- View all extracted controls
- High confidence controls (≥75%) shown by default
- Click "Show Low Confidence" to see flagged items
- Edit fields inline or use batch edit mode

#### CUECs Tab
- Complementary User Entity Controls
- Grouped by framework alignment
- Edit descriptions and confidence scores

#### Deviations Tab
- Controls with noted deviations
- Only high confidence (≥75%) deviations shown
- Review deviation descriptions and summaries

#### Subservice Orgs Tab
- Third-party service organizations
- View controls managed by each organization
- Edit organization names and descriptions

### Step 4: Handle Duplicates

The system automatically merges high-confidence duplicates (≥70% similarity). For remaining duplicates:

1. Go to **Controls Tab**
2. Click **"Suggest Merges"** button
3. Review suggested merges with confidence scores
4. Click **"Merge"** on suggestions you approve
5. System consolidates data into primary control

### Step 5: Generate Executive Summary

1. Navigate to **Executive Summary** tab
2. Click **"Generate Summary"** (if not auto-generated)
3. AI creates concise report overview
4. Edit summary if needed
5. Click **"Save"** to persist changes

## Tips for Best Results

### Upload Quality
- Use text-based PDFs (not scanned images)
- Ensure PDF is not password-protected
- Reports with clear formatting extract better

### Review Process
1. **Start with high confidence items** - Review ≥75% confidence first
2. **Check deviations carefully** - Ensure accuracy before reporting
3. **Merge duplicates early** - Reduces manual review burden
4. **Use batch edit** - For similar changes across multiple records

### Performance
- Large reports (>200 controls) take 10-15 minutes
- First extraction is slower (GPT model loading)
- Subsequent extractions are faster (caching)

## Common First-Time Issues

### Long Processing Time
- **Cause**: GPT API rate limiting or large report
- **Solution**: Wait patiently, progress bar shows status

### Low Confidence Scores
- **Cause**: Poor PDF formatting or unclear text
- **Solution**: Review and manually edit flagged items

### Missing Controls
- **Cause**: Controls in non-standard format
- **Solution**: Use manual entry or adjust extraction settings

### Duplicate Controls Not Merging
- **Cause**: Similarity below 70% threshold
- **Solution**: Use "Suggest Merges" and manually approve

## Next Steps

- [Architecture Overview](#architecture-overview) - Understand the system
- [Extraction Workflow](#extraction-workflow) - How extraction works
- [Controls Tab Guide](#controls-tab) - Detailed feature guide
- [Troubleshooting](#common-errors) - Common issues and solutions

## Getting Help

- Press **F1** to open this help system anytime
- Check console logs for detailed error messages
- Review `diagnostic_report.txt` for system diagnostics
