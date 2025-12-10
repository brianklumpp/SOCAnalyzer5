# Extraction Workflow

## Overview

The extraction workflow processes SOC 1 and SOC 2 PDF reports through multiple stages to extract structured data.

## Workflow Stages

### 1. PDF Upload & Validation
- File size check (max 25 MB)
- PDF format validation
- Report type detection (SOC1, SOC2, or COMBINED)

### 2. Text Extraction
- PyMuPDF extracts text from PDF
- Page markers inserted (`=== PAGE X ===`)
- Text saved to `data/tmp/{scan_id}.txt`

### 3. Section Detection
Identifies major report sections using GPT:
- Management Assertion
- Service Auditor Report
- Description of System
- Control Descriptions
- Tests of Controls

### 4. Table of Contents (TOC) Extraction
- Extracts section headings and page numbers
- Calculates page offset for accurate references
- Maps TOC entries to detected sections

### 5. Metadata Extraction
Parallel extraction of report details:
- **Auditor**: Auditing firm name
- **Company**: Service organization
- **Product**: Service/product name
- **Report Date**: Report issuance date
- **Coverage Period**: Audit period dates

### 6. Control Extraction

Uses unified `control_extractor.py` with report type parameter (SOC1/SOC2/COMBINED).

#### Chunking Strategy
- Text divided into overlapping chunks
- Token limits: 1000 tokens per chunk
- Overlap: 200 tokens
- Preserves control boundaries

#### GPT Extraction
For each chunk:
1. Send to GPT-4 with extraction prompt
2. Parse JSON response
3. Extract control fields:
   - Control ID
   - Description
   - Test procedures
   - Test results
   - Framework criteria (dynamically loaded based on report type)
   - Deviation information

#### Framework Mapping
- **Dynamic Framework Loading**: Frameworks automatically selected based on report type:
  - SOC2: TSC, COSO, ISO 27001, NIST
  - SOC1: Financial Assertions, COSO ICFR, ISAE 3402, CSAE 3416, AAF 01/06, GS 007
  - COMBINED: All frameworks
- **GPT-Based Mapping**: Each control is mapped to applicable framework criteria
- **Multi-Framework Support**: Controls can map to multiple frameworks simultaneously
- **Confidence Scoring**: Each mapping includes confidence scores

#### Continuation Handling
- Detects controls split across chunks
- Merges continuation segments
- Validates completeness

#### Validation
- Pattern-based ID verification
- Field completeness check
- Confidence scoring (6-factor system)
- Page reference extraction

### 7. CUEC Extraction
Uses unified `cuec_extractor.py` with report type parameter.

Identifies Complementary User Entity Controls:
- Pattern matching for CUEC sections (different keywords for SOC1 vs SOC2)
- GPT extraction of CUEC details
- Dynamic framework mapping based on report type

### 8. Subservice Organization Detection
Finds third-party vendors:
- Keyword-based detection
- Distance scoring from keywords
- GPT validation of subservice orgs

### 9. Data Insertion
Structured data inserted into PostgreSQL:
- Scan metadata
- Company information
- Controls with confidence scores
- CUECs
- Subservice organizations

### 10. Post-Processing
- Duplicate detection
- Merge suggestions
- Executive summary generation
- Framework coverage calculation

## Progress Tracking

Real-time updates via WebSocket:
- Overall percentage complete
- Extractor-specific status
- Line-based progress for controls
- Running counts

## Error Handling

- Transient errors: Retry with backoff
- Permanent errors: Log and continue
- Bad chunks: Mark and skip
- Validation failures: Flag for review

## Performance Optimization

- Parallel extractor execution
- Redis caching
- Incremental progress storage
- Efficient chunk processing
