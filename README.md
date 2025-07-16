# SOCAnalyzer5

SOCAnalyzer5 is a comprehensive platform for analyzing SOC 2 reports, extracting key data, and providing structured outputs for further review and automation. The application features a FastAPI backend for PDF parsing, data normalization, and database management, as well as a React-based frontend for interactive report analysis and editing.

---

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Backend](#backend)
  - [Key Python Files](#key-python-files)
  - [Function Documentation](#function-documentation)
  - [Database Schema](#database-schema)
  - [JSON Outputs](#json-outputs)
- [Frontend](#frontend)
  - [Key Files & Components](#key-files--components)
- [Packages & Dependencies](#packages--dependencies)
- [Relations Between Files](#relations-between-files)
- [Test Scripts](#test-scripts)
- [Data & Output](#data--output)
- [Setup & Usage](#setup--usage)

---

## Overview
SOCAnalyzer5 automates the extraction and normalization of data from SOC 2 PDF reports. It supports:
- Parsing and extracting company, product, auditor, coverage period, controls, CUECs, subservice organizations, and more.
- Normalizing and storing extracted data in a relational database.
- Providing a web interface for reviewing and editing extracted data.
- Exporting structured JSON outputs for downstream use.

---

## Architecture
- **Backend:** Python (FastAPI), SQLAlchemy ORM, PDF extraction utilities, data normalization, and REST API.
- **Frontend:** React (TypeScript), interactive UI for report analysis and editing.
- **Database:** Relational (SQLite or configurable), managed via SQLAlchemy models.
- **Data:** JSON outputs for intermediate and final results.

---

## Backend

### Key Python Files
- `main.py`: FastAPI app, API endpoints, normalization logic, orchestrates extraction and DB operations.
- `models.py`: SQLAlchemy ORM models for all entities (Scan, Company, Control, CUEC, etc.).
- `pdf_handler.py`: PDF parsing and text extraction utilities.
- `extractors/`: Modular extractors for company, product, auditor, controls, CUECs, coverage period, subservice orgs, etc.
- `sync_schema.py`: Utility for syncing DB schema.
- `scan_model.py`: Alternate/legacy scan model (for compatibility).
- `config.py`, `gpt_client.py`: Configuration and GPT/OpenAI integration (if used).

### Function Documentation
- **Normalization Functions:**
  - Robustly extract and normalize fields (company, product, auditor, subservice_orgs, coverage_period) from parsed data, handling alternate keys and moving fields as needed.
- **PDF Extraction:**
  - Utilities to extract text and tables from PDF files for downstream parsing.
- **API Endpoints:**
  - Endpoints for uploading reports, retrieving scan results, and managing entities.
- **Database Operations:**
  - CRUD operations for all entities via SQLAlchemy models.

### Database Schema
- **Scan:** Represents a report scan (id, filename, date, etc.).
- **Company:** Company name, related products, and reports.
- **Product:** Product name, company, and related controls.
- **Auditor:** Auditor name, related scans.
- **Control:** Control id, description, type, related scan/product.
- **CUEC:** Complementary User Entity Controls, linked to scan/product.
- **SubserviceOrg:** Subservice organizations, linked to scan.
- **Setting:** App settings.
- **ScanHistory:** Tracks scan history and changes.

(Relations: Scan ↔ Company/Product/Auditor/Control/CUEC/SubserviceOrg)

### JSON Outputs
- Intermediate and final JSONs are stored in `data/json/`.
- JSONs include normalized fields: company, product, auditor, coverage_period, controls, CUECs, subservice_orgs, etc.
- Used for both DB import and frontend display.

---

## Frontend

### Key Files & Components
- `src/App.tsx`: Main React app entry point.
- `src/router.tsx`: Routing logic for navigation.
- `src/pages/AnalyzerPage.tsx`: Main analysis UI, displays extracted data.
- `src/pages/ReportPage.tsx`: Detailed report view and editing.
- `src/components/EditableTable.tsx`: Table component for editing controls and CUECs.

---

## Packages & Dependencies

### Backend (Python)
- `fastapi`, `uvicorn`: API framework and server.
- `sqlalchemy`: ORM for database models.
- `pypdf`, `pdfminer.six`: PDF parsing.
- `openai`: (optional) GPT integration.
- `pytest`: Testing.

### Frontend (React/TypeScript)
- `react`, `react-dom`, `react-router-dom`: Core React and routing.
- `axios`: HTTP requests.
- `material-ui` or `antd`: UI components (if used).
- `typescript`: Type safety.

---

## Relations Between Files
- `main.py` imports extractors and models, orchestrates extraction and normalization.
- `extractors/` modules are called by `main.py` for field-specific parsing.
- `models.py` defines DB schema, used by all backend logic.
- `pdf_handler.py` is used by extractors and main logic for PDF text extraction.
- Frontend fetches data from backend API endpoints for display and editing.
- Test scripts use backend logic to validate extraction, normalization, and DB import.

---

## Test Scripts
- Located in `test_scripts/`:
  - `test_combine_and_insert.py`: Combines JSONs and tests DB insertion.
  - `test_full_pipeline.py`: End-to-end test of extraction, normalization, and DB import.
  - `test_embedding.py`: Tests OpenAI embedding integration.
  - `pdf_page7_extract_test.py`, `debug_pdf_extract.py`: PDF extraction/debugging utilities.

---

## Data & Output
- **Input:** SOC 2 PDF reports (uploaded via frontend or API).
- **Intermediate:** Extracted and normalized JSONs in `data/json/`.
- **Output:** Structured data in DB, downloadable JSONs, and editable frontend tables.
- **Logs:** Located in `data/logs/`.

---

## Setup & Usage

### Backend
1. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
2. Run the FastAPI server:
   ```powershell
   uvicorn app.main:app --reload
   ```

### Frontend
1. Install dependencies:
   ```powershell
   npm install
   ```
2. Start the React app:
   ```powershell
   npm start
   ```

### Data
- Place SOC 2 PDF reports in the appropriate directory or upload via the frontend.
- Extracted data and logs will appear in `data/json/` and `data/logs/`.

---

## Contact & Support
For questions or support, please contact the project maintainer or open an issue.
