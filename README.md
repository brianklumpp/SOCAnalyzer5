## Containerized run (Docker)

Prereqs: Docker Desktop (or engine) installed.

1) Prepare environment (do NOT commit secrets):
   - Create a `.env` file next to `docker-compose.yml` (compose reads it automatically):
     
     DATABASE_URL_ASYNC=postgresql+asyncpg://user:pass@dbhost:5432/dbname
     LLM_PROVIDER=dataiku_dss
     DATAIKU_DSS_HOST=https://dataiku-dss.corp.nandps.com/
     DATAIKU_DSS_API_KEY=...
     DATAIKU_DSS_PROJECT=SOLIDIGM_GPT_API_ACCESS
     DATAIKU_VERIFY_SSL=true
     DATAIKU_CA_BUNDLE=/certs/corp-ca-bundle.pem
     REQUESTS_CA_BUNDLE=/certs/corp-ca-bundle.pem
     EMBEDDING_PROVIDER=openai
     OPENAI_API_KEY=...
     OPENAI_EMBEDDING_MODEL=text-embedding-ada-002
     CONTROL_EMBEDDING_MAPPING_ENABLED=true

2) Place your corporate CA bundle on the host and mount if needed (edit compose):
   - Example: create `certs/` and put `corp-ca-bundle.pem` there; then add a volume mount to the backend service (e.g., `- ./certs:/certs:ro`).

3) Build and run (Docker-only):
   
  docker compose up --build

4) Access:
  - Backend: http://localhost:8000
  - Frontend: http://localhost:3000 (Dockerized frontend)

Notes:
- Data/output and JSON logs are persisted via the `./data:/app/data` bind mount.
- Do not bake secrets into images; use compose `.env` or your secret manager in prod.

### Helper script (Windows): socanalyzer.ps1
Use the Docker-only helper to manage containers like a service:

```powershell
./socanalyzer.ps1 start     # start containers in background (no rebuild)
./socanalyzer.ps1 status    # show status/ports for frontend, backend, postgres, redis
./socanalyzer.ps1 restart   # restart running containers (no rebuild)
./socanalyzer.ps1 stop      # stop running containers (do not remove)
./socanalyzer.ps1 rebuild   # rebuild images and start containers (up -d --build)
./socanalyzer.ps1 down      # stop and remove containers (volumes preserved)
```

Service-like behavior: docker-compose services include `restart: unless-stopped`, so they will restart on reboot unless you stop them.
# SOCAnalyzer5

## ⚠️ IMPORTANT: API Approach Deprecated (November 2025)

**The FastAPI background threading approach has been deprecated due to stability issues.**

Threading-related problems (hanging processes, high CPU usage) led to reverting to direct script execution.

### New Recommended Usage (Direct Execution - No Threading Issues)

**🎯 Interactive Mode (Easiest - Guided Wizard):**
```powershell
# Launch interactive TUI with menu-driven workflow
.\interactive.ps1

# Or use batch file
interactive.bat
```

**📋 Command Line Mode:**
```powershell
# List available PDF reports
.\run_scan.ps1 -ListReports

# Analyze a PDF report (auto-inserts to database)
.\run_scan.ps1 soc2_reports\Okta.pdf

# With verbose logging
.\run_scan.ps1 Okta.pdf -Verbose
```

Or using Python directly:
```bash
python run_analysis.py soc2_reports/Okta.pdf --verbose
```

**See [DIRECT_EXECUTION_GUIDE.md](DIRECT_EXECUTION_GUIDE.md) for complete documentation.**

### Why the Change?
- ✅ **Stable**: No threading issues or hanging processes
- ✅ **Simple**: Direct execution, easier debugging
- ✅ **Fast**: No API/Redis overhead
- ✅ **Transparent**: Real-time console progress
- ❌ **API `/analyze/` endpoint disabled** (returns error message)

---

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
- [Project policy: No regex/text fallbacks](#project-policy-no-regextext-fallbacks)
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
- Backend (FastAPI + SQLAlchemy + Alembic):
  - FastAPI service exposes REST endpoints for uploading PDFs, running extractors, generating executive summaries, and retrieving reports.
  - SQLAlchemy models with async queries (PostgreSQL target). Schema managed via Alembic migrations.
  - PDF extraction layer plus modular extractors for auditor, company, product, controls, CUECs, subservice orgs, coverage period, and report dates.
  - Unified LLM adapter that prioritizes the corporate Dataiku provider; Azure/OpenAI are optional fallbacks.
- Frontend (React):
  - Interactive report review and editing, built with React. In development it runs on port 3000; in production it’s built into static files.
  - Local scripts: If Docker’s frontend container is running (port 3000), the script will skip starting a local static server to avoid duplicates. If Docker isn’t running, the script can serve the build locally (default port 3001).
- Database (PostgreSQL):
  - Primary datastore for scans, companies, products, controls, CUECs, and subservice orgs. Managed by SQLAlchemy and Alembic.
- Caching/Jobs (Redis):
  - Used for background orchestration (optional; started via Docker in local scripts).
- Data & Logs:
  - JSON inputs/outputs and logs under `data/` for reproducibility and auditing.

### Requirements & tools
- Runtime
  - Python 3.10+
  - Node.js 18+ (for frontend build/dev)
  - PostgreSQL 14+ (managed DB)
  - Redis (Docker container is fine for local)
  - PowerShell (Windows scripts), Bash (optional on macOS/Linux)
- Dev/Ops
  - Alembic (DB migrations)
  - Docker Desktop (optional, for containerized runs)
  - Corporate CA bundle (if your environment requires TLS inspection), see `certs/`
  - Dataiku DSS API access (host + API key) if using corporate LLM
  - OpenAI/Azure OpenAI keys (optional fallback)

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
Primary entities (PostgreSQL):
- Scan: one record per analyzed report (id, filename, scan_date, coverage_start/end, report_date, auditor, gpt_cost/model, result_json, etc.)
- Company: extracted company info; related to a Scan
- Product: extracted product info; related to a Scan
- Control: parsed controls with similarity metrics, framework ids, opinions, and deviation metadata
  - Includes `has_deviation` (BOOLEAN) and `deviation_desc` (TEXT); introduced via Alembic migration
- CUEC: Complementary User Entity Controls with framework alignment, confidence, and annotation
- SubserviceOrg: identified subservice organizations with confidence and context
- Setting: application-level settings

(Relations: Scan ↔ Company/Product/Auditor/Control/CUEC/SubserviceOrg)

Migrations (Alembic)
- Apply migrations whenever models change:
  ```powershell
  alembic -c backend/alembic.ini upgrade head
  ```
- Or set `RUN_MIGRATIONS_ON_START=true` in `.env` to let the app migrate on startup.

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
- `fastapi`, `uvicorn`: API framework and server
- `sqlalchemy`, `asyncpg`: ORM and async PostgreSQL driver
- `alembic`: Database migrations
- `redis` (optional): background orchestration/cache
- `pypdf`, `pdfminer.six`: PDF parsing
- `openai` (optional), `azure-*` (optional): LLM fallbacks
- `pytest`: Testing

### Frontend (React/TypeScript)
- `react`, `react-dom`, `react-router-dom`: Core React and routing.
- `axios`: HTTP requests.
- `material-ui` or `antd`: UI components (if used).
- `typescript`: Type safety.

---

## Relations Between Files
- `backend/app/main.py` orchestrates extraction, normalization, LLM calls, and API endpoints
- `backend/app/models.py` defines ORM models used by the backend
- `backend/app/pdf_handler.py` performs PDF text/table extraction
- `backend/app/extractors/` contains field-specific extractors invoked by `main.py`
- `backend/app/gpt_client.py` routes LLM calls (Dataiku-first) with safe logging
- Frontend consumes backend endpoints for report list/detail, executive summaries, and editing
- Test scripts exercise extraction, normalization, and DB import paths

---

## Extractors and GPT capabilities

### Extractors (backend/app/extractors)
- `company.py`, `product.py`: detect and normalize company/product names and related fields
- `auditor.py`: identify auditor firm (uses curated list and heuristics)
- `coverage_period.py`, `report_date.py`: extract coverage windows and report issuance dates
- `control_extractor.py` / `control_extractor_v2.py`: parse controls, derive framework alignment, similarity/confidence, and tooling-assisted opinions
- `cuec_extractor.py`: extract Complementary User Entity Controls with alignment/confidence
- `subservice_orgs.py`: detect subservice organizations with confidence and context snippets
- `section_extractor.py`: support for locating and extracting specific report sections

Inputs: parsed PDF text and metadata from `pdf_handler.py`.

Outputs: normalized dicts/lists with confidence scores, annotations, and source references (page/line refs where available).

### GPT/LLM capabilities (backend/app/gpt_client.py)
- Provider routing: Dataiku DSS (preferred), Azure OpenAI/OpenAI (fallbacks)
- Use cases: classification/normalization assistance and generating executive summaries
- Safety & observability:
  - Optional JSONL logging with redaction and truncation (off by default; enable via config)
  - Token budgeting and response size limits to protect costs and stability
  - Cost/model tracking persisted on the `Scan` where applicable

Executive Summary API:
- `GET /executive_summary/{scan_id}`: retrieve stored summary (if present)
- `POST /executive_summary/{scan_id}`: generate (or regenerate) using the configured provider
- `PATCH /executive_summary/{scan_id}`: update/override stored summary

Configuration (see `backend/app/config.py`):
- `LLM_PROVIDER` defaults to Dataiku; set provider keys/hosts in `.env`
- Logging controls and paths for GPT calls (opt-in)

---

## Project policy: No regex/text fallbacks

This project intentionally avoids regex- or plain-text–based fallbacks when GPT returns an empty or unparsable result. Extractors are GPT-first by design to minimize brittle parsing and hidden behavior.

- Enforced by config flag: `ALLOW_REGEX_FALLBACKS` (default: `false`).
- Location: `backend/app/config.py` (can be overridden in `.env`).
- When `false` (default), extractors will not synthesize values via regex/text heuristics. They will surface empties so you can triage prompts, routing, or section detection.
- If you temporarily need heuristics for debugging, set `ALLOW_REGEX_FALLBACKS=true` in `.env`, re-run analysis, and then turn it back off.

Embedding note
- Corporate LLM routing is Dataiku-first. For embedding-based mappings (e.g., framework alignment) where corporate support is not available, `EMBEDDING_PROVIDER=openai` is supported. Consider adding caching and batching to control cost.

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

### Backend (local dev)
1) Install dependencies
  ```powershell
  pip install -r requirements.txt
  ```
2) Environment configuration
  - Create `.env` with DB/LLM settings. Common keys:
    - `DATABASE_URL_ASYNC=postgresql+asyncpg://user:pass@localhost:5432/socanalyzer5`
    - `RUN_MIGRATIONS_ON_START=true` (optional)
    - `LLM_PROVIDER=dataiku_dss` and related `DATAIKU_*` settings
    - Optional fallbacks: `OPENAI_API_KEY`, `AZURE_OPENAI_*`
3) Database migrations
  ```powershell
  alembic -c backend/alembic.ini upgrade head
  ```
4) Start the backend
  - Dev server:
    ```powershell
    uvicorn backend.app.main:app --reload
    ```
  - Or use the script to start Redis + backend (+ serve frontend build):
    ```powershell
    ./start-all.ps1
    ```

### Frontend
1) Install dependencies
  ```powershell
  npm install
  ```
2) Dev server (port 3000)
  ```powershell
  npm start
  ```
3) Production build
  ```powershell
  npm run build
  # then run ./start-all.ps1
  ```
  - If the Dockerized frontend is running (port 3000), the local script will not start a second frontend.
  - If Docker is not running or you prefer the local server, the script will serve the build on port 3001 by default.
  - You can override or force behavior via environment variables (see below).

### Startup script environment variables
- `SOCANALYZER_SKIP_LOCAL_FRONTEND=1`
  - Always skip starting the local static server (use the Dockerized frontend on port 3000).
- `SOCANALYZER_FRONTEND_PORT=PORT`
  - Port for the local static server (default: 3001) when the Dockerized frontend is not running.
- `SOCANALYZER_SKIP_REDIS=1`
  - Skip starting Redis via Docker in the start-all script.
- `SOCANALYZER_FORCE_DOCKER=1`
  - Treat Docker as available even if basic checks fail.

### Data
- Place SOC 2 PDF reports in the appropriate directory or upload via the frontend.
- Extracted data and logs will appear in `data/json/` and `data/logs/`.

---

## Appendix: How we log LLM calls

LLM request/response logging is opt-in and designed to be safe by default.

- Location: JSONL file at `data/logs/gpt_calls.log` (one event per line)
- Enable via env flags in `.env`:
  - `LOG_GPT_REQUESTS=true` — master switch to log calls
  - `LOG_GPT_PROMPTS=true` — include redacted and truncated prompt/response excerpts
  - `LOG_GPT_MAX_PROMPT_CHARS=800` — max characters for prompt excerpts
  - `LOG_GPT_MAX_RESPONSE_CHARS=800` — max characters for response excerpts
  - `LOG_GPT_SAMPLE_RATE=1.0` — probability to log a call (e.g., 0.1 logs ~10%)

What gets logged
- Request: timestamp, extractor name, provider, model, sampling params, prompt size, optional redacted excerpt
- Response: timestamp, duration, usage (if available), response size, optional redacted excerpt
- Error: timestamp, duration, and error string

Safety controls
- Redaction: masks common emails and truncates long text with an ellipsis
- Truncation: prompt/response excerpts limited by the `LOG_GPT_MAX_*_CHARS` values
- Sampling: reduce volume by setting `LOG_GPT_SAMPLE_RATE` < 1.0

Notes
- Full prompts are never persisted unless you enable excerpts (`LOG_GPT_PROMPTS=true`)
- Provider preference is Dataiku-first (`LLM_PROVIDER=dataiku_dss`), with Azure/OpenAI fallback

---

## Appendix: Core data model (ERD)

The core PostgreSQL entities and relations are shown below.

```mermaid
erDiagram
  Scan ||--o{ Control : contains
  Scan ||--o{ CUEC : contains
  Scan ||--o{ SubserviceOrg : contains
  Scan ||--o| Company : has
  Scan ||--o| Product : has

  Scan {
    int id PK
    string pdf_filename
    datetime scan_date
    datetime coverage_start
    datetime coverage_end
    jsonb result_json
    string auditor
    string gpt_model
    float gpt_cost
  }
  Company {
    int id PK
    int scan_id FK
    string name
    string parent_company
  }
  Product {
    int id PK
    int scan_id FK
    string name
  }
  Control {
    int id PK
    int scan_id FK
    string control_id
    text control_desc
    boolean has_deviation
    text deviation_desc
    float control_tsc_similarity
    float control_coso_similarity
    float control_tsc_confidence_pct
    float control_coso_confidence_pct
  }
  CUEC {
    int id PK
    int scan_id FK
    string cuec_tsc_id
    text cuec_description
    float cuec_tsc_similarity
    float cuec_coso_similarity
    float cuec_tsc_confidence_pct
    float cuec_coso_confidence_pct
  }
  SubserviceOrg {
    int id PK
    int scan_id FK
    string name
    float confidence
    text third_party_description
  }
```

---

## Contact & Support
For questions or support, please contact the project maintainer or open an issue.
