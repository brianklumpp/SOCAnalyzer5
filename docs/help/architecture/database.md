# Database Schema

## Overview

SOC Analyzer uses PostgreSQL 15 as its primary data store, managing all extracted data, audit trails, and analysis results.

## Core Tables

### Scan
Stores metadata for each analyzed report:
- `id`: Primary key
- `pdf_filename`: Original file name
- `scan_date`: Timestamp of analysis
- `report_type`: SOC1, SOC2, or COMBINED
- `progress_status`: Extraction progress tracking

### Company
Service organization information:
- `name`: Company name
- `parent_company`: Parent organization
- `confidence`: Extraction confidence score
- `company_domain`: Web domain
- `logo_url`: Company logo path

### Control
Individual controls extracted from reports:
- `control_id`: Control identifier (e.g., CC6.1, EL-06-02)
- `control_desc`: Full control description
- `control_test`: Test procedures
- `control_test_results`: Test outcomes
- `has_deviation`: Deviation flag
- `deviation_desc`: Deviation details
- `confidence`: Overall confidence score
- `merged_to_control_id`: Merge tracking
- `is_duplicate_instance`: Duplicate instance flag
- `duplicate_group_id`: Groups related instances

### CUEC
Complementary User Entity Controls:
- `cuec_number`: CUEC identifier
- `cuec_desc`: Description
- `confidence`: Extraction confidence

### SubserviceOrg
Third-party service organizations:
- `name`: Vendor name
- `third_party_description`: Service description
- `likely_so`: Subservice organization flag

## Relationships

- `Scan` → `Company` (one-to-one)
- `Scan` → `Control` (one-to-many)
- `Scan` → `CUEC` (one-to-many)
- `Scan` → `SubserviceOrg` (one-to-many)

## Audit Tables

### ConfidenceWeights
Tracks confidence calculation weights for each scan.

### ConfidenceWeightAudit
Historical record of all weight changes.

### ControlReview
Manual review tracking for controls.

### PatternReviewQueue
Queue for pattern-based validation.

## Connection Details

- **Host**: localhost (Docker: postgres container)
- **Port**: 5433 (external) → 5432 (internal)
- **Database**: soc2analyzer
- **User**: soc2_analyzer

## Migrations

Database schema changes are managed through Alembic migrations in `backend/alembic/versions/`.
