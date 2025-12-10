# Backend Services

## Overview

The backend is built with FastAPI (Python 3.13) and provides RESTful APIs for all system operations.

## Core Components

### FastAPI Application (`backend/app/main.py`)
Main API server with endpoints for:
- Report upload and analysis
- Data retrieval and updates
- Control merging and validation
- Executive summary generation
- Real-time progress tracking

### Extractors (`backend/app/extractors/`)
Specialized modules for data extraction:

#### Control Extractors
- `control_extractor.py`: Unified control extractor for SOC1, SOC2, and COMBINED reports
  - Supports dynamic framework mapping (TSC, COSO, ISAE 3402, CSAE 3416, AAF 01/06, GS 007, etc.)
  - Handles report type parameter for proper framework selection
  - Includes optional financial assertion mapping for SOC1 reports

#### CUEC Extractor
- `cuec_extractor.py`: Unified CUEC (Complementary User Entity Controls) extractor
  - Supports SOC1 and SOC2 report types with appropriate keyword sets
  - Dynamic framework mapping for multi-framework support

#### Other Extractors
- `auditor.py`: Auditing firm identification
- `company.py`: Service organization details
- `product.py`: Product/service identification
- `report_date.py`: Report date extraction
- `coverage_period.py`: Audit period detection
- `subservice_extractor.py`: Third-party vendor detection

**Note**: Legacy extractors (v2, v4, v4_soc1, combined) have been archived. The unified extractors provide complete functionality for all report types.

### PDF Handler (`backend/app/pdf_handler.py`)
PDF processing utilities:
- Text extraction with PyMuPDF
- Page marker insertion
- TOC extraction
- Section detection

### GPT Client (`backend/app/gpt_client.py`)
OpenAI API integration:
- Prompt management
- Token counting
- Response parsing
- Error handling

### Configuration (`backend/app/config.py`)
System-wide configuration:
- API keys
- Model settings
- Extraction prompts
- Framework criteria (TSC, COSO)

## Database Layer

### Models (`backend/app/models.py`)
SQLAlchemy ORM models for all database tables.

### Database (`backend/app/database.py`)
Connection management and session handling.

## API Endpoints

### Analysis
- `POST /analyze/`: Upload and analyze PDF
- `GET /analyze/status/{job_id}`: Check progress
- `GET /analyze/status_min/{job_id}`: Lightweight status

### Reports
- `GET /report/{scan_id}`: Full report data
- `DELETE /report/{scan_id}`: Delete scan

### Controls
- `GET /report/{scan_id}/controls`: List controls
- `PUT /controls/{control_id}`: Update control
- `POST /controls/merge`: Merge controls
- `GET /report/{scan_id}/controls/suggest-merges`: Get merge suggestions
- `POST /report/{scan_id}/controls/link_instances`: Link duplicate instances
- `POST /report/{scan_id}/controls/unlink_instance/{control_id}`: Unlink instance

### Help System
- `GET /help/index`: Help topics index
- `GET /help/content/{topic_id}`: Topic content

## Background Tasks

- Scan processing with Redis job tracking
- Executive summary generation
- Control merge detection
- Framework mapping

## WebSocket Support

Real-time updates via Socket.IO for:
- Extraction progress
- Extractor status
- Control counts
