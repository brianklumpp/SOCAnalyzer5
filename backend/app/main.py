import os
import sys
import json as _json
import threading
import time
import datetime
import logging
import traceback
import pathlib
import asyncio
import sqlalchemy
from sqlalchemy import and_
import sqlalchemy.dialects.postgresql as pg_dialect
import redis.asyncio as redis
import redis as sync_redis
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request, UploadFile, File, APIRouter, Form, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi import Body
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
# Removed premature stream_handler formatter assignment (stream_handler not yet defined here).
from typing import Optional, Dict, Any, Tuple

# Boot marker to verify container/image version and source path
logging.warning(f"[BOOT] Loaded backend.app.main from {__file__}")
from sqlalchemy.future import select
from sqlalchemy.exc import MultipleResultsFound
from .models import Company, Control, CUEC, SubserviceOrg, Product, Setting, Base
from .models import Scan, ConfidenceWeights, ConfidenceWeightAudit
from .database import engine, get_db
from .config import AUTO_CREATE_SCHEMA, RUN_MIGRATIONS_ON_START, ALEMBIC_INI_PATH, LOG_LEVEL, EXCLUDE_ACCESS_LOG_PATHS, DOCKER_CONTROL_ENABLED
from .config import REDIS_URL, TSC_CRITERIA, COSO_2013_CRITERIA, EXECUTIVE_SUMMARY_PROMPT
from .frameworks.mapper import map_cuec_to_frameworks_dynamic as map_cuec_to_frameworks
from . import config as cfg
from .services.excel_export import ExcelExportService
from .services import redis_service
from .services import utils
from .services import framework_service
from .services import analysis_service
from .config import (
    EXEC_SUMMARY_TEST_RESULTS_BUDGET_CHARS,
    EXEC_SUMMARY_PER_CONTROL_MAX_CHARS,
    EXEC_SUMMARY_MAX_NON_DEVIATION_CONTROLS,
    EXEC_SUMMARY_TOKEN_WARNING_THRESHOLD,
    MAX_INPUT_TOKENS,
    CHARS_PER_TOKEN,
)
from .explicit_sql_insert import insert_extracted_data
import concurrent.futures
from .gpt_client import gpt_extract, set_gpt_log_context

# Import routers
from .routers import (
    scan_router,
    report_router,
    control_router,
    cuec_router,
    suborg_router,
    deviation_router,
    # executive_summary_router,  # Temporarily disabled - endpoints exist in main.py
    # baseline_router,  # Disabled - models not yet implemented
    config_router,
)

app = FastAPI()
# Minimal direct diagnostic route (bypasses router) to ensure availability
@app.get("/diag/gpt_logging", tags=["diag"], include_in_schema=True)
async def diag_gpt_logging_root():
    try:
        from .gpt_client import gpt_logging_status, log_gpt_event
        status = gpt_logging_status()
        log_gpt_event("diag_root", {"message": "direct app route", "path": status.get("path")})
        return {"ok": True, "status": status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# Middleware to suppress access logs for noisy polling endpoints
@app.middleware("http")
async def suppress_noisy_access_logs(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(p) for p in EXCLUDE_ACCESS_LOG_PATHS):
        # Temporarily set uvicorn access logger to WARNING
        import logging as _logging
        access_logger = _logging.getLogger("uvicorn.access")
        old_level = access_logger.level
        access_logger.setLevel(_logging.WARNING)
        try:
            response = await call_next(request)
        finally:
            access_logger.setLevel(old_level)
        return response
    return await call_next(request)

# Enable CORS for frontend (move this up to the first app instance)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure tables exist on startup (useful for dev/docker-compose)
@app.on_event("startup")
async def _init_db_on_startup():
    try:
        if RUN_MIGRATIONS_ON_START:
            import subprocess, os
            # Run alembic upgrade head using configured alembic.ini
            subprocess.check_call([
                'alembic', '-c', ALEMBIC_INI_PATH, 'upgrade', 'head'
            ], cwd=os.path.dirname(ALEMBIC_INI_PATH))
        elif AUTO_CREATE_SCHEMA:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
    except Exception:
        # Ignore if migrations handled elsewhere
        pass
    # Capture the running event loop for cross-thread scheduling (e.g., WS broadcasts)
    try:
        app.state.loop = asyncio.get_event_loop()
    except Exception:
        app.state.loop = None
    # Emit GPT logging status at startup for diagnostics and write a test event
    try:
        from .gpt_client import gpt_logging_status, log_gpt_event
        status = gpt_logging_status()
        logging.info(f"[STARTUP] GPT logging status: enabled={status.get('enabled')} ready={status.get('logger_ready')} path={status.get('path')}")
        if status.get('enabled'):
            log_gpt_event("startup_check", {"message": "backend startup", "service": "backend"})
    except Exception as _gpt_init_err:
        logging.warning(f"[STARTUP] GPT logging status check failed: {_gpt_init_err}")

# Helper function to mark executive summary as stale
async def mark_executive_summary_stale(scan_id: int, db):
    """Mark the executive summary as stale when data changes that could impact it"""
    scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if scan_row:
        scan_row.executive_summary_stale = True
        db.add(scan_row)

# Set up backend error logging (move this up to the first app instance)
import pathlib
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
os.makedirs(PROJECT_ROOT / 'data/logs', exist_ok=True)
backend_log_path = str(PROJECT_ROOT / 'data/logs/backend_errors.log')
# Clear the log file at startup
with open(backend_log_path, 'w', encoding='utf-8'):
    pass
# Set up a human-readable log format
log_format = '\n%(asctime)s | %(levelname)s | %(module)s | %(message)s\n' + ('-'*80)
root_logger = logging.getLogger()
# Use configured log level
root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
# Remove all handlers first (avoid duplicate logs on reload)
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)
file_handler = logging.FileHandler(backend_log_path, encoding='utf-8')
file_handler.setFormatter(logging.Formatter(log_format))
root_logger.addHandler(file_handler)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter(log_format))
root_logger.addHandler(stream_handler)

# Set up separate log files for each section
section_log_paths = {
    'Management_Assertion': str(PROJECT_ROOT / 'data/logs/management_assertion.log'),
    'Service_Auditor_Report': str(PROJECT_ROOT / 'data/logs/service_auditor_report.log'),
    'Description_of_System': str(PROJECT_ROOT / 'data/logs/description_of_system.log'),
    'Control_Descriptions': str(PROJECT_ROOT / 'data/logs/control_descriptions.log')
}

# Initialize log files
for path in section_log_paths.values():
    with open(path, 'w', encoding='utf-8'):
        pass

# Function to get logger for a specific section
def get_section_logger(section_name):
    log_path = section_log_paths.get(section_name)
    if not log_path:
        return None
    logger = logging.getLogger(section_name)
    if not logger.hasHandlers():
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(file_handler)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    return logger

# Helper function to parse page references
# Utility functions moved to services/utils.py
_parse_page_refs = utils.parse_page_refs

# Example usage
management_assertion_logger = get_section_logger('Management_Assertion')
if management_assertion_logger and logging.getLogger().isEnabledFor(logging.DEBUG):
    management_assertion_logger.info('This is a test log for Management Assertion section.')

# --- TEST: Insert combined_result.json into DB for fast iteration ---
test_router = APIRouter()

@test_router.post("/test/insert_combined_result")
async def test_insert_combined_result(db=Depends(get_db)):
    """
    Loads data/json/combined_result.json and inserts all entities using explicit SQL insert logic.
    Returns a summary of what was inserted.
    """
    import pathlib
    project_root = pathlib.Path(__file__).resolve().parents[2]
    combined_path = str(project_root / "data" / "json" / "combined_result.json")
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        summary = await loop.run_in_executor(pool, insert_extracted_data, combined_path)
    return {"insert_summary": summary}

app.include_router(test_router)

# --- Diagnostics router ---
diag_router = APIRouter(prefix="/diag")

@diag_router.get("/gpt_logging")
async def diag_gpt_logging():
    try:
        from .gpt_client import gpt_logging_status, log_gpt_event
        status = gpt_logging_status()
        log_gpt_event("diag", {"message": "manual diag hit", "path": status.get("path")})
        return {"ok": True, "status": status}
    except Exception as e:
        return {"ok": False, "error": str(e)}

app.include_router(diag_router)

# --- Register modular routers (v2.0.0 refactoring) ---
# Analysis and scan operations
app.include_router(scan_router.router, tags=["scan"])

# Report operations
app.include_router(report_router.router, tags=["report"])

# Control operations
app.include_router(control_router.router, tags=["control"])

# CUEC operations
app.include_router(cuec_router.router, tags=["cuec"])

# Subservice organization operations
app.include_router(suborg_router.router, tags=["suborg"])

# Deviation operations
app.include_router(deviation_router.router, tags=["deviation"])

# Executive summary operations
# app.include_router(executive_summary_router.router, tags=["executive_summary"])  # Temporarily disabled - endpoints exist in main.py

# Validation and baseline operations (disabled - models not yet implemented)
# app.include_router(baseline_router.router, tags=["baseline"])

# Settings and configuration
app.include_router(config_router.router, tags=["config"])

if __name__ == "__main__" and sys.argv[-1] == "test_insert_combined_result":
    async def _main():
        # Use a dummy dependency context
        class DummyDepends:
            async def __aenter__(self):
                return await get_db().__anext__()
            async def __aexit__(self, exc_type, exc, tb):
                pass
        async with DummyDepends() as db:
            result = await test_insert_combined_result(db)
            print("Inserted test combined_result.json:", result)
    asyncio.run(_main())


# --------- SPA static fallback for UI routes under /app ---------
# Serve the built React app's index.html for any /app/* route and /app-settings
FRONTEND_BUILD_DIR = PROJECT_ROOT / 'frontend' / 'build'
FRONTEND_BUILD_INDEX = FRONTEND_BUILD_DIR / 'index.html'

def _spa_index_response():
    if FRONTEND_BUILD_INDEX.exists():
        return FileResponse(str(FRONTEND_BUILD_INDEX))
    return JSONResponse({"error": "UI build not found"}, status_code=404)

@app.get("/app-settings", include_in_schema=False)
async def spa_app_settings():
    return _spa_index_response()

@app.get("/app/{full_path:path}", include_in_schema=False)
async def spa_catch_all(full_path: str):
    return _spa_index_response()

# Serve static assets for the SPA so relative URLs like `static/js/...` resolve
if FRONTEND_BUILD_DIR.exists():
    # Mount at /app to support deep-linking like /app/report/123
    app.mount("/app", StaticFiles(directory=str(FRONTEND_BUILD_DIR), html=True), name="spa")
    # Mount /static for asset paths in index.html
    static_dir = FRONTEND_BUILD_DIR / 'static'
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    # Common top-level assets
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        path = FRONTEND_BUILD_DIR / 'favicon.ico'
        if path.exists():
            return FileResponse(str(path))
        return JSONResponse(status_code=404, content={"error": "favicon not found"})

    @app.get("/manifest.json", include_in_schema=False)
    async def manifest():
        path = FRONTEND_BUILD_DIR / 'manifest.json'
        if path.exists():
            return FileResponse(str(path))
        return JSONResponse(status_code=404, content={"error": "manifest not found"})

    @app.get("/asset-manifest.json", include_in_schema=False)
    async def asset_manifest():
        path = FRONTEND_BUILD_DIR / 'asset-manifest.json'
        if path.exists():
            return FileResponse(str(path))
        return JSONResponse(status_code=404, content={"error": "asset-manifest not found"})


@app.get("/estimate-time")
async def estimate_processing_time(report_type: str = "SOC2", db=Depends(get_db)):
    """
    Estimate processing time based on historical data.
    
    Args:
        report_type: Report type (SOC1, SOC2, COMBINED)
        
    Returns:
        {
            "report_type": str,
            "estimated_seconds": float,
            "based_on_scans": int,  # Number of historical scans used
            "is_fixed_estimate": bool  # True if <3 scans, using fixed 25 min
        }
    """
    try:
        from .models import ReportType
        
        # Validate report type
        try:
            rt_enum = ReportType[report_type.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid report_type: {report_type}")
        
        # Query last 10 scans of this type with elapsed_seconds data
        result = await db.execute(
            select(Scan)
            .where(Scan.report_type == rt_enum)
            .where(Scan.elapsed_seconds.isnot(None))
            .order_by(Scan.id.desc())
            .limit(10)
        )
        scans = result.scalars().all()
        
        # Use base estimate if fewer than minimum samples
        min_samples = cfg.PROGRESS_HISTORY_MIN_SAMPLES
        if len(scans) < min_samples:
            # Use base estimate from config (20 min SOC1, 35 min SOC2)
            base_estimate = cfg.PROGRESS_BASE_ESTIMATE_SOC1 if rt_enum == ReportType.SOC1 else cfg.PROGRESS_BASE_ESTIMATE_SOC2
            return {
                "report_type": report_type,
                "estimated_seconds": float(base_estimate),
                "based_on_scans": len(scans),
                "is_fixed_estimate": True
            }
        
        # Filter outliers using standard deviation (remove values > 2 std dev from mean)
        import numpy as np
        elapsed_times = [s.elapsed_seconds for s in scans if s.elapsed_seconds]
        if len(elapsed_times) < min_samples:
            base_estimate = cfg.PROGRESS_BASE_ESTIMATE_SOC1 if rt_enum == ReportType.SOC1 else cfg.PROGRESS_BASE_ESTIMATE_SOC2
            return {
                "report_type": report_type,
                "estimated_seconds": float(base_estimate),
                "based_on_scans": len(elapsed_times),
                "is_fixed_estimate": True
            }
        
        times_array = np.array(elapsed_times)
        mean_time = np.mean(times_array)
        std_time = np.std(times_array)
        
        # Filter outliers (keep values within 2 standard deviations)
        filtered_times = times_array[np.abs(times_array - mean_time) <= 2 * std_time]
        
        if len(filtered_times) < min_samples:
            # Not enough data after filtering, use base estimate
            base_estimate = cfg.PROGRESS_BASE_ESTIMATE_SOC1 if rt_enum == ReportType.SOC1 else cfg.PROGRESS_BASE_ESTIMATE_SOC2
            return {
                "report_type": report_type,
                "estimated_seconds": float(base_estimate),
                "based_on_scans": len(elapsed_times),
                "is_fixed_estimate": True
            }
        
        # Apply EMA smoothing (0.7 * new + 0.3 * previous) - use most recent first
        ema_estimate = float(filtered_times[0])  # Start with most recent
        for time_val in filtered_times[1:]:
            ema_estimate = 0.7 * time_val + 0.3 * ema_estimate
        
        return {
            "report_type": report_type,
            "estimated_seconds": round(ema_estimate, 1),
            "based_on_scans": len(filtered_times),
            "is_fixed_estimate": False
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error estimating time: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scan/{scan_id}/progress")
async def get_scan_progress(scan_id: int, db=Depends(get_db)):
    """
    Get real-time progress status for a scan.
    
    Returns:
        {
            "scan_id": int,
            "progress_status": str,  # Current extraction step
            "elapsed_seconds": float,  # Time elapsed so far
            "estimated_seconds": float,  # Total estimated time (from historical data)
            "estimated_remaining": float,  # Estimated time remaining
            "percent_complete": float  # Progress percentage (0-90 during scan, 100 when complete)
        }
    """
    try:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        progress_status = scan.progress_status or "Not started"
        
        # Calculate elapsed time dynamically from scan_date timestamp
        if scan.scan_date:
            now = datetime.datetime.now(datetime.timezone.utc)
            scan_date_aware = scan.scan_date if scan.scan_date.tzinfo else scan.scan_date.replace(tzinfo=datetime.timezone.utc)
            elapsed_seconds = (now - scan_date_aware).total_seconds()
        else:
            elapsed_seconds = scan.elapsed_seconds or 0.0
        
        estimated_seconds = scan.estimated_time_seconds or 1500.0  # Default 25 minutes
        
        # Calculate remaining time
        estimated_remaining = max(0, estimated_seconds - elapsed_seconds)
        
        # Calculate percent complete with 90% cap during scan, 100% when complete
        is_complete = scan.elapsed_seconds is not None  # elapsed_seconds only set when scan finishes
        
        if is_complete:
            percent_complete = 100.0
        elif estimated_seconds > 0:
            # Cap at 90% during active scan
            raw_percent = (elapsed_seconds / estimated_seconds) * 100
            percent_complete = min(90.0, raw_percent)
        else:
            percent_complete = 0.0
        
        return {
            "scan_id": scan_id,
            "progress_status": progress_status,
            "elapsed_seconds": round(elapsed_seconds, 1),
            "estimated_seconds": round(estimated_seconds, 1),
            "estimated_remaining": round(estimated_remaining, 1),
            "percent_complete": round(percent_complete, 1)
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting scan progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# REMOVED: @app.get("/report/{scan_id}") - Duplicate endpoint (258 lines)
# Now handled by backend/app/routers/report_router.py line 20

# REMOVED: @app.get("/pdf/{scan_id}") - Duplicate endpoint (~30 lines)
# Now handled by backend/app/routers/report_router.py

# REMOVED: @app.get("/export/excel/{scan_id}") - Duplicate endpoint (~50 lines)
# Now handled by backend/app/routers/report_router.py

# REMOVED: @app.get("/report/{scan_id}/pdf") - Duplicate endpoint (~40 lines)
# Now handled by backend/app/routers/report_router.py line 317


# ------------------------------
# Deviation Endpoints
# ------------------------------

# REMOVED: @app.get("/report/{scan_id}/deviations") - Duplicate endpoint (~50 lines)
# Now handled by backend/app/routers/deviation_router.py line 18

# REMOVED: Deviation endpoints (5 duplicates, ~180 lines total)
# All now handled by backend/app/routers/deviation_router.py:
# - PATCH /control/{control_id}/deviation-summary
# - POST /control/{control_id}/regenerate-deviation-summary  
# - POST /report/{scan_id}/deviations/regenerate-all
# - GET /report/{scan_id}/deviations/regenerate-progress
# - POST /report/{scan_id}/deviation


# ------------------------------
# Subservice Orgs PATCH endpoints
# ------------------------------
from fastapi import Body

ALLOWED_SUBORG_FIELDS = {
    "confidence",
    "confidence_justification",
    "annotation",
    "analyst_notes",
    "third_party_description",
    "third_party_page_ref",
    "name",
}

def _suborg_apply_changes(suborg: SubserviceOrg, data: Dict[str, Any]):
    for k in ALLOWED_SUBORG_FIELDS:
        if k in data:
            # Normalize confidence to float if passed as string percentage or whole number
            if k == "confidence":
                v = data[k]
                if isinstance(v, str):
                    s = v.strip()
                    try:
                        if s.endswith('%'):
                            suborg.confidence = float(s[:-1]) / 100.0
                        else:
                            n = float(s)
                            suborg.confidence = n / 100.0 if n > 1 else n
                    except Exception:
                        # Ignore invalid parses
                        pass
                elif isinstance(v, (int, float)):
                    suborg.confidence = (float(v) / 100.0) if float(v) > 1 else float(v)
                continue
            setattr(suborg, k, data[k])

# REMOVED: PATCH /report/{scan_id}/suborgs/id/{suborg_id}
# Now handled by backend/app/routers/suborg_router.py

# REMOVED: PATCH /report/{scan_id}/suborgs/{suborg_name}
# Now handled by backend/app/routers/suborg_router.py


# Redis job management functions moved to services/redis_service.py
get_job = redis_service.get_job
set_job = redis_service.set_job
del_job = redis_service.del_job

# Redis client management moved to services/redis_service.py
def _get_redis():
    """Get Redis client - wrapper for backward compatibility."""
    return redis_service.get_redis_client(REDIS_URL)

# --- Helpers for artifact presence and lightweight counts ---
# Utility functions moved to services/utils.py
_project_root = utils.get_project_root
_artifact_presence = utils.get_artifact_presence

# Utility function moved to services/utils.py
_reset_scan_state = utils.reset_scan_state

def _safe_len(val) -> int:
    try:
        return len(val) if isinstance(val, (list, dict, str)) else (int(val) if isinstance(val, (int, float)) else 0)
    except Exception:
        return 0

def _result_counts_from_obj(result: Dict[str, Any]) -> Dict[str, int]:
    counts = {
        "company": 1 if bool(result.get("company")) else 0,
        "product": 1 if bool(result.get("product")) else 0,
        "auditor": 1 if bool(result.get("auditor")) else 0,
        "report_date": 1 if bool(result.get("report_date")) else 0,
        "coverage_period": 1 if bool(result.get("coverage_period")) else 0,
        "control": _safe_len(result.get("controls") or []),
        "cuec": _safe_len(result.get("cuecs") or []),
        "subservice_org": _safe_len(result.get("subservice_orgs") or []),
    }
    return counts

def _result_counts_from_disk() -> Dict[str, int]:
    import json as _j
    base = _project_root()
    def _load(path: str):
        try:
            with open(str(base / path), 'r', encoding='utf-8') as f:
                return _j.load(f)
        except Exception:
            return None
    def _streaming_array_count(path: str) -> int:
        """Best-effort count for a file being incrementally written as JSON objects separated by commas.

        control_extractor_v2 writes an initial '[]\n' then appends each object with a leading comma, finally
        overwriting the whole file with a proper {"controls": [...]} structure when complete. While in-flight,
        json.load() fails; this heuristic counts objects so UI progress/counts reflect partial extraction.
        """
        file_path = str(base / path)
        if not os.path.isfile(file_path):
            return 0
        count = 0
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    ls = line.lstrip()
                    # Skip the opening [] line
                    if ls.startswith('[]'):
                        continue
                    # Detect start of an object
                    if ls.startswith('{'):
                        count += 1
            return count
        except Exception:
            return 0
    counts = {"company": 0, "product": 0, "auditor": 0, "report_date": 0, "coverage_period": 0, "control": 0, "cuec": 0, "subservice_org": 0}
    # company/product/auditor/report_date/coverage_period are dict-ish
    counts["company"] = 1 if _load('data/json/company_result.json') else 0
    counts["product"] = 1 if _load('data/json/product_result.json') else 0
    counts["auditor"] = 1 if _load('data/json/auditor_result.json') else 0
    counts["report_date"] = 1 if _load('data/json/report_date_result.json') else 0
    counts["coverage_period"] = 1 if _load('data/json/coverage_period_result.json') else 0
    # list-like inside dicts
    cuec_obj = _load('data/json/cuec_result.json') or {}
    ctrl_obj = _load('data/json/control_result.json') or {}
    so_obj = _load('data/json/subservice_orgs_result.json') or {}
    counts["cuec"] = _safe_len((cuec_obj or {}).get("cuecs") or cuec_obj.get("third_parties") or [])
    if isinstance(ctrl_obj, dict) and "controls" in ctrl_obj:
        counts["control"] = _safe_len(ctrl_obj.get("controls") or [])
    else:
        # Fallback to streaming partial file heuristic while control extractor still running
        counts["control"] = _streaming_array_count('data/json/control_result.json')
    counts["subservice_org"] = _safe_len((so_obj or {}).get("third_parties") or [])
    return counts

# (Removed duplicate earlier definition of _build_combined_results_from_disk; keeping the comprehensive version below.)

def run_analysis_job(job_id, temp_pdf_path, filename, report_type, db, resume=False):
    import logging
    import asyncio
    import threading
    import time
    start_time = time.time()
    
    logging.error(f"[DEBUG run_analysis_job] ENTRY - Thread: {threading.current_thread().name}, job_id={job_id}, report_type='{report_type}', type={type(report_type)}, resume={resume}")
    logging.error(f"[DEBUG run_analysis_job] Condition check - not resume: {not resume}, not report_type: {not report_type}, cfg.REPORT_TYPE_AUTO_DETECT: {cfg.REPORT_TYPE_AUTO_DETECT}")
    
    # Auto-detect report type if not provided or if auto-detection is enabled
    if not resume and (not report_type or cfg.REPORT_TYPE_AUTO_DETECT):
        try:
            from .extractors.report_type_detector import detect_report_type, compute_pdf_hash
            from .models import ReportTypeDetection
            from datetime import datetime, timedelta
            
            # Update job status to show detection in progress
            redis_client = sync_redis.from_url(REDIS_URL, decode_responses=True)
            job = _json.loads(redis_client.get(f"job:{job_id}") or "{}")
            job["status"] = "Detecting report type..."
            job["progress"] = 1
            redis_client.set(f"job:{job_id}", _json.dumps(job), ex=60*60*24)
            
            logging.info(f"[REPORT_TYPE_DETECTION] Starting auto-detection for job_id={job_id}")
            
            # Create sync session for database queries (since we're in a thread)
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            sync_db_url = cfg.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
            sync_engine = create_engine(sync_db_url, echo=False)
            SessionLocal = sessionmaker(bind=sync_engine)
            sync_db = SessionLocal()
            
            try:
                # Read PDF and compute hash
                with open(temp_pdf_path, 'rb') as pdf_file:
                    pdf_bytes = pdf_file.read()
                pdf_hash = compute_pdf_hash(pdf_bytes)
                
                # Check cache first
                cached_detection = None
                if cfg.REPORT_TYPE_CACHE_ENABLED:
                    cached_detection = sync_db.query(ReportTypeDetection).filter_by(pdf_hash=pdf_hash).first()
                if cached_detection:
                    # Check if cache is expired
                    if cached_detection.expires_at and cached_detection.expires_at < datetime.utcnow():
                        logging.info(f"[REPORT_TYPE_DETECTION] Cache expired for pdf_hash={pdf_hash}")
                        cached_detection = None
                    else:
                        # Use cached result (prefer user override if available)
                        if cached_detection.user_confirmed_type:
                            report_type = cached_detection.user_confirmed_type
                            logging.info(f"[REPORT_TYPE_DETECTION] Using cached user override: {report_type}")
                        else:
                            report_type = cached_detection.detected_type
                            logging.info(f"[REPORT_TYPE_DETECTION] Using cached detection: {report_type} (confidence={cached_detection.confidence:.2f})")
                        
                        # Update Redis job status with cached detection
                        redis_client = sync_redis.from_url(REDIS_URL, decode_responses=True)
                        job = _json.loads(redis_client.get(f"job:{job_id}") or "{}")
                        job["status"] = f"Detected: {report_type}"
                        job["progress"] = 2
                        job["detected_report_type"] = report_type
                        job["detected_subtype"] = cached_detection.detected_subtype or 'TYPE2'
                        job["detection_confidence"] = cached_detection.confidence
                        # Update identified_entities with report_type
                        if "identified_entities" not in job:
                            job["identified_entities"] = {}
                        job["identified_entities"]["report_type"] = report_type
                        redis_client.set(f"job:{job_id}", _json.dumps(job), ex=60*60*24)
                        logging.info(f"[REPORT_TYPE_DETECTION] Updated job status with cached detection")
                        logging.info(f"[PROGRESS] Report type identified: {report_type}")
                
                # Run detection if no valid cache
                if not cached_detection:
                    # Extract text for detection (we need this anyway for analysis)
                    from .pdf_handler import extract_text_from_pdf
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp_txt:
                        extracted_text = extract_text_from_pdf(temp_pdf_path, tmp_txt.name)
                    
                    # Run detection
                    detection_result = detect_report_type(
                        extracted_text=extracted_text,
                        pdf_hash=pdf_hash,
                        job_id=job_id
                    )
                    
                    # Store detection in database
                    try:
                        expires_at = datetime.utcnow() + timedelta(days=cfg.REPORT_TYPE_CACHE_TTL_DAYS)
                        new_detection = ReportTypeDetection(
                            pdf_hash=pdf_hash,
                            detected_type=detection_result['detected_type'],
                            detected_subtype=detection_result['detected_subtype'],
                            confidence=detection_result['confidence'],
                            evidence=detection_result['evidence'],
                            analysis_stage=detection_result['analysis_stage'],
                            expires_at=expires_at
                        )
                        sync_db.add(new_detection)
                        sync_db.commit()
                        logging.info(f"[REPORT_TYPE_DETECTION] Stored detection in cache")
                    except Exception as e:
                        logging.error(f"[REPORT_TYPE_DETECTION] Failed to store detection: {e}", exc_info=True)
                        sync_db.rollback()
                    
                    # Check if user confirmation is required
                    if detection_result['requires_confirmation']:
                        logging.info(
                            f"[REPORT_TYPE_DETECTION] Confidence below threshold "
                            f"({detection_result['confidence']:.2f} < {cfg.REPORT_TYPE_CONFIDENCE_THRESHOLD}), "
                            f"awaiting user confirmation"
                        )
                        
                        # Update job status to await confirmation
                        redis_client = sync_redis.from_url(REDIS_URL, decode_responses=True)
                        job = _json.loads(redis_client.get(f"job:{job_id}") or "{}")
                        job["status"] = "AWAITING_CONFIRMATION"
                        job["awaiting_confirmation"] = True
                        job["detection_result"] = detection_result
                        job["pdf_hash"] = pdf_hash
                        job["temp_pdf_path"] = temp_pdf_path
                        job["filename"] = filename
                        redis_client.set(f"job:{job_id}", _json.dumps(job), ex=60*60*24)
                        
                        # Exit thread - will resume when user confirms
                        logging.info(f"[REPORT_TYPE_DETECTION] Paused for user confirmation")
                        return
                    else:
                        # Use detected type
                        report_type = detection_result['detected_type']
                        logging.info(
                            f"[REPORT_TYPE_DETECTION] Auto-detected: {report_type} "
                            f"(confidence={detection_result['confidence']:.2f})"
                        )
                        
                        # Update job status with detected type and identified_entities
                        redis_client = sync_redis.from_url(REDIS_URL, decode_responses=True)
                        job = _json.loads(redis_client.get(f"job:{job_id}") or "{}")
                        job["status"] = f"Detected: {report_type}"
                        job["progress"] = 2
                        job["detected_report_type"] = report_type
                        job["detected_subtype"] = detection_result.get('detected_subtype', 'TYPE2')
                        job["detection_confidence"] = detection_result['confidence']
                        # Update identified_entities with report_type
                        if "identified_entities" not in job:
                            job["identified_entities"] = {}
                        job["identified_entities"]["report_type"] = report_type
                        redis_client.set(f"job:{job_id}", _json.dumps(job), ex=60*60*24)
                        logging.info(f"[PROGRESS] Report type identified: {report_type}")
            finally:
                # Close sync session
                sync_db.close()
        except Exception as e:
            logging.error(f"[REPORT_TYPE_DETECTION] Detection failed: {e}", exc_info=True)
            # Fall back to provided report_type or default
            if not report_type:
                report_type = "SOC2"
                logging.warning(f"[REPORT_TYPE_DETECTION] Falling back to default: {report_type}")
    
    # Track progress and last update for watchdog
    last_progress_value = {"val": 0}
    last_progress_ts = {"ts": time.time()}

    def progress_callback(percent, status=None):
        # logging.info(f"[INFO] progress_callback: job_id={job_id}, percent={percent}, status={status}")
        redis_client = sync_redis.from_url(REDIS_URL, decode_responses=True)
        job_json = redis_client.get(f"job:{job_id}")
        if isinstance(job_json, str):
            job = _json.loads(job_json)
        else:
            job = {}
        # Only update progress and status, do not set 'done' or 'error' here
        job["progress"] = percent
        job["status"] = status or job.get("status", "")
        job.pop("done", None)
        job.pop("error", None)
        redis_client.set(f"job:{job_id}", _json.dumps(job), ex=60*60*24)
        # Update watchdog trackers
        try:
            last_progress_value["val"] = int(percent or 0)
        except Exception:
            last_progress_value["val"] = 0
        last_progress_ts["ts"] = time.time()
        # Also broadcast progress over WebSocket to connected clients
        try:
            loop = getattr(app.state, 'loop', None)
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(broadcast_progress(percent, status), loop)
        except Exception:
            pass

    def checklist_callback(extractor_statuses):
        # Demote to info-level and only emit at INFO+
        if logging.getLogger().isEnabledFor(logging.INFO):
            logger = logging.getLogger('checklist')
            logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
            logger.info(f"[checklist_callback] job_id={job_id}, checklist={extractor_statuses}")
        redis_client = sync_redis.from_url(REDIS_URL, decode_responses=True)
        job_json = redis_client.get(f"job:{job_id}")
        if isinstance(job_json, str):
            job = _json.loads(job_json)
        else:
            job = {}
        # Only update checklist, do not set 'done' or 'error' here
        job["checklist"] = extractor_statuses
        job.pop("done", None)
        job.pop("error", None)
        redis_client.set(f"job:{job_id}", _json.dumps(job), ex=60*60*24)
    # Watchdog to finalize from disk if job stalls after high progress
    stop_event = threading.Event()
    def _watchdog():
        try:
            while not stop_event.is_set():
                time.sleep(5)
                idle = time.time() - last_progress_ts["ts"]
                try:
                    from . import config as _cfg
                    min_progress = int(getattr(_cfg, 'JOB_WATCHDOG_MIN_PROGRESS', 95))
                    idle_secs = int(getattr(_cfg, 'JOB_WATCHDOG_IDLE_SECONDS', 0))
                except Exception:
                    min_progress = 95
                    idle_secs = 0
                if idle_secs <= 0:
                    # Watchdog disabled
                    continue
                if last_progress_value["val"] >= min_progress and idle > idle_secs:
                    logging.warning(f"[WATCHDOG] job_id={job_id} idle_for={int(idle)}s at progress={last_progress_value['val']} — finalizing from disk")
                    try:
                        results = _build_combined_results_from_disk()
                        # Only mark done if there's any content; otherwise keep waiting
                        if isinstance(results, dict) and len(results.keys()) > 0:
                            # Ensure combined_result.json exists (writer inside helper is guarded)
                            async def _update_final():
                                rc = _get_redis()
                                job = await get_job(job_id, rc) or {}
                                # Filter out pdf_file bytes before storing in Redis
                                results_for_redis = {k: v for k, v in results.items() if k != 'pdf_file'}
                                job["result"] = results_for_redis
                                job["done"] = True
                                job["error"] = None
                                job["db_saved"] = job.get("db_saved", False)
                                job["progress"] = 100
                                job["status"] = "Finalized from disk (watchdog)"
                                job["finalized"] = True
                                await set_job(job_id, job, rc)
                            loop = getattr(app.state, 'loop', None)
                            if loop and loop.is_running():
                                asyncio.run_coroutine_threadsafe(_update_final(), loop)
                            else:
                                asyncio.run(_update_final())
                            try:
                                asyncio.run(broadcast_progress(100, "Finalized from disk"))
                                asyncio.run(broadcast_done())
                            except Exception:
                                pass
                            stop_event.set()
                            break
                    except Exception as e:
                        logging.error(f"[WATCHDOG] finalize failed: {e}\n{traceback.format_exc()}")
        except Exception as e:
            logging.error(f"[WATCHDOG] unexpected error: {e}")

    wd_thr = threading.Thread(target=_watchdog, name=f"job-watchdog-{job_id}", daemon=True)
    wd_thr.start()

    try:
        # Set job_id into GPT logging context for the duration of this analysis thread
        try:
            set_gpt_log_context(job_id=job_id)
        except Exception:
            pass
        from .analyze import analyze_pdf_file
        redis_client = sync_redis.from_url(REDIS_URL, decode_responses=True)
        # Check for cancellation before starting
        job_json = redis_client.get(f"job:{job_id}")
        if job_json and isinstance(job_json, str):
            job = _json.loads(job_json)
            if job.get("cancelled"):
                raise Exception("Scan cancelled by user")
        # Run the analysis, but check for cancellation after each major step
        logging.error(f"[DEBUG] Calling analyze_pdf_file with report_type={report_type}, type={type(report_type)}")
        results = analyze_pdf_file(
            temp_pdf_path,
            progress_callback=progress_callback,
            checklist_callback=checklist_callback,
            report_type=report_type,
            job_id=job_id
        )
        
    # Add timing, filename, and report_type metadata to results
        elapsed_time = time.time() - start_time
        results["estimated_time_seconds"] = elapsed_time
        results["pdf_filename"] = filename
        results["report_type"] = report_type
        logging.info(f"[run_analysis_job] Added report_type to results: {report_type}")
        
        # Auto-detect standards from extracted text
        # Strategy: Use report_type to get baseline frameworks (most reliable),
        # then scan text for additional regional/international standards
        try:
            from .frameworks.loader import detect_frameworks_from_standards
            extracted_text = results.get("extracted_text", "")
            if extracted_text:
                detected_standards = detect_frameworks_from_standards(extracted_text, report_type=report_type)
                results["detected_standards"] = detected_standards
                logging.info(f"[STANDARDS_DETECTION] Detected frameworks for {report_type}: {detected_standards}")
            else:
                # Fallback to defaults if no text available
                from .frameworks.loader import get_default_frameworks_for_report
                detected_standards = get_default_frameworks_for_report(report_type) if report_type else []
                results["detected_standards"] = detected_standards
                logging.warning(f"[STANDARDS_DETECTION] No extracted text, using defaults: {detected_standards}")
        except Exception as e:
            logging.error(f"[STANDARDS_DETECTION] Failed to detect standards: {e}", exc_info=True)
            results["detected_standards"] = []
        # Ensure combined_result.json exists (some edge cases may skip write inside analyze_pdf_file) by rebuilding from disk artifacts now.
        try:
            # This will also emit a combined_result.json write attempt internally
            disk_combined = _build_combined_results_from_disk()
            if isinstance(disk_combined, dict) and disk_combined:
                # Merge any keys missing from in-memory results (avoid overwriting richer in-memory structures)
                for k, v in disk_combined.items():
                    if k not in results:
                        results[k] = v
                results.setdefault('_combined_rebuild', True)
        except Exception as _cr_err:
            logging.error(f"[run_analysis_job] combined_result rebuild failed: {_cr_err}")
        # Last-resort: write the in-memory results to combined_result.json directly
        try:
            PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
            combined_path = (PROJECT_ROOT / 'data' / 'json' / 'combined_result.json')
            combined_path.parent.mkdir(parents=True, exist_ok=True)
            # Filter out pdf_file bytes before JSON serialization
            results_for_json = {k: v for k, v in results.items() if k != 'pdf_file'}
            with open(str(combined_path), 'w', encoding='utf-8') as cf:
                _json.dump(results_for_json, cf, ensure_ascii=False, indent=2)
            logging.info(f"[run_analysis_job] Wrote combined_result.json to {combined_path}")
        except Exception as _werr:
            logging.error(f"[run_analysis_job] Failed to write combined_result.json: {_werr}")
        # Check for cancellation after analysis
        job_json = redis_client.get(f"job:{job_id}")
        if job_json and isinstance(job_json, str):
            job = _json.loads(job_json)
            if job.get("cancelled"):
                raise Exception("Scan cancelled by user")
        
        # AUTOMATICALLY INSERT INTO DATABASE when scan completes
        try:
            import tempfile
            # Write result to a temp file and call insert_extracted_data
            # Filter out pdf_file bytes before JSON serialization
            results_for_db = {k: v for k, v in results.items() if k != 'pdf_file'}
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmpf:
                _json.dump(results_for_db, tmpf, ensure_ascii=False)
                tmpf.flush()
                tmp_path = tmpf.name
            
            # Insert into database with PDF path for storage
            summary = insert_extracted_data(tmp_path, pdf_path=temp_pdf_path, job_id=job_id)
            logging.error(f"[SUCCESS] Database insertion completed: {summary}")
            
            # Calculate and store elapsed_seconds and completion status
            elapsed_seconds = time.time() - start_time
            scan_id = summary.get("scan_id")
            if scan_id:
                try:
                    scan = db.query(Scan).filter(Scan.id == scan_id).first()
                    if scan:
                        scan.elapsed_seconds = elapsed_seconds
                        scan.progress_status = "Scan Complete"
                        db.commit()
                        logging.info(f"[ELAPSED_TIME] Stored elapsed_seconds={elapsed_seconds:.1f}s and progress_status='Scan Complete' for scan_id={scan_id}")
                except Exception as elapsed_err:
                    logging.error(f"[ERROR] Failed to store elapsed_seconds: {elapsed_err}")
            
            # Clean up temp file
            import os
            try:
                os.unlink(tmp_path)
            except:
                pass
                
            # Add insertion summary to results
            results["db_insertion_summary"] = summary
            
        except Exception as db_error:
            logging.error(f"[ERROR] Database insertion failed: {db_error}")
            # Don't fail the entire scan if DB insertion fails, just log it
            results["db_insertion_error"] = str(db_error)
        
        async def _update():
            redis_client = _get_redis()
            logging.error(f"[DEBUG] [result_update:_update] Thread: {threading.current_thread().name}, job_id={job_id}, redis_client={id(redis_client)}")
            # Merge latest job state to preserve progress, status, checklist
            job = await get_job(job_id, redis_client) or {}
            # Filter out pdf_file bytes before storing in Redis
            results_for_redis = {k: v for k, v in results.items() if k != 'pdf_file'}
            job["result"] = results_for_redis
            job["done"] = True
            job["error"] = None
            # Only mark as saved if no DB insertion error was captured
            job["db_saved"] = ("db_insertion_error" not in results)
            # Preserve progress, status, checklist if present
            job["progress"] = job.get("progress", 100)
            job["status"] = job.get("status", "Complete")
            job["checklist"] = job.get("checklist", [])
            await set_job(job_id, job, redis_client)
        try:
            loop = asyncio.get_running_loop()
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(f"[DEBUG] [result_update] Using running loop: {id(loop)}")
            loop.create_task(_update())
        except RuntimeError:
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(f"[DEBUG] [result_update] No running event loop, creating new one.")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(f"[DEBUG] [result_update] Before run_until_complete, loop: {id(loop)}")
                loop.run_until_complete(_update())
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(f"[DEBUG] [result_update] After run_until_complete, loop: {id(loop)}")
            except Exception as exc:
                logging.error(f"[DEBUG] [result_update] Exception in run_until_complete: {exc}")
                raise
            finally:
                loop.close()
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(f"[DEBUG] [result_update] Closed event loop: {id(loop)}")
        # Signal watchdog to stop; normal path completed
        stop_event.set()
        # DB write removed from background thread. Will be handled in result endpoint.
    except Exception as e:
        async def _update():
            redis_client = _get_redis()
            logging.error(f"[DEBUG] [error_update:_update] Thread: {threading.current_thread().name}, job_id={job_id}, redis_client={id(redis_client)}")
            # Merge latest job state to preserve progress, status, checklist
            job = await get_job(job_id, redis_client) or {}
            job["error"] = str(e)
            job["done"] = True
            # Preserve progress, status, checklist if present
            job["progress"] = job.get("progress", 100)
            job["status"] = job.get("status", "Error")
            job["checklist"] = job.get("checklist", [])
            await set_job(job_id, job, redis_client)
        try:
            loop = asyncio.get_running_loop()
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(f"[DEBUG] [error_update] Using running loop: {id(loop)}")
            loop.create_task(_update())
        except RuntimeError:
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(f"[DEBUG] [error_update] No running event loop, creating new one.")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(f"[DEBUG] [error_update] Before run_until_complete, loop: {id(loop)}")
                loop.run_until_complete(_update())
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(f"[DEBUG] [error_update] After run_until_complete, loop: {id(loop)}")
            except Exception as exc:
                logging.error(f"[DEBUG] [error_update] Exception in run_until_complete: {exc}")
                raise
            finally:
                loop.close()
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(f"[DEBUG] [error_update] Closed event loop: {id(loop)}")
    finally:
        try:
            os.remove(temp_pdf_path)
        except Exception as e:
            pass


# --- FastAPI app definition must come before any route decorators ---
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Optional
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request, Depends, UploadFile, File
from sqlalchemy.future import select
from .models import Setting, Base
from .database import engine, get_db
import threading
import time
import sqlalchemy
import sqlalchemy.dialects.postgresql as pg_dialect
import asyncio
import os
import datetime
import logging
import traceback


# ...existing code...

@app.post("/analyze/")
async def analyze_pdf_bg(
    file: UploadFile = File(...), 
    report_type: str = Form(None),
    db=Depends(get_db)
):
    """
    Upload and analyze a SOC report PDF.
    
    Args:
        file: PDF file to analyze
        report_type: Report type - "SOC1", "SOC2", or "COMBINED" (default: None for auto-detection)
        db: Database session
        
    Returns:
        {"job_id": str} - Job ID for polling status
    """
    logging.error(f"[DEBUG /analyze/] Received report_type='{report_type}', type={type(report_type)}, file={file.filename}")
    import uuid
    import shutil
    import threading
    
    # Normalize report_type - keep as None for auto-detection, or use provided value
    if report_type and report_type.strip() == "":
        report_type = None
    
    if report_type:
        logging.error(f"[DEBUG /analyze/] Using explicit report_type='{report_type}'")
    else:
        logging.error(f"[DEBUG /analyze/] report_type=None, will use auto-detection")
    
    temp_dir = "data/tmp"
    os.makedirs(temp_dir, exist_ok=True)
    filename = file.filename if file.filename else "uploaded.pdf"
    temp_pdf_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{filename}")
    
    with open(temp_pdf_path, "wb") as f_out:
        shutil.copyfileobj(file.file, f_out)
    
    # Reset prior artifacts/logs to ensure clean scan state
    try:
        _reset_scan_state()
    except Exception:
        pass
    
    job_id = str(uuid.uuid4())
    logging.error(f"[DEBUG /analyze/] Creating job {job_id} with report_type='{report_type}'")
    await set_job(job_id, {
        "status": "Queued",
        "progress": 0,
        "done": False,
        "result": None,
        "error": None,
        "checklist": [],
        "filename": filename,
        "report_type": report_type,
        "start_time": time.time(),
        "identified_entities": {},
        "counters": {
            "subservice_orgs_count": 0,
            "controls_count": 0,
            "controls_total_estimate": 0,
            "controls_percent": 0,
            "controls_mapped_count": 0,
            "controls_mapped_percent": 0,
            "cuecs_count": 0
        },
        "phase_completion": {
            "logo_fetched": False,
            "cleanup_done": False,
            "db_uploaded": False
        },
        "extraction_partial": False
    })
    
    # Start background thread with report_type parameter
    logging.error(f"[DEBUG /analyze/] Starting thread with args: job_id={job_id}, filename={filename}, report_type='{report_type}'")
    thread = threading.Thread(
        target=run_analysis_job, 
        args=(job_id, temp_pdf_path, filename, report_type, db)
    )
    thread.start()
    
    return {"job_id": job_id}

@app.post("/analyze/cancel/{job_id}")
async def cancel_analysis_job(job_id: str):
    """
    Cancel an in-progress analysis job.
    Sets the 'cancelled' flag in Redis, which will be checked by run_analysis_job.
    """
    # Load current job status from Redis
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Set cancelled flag
    job["cancelled"] = True
    job["status"] = "Cancelled"
    await set_job(job_id, job)
    
    return {"message": f"Job {job_id} has been cancelled", "job_id": job_id}

@app.post("/analyze/confirm-type/{job_id}")
async def confirm_report_type(
    job_id: str,
    confirmed_type: str = Form(...),
    confirmed_subtype: str = Form(...),
    db=Depends(get_db)
):
    """
    User confirmation of detected report type.
    Updates the detection cache with user override and resumes analysis.
    
    Args:
        job_id: Job ID awaiting confirmation
        confirmed_type: User-confirmed report type ('SOC1', 'SOC2', or 'COMBINED')
        confirmed_subtype: User-confirmed subtype ('TYPE1' or 'TYPE2')
    """
    import logging
    from .models import ReportTypeDetection
    from datetime import datetime
    
    logging.info(f"[CONFIRM_TYPE] job_id={job_id}, confirmed_type={confirmed_type}, confirmed_subtype={confirmed_subtype}")
    
    # Load job from Redis
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Validate status
    if job.get("status") != "AWAITING_CONFIRMATION":
        raise HTTPException(
            status_code=400, 
            detail=f"Job is not awaiting confirmation (status: {job.get('status')})"
        )
    
    # Update detection cache with user override
    pdf_hash = job.get("pdf_hash")
    if pdf_hash:
        try:
            detection = db.query(ReportTypeDetection).filter_by(pdf_hash=pdf_hash).first()
            if detection:
                detection.user_confirmed_type = confirmed_type
                detection.user_confirmed_subtype = confirmed_subtype
                detection.user_confirmed_at = datetime.utcnow()
                db.commit()
                logging.info(f"[CONFIRM_TYPE] Updated detection cache for pdf_hash={pdf_hash}")
        except Exception as e:
            logging.error(f"[CONFIRM_TYPE] Failed to update detection cache: {e}", exc_info=True)
            db.rollback()
    
    # Update job with confirmed type and resume analysis
    job["report_type"] = confirmed_type
    job["report_subtype"] = confirmed_subtype
    job["status"] = "Resuming analysis..."
    job["awaiting_confirmation"] = False
    await set_job(job_id, job)
    
    # Start background thread to continue analysis
    temp_pdf_path = job.get("temp_pdf_path")
    filename = job.get("filename")
    
    if not temp_pdf_path or not filename:
        raise HTTPException(status_code=500, detail="Job missing required file information")
    
    logging.info(f"[CONFIRM_TYPE] Resuming analysis with report_type={confirmed_type}")
    thread = threading.Thread(
        target=run_analysis_job,
        args=(job_id, temp_pdf_path, filename, confirmed_type, db, True)  # resume=True
    )
    thread.start()
    
    return {
        "message": "Report type confirmed, analysis resuming",
        "job_id": job_id,
        "confirmed_type": confirmed_type,
        "confirmed_subtype": confirmed_subtype
    }

# New endpoint: poll job status
@app.get("/analyze/status/{job_id}")
async def get_job_status(job_id: str):
    import logging
    # Remove or downgrade excessive logging for status checks
    # print(f"[PRINT] get_job_status called for job_id={job_id}")
    logging.info(f"[INFO] get_job_status: called for job_id={job_id}")
    job = await get_job(job_id)
    if not job:
        # Distinguish true miss vs transient Redis issue by a second quick guarded fetch
        transient = False
        try:
            _ = await get_job(job_id)
        except Exception:
            transient = True
        logging.error(f"[ERROR] get_job_status: job_id={job_id} NOT FOUND (transient={transient})")
        return {"error": "Job not found", "transient_unavailable": transient}
    # Remove detailed job state logging for status checks
    # print(f"[PRINT] get_job_status: job_id={job_id}, job={job}")
    # logging.info(f"[INFO] get_job_status: job_id={job_id}, job={job}")
    # print(f"[PRINT] get_job_status fields: progress={job.get('progress')}, checklist={job.get('checklist')}, status={job.get('status')}, done={job.get('done')}, error={job.get('error')}, filename={job.get('filename')}")
    # logging.info(f"[INFO] get_job_status fields: progress={job.get('progress')}, checklist={job.get('checklist')}, status={job.get('status')}, done={job.get('done')}, error={job.get('error')}, filename={job.get('filename')}")
    # Build artifacts presence and counts; keep mid-run path ultra-lightweight to avoid disk I/O
    artifacts = None
    counts = None
    if job.get("done"):
        artifacts = _artifact_presence()
        result_obj = job.get("result") or {}
        counts = _result_counts_from_obj(result_obj) if result_obj else _result_counts_from_disk()
    
    # Calculate elapsed time
    import time
    elapsed_seconds = 0
    start_time = job.get("start_time")
    if start_time:
        elapsed_seconds = int(time.time() - start_time)
    
    # Extract new progress fields with graceful defaults
    identified_entities = job.get("identified_entities", {})
    counters = job.get("counters", {
        "controls_count": 0,
        "controls_total_estimate": 0,
        "controls_percent": 0,
        "controls_mapped_count": 0,
        "controls_mapped_percent": 0,
        "subservice_orgs_count": 0,
        "cuecs_count": 0
    })
    phase_completion = job.get("phase_completion", {
        "logo_fetched": False,
        "cleanup_complete": False,
        "db_uploaded": False
    })
    extraction_partial = job.get("extraction_partial", False)
    
    return {
        "status": job.get("status"),
        "progress": job.get("progress"),
        "done": job.get("done"),
        "error": job.get("error"),
        "checklist": job.get("checklist", []),
        "filename": job.get("filename"),
        "finalized": bool(job.get("finalized", False) or str(job.get("status", "")).lower().startswith("finalized")),
        "artifacts": artifacts,
        "counts": counts,
        "transient_unavailable": False,
        # New real-time progress fields
        "elapsed_seconds": elapsed_seconds,
        "identified_entities": identified_entities,
        "counters": counters,
        "phase_completion": phase_completion,
        "extraction_partial": extraction_partial,
        # Debug payload removed to reduce response size and avoid client timeouts
    }

# Ultra-lightweight status endpoint to use during active scans
@app.get("/analyze/status_min/{job_id}")
async def get_job_status_min(job_id: str, include_artifacts: bool = False):
    """Ultra-lightweight status endpoint.

    Now returns counts and checklist mid-run so the UI can render progress bars without
    needing the heavier /analyze/status endpoint. Disk counts are inexpensive small file loads.
    Artifacts presence is optional (include_artifacts=true) or automatically included when done.
    """
    job = await get_job(job_id)
    if not job:
        # best-effort transient flag on redis access race
        transient = False
        try:
            _ = await get_job(job_id)
        except Exception:
            transient = True
        return {"error": "Job not found", "transient_unavailable": transient}
    # Lightweight counts from disk OR embedded result if already present
    result_obj = job.get("result") or {}
    counts = _result_counts_from_obj(result_obj) if result_obj else _result_counts_from_disk()
    # Checklist preserved in job dict for stepper
    checklist = job.get("checklist", [])
    artifacts = None
    if job.get("done") or include_artifacts:
        artifacts = _artifact_presence()
    
    # Calculate elapsed time
    import time
    elapsed_seconds = 0
    start_time = job.get("start_time")
    if start_time:
        elapsed_seconds = int(time.time() - start_time)
    
    # Extract new progress fields with graceful defaults
    identified_entities = job.get("identified_entities", {})
    counters = job.get("counters", {
        "controls_count": 0,
        "controls_total_estimate": 0,
        "controls_percent": 0,
        "controls_mapped_count": 0,
        "controls_mapped_percent": 0,
        "subservice_orgs_count": 0,
        "cuecs_count": 0
    })
    phase_completion = job.get("phase_completion", {
        "logo_fetched": False,
        "cleanup_complete": False,
        "db_uploaded": False
    })
    extraction_partial = job.get("extraction_partial", False)
    # Optional line-based progress (e.g., control extraction advancing through section)
    def _line_progress():
        try:
            proj_root = pathlib.Path(__file__).resolve().parents[2]
            json_dir = proj_root / 'data' / 'json'
            progress = {}
            ctrl_path = json_dir / 'control_progress.json'
            if ctrl_path.exists():
                with open(ctrl_path, 'r', encoding='utf-8') as f:
                    meta = _json.load(f)
                s = meta.get('section_start_line')
                e = meta.get('section_end_line')
                cur = meta.get('current_line')
                pct = None
                if isinstance(s, int) and isinstance(e, int) and isinstance(cur, int) and e > s:
                    pct = round(((cur - s) / (e - s)) * 100, 2)
                progress['controls'] = {
                    'section_start_line': s,
                    'section_end_line': e,
                    'current_line': cur,
                    'percent_complete': pct,
                    'extracted_controls': meta.get('extracted_controls'),
                }
            return progress
        except Exception as _lp_err:
            logging.warning(f"[status_min] line progress error: {_lp_err}")
            return {}
    line_progress = _line_progress()
    return {
        "status": job.get("status"),
        "progress": job.get("progress"),
        "done": job.get("done"),
        "error": job.get("error"),
        "counts": counts,
        "checklist": checklist,
        "artifacts": artifacts,
        "report_type": job.get("report_type"),  # Added for frontend report type display
        "detected_report_type": job.get("detected_report_type"),  # Early detection result
        "detected_subtype": job.get("detected_subtype"),  # Type 1 or Type 2
        "detection_confidence": job.get("detection_confidence"),  # Confidence score
        "awaiting_confirmation": job.get("awaiting_confirmation"),  # User confirmation needed
        "detection_result": job.get("detection_result"),  # Full detection result for confirmation
        "transient_unavailable": False,
        "line_progress": line_progress,
        # New real-time progress fields
        "elapsed_seconds": elapsed_seconds,
        "identified_entities": identified_entities,
        "counters": counters,
        "phase_completion": phase_completion,
        "extraction_partial": extraction_partial,
    }

# New endpoint: get job result
@app.get("/analyze/result/{job_id}")
async def get_job_result(job_id: str, force_save: bool = False, format: Optional[str] = None, request: Request = None, db=Depends(get_db)):
    """Return analysis results with content negotiation.

    Behavior:
    - If force_save (or not yet saved) persists result to DB first.
    - Honors format=text or format=summary even on first (persisting) call.
    - format=text => raw extracted_text only (text/plain)
    - format=summary => compact JSON: counts, artifacts, keys, finalized (+ optional insert_summary if just saved)
    - default => full results JSON.
    """
    job = await get_job(job_id)
    if not job:
        return {"error": "Job not found"}
    if not job.get("done"):
        return {"error": "Job not finished yet"}

    # Pre-calc negotiation flags early so we can honor them after persistence
    fmt = (format or "").lower().strip()
    accept = (request.headers.get("accept") if request else "")
    wants_text = (fmt == "text") or ("text/plain" in (accept or ""))
    wants_summary = (fmt == "summary") or ("application/summary+json" in (accept or ""))

    # Persist to DB if not saved yet or force_save requested
    insert_summary = None
    if (force_save or not job.get("db_saved")) and job.get("result"):
        import tempfile, json as _json
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmpf:
            _json.dump(job["result"], tmpf, ensure_ascii=False)
            tmpf.flush()
            tmp_path = tmpf.name
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            insert_summary = await loop.run_in_executor(pool, insert_extracted_data, tmp_path)
        job["db_saved"] = True
        await set_job(job_id, job)

    # If there was an error, return it along with any partial result
    if job.get("error"):
        return {"error": job.get("error"), "partial_result": job.get("result")}

    res_obj = job.get("result") or {}

    if wants_text:
        from starlette.responses import Response
        text = res_obj.get("extracted_text") or ""
        return Response(content=text, media_type="text/plain; charset=utf-8")

    if wants_summary:
        summary_payload = {
            "counts": _result_counts_from_obj(res_obj),
            "artifacts": _artifact_presence(),
            "keys": sorted(list(res_obj.keys())),
            "finalized": bool(job.get("finalized", False) or str(job.get("status", "")).lower().startswith("finalized")),
        }
        if insert_summary is not None:
            # Include minimal DB insertion confirmation without dumping large result
            summary_payload["db_inserted"] = True
            summary_payload["insert_summary"] = insert_summary
        return summary_payload

    # Default: full JSON results (backward compatible); include insert_summary if applicable
    default_response = {"results": res_obj}
    if insert_summary is not None:
        default_response["insert_summary"] = insert_summary
        default_response["summary"] = {
            "counts": _result_counts_from_obj(res_obj),
            "artifacts": _artifact_presence(),
        }
    return default_response

# (Removed duplicate earlier /analyze/resume route that only finalized from artifacts.)

# Analysis utility functions moved to services/analysis_service.py
_build_combined_results_from_disk = analysis_service.build_combined_results_from_disk


@app.post("/analyze/finalize/{job_id}")
async def finalize_job_from_disk(job_id: str, force_save: bool = True, db=Depends(get_db)):
    """Rebuild job results from extractor JSONs on disk and mark the job done.

    Useful when a background job was interrupted but individual extractor outputs exist.
    """
    # Build result object from disk
    results = _build_combined_results_from_disk()
    if not results:
        return JSONResponse({"error": "No extractor outputs found on disk"}, status_code=404)

    # Try to persist to DB (optional)
    insert_summary = None
    scan_id_for_learning = None
    if force_save:
        try:
            import tempfile
            # Filter out pdf_file bytes before JSON serialization
            results_for_db = {k: v for k, v in results.items() if k != 'pdf_file'}
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmpf:
                _json.dump(results_for_db, tmpf, ensure_ascii=False)
                tmpf.flush()
                tmp_path = tmpf.name
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                insert_summary = await loop.run_in_executor(pool, insert_extracted_data, tmp_path)
            
            # After successful insertion, learn patterns from this scan
            if insert_summary and insert_summary.get("control", 0) > 0:
                try:
                    # Get scan_id from the latest scan (just inserted)
                    scan_result = await db.execute(
                        select(Scan).order_by(Scan.id.desc()).limit(1)
                    )
                    latest_scan = scan_result.scalar_one_or_none()
                    
                    if latest_scan:
                        scan_id_for_learning = latest_scan.id
                        
                        # Run automated cleanup first (if enabled)
                        if config.ENABLE_AUTO_MERGE:
                            try:
                                cleanup_stats = await automated_cleanup(scan_id_for_learning, db)
                                if cleanup_stats:
                                    logging.info(f"[/analyze/finalize] Automated cleanup complete: {cleanup_stats}")
                            except Exception as cleanup_err:
                                logging.warning(f"[/analyze/finalize] Automated cleanup failed: {cleanup_err}")
                        else:
                            logging.info(f"[/analyze/finalize] Automated cleanup disabled (ENABLE_AUTO_MERGE=false)")
                        
                        # Apply incomplete control penalties
                        try:
                            penalty_count = await penalize_incomplete_controls(scan_id_for_learning, db)
                            logging.info(f"[/analyze/finalize] Incomplete control penalties applied: {penalty_count} controls")
                        except Exception as penalty_err:
                            logging.warning(f"[/analyze/finalize] Incomplete control penalties failed: {penalty_err}")
                        
                        # Generate deviation summaries for high-confidence controls (unless deferred)
                        if not cfg.DEFER_DEVIATION_SUMMARY:
                            try:
                                from .post_processors.deviation_summarizer import generate_summaries
                                import redis.asyncio as aioredis
                                
                                redis_client_deviation = None
                                try:
                                    redis_client_deviation = aioredis.from_url("redis://socanalyzer-redis:6379", decode_responses=True)
                                except Exception as redis_err:
                                    logging.warning(f"[/analyze/finalize] Redis not available for deviation summaries: {redis_err}")
                                
                                deviation_stats = await generate_summaries(scan_id_for_learning, db, redis_client_deviation)
                                logging.info(f"[/analyze/finalize] Deviation summaries generated: {deviation_stats}")
                                
                                if redis_client_deviation:
                                    await redis_client_deviation.close()
                            except Exception as deviation_err:
                                logging.warning(f"[/analyze/finalize] Deviation summary generation failed: {deviation_err}")
                        else:
                            logging.info(f"[/analyze/finalize] Deviation summary generation deferred (DEFER_DEVIATION_SUMMARY=true)")
                        
                        # Then run pattern learning
                        from .services.verification_service import ControlVerificationService
                        
                        service = ControlVerificationService()
                        learning_stats = await service.learn_patterns_from_scan(
                            scan_id_for_learning, 
                            db
                        )
                        logging.info(f"[/analyze/finalize] Pattern learning complete: {learning_stats}")
                except Exception as learn_err:
                    logging.warning(f"[/analyze/finalize] Pattern learning failed: {learn_err}")
                    # Don't fail the finalize if pattern learning fails
        except Exception as e:
            logging.error(f"[/analyze/finalize] DB insertion failed: {e}")

    # Update job in Redis and broadcast done
    redis_client = _get_redis()
    job = await get_job(job_id, redis_client) or {}
    # Filter out pdf_file bytes before storing in Redis
    results_for_redis = {k: v for k, v in results.items() if k != 'pdf_file'}
    job["result"] = results_for_redis
    job["done"] = True
    job["error"] = None
    job["db_saved"] = bool(insert_summary) if force_save else job.get("db_saved", False)
    job["progress"] = 100
    job["status"] = "Finalized from disk"
    job["finalized"] = True
    await set_job(job_id, job, redis_client)
    try:
        await broadcast_progress(100, "Finalized from disk")
        await broadcast_done()
    except Exception:
        pass
    resp = {"results": results}
    if insert_summary is not None:
        resp["insert_summary"] = insert_summary
    return resp

# --- Resume selected extractors and rebuild combined results ---
from pydantic import BaseModel

class ResumeRequest(BaseModel):
    # Allow omitted/empty extractors to trigger finalize-from-disk behavior
    extractors: Optional[list[str]] = None
    force_save: Optional[bool] = False
    start_at_control: Optional[int] = None  # granular resume: control sequence index to resume from
    start_at_line: Optional[int] = None     # granular resume: starting line number within control section

@app.post("/analyze/resume/{job_id}")
async def resume_extractors(job_id: str, payload: ResumeRequest, db=Depends(get_db)):
    """Rerun one or more extractors and refresh combined_result.json and job result.

    Valid extractor names: controls, cuecs, subservice_orgs, product, auditor, company, report_date, coverage_period
    """
    valid = {
        "controls": "control_extraction",
        "cuecs": "cuec_extraction",
        "subservice_orgs": "subservice_orgs_extraction",
        "product": "product_extraction",
        "auditor": "auditor_extraction",
        "company": "company_extraction",
        "report_date": "report_date_extraction",
        "coverage_period": "coverage_period_extraction",
    }
    requested = [e for e in (payload.extractors or []) if e in valid]
    # Persist granular resume hints in job for downstream extractor usage
    try:
        redis_client = _get_redis()
        job = await get_job(job_id, redis_client) or {}
        if payload.start_at_control is not None:
            job['resume_start_at_control'] = int(payload.start_at_control)
        if payload.start_at_line is not None:
            job['resume_start_at_line'] = int(payload.start_at_line)
        if payload.start_at_control is not None or payload.start_at_line is not None:
            await set_job(job_id, job, redis_client)
    except Exception as _gran_err:
        logging.warning(f"[resume] Failed to persist granular resume params: {_gran_err}")
    if not requested:
        # No extractors provided: finalize from disk artifacts (backward compatible behavior)
        try:
            results = _build_combined_results_from_disk()
            redis_client = _get_redis()
            job = await get_job(job_id, redis_client) or {}
            # Filter out pdf_file bytes before storing in Redis
            results_for_redis = {k: v for k, v in results.items() if k != 'pdf_file'}
            job["result"] = results_for_redis
            job["done"] = True
            job["error"] = None
            job["progress"] = 100
            job["status"] = "Finalized from disk"
            job["finalized"] = True
            if payload.force_save:
                try:
                    import tempfile
                    # Filter out pdf_file bytes before JSON serialization
                    results_for_db = {k: v for k, v in results.items() if k != 'pdf_file'}
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmpf:
                        _json.dump(results_for_db, tmpf, ensure_ascii=False)
                        tmpf.flush()
                        tmp_path = tmpf.name
                    loop = asyncio.get_event_loop()
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        insert_summary = await loop.run_in_executor(pool, insert_extracted_data, tmp_path)
                    job["db_saved"] = True
                    await set_job(job_id, job, redis_client)
                    await broadcast_progress(100, job["status"])
                    return {"status": "ok", "results": results, "insert_summary": insert_summary}
                except Exception as e:
                    logging.error(f"[/analyze/resume finalize] DB insertion failed: {e}")
            await set_job(job_id, job, redis_client)
            await broadcast_progress(100, job["status"])
            return {"status": "ok", "results": results}
        except Exception as e:
            logging.error(f"[/analyze/resume finalize] Failed: {e}\n{traceback.format_exc()}")
            return JSONResponse({"error": str(e)}, status_code=500)

    # Run the selected extractors synchronously
    try:
        from .extractors.control_extractor import extract_controls
        from .extractors.cuec_extractor import extract_cuecs
        from .extractors.subservice_orgs import extract_subservice_orgs, filter_third_parties_with_gpt
        from .extractors.product import extract_product_from_report
        from .extractors.auditor import extract_auditor_from_report
        from .extractors.company import extract_company_from_report
        from .extractors.report_date import extract_report_date
        from .extractors.coverage_period import extract_coverage_period
        ran = {}
        for name in requested:
            if name == "controls":
                # Pass granular start hints if available
                # Refresh latest job snapshot including granular hints and report type
                redis_client = _get_redis()
                job = await get_job(job_id, redis_client) or {}
                start_at_line = job.get('resume_start_at_line')
                report_type = job.get('report_type', 'SOC2')  # Default to SOC2 if not set
                
                # Load section results for unified extractor
                try:
                    import json as _json_module
                    with open(data_path('data/json/section_results.json'), 'r', encoding='utf-8') as sf:
                        sections = _json_module.load(sf)
                except Exception as section_err:
                    logging.error(f"Failed to load section_results.json: {section_err}")
                    sections = []
                
                # Call unified extractor with report type and sections
                try:
                    ran[name] = extract_controls(
                        sections=sections,
                        report_type=report_type,
                        enable_assertion_mapping=False,  # Can be enabled based on config or user preference
                        start_at_line=start_at_line
                    )
                except TypeError as te:
                    # Fallback to minimal signature if something is wrong
                    logging.error(f"extract_controls signature error: {te}, trying minimal call")
                    ran[name] = extract_controls(sections=sections, report_type=report_type)
            elif name == "cuecs":
                ran[name] = extract_cuecs()
            elif name == "subservice_orgs":
                # returns tuple (raw, postprocessed)
                ran[name] = (extract_subservice_orgs(), filter_third_parties_with_gpt())
            elif name == "product":
                ran[name] = extract_product_from_report()
            elif name == "auditor":
                ran[name] = extract_auditor_from_report()
            elif name == "company":
                ran[name] = extract_company_from_report()
            elif name == "report_date":
                ran[name] = extract_report_date()
            elif name == "coverage_period":
                ran[name] = extract_coverage_period()
        # Rebuild combined results from disk outputs
        results = _build_combined_results_from_disk()
        redis_client = _get_redis()
        job = await get_job(job_id, redis_client) or {}
        # Filter out pdf_file bytes before storing in Redis
        results_for_redis = {k: v for k, v in results.items() if k != 'pdf_file'}
        job["result"] = results_for_redis
        job["status"] = f"Resumed extractors: {', '.join(requested)}"
        job["done"] = True
        job["progress"] = 100
        job["finalized"] = False  # job is now from fresh extractors
        if payload.force_save:
            # Optionally re-insert into DB (may create duplicates if the same scan already saved)
            try:
                import tempfile
                # Filter out pdf_file bytes before JSON serialization
                results_for_db = {k: v for k, v in results.items() if k != 'pdf_file'}
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmpf:
                    _json.dump(results_for_db, tmpf, ensure_ascii=False)
                    tmpf.flush()
                    tmp_path = tmpf.name
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    insert_summary = await loop.run_in_executor(pool, insert_extracted_data, tmp_path)
                job["db_saved"] = True
                await set_job(job_id, job, redis_client)
                await broadcast_progress(100, job["status"])
                return {"status": "ok", "results": results, "insert_summary": insert_summary}
            except Exception as e:
                logging.error(f"[/analyze/resume] DB insertion failed: {e}")
        await set_job(job_id, job, redis_client)
        await broadcast_progress(100, job["status"])
        return {"status": "ok", "results": results}
    except Exception as e:
        logging.error(f"[/analyze/resume] extractor run failed: {e}\n{traceback.format_exc()}")
        return JSONResponse({"error": str(e)}, status_code=500)

# Progressive partial controls endpoint
@app.get("/analyze/controls_partial/{job_id}")
async def get_partial_controls(job_id: str, min_pct: float = 20.0, limit: int = 0):
    """Expose partial controls mid-run with completion percentage.
    - min_pct: threshold at which frontends may decide to show the panel (informational only here)
    - limit: truncate the returned list to the first N controls if > 0
    """
    job = await get_job(job_id)
    if not job:
        return {"error": "Job not found"}
    try:
        import os, json
        # Use centralized config path; ensure string for os.path.exists
        path = str(cfg.CONTROL_JSON_PATH)
        if not os.path.exists(path):
            return {"controls": [], "count": 0, "completion_pct": 0.0, "estimated_total": None}
        controls = []
        data = None
        # Attempt strict JSON parse first; if it fails (mid-run streaming file), fall back to tolerant line parser
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            controls = (data or {}).get('controls') or []
        except Exception:
            # Tolerant streaming reader: treat each line starting with '{' or ',{' as one JSON object
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        ls = line.lstrip()
                        if not ls:
                            continue
                        # Skip opening placeholder lines like []
                        if ls.startswith('[]') or ls.startswith('[') or ls.startswith(']'):
                            continue
                        if ls.startswith('{') or ls.startswith(',{'):
                            js = ls.lstrip(',').rstrip().rstrip(',')
                            try:
                                obj = json.loads(js)
                                controls.append(obj)
                            except Exception:
                                # Best effort only; skip malformed fragment
                                continue
            except Exception as e_stream:
                logging.error(f"[/analyze/controls_partial] tolerant parse failed: {e_stream}")
                controls = []
        minimal = [
            {
                'control_seq': c.get('control_seq'),
                'control_id': c.get('control_id'),
                'control_desc': c.get('control_desc'),
                'has_deviation': c.get('has_deviation'),
            }
            for c in controls
            if (c.get('control_id') or c.get('control_desc'))
        ]
        if limit > 0:
            minimal = minimal[:limit]
        est_total = job.get('controls_estimate')
        completion_pct = None
        if isinstance(est_total, int) and est_total > 0:
            completion_pct = round(100.0 * len(controls) / est_total, 2)
        else:
            # fallback heuristic: assume 100 controls for scaling when unknown
            completion_pct = round(min(100.0, len(controls)), 2) if len(controls) <= 100 else 100.0
        return {
            'controls': minimal,
            'count': len(minimal),
            'total_parsed': len(controls),
            'completion_pct': completion_pct,
            'estimated_total': est_total,
            'finalized': bool(job.get('finalized')),
            'threshold_met': completion_pct >= float(min_pct)
        }
    except Exception as e:
        logging.error(f"[/analyze/controls_partial] error: {e}\n{traceback.format_exc()}")
        return JSONResponse({"error": str(e)}, status_code=500)

# Set up backend error logging
import pathlib
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
os.makedirs(PROJECT_ROOT / 'data/logs', exist_ok=True)
backend_log_path = str(PROJECT_ROOT / 'data/logs/backend_errors.log')
# Clear the log file at startup
with open(backend_log_path, 'w', encoding='utf-8'):
    pass
# Set up a human-readable log format
log_format = '\n%(asctime)s | %(levelname)s | %(module)s | %(message)s\n' + ('-'*80)
root_logger = logging.getLogger()
root_logger.setLevel(logging.ERROR)
# Remove all handlers first (avoid duplicate logs on reload)
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)
file_handler = logging.FileHandler(backend_log_path, encoding='utf-8')
file_handler.setFormatter(logging.Formatter(log_format))
root_logger.addHandler(file_handler)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter(log_format))
root_logger.addHandler(stream_handler)

## (Removed duplicate FastAPI app definition and CORS middleware)
WEBSOCKET_CLIENTS = set()
@app.websocket("/ws")
async def websocket_progress(websocket: WebSocket):
    await websocket.accept()
    WEBSOCKET_CLIENTS.add(websocket)
    try:
        logging.info(f"WebSocket client connected: {websocket.client}")
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=10)
                logging.info(f"WebSocket message received: {msg}")
            except asyncio.TimeoutError:
                # No message, just keep alive
                pass
    except WebSocketDisconnect:
        logging.info(f"WebSocket client disconnected: {websocket.client}")
        WEBSOCKET_CLIENTS.remove(websocket)
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
        WEBSOCKET_CLIENTS.remove(websocket)

# Helper to broadcast progress to all clients
import asyncio
async def broadcast_progress(percent: int, status: Optional[str] = None):
    msg = {"type": "progress", "percent": percent}
    if status:
        msg["status"] = status
    for ws in list(WEBSOCKET_CLIENTS):
        try:
            await ws.send_json(msg)
        except Exception:
            pass

async def broadcast_done():
    for ws in list(WEBSOCKET_CLIENTS):
        try:
            await ws.send_json({"type": "done"})
        except Exception:
            pass

async def broadcast_checklist(extractor_statuses):
    msg = {"type": "extractor_status", "extractors": extractor_statuses}
    for ws in list(WEBSOCKET_CLIENTS):
        try:
            await ws.send_json(msg)
        except Exception:
            pass

# Settings endpoints
@app.get("/settings")
async def get_settings(request: Request, db=Depends(get_db)):
    # Content negotiation: if browser navigates to /settings expecting HTML, serve SPA index
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        # Serve the React app to avoid UI/API route collision when deep-linking
        FRONTEND_INDEX = PROJECT_ROOT / 'frontend' / 'build' / 'index.html'
        if FRONTEND_INDEX.exists():
            return FileResponse(str(FRONTEND_INDEX))
        return JSONResponse({"error": "UI build not found"}, status_code=404)
    # API JSON response for programmatic clients
    result = await db.execute(select(Setting))
    rows = result.scalars().all()
    return {row.key: row.value for row in rows}

@app.post("/settings")
async def update_settings(request: Request, db=Depends(get_db)):
    data = await request.json()
    logging.debug(f"/settings payload: {data}")
    try:
        for key, value in data.items():
            stmt = pg_dialect.insert(Setting).values(key=key, value=str(value)).on_conflict_do_update(
                index_elements=[Setting.key], set_={"value": str(value)}
            )
            await db.execute(stmt)
        await db.commit()
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        logging.error(f"/settings DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# Runtime config introspection endpoints
@app.get("/config/runtime")
async def get_runtime_config():
    from . import config as cfg
    return {
        "model": {
            "default_model": cfg.DEFAULT_GPT_MODEL,
            "provider": cfg.LLM_PROVIDER,
            "temperature": cfg.DEFAULT_TEMPERATURE,
            "top_p": cfg.DEFAULT_TOP_P,
        },
        "token_windows": {
            "max_total_tokens": cfg.MAX_TOTAL_TOKENS,
            "max_output_tokens": cfg.MAX_OUTPUT_TOKENS,
            "max_input_tokens": cfg.MAX_INPUT_TOKENS,
        },
        "budgets": {
            "system_tokens": cfg.GPT_SYSTEM_TOKENS,
            "user_tokens": cfg.GPT_USER_TOKENS,
            "response_tokens": cfg.GPT_RESPONSE_TOKENS,
            "available_tokens": cfg.GPT_AVAILABLE_TOKENS,
        },
        "chunking": {
            "chars_per_token": cfg.CHARS_PER_TOKEN,
            "default_chunk_size": cfg.DEFAULT_CHUNK_SIZE,
            "primary_chunk_size": cfg.PRIMARY_CHUNK_SIZE,
            "description_chunk_size": cfg.DESCRIPTION_CHUNK_SIZE,
            "subservice_chunk_size": cfg.SUBSERVICE_CHUNK_SIZE,
            "max_chunk_size": cfg.MAX_CHUNK_SIZE,
            "text_overlap": cfg.TEXT_OVERLAP,
        },
        "executive_summary": {
            "test_results_budget_chars": cfg.EXEC_SUMMARY_TEST_RESULTS_BUDGET_CHARS,
            "per_control_max_chars": cfg.EXEC_SUMMARY_PER_CONTROL_MAX_CHARS,
            "max_non_deviation_controls": cfg.EXEC_SUMMARY_MAX_NON_DEVIATION_CONTROLS,
        },
        "thresholds": {
            "high_confidence_threshold": cfg.HIGH_CONFIDENCE_THRESHOLD,
            "merge_suggestion_min_confidence": cfg.MERGE_SUGGESTION_MIN_CONFIDENCE,
            "auto_merge_min_confidence": cfg.AUTO_MERGE_MIN_CONFIDENCE,
        },
        "help": {
            "version": "5.0.0",
            "last_updated": "2025-12-03"
        },
        "feature_toggles": {
            "allow_regex_fallbacks": cfg.ALLOW_REGEX_FALLBACKS,
            "control_embedding_mapping_enabled": cfg.CONTROL_EMBEDDING_MAPPING_ENABLED,
            "docker_control_enabled": cfg.DOCKER_CONTROL_ENABLED,
            "quick_test_mode_enabled": cfg.QUICK_TEST_MODE_ENABLED,
        },
        "quick_test": {
            "enabled": cfg.QUICK_TEST_MODE_ENABLED,
            "max_controls": cfg.QUICK_TEST_MAX_CONTROLS,
        }
    }

@app.get("/config/budgets")
async def get_budget_snapshot():
    from . import config as cfg
    return {
        "timestamp": time.time(),
        "model": cfg.DEFAULT_GPT_MODEL,
        "token_window": cfg.MAX_TOTAL_TOKENS,
        "input_tokens_budget": cfg.MAX_INPUT_TOKENS,
        "output_tokens_budget": cfg.MAX_OUTPUT_TOKENS,
        "available_tokens_after_overheads": cfg.GPT_AVAILABLE_TOKENS,
        "derived_chunk_sizes": {
            "default": cfg.DEFAULT_CHUNK_SIZE,
            "primary": cfg.PRIMARY_CHUNK_SIZE,
            "description": cfg.DESCRIPTION_CHUNK_SIZE,
            "subservice": cfg.SUBSERVICE_CHUNK_SIZE,
        },
        "overlap_chars": cfg.TEXT_OVERLAP,
        "chars_per_token": cfg.CHARS_PER_TOKEN,
    }

@app.post("/config/quick-test-mode")
async def toggle_quick_test_mode(request: Request):
    """Toggle quick test mode by updating .env file"""
    from pathlib import Path
    import os
    
    try:
        data = await request.json()
        enabled = data.get("enabled", False)
        max_controls = data.get("max_controls", 10)
        
        # Find .env file
        env_file = Path(os.getenv("ENV_FILE_PATH", ".env"))
        if not env_file.is_absolute():
            # Try project root
            env_file = Path(__file__).parent.parent.parent / ".env"
        
        if not env_file.exists():
            return JSONResponse({"error": ".env file not found"}, status_code=404)
        
        # Read current content
        content = env_file.read_text(encoding='utf-8')
        
        # Remove existing settings
        import re
        content = re.sub(r'(?m)^QUICK_TEST_MODE=.*$', '', content)
        content = re.sub(r'(?m)^QUICK_TEST_MAX_CONTROLS=.*$', '', content)
        content = re.sub(r'(?m)^\s*# Quick Test Mode.*$', '', content)
        content = content.strip()
        
        # Add new settings if enabled
        if enabled:
            content += f"\n\n# Quick Test Mode - Extract limited controls for faster testing\nQUICK_TEST_MODE=true\nQUICK_TEST_MAX_CONTROLS={max_controls}\n"
        
        # Write back
        env_file.write_text(content, encoding='utf-8')
        
        return {
            "status": "ok",
            "enabled": enabled,
            "max_controls": max_controls if enabled else None,
            "message": "Settings updated. Backend restart required for changes to take effect.",
            "requires_restart": True
        }
    except Exception as e:
        logging.error(f"Error toggling quick test mode: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# Help system endpoints
@app.get("/help/index")
async def get_help_index():
    """Get help topics index/manifest"""
    import json
    from pathlib import Path
    
    try:
        help_index_path = Path(__file__).parent.parent.parent / "docs" / "help" / "index.json"
        with open(help_index_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading help index: {e}")
        raise HTTPException(status_code=500, detail="Help index not found")

@app.get("/help/content/{topic_id}")
async def get_help_content(topic_id: str):
    """Get markdown content for a specific help topic"""
    import json
    from pathlib import Path
    
    try:
        # Load index to validate topic and get file path
        help_dir = Path(__file__).parent.parent.parent / "docs" / "help"
        index_path = help_dir / "index.json"
        
        with open(index_path, 'r', encoding='utf-8') as f:
            index = json.load(f)
        
        # Find topic in index
        topic_file = None
        for category in index['categories']:
            for topic in category['topics']:
                if topic['id'] == topic_id:
                    topic_file = topic['filePath']
                    break
            if topic_file:
                break
        
        if not topic_file:
            raise HTTPException(status_code=404, detail="Help topic not found")
        
        # Read markdown file
        content_path = help_dir / topic_file
        
        # Security: ensure path is within help directory
        if not str(content_path.resolve()).startswith(str(help_dir.resolve())):
            raise HTTPException(status_code=403, detail="Invalid topic path")
        
        with open(content_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return Response(content=content, media_type="text/markdown")
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error loading help content for {topic_id}: {e}")
        raise HTTPException(status_code=500, detail="Help content not found")

# Docker control endpoints (guarded)
def _run_docker_cmd(args):
    import subprocess
    try:
        out = subprocess.check_output(args, stderr=subprocess.STDOUT, timeout=12).decode("utf-8", errors="replace")
        return {"ok": True, "output": out}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "output": e.output.decode("utf-8", errors="replace"), "code": e.returncode}
    except Exception as e:
        return {"ok": False, "output": str(e)}

@app.get("/docker/status")
async def docker_status():
    if not DOCKER_CONTROL_ENABLED:
        return JSONResponse({"error": "Docker control disabled"}, status_code=403)
    # Include stopped containers too so UI can present Start actions
    result = _run_docker_cmd(["docker", "ps", "-a", "--format", "{{.Names}}::{{.Status}}"])
    if not result["ok"]:
        return JSONResponse({"error": result["output"]}, status_code=500)
    services = []
    for line in result["output"].strip().splitlines():
        if "::" in line:
            name, status = line.split("::", 1)
            services.append({"name": name, "status": status})
    return {"services": services}

@app.post("/docker/stop/{container}")
async def docker_stop(container: str):
    if not DOCKER_CONTROL_ENABLED:
        return JSONResponse({"error": "Docker control disabled"}, status_code=403)
    result = _run_docker_cmd(["docker", "stop", container])
    if not result["ok"]:
        return JSONResponse({"error": result["output"]}, status_code=500)
    return {"status": "stopped", "container": container}

@app.post("/docker/restart/{container}")
async def docker_restart(container: str):
    if not DOCKER_CONTROL_ENABLED:
        return JSONResponse({"error": "Docker control disabled"}, status_code=403)
    result = _run_docker_cmd(["docker", "restart", container])
    if not result["ok"]:
        return JSONResponse({"error": result["output"]}, status_code=500)
    return {"status": "restarted", "container": container}

@app.post("/docker/start/{container}")
async def docker_start(container: str):
    if not DOCKER_CONTROL_ENABLED:
        return JSONResponse({"error": "Docker control disabled"}, status_code=403)
    result = _run_docker_cmd(["docker", "start", container])
    if not result["ok"]:
        return JSONResponse({"error": result["output"]}, status_code=500)
    return {"status": "started", "container": container}

# History endpoints
@app.get("/history")
async def get_history(limit: int = 100, db=Depends(get_db)):
    """
    Get scan history with minimal metadata for dropdown/list.
    Excludes heavy result_json field for performance.
    
    Args:
        limit: Maximum number of scans to return (default 100, max 500)
    """
    # Cap limit to prevent excessive queries
    limit = min(max(1, limit), 500)
    
    # Get scans with optimized query
    result = await db.execute(
        select(Scan)
        .order_by(Scan.scan_date.desc())
        .limit(limit)
    )
    scan_rows = result.scalars().all()
    
    history = []
    for row in scan_rows:
        # Get company name for this scan
        # Order by confidence DESC, id DESC to get the most confident/recent company record
        company_result = await db.execute(
            select(Company)
            .where(Company.scan_id == row.id)
            .order_by(Company.confidence.desc().nullslast(), Company.id.desc())
            .limit(1)
        )
        company_row = company_result.scalar_one_or_none()
        company_name = company_row.name if company_row else None
        company_domain = company_row.company_domain if company_row else None
        logo_url = company_row.logo_url if company_row else None
        
        history.append({
            "id": row.id,
            "timestamp": row.scan_date.isoformat() if row.scan_date else None,
            "filename": row.pdf_filename,
            "product": row.product,
            "company": company_name,
            "company_domain": company_domain,
            "logo_url": logo_url,
            "coverage_start": row.coverage_start.date().isoformat() if row.coverage_start else None,
            "coverage_end": row.coverage_end.date().isoformat() if row.coverage_end else None,
            "report_date": row.report_date.isoformat() if row.report_date else None,
            "report_type": row.report_type.value if row.report_type else "SOC2"
            # Note: result_json excluded for performance - use /report/{scan_id} for full data
        })
    
    return history

@app.get("/report_diag/{scan_id}")
async def report_diag(scan_id: int):
    try:
        logging.error(f"[REPORT_DIAG] Entered report_diag with scan_id={scan_id}")
        return {"ok": True, "scan_id": scan_id}
    except Exception as e:
        logging.error(f"[REPORT_DIAG] error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/report/{scan_id}")
async def delete_scan(scan_id: int, db=Depends(get_db)):
    """
    Delete a scan and all associated data (controls, cuecs, subservice_orgs, etc.)
    Useful for testing/cleanup.
    """
    from sqlalchemy import delete
    try:
        # Delete in order to respect foreign key constraints
        # Controls, CUECs, SubserviceOrgs reference scan_id
        await db.execute(delete(Control).where(Control.scan_id == scan_id))
        await db.execute(delete(CUEC).where(CUEC.scan_id == scan_id))
        await db.execute(delete(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id))
        
        # Company, Product reference scan_id
        await db.execute(delete(Company).where(Company.scan_id == scan_id))
        await db.execute(delete(Product).where(Product.scan_id == scan_id))
        
        # Finally delete the scan itself
        scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan_row = scan_result.scalar_one_or_none()
        if not scan_row:
            raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")
        
        await db.delete(scan_row)
        await db.commit()
        
        logging.info(f"[DELETE_SCAN] Successfully deleted scan {scan_id} and all associated data")
        return {"status": "deleted", "scan_id": scan_id}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"Error deleting scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "SOCAnalyzer backend is running"}

# Example endpoint for PDF upload (to be connected to analyze.py logic)


# (Legacy/duplicate) analyze endpoint removed to avoid conflicts with the background job system

# Create tables if not exist (for dev)
async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

import sys
if __name__ == "__main__" and sys.argv[0].endswith("main.py") and sys.argv[-1] != "test_insert_combined_result":
    asyncio.get_event_loop().run_until_complete(init_models())

# REMOVED: @app.post("/analyze/cancel/{job_id}") - Duplicate endpoint (12 lines)
# Now handled by existing cancel_analysis_job function at line 1378

async def update_scan_gpt_fields(scan_id, gpt_cost=None, gpt_model=None, estimated_time_seconds=None, db=None):
    if db is None:
        raise ValueError("A valid async database session (db) must be provided.")
    from .models import Scan
    from sqlalchemy.future import select
    update_fields = {}
    if gpt_cost is not None:
        update_fields['gpt_cost'] = gpt_cost
    if gpt_model is not None:
        update_fields['gpt_model'] = gpt_model
    if estimated_time_seconds is not None:
        update_fields['estimated_time_seconds'] = estimated_time_seconds
    if not update_fields:
        return
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan_row = result.scalar_one_or_none()
    if scan_row:
        for k, v in update_fields.items():
            setattr(scan_row, k, v)
        db.add(scan_row)
        await db.commit()

async def add_gpt_usage(scan_id, model, cost, seconds, db):
    from .models import Scan
    from sqlalchemy.future import select
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan_row = result.scalar_one_or_none()
    if scan_row:
        usage = scan_row.gpt_usage_details or []
        usage.append({"model": model, "cost": cost, "estimated_time_seconds": seconds})
        scan_row.gpt_usage_details = usage
        db.add(scan_row)
        await db.commit()

def sanitize_orm_kwargs(kwargs):
    for k, v in kwargs.items():
        if isinstance(v, (list, dict)):
            kwargs[k] = _json.dumps(v, ensure_ascii=False)
    return kwargs

@app.get("/framework_criteria")
async def get_framework_criteria():
    """
    Get all framework criteria grouped by framework and section.
    Returns a dynamic structure supporting all registered frameworks.
    """
    return framework_service.get_all_framework_criteria()

@app.get("/executive_summary/{scan_id}")
async def get_executive_summary(scan_id: int, force_refresh: bool = False, db=Depends(get_db)):
    # Force fresh read from database to avoid caching issues
    await db.commit()  # Ensure any pending transactions are committed
    scan_row = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan_row = scan_row.scalar_one_or_none()
    if not scan_row:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    # Get existing summary and staleness flag
    existing_summary = getattr(scan_row, "executive_summary", None)
    is_stale = bool(getattr(scan_row, "executive_summary_stale", False))
    
    # NEW BEHAVIOR: Do NOT auto-generate an executive summary on page load.
    # Always return the cached summary (even if null) and the staleness flag
    # when force_refresh is not requested. Generation is expensive (GPT call)
    # and should only be triggered explicitly via the POST regeneration endpoint
    # or when force_refresh=True is passed.
    if not force_refresh:
        # Return whatever is stored (could be None) so the frontend can show
        # the cached summary and a stale-warning if appropriate.
        summary = existing_summary
        await db.rollback()  # Clean up any pending transaction

        # Parse the JSON if it's stored as a string
        if isinstance(summary, str):
            import json
            try:
                summary = json.loads(summary)
            except Exception:
                pass  # If parsing fails, return as-is

        return {"executive_summary": summary, "is_stale": is_stale}
    
    # Otherwise, generate summary using GPT (only if force_refresh=True or no summary exists)
    controls = (await db.execute(select(Control).where(Control.scan_id == scan_id))).scalars().all()
    high_conf_controls = [
        ctrl for ctrl in controls
        if isinstance(getattr(ctrl, 'control_confidence', 0), (int, float)) and getattr(ctrl, 'control_confidence', 0) >= 0.89
    ]
    cuecs = (await db.execute(select(CUEC).where(CUEC.scan_id == scan_id))).scalars().all()
    suborgs = (await db.execute(select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id))).scalars().all()
    tsc_ids_found = set([getattr(ctrl, "control_tsc_id", None) for ctrl in controls if getattr(ctrl, "control_tsc_id", None)])
    coso_ids_found = set([getattr(ctrl, "control_coso_id", None) for ctrl in controls if getattr(ctrl, "control_coso_id", None)])
    tsc_criteria = TSC_CRITERIA
    coso_criteria = COSO_2013_CRITERIA
    tsc_table = [
        {"id": crit["id"], "description": crit["description"], "section": crit.get("section", "Unspecified"), "present": crit["id"] in tsc_ids_found}
        for crit in tsc_criteria
    ]
    coso_table = [
        {"id": crit["id"], "description": crit["description"], "section": crit.get("component", "Unspecified"), "present": crit["id"] in coso_ids_found}
        for crit in coso_criteria
    ]
    suborg_count = len([o for o in suborgs if getattr(o, "confidence", 0) >= 0.9])
    cuec_count = len([c for c in cuecs if getattr(c, "cuec_confidence", 0) >= 0.9])
    tsc_table_str = "\n".join([f"{row['section']}: {row['id']} - {row['description']} ({'✔' if row['present'] else '✗'})" for row in tsc_table])
    coso_table_str = "\n".join([f"{row['section']}: {row['id']} - {row['description']} ({'✔' if row['present'] else '✗'})" for row in coso_table])
    
    # Budgeted control test results string (prioritize deviations, then include up to N non-deviations)
    def _truncate(s: str, max_chars: int) -> str:
        s = s or ''
        if len(s) <= max_chars:
            return s
        return s[: max_chars - 3] + '...'

    dev_controls = [
        ctrl for ctrl in high_conf_controls
        if bool(getattr(ctrl, 'has_deviation', False)) and isinstance(getattr(ctrl, 'control_test_results', ''), str)
           and getattr(ctrl, 'control_test_results', '').strip()
    ]
    non_dev_controls = [
        ctrl for ctrl in high_conf_controls
        if (not bool(getattr(ctrl, 'has_deviation', False))) and isinstance(getattr(ctrl, 'control_test_results', ''), str)
           and getattr(ctrl, 'control_test_results', '').strip()
    ]
    # Limit non-deviation controls to configured maximum to reduce prompt size
    non_dev_controls = non_dev_controls[:EXEC_SUMMARY_MAX_NON_DEVIATION_CONTROLS]

    selected_controls = dev_controls + non_dev_controls
    parts = []
    used = 0
    for ctrl in selected_controls:
        cid = getattr(ctrl, 'control_id', 'Unknown')
        res = _truncate(getattr(ctrl, 'control_test_results', ''), EXEC_SUMMARY_PER_CONTROL_MAX_CHARS)
        chunk = f"Control {cid}: {res}"
        if used + len(chunk) + 1 > EXEC_SUMMARY_TEST_RESULTS_BUDGET_CHARS:
            break
        parts.append(chunk)
        used += len(chunk) + 1
    control_test_results_str = "\n".join(parts)

    # Prepare detected deviations list from control-level fields (high-confidence only)
    detected_deviations_list = [
        f"Control {getattr(ctrl, 'control_id', 'Unknown')}: {getattr(ctrl, 'deviation_desc', '').strip()}"
        for ctrl in high_conf_controls
        if bool(getattr(ctrl, 'has_deviation', False)) and isinstance(getattr(ctrl, 'deviation_desc', ''), str) and getattr(ctrl, 'deviation_desc', '').strip()
    ]
    detected_deviations_str = "\n".join(detected_deviations_list) if detected_deviations_list else "None."

    # Helper for later de-duplication only; no heuristic deviation detection here
    def _norm_text(s):
        try:
            return " ".join((s or "").strip().lower().split())
        except Exception:
            return ""
    
    # Format CUEC control strength assessments for high-confidence CUECs (≥90%)
    high_conf_cuecs_with_strength = [
        cuec for cuec in cuecs 
        if getattr(cuec, 'cuec_confidence', 0) >= 0.9 and getattr(cuec, 'control_strength', None)
    ]
    cuec_control_strengths_str = "\n".join([
        f"CUEC {getattr(cuec, 'cuec_tsc_id', 'Unknown')} - {getattr(cuec, 'control_strength', 'Not Set')}: {getattr(cuec, 'cuec_description', '')[:150]}..."
        for cuec in high_conf_cuecs_with_strength
    ]) if high_conf_cuecs_with_strength else "No high-confidence CUECs with control strength assessments found."
    
    # Get company and product names for prompt
    company_name = None
    product_name = None
    company_row = (await db.execute(select(Company).where(Company.scan_id == scan_id))).scalars().first()
    if company_row:
        company_name = getattr(company_row, 'name', '') or ''
    product_row = (await db.execute(select(Product).where(Product.scan_id == scan_id))).scalars().first()
    if product_row:
        product_name = getattr(product_row, 'name', '') or ''
    
    # Get SOX vendor status
    is_sox_vendor = getattr(scan_row, 'is_sox_vendor', False)
    sox_vendor_str = "Yes - Subject to SOX Compliance" if is_sox_vendor else "No"
    
    # Get coverage period dates
    coverage_start = getattr(scan_row, 'coverage_start', None)
    coverage_end = getattr(scan_row, 'coverage_end', None)
    if coverage_start and coverage_end:
        coverage_period_str = f"{coverage_start.strftime('%B %d, %Y')} to {coverage_end.strftime('%B %d, %Y')}"
    elif coverage_start:
        coverage_period_str = f"starting {coverage_start.strftime('%B %d, %Y')}"
    elif coverage_end:
        coverage_period_str = f"ending {coverage_end.strftime('%B %d, %Y')}"
    else:
        coverage_period_str = "the audit period"
    
    prompt = EXECUTIVE_SUMMARY_PROMPT.format(
        suborg_count=suborg_count,
        cuec_count=cuec_count,
        tsc_covered=sum(1 for row in tsc_table if row['present']),
        tsc_total=len(tsc_table),
        coso_covered=sum(1 for row in coso_table if row['present']),
        coso_total=len(coso_table),
        tsc_table=tsc_table_str,
        coso_table=coso_table_str,
        coverage_period=coverage_period_str,
        control_test_results=control_test_results_str,
        detected_deviations=detected_deviations_str,
        cuec_control_strengths=cuec_control_strengths_str,
        company=company_name,
        product=product_name,
        is_sox_vendor=sox_vendor_str
    )
    # No heuristic pre-computed deviations; rely on GPT to analyze control_test_results in the prompt
    import json
    

    
    print(f"REGENERATE DEBUG: Generating new executive summary for scan {scan_id}")
    print(f"REGENERATE DEBUG: Calling GPT to generate real summary")
    
    # Calculate prompt size and check token limits
    prompt_chars = len(prompt)
    estimated_tokens = prompt_chars / CHARS_PER_TOKEN
    token_percentage = estimated_tokens / MAX_INPUT_TOKENS
    
    # Log prompt size metrics
    print(f"REGENERATE DEBUG: Prompt size: {prompt_chars:,} chars, ~{estimated_tokens:,.0f} tokens ({token_percentage:.1%} of limit)")
    
    # Check if prompt exceeds token limits
    if token_percentage >= 1.0:
        error_msg = (
            f"Executive summary cannot be generated - prompt size ({estimated_tokens:,.0f} tokens) "
            f"exceeds token limit ({MAX_INPUT_TOKENS:,} tokens). "
            f"Report has {len(high_conf_controls)} controls, {len(detected_deviations_list)} deviations, "
            f"and {len(high_conf_cuecs_with_strength)} CUECs. Please contact support."
        )
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
    
    # Warn if approaching token limit
    if token_percentage >= EXEC_SUMMARY_TOKEN_WARNING_THRESHOLD:
        warning_msg = (
            f"Executive summary prompt approaching token limit: {estimated_tokens:,.0f} tokens "
            f"({token_percentage:.1%} of {MAX_INPUT_TOKENS:,} max). "
            f"Report has {len(high_conf_controls)} controls, {len(detected_deviations_list)} deviations, "
            f"and {len(high_conf_cuecs_with_strength)} CUECs."
        )
        logger.warning(warning_msg)
    
    # Log the full prompt being sent to GPT
    print(f"REGENERATE DEBUG: Executive Summary GPT Prompt:")
    print("=" * 80)
    print(prompt)
    print("=" * 80)
    
    # Also log to file for later review (reset file each time)
    from pathlib import Path
    log_dir = Path(__file__).parent.parent.parent / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "executive_summary_gpt.log"
    
    with open(log_file, 'w', encoding='utf-8') as f:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{'='*80}\n")
        f.write(f"EXECUTIVE SUMMARY GENERATION - {timestamp}\n")
        f.write(f"Scan ID: {scan_id}\n")
        f.write(f"Prompt Size: {prompt_chars:,} chars (~{estimated_tokens:,.0f} tokens, {token_percentage:.1%} of {MAX_INPUT_TOKENS:,} limit)\n")
        if token_percentage >= EXEC_SUMMARY_TOKEN_WARNING_THRESHOLD:
            f.write(f"⚠️  WARNING: Prompt size exceeds {EXEC_SUMMARY_TOKEN_WARNING_THRESHOLD:.0%} threshold\n")
        f.write(f"Report Stats: {len(high_conf_controls)} controls, {len(detected_deviations_list)} deviations, {len(high_conf_cuecs_with_strength)} CUECs\n")
        f.write(f"{'='*80}\n")
        f.write(f"PROMPT:\n{prompt}\n")
        f.write(f"{'-'*80}\n")
    
    # Generate real summary using GPT
    gpt_summary = gpt_extract(prompt, "executive_summary")
    
    print(f"REGENERATE DEBUG: GPT Response received (length: {len(gpt_summary)} chars)")
    print(f"REGENERATE DEBUG: GPT Response preview: {gpt_summary[:200]}...")
    
    # Log the response to file as well
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"RESPONSE:\n{gpt_summary}\n")
        f.write(f"{'='*80}\n")
    
    # Parse the GPT response JSON
    # Clean the GPT response by removing markdown code fences
    cleaned_response = gpt_summary.strip()
    if cleaned_response.startswith('```json'):
        cleaned_response = cleaned_response[7:]  # Remove ```json
    elif cleaned_response.startswith('```'):
        cleaned_response = cleaned_response[3:]   # Remove ```
    if cleaned_response.endswith('```'):
        cleaned_response = cleaned_response[:-3]  # Remove trailing ```
    cleaned_response = cleaned_response.strip()
    
    try:
        summary_json = json.loads(cleaned_response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Executive summary is not valid JSON: {e}\nRaw response: {gpt_summary}\nCleaned response: {cleaned_response}")
    required_keys = ["about_company", "key_findings", "areas_of_concern", "recommendations"]
    if not all(k in summary_json for k in required_keys):
        raise HTTPException(status_code=500, detail=f"Executive summary JSON missing required keys. Got: {list(summary_json.keys())}\nRaw response: {gpt_summary}")
    
    # Let GPT decide deviations_noted; do minimal de-duplication only.
    def _norm_text(s):
        try:
            return " ".join((s or "").strip().lower().split())
        except Exception:
            return ""
    deduped = []
    seen = set()
    for dev in (summary_json.get("deviations_noted") or []):
        if not isinstance(dev, dict):
            continue
        cid = str(dev.get("control_id") or "")
        summary = dev.get("deviation_summary") or ""
        k = (cid, _norm_text(summary))
        if k in seen:
            continue
        seen.add(k)
        deduped.append({"control_id": cid, "deviation_summary": summary})
    summary_json["deviations_noted"] = deduped

    # Ensure legacy recommendations includes both split lists if present
    try:
        risk_list = summary_json.get("recommendations_risk_mitigations") or []
        contract_list = summary_json.get("recommendations_contract_enhancements") or []
        base_list = summary_json.get("recommendations") or []
        # Union while preserving order
        combined = []
        seen = set()
        for item in list(base_list) + list(risk_list) + list(contract_list):
            key = (item or "").strip()
            if key and key not in seen:
                seen.add(key)
                combined.append(key)
        summary_json["recommendations"] = combined
    except Exception:
        pass
    
    # Save the generated summary to the database and reset staleness flag
    print(f"REGENERATE DEBUG: Saving new executive summary to database for scan {scan_id}")
    print(f"REGENERATE DEBUG: Summary JSON keys being saved: {list(summary_json.keys())}")
    print(f"REGENERATE DEBUG: Has sox_objective: {'sox_objective' in summary_json}")
    print(f"REGENERATE DEBUG: Has sox_assessors_conclusion: {'sox_assessors_conclusion' in summary_json}")
    scan_row.executive_summary = summary_json
    scan_row.executive_summary_stale = False  # Reset staleness flag
    db.add(scan_row)
    await db.commit()
    
    print(f"REGENERATE DEBUG: Executive summary saved successfully for scan {scan_id}")
    print(f"REGENERATE DEBUG: Returning summary with keys: {list(summary_json.keys())}")
    return {"executive_summary": summary_json, "is_stale": False}

@app.post("/executive_summary/{scan_id}")
async def regenerate_executive_summary(scan_id: int, db=Depends(get_db)):
    """Force regeneration of executive summary"""
    print(f"REGENERATE DEBUG: Received request to regenerate executive summary for scan {scan_id}")
    
    scan_row = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan_row = scan_row.scalar_one_or_none()
    if not scan_row:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    print(f"REGENERATE DEBUG: Found scan {scan_id}, triggering force regeneration")
    
    # Rollback to release the row lock before calling get_executive_summary
    await db.rollback()
    
    # Call the GET endpoint with force_refresh=True to regenerate
    result = await get_executive_summary(scan_id=scan_id, force_refresh=True, db=db)
    
    print(f"REGENERATE DEBUG: Executive summary regenerated for scan {scan_id}")
    return result

@app.patch("/executive_summary/{scan_id}")
async def patch_executive_summary(scan_id: int, data: dict, db=Depends(get_db)):
    summary = data.get("executive_summary")
    if not summary:
        raise HTTPException(status_code=400, detail="No executive_summary provided")
    scan_row = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan_row = scan_row.scalar_one_or_none()
    if not scan_row:
        raise HTTPException(status_code=404, detail="Scan not found")
    scan_row.executive_summary = summary
    db.add(scan_row)
    await db.commit()
    return {"status": "ok"}

@app.post("/report/{scan_id}/reload_extracted_text")
async def reload_extracted_text(scan_id: int, db=Depends(get_db)):
    """
    Reload extracted text from output.txt into the database for a specific scan.
    Useful when the text was extracted but not saved to the database.
    """
    try:
        # Check if scan exists
        scan_row = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan_row = scan_row.scalar_one_or_none()
        if not scan_row:
            return JSONResponse({"error": "Scan not found"}, status_code=404)
        
        # Try to load from output.txt
        PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
        output_path = PROJECT_ROOT / 'data' / 'output' / 'output.txt'
        
        if not output_path.exists():
            return JSONResponse({
                "error": "output.txt not found",
                "message": "The extracted text file does not exist. Run text extraction first."
            }, status_code=404)
        
        with open(output_path, 'r', encoding='utf-8') as f:
            extracted_text = f.read()
        
        if not extracted_text:
            return JSONResponse({
                "error": "output.txt is empty",
                "message": "The extracted text file exists but is empty."
            }, status_code=400)
        
        # Update the scan with extracted text
        scan_row.extracted_text = extracted_text
        db.add(scan_row)
        await db.commit()
        
        return {
            "status": "ok",
            "scan_id": scan_id,
            "text_length": len(extracted_text),
            "message": "Extracted text loaded successfully"
        }
    except Exception as e:
        await db.rollback()
        logging.error(f"Failed to reload extracted text for scan {scan_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.patch("/report/{scan_id}/overview")
async def patch_report_overview(scan_id: int, data: dict, db=Depends(get_db)):
    logging.debug(f"/report/{scan_id}/overview payload: {data}")
    try:
        from datetime import datetime
        
        def parse_date(date_str):
            """Parse various date string formats to datetime object"""
            if not date_str:
                return None
            if isinstance(date_str, datetime):
                return date_str
            # Try multiple date formats
            for fmt in [
                "%Y-%m-%dT%H:%M:%S.%f",  # ISO with microseconds
                "%Y-%m-%dT%H:%M:%S",      # ISO without microseconds
                "%Y-%m-%d",               # Date only
            ]:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            # If all formats fail, return None
            return None
        
        scan_row = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan_row = scan_row.scalar_one_or_none()
        if not scan_row:
            return JSONResponse({"error": "Scan not found"}, status_code=404)
        if "company" in data:
            scan_row.company = data["company"]
        if "product" in data:
            scan_row.product = data["product"]
        if "coverageStart" in data:
            scan_row.coverage_start = parse_date(data["coverageStart"])
        if "coverageEnd" in data:
            scan_row.coverage_end = parse_date(data["coverageEnd"])
        if "reportDate" in data:
            scan_row.report_date = parse_date(data["reportDate"])
        if "auditor" in data:
            scan_row.auditor = data["auditor"]
        if "scanDate" in data:
            scan_row.scan_date = parse_date(data["scanDate"])
        if "isSoxVendor" in data:
            scan_row.is_sox_vendor = bool(data["isSoxVendor"])
        
        # Mark executive summary as stale since overview data changed (especially SOX vendor status affects summary)
        scan_row.executive_summary_stale = True
        
        db.add(scan_row)
        await db.commit()
        
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/overview DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.patch("/report/{scan_id}/controls/{control_id}/annotation")
async def patch_control_annotation(scan_id: int, control_id: str, data: Dict[str, Any] = Body(...), db=Depends(get_db)):
    try:
        ctrl = (await db.execute(select(Control).where(Control.scan_id == scan_id, Control.control_id == control_id))).scalar_one_or_none()
    except MultipleResultsFound:
        return JSONResponse({
            "error": "Multiple controls matched control_id. Use ID endpoint /report/{scan_id}/controls/id/{control_db_id}"
        }, status_code=409)
    if not ctrl:
        raise HTTPException(status_code=404, detail="Control not found")
    ctrl.annotation = data.get("annotation", "")
    db.add(ctrl)
    await db.commit()
    return {"status": "ok"}

# REMOVED: Control Router duplicates (2 endpoints, ~185 lines)
# - @app.patch("/report/{scan_id}/controls/{control_id}") 
# - @app.patch("/report/{scan_id}/controls/id/{control_db_id}")
# Now handled by backend/app/routers/control_router.py

# NOTE: Keep normalization inline in handlers to avoid import scope issues

async def automated_cleanup(scan_id: int, db):
    """
    Automated cleanup tasks that run after scan completion:
    1. Flag extraction errors (blank control_ids, duplicate control_ids with low similarity)
    2. Auto-merge high-confidence duplicate controls (score >= 0.85)
    3. Flag low-confidence CUECs and subservice orgs
    """
    try:
        logging.error(f"[CLEANUP] Starting automated cleanup for scan {scan_id}")
        cleanup_stats = {
            "extraction_errors_flagged": 0,
            "controls_auto_merged": 0,
            "low_confidence_cuecs": 0,
            "low_confidence_subservice_orgs": 0
        }
        
        # 1. Get all controls for analysis (include duplicate instances)
        result = await db.execute(
            select(Control).where(
                Control.scan_id == scan_id,
                and_(
                    (Control.merged_to_control_id == None) | 
                    (Control.merged_to_control_id == 'DUPLICATE_INSTANCE')
                )
            ).order_by(Control.control_seq)
        )
        controls = result.scalars().all()
        
        # 2. Flag blank control_ids as extraction errors
        blank_controls = [c for c in controls if not c.control_id or str(c.control_id).strip() == ""]
        for ctrl in blank_controls:
            if ctrl.control_confidence > 0.1:
                ctrl.control_confidence = 0.1
                note = "\nAutomated cleanup: Extraction error - no valid control_id extracted"
                ctrl.confidence_calc = (ctrl.confidence_calc or "") + note
                db.add(ctrl)
                cleanup_stats["extraction_errors_flagged"] += 1
        
        # 3. Group by control_id and process duplicates
        control_groups = {}
        for ctrl in controls:
            if not ctrl.control_id or str(ctrl.control_id).strip() == "":
                continue
            ctrl_id = str(ctrl.control_id).strip()
            if ctrl_id not in control_groups:
                control_groups[ctrl_id] = []
            control_groups[ctrl_id].append(ctrl)
        
        from .gpt_client import gpt_extract
        
        # 4. Process each duplicate group
        for ctrl_id, group in control_groups.items():
            if len(group) < 2:
                continue
            
            # Sort by confidence to pick primary
            group.sort(key=lambda c: c.control_confidence or 0, reverse=True)
            primary = group[0]
            candidates = group[1:]
            
            # Evaluate each candidate for merging or flagging
            for candidate in candidates:
                confidence_score = 0.0
                
                # Calculate similarity (same logic as suggest-merges)
                desc1 = (primary.control_desc or "").strip()
                desc2 = (candidate.control_desc or "").strip()
                
                if desc1 and desc2:
                    try:
                        similarity_prompt = f"""Rate the semantic similarity between these two control descriptions on a scale of 0.0 to 1.0.
Return ONLY a number between 0.0 and 1.0, nothing else.

Description 1: {desc1[:500]}
Description 2: {desc2[:500]}"""
                        
                        sim_response = gpt_extract(similarity_prompt, "automated_cleanup")
                        desc_similarity = float(sim_response.strip())
                        desc_similarity = max(0.0, min(1.0, desc_similarity))
                        confidence_score += desc_similarity * 0.65  # Reduced from 0.70 to 0.65
                    except Exception:
                        if desc1.lower() == desc2.lower():
                            confidence_score += 0.65
                        else:
                            confidence_score += 0.39
                
                # TSC/COSO mapping match
                if primary.control_tsc_id and candidate.control_tsc_id:
                    if primary.control_tsc_id == candidate.control_tsc_id:
                        confidence_score += 0.15
                
                if primary.control_coso_id and candidate.control_coso_id:
                    if primary.control_coso_id == candidate.control_coso_id:
                        if not (primary.control_tsc_id and candidate.control_tsc_id and primary.control_tsc_id == candidate.control_tsc_id):
                            confidence_score += 0.15
                
                # Test procedure similarity
                test1 = (primary.control_test or "").strip()
                test2 = (candidate.control_test or "").strip()
                if test1 and test2:
                    if test1.lower() == test2.lower():
                        confidence_score += 0.10
                    elif len(test1) > 20 and len(test2) > 20 and test1[:50].lower() == test2[:50].lower():
                        confidence_score += 0.07
                
                # Deviation flag agreement
                if primary.has_deviation == candidate.has_deviation:
                    confidence_score += 0.05
                
                # Page proximity bonus - if controls are on adjacent pages, likely chunk-split duplicates
                primary_pages = primary.control_page_refs or []
                candidate_pages = candidate.control_page_refs or []
                if primary_pages and candidate_pages:
                    primary_min = min([int(p) for p in primary_pages if str(p).isdigit()])
                    primary_max = max([int(p) for p in primary_pages if str(p).isdigit()])
                    candidate_min = min([int(p) for p in candidate_pages if str(p).isdigit()])
                    candidate_max = max([int(p) for p in candidate_pages if str(p).isdigit()])
                    
                    # Adjacent pages or overlapping ranges
                    if abs(primary_max - candidate_min) <= 1 or abs(candidate_max - primary_min) <= 1:
                        confidence_score += cfg.PAGE_PROXIMITY_WEIGHT  # +0.05 for adjacent pages
                
                # Decision: merge if high confidence, flag if low confidence
                if confidence_score >= cfg.AUTO_MERGE_MIN_CONFIDENCE:  # Changed from 0.85 to configurable 0.70
                    # Auto-merge high-confidence duplicates
                    candidate.merged_to_control_id = str(primary.id)
                    original_conf = candidate.control_confidence
                    candidate.control_confidence = 0.0
                    note = f"\nAutomated cleanup: Merged to control {primary.id} on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Original confidence: {original_conf:.2f} | Merge confidence: {confidence_score:.2f} | New confidence: 0.0 (merged duplicate)"
                    candidate.confidence_calc = (candidate.confidence_calc or "") + note
                    
                    # Consolidate page refs to primary
                    primary_pages_set = set(primary.control_page_refs or [])
                    candidate_pages_set = set(candidate.control_page_refs or [])
                    merged_pages = sorted(primary_pages_set | candidate_pages_set)
                    primary.control_page_refs = merged_pages
                    
                    # Update primary annotation
                    merge_note = f"Consolidated from automated cleanup on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    primary.annotation = merge_note
                    
                    # Track merge history
                    merge_event = {
                        "timestamp": datetime.datetime.now().isoformat(),
                        "type": "auto",
                        "confidence": round(confidence_score, 3),
                        "merged_from_ids": [str(candidate.id)],
                        "reason": f"Automated cleanup: duplicate control_id with {confidence_score:.2f} similarity"
                    }
                    if not primary.merge_history:
                        primary.merge_history = []
                    primary.merge_history.append(merge_event)
                    
                    db.add(candidate)
                    db.add(primary)
                    cleanup_stats["controls_auto_merged"] += 1
                    logging.error(f"[CLEANUP] Auto-merged control {candidate.id} to {primary.id} (score: {confidence_score:.2f})")
                    
                elif confidence_score < 0.60:
                    # Flag as extraction error if similarity is low
                    if candidate.control_confidence > 0.3:
                        candidate.control_confidence = 0.3
                        note = f"\nAutomated cleanup: Likely extraction error - duplicate control_id with dissimilar description (similarity score: {confidence_score:.2f})"
                        candidate.confidence_calc = (candidate.confidence_calc or "") + note
                        db.add(candidate)
                        cleanup_stats["extraction_errors_flagged"] += 1
        
        # 5. Flag low-confidence CUECs
        cuec_result = await db.execute(
            select(CUEC).where(CUEC.scan_id == scan_id)
        )
        cuecs = cuec_result.scalars().all()
        for cuec in cuecs:
            if cuec.cuec_confidence and cuec.cuec_confidence < 0.5:
                if not cuec.cuec_justification or "low confidence" not in cuec.cuec_justification.lower():
                    note = f"\nAutomated cleanup: Low confidence CUEC (confidence: {cuec.cuec_confidence:.2f})"
                    cuec.cuec_justification = (cuec.cuec_justification or "") + note
                    db.add(cuec)
                    cleanup_stats["low_confidence_cuecs"] += 1
        
        # 6. Flag low-confidence subservice orgs
        so_result = await db.execute(
            select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id)
        )
        subservice_orgs = so_result.scalars().all()
        for so in subservice_orgs:
            if so.confidence and so.confidence < 0.5:
                if not so.confidence_justification or "low confidence" not in so.confidence_justification.lower():
                    note = f"\nAutomated cleanup: Low confidence subservice org (confidence: {so.confidence:.2f})"
                    so.confidence_justification = (so.confidence_justification or "") + note
                    db.add(so)
                    cleanup_stats["low_confidence_subservice_orgs"] += 1
        
        # Commit all changes
        await db.commit()
        
        logging.error(f"[CLEANUP] Completed for scan {scan_id}: {cleanup_stats}")
        return cleanup_stats
        
    except Exception as e:
        logging.error(f"[CLEANUP] Error in automated cleanup for scan {scan_id}: {e}", exc_info=True)
        await db.rollback()
        return None

async def penalize_incomplete_controls(scan_id: int, db):
    """
    Apply confidence penalty to controls missing required fields.
    
    Reduces confidence by CONTROL_INCOMPLETE_PENALTY (default 0.20) for controls missing:
    - control_id
    - control_desc
    - control_test
    - control_test_results
    
    This helps identify low-quality extractions that need review.
    """
    try:
        from . import config as cfg
        
        logging.error(f"[INCOMPLETE-PENALTY] Starting for scan {scan_id}")
        
        result = await db.execute(
            select(Control).where(
                Control.scan_id == scan_id,
                and_(
                    (Control.merged_to_control_id == None) | 
                    (Control.merged_to_control_id == 'DUPLICATE_INSTANCE')
                )
            )
        )
        controls = result.scalars().all()
        
        penalized_count = 0
        for ctrl in controls:
            missing_fields = []
            if not ctrl.control_id or str(ctrl.control_id).strip() == "":
                missing_fields.append("control_id")
            if not ctrl.control_desc or str(ctrl.control_desc).strip() == "":
                missing_fields.append("control_desc")
            if not ctrl.control_test or str(ctrl.control_test).strip() == "":
                missing_fields.append("control_test")
            if not ctrl.control_test_results or str(ctrl.control_test_results).strip() == "":
                missing_fields.append("control_test_results")
            
            if missing_fields:
                original_conf = ctrl.control_confidence or 0.0
                penalty = cfg.CONTROL_INCOMPLETE_PENALTY
                new_conf = max(0.0, original_conf - penalty)
                
                ctrl.control_confidence = new_conf
                note = f"\nIncomplete control penalty: -{penalty:.2f} for missing fields: {', '.join(missing_fields)} | Original: {original_conf:.2f} → New: {new_conf:.2f}"
                ctrl.confidence_calc = (ctrl.confidence_calc or "") + note
                db.add(ctrl)
                penalized_count += 1
        
        await db.commit()
        logging.error(f"[INCOMPLETE-PENALTY] Penalized {penalized_count} controls for scan {scan_id}")
        return penalized_count
        
    except Exception as e:
        logging.error(f"[INCOMPLETE-PENALTY] Error for scan {scan_id}: {e}", exc_info=True)
        await db.rollback()
        return 0

@app.post("/report/{scan_id}/cleanup")
async def trigger_cleanup(scan_id: int, db=Depends(get_db)):
    """Manually trigger automated cleanup for a scan (for testing)"""
    try:
        cleanup_stats = await automated_cleanup(scan_id, db)
        if cleanup_stats:
            return {"status": "success", "stats": cleanup_stats}
        else:
            return {"status": "error", "message": "Cleanup failed"}
    except Exception as e:
        logging.error(f"Error triggering cleanup: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

def detect_duplicate_type(ctrl1: Control, ctrl2: Control) -> Tuple[str, float, Dict[str, Any]]:
    """
    Classify duplicate controls as IDENTICAL, CRITERIA_VARIANT, TEST_VARIANT, or AMBIGUOUS.
    
    Returns:
        Tuple of (type, confidence, metadata) where:
        - type: "IDENTICAL" | "CRITERIA_VARIANT" | "TEST_VARIANT" | "AMBIGUOUS"
        - confidence: 0.0-1.0 score for this classification
        - metadata: dict with detailed comparison info
    """
    from .gpt_client import gpt_extract
    
    metadata = {}
    
    # Extract descriptions
    desc1 = (ctrl1.control_desc or "").strip()
    desc2 = (ctrl2.control_desc or "").strip()
    
    if not desc1 or not desc2:
        return ("AMBIGUOUS", 0.3, {"reason": "Missing description(s)"})
    
    # 1. Calculate description similarity using GPT
    try:
        desc_prompt = f"""Rate the semantic similarity between these two control descriptions on a scale of 0.0 to 1.0.
Return ONLY a number between 0.0 and 1.0, nothing else.

Description 1: {desc1[:500]}
Description 2: {desc2[:500]}"""
        
        desc_sim_response = gpt_extract(desc_prompt, "duplicate_detection")
        desc_similarity = float(desc_sim_response.strip())
        desc_similarity = max(0.0, min(1.0, desc_similarity))
        metadata["description_similarity"] = desc_similarity
    except Exception as e:
        logging.warning(f"Description similarity GPT call failed: {e}")
        # Fallback: exact match check
        desc_similarity = 1.0 if desc1.lower() == desc2.lower() else 0.6
        metadata["description_similarity"] = desc_similarity
        metadata["desc_sim_fallback"] = True
    
    # 2. Compare TSC/COSO mappings
    tsc1 = ctrl1.control_tsc_mappings or []
    tsc2 = ctrl2.control_tsc_mappings or []
    coso1 = ctrl1.control_coso_mappings or []
    coso2 = ctrl2.control_coso_mappings or []
    
    # Get primary criteria (first in array)
    tsc1_primary = tsc1[0].get("id") if tsc1 and isinstance(tsc1, list) and len(tsc1) > 0 else None
    tsc2_primary = tsc2[0].get("id") if tsc2 and isinstance(tsc2, list) and len(tsc2) > 0 else None
    coso1_primary = coso1[0].get("id") if coso1 and isinstance(coso1, list) and len(coso1) > 0 else None
    coso2_primary = coso2[0].get("id") if coso2 and isinstance(coso2, list) and len(coso2) > 0 else None
    
    criteria_match = (tsc1_primary == tsc2_primary if tsc1_primary and tsc2_primary else False) or \
                     (coso1_primary == coso2_primary if coso1_primary and coso2_primary else False)
    
    metadata["criteria_match"] = criteria_match
    metadata["tsc1_primary"] = tsc1_primary
    metadata["tsc2_primary"] = tsc2_primary
    metadata["coso1_primary"] = coso1_primary
    metadata["coso2_primary"] = coso2_primary
    
    # 3. Compare test procedures using GPT
    test1 = (ctrl1.control_test or "").strip()
    test2 = (ctrl2.control_test or "").strip()
    
    test_difference = 0.0
    if test1 and test2:
        try:
            test_prompt = f"""Rate how different these test procedures are on a scale of 0.0 to 1.0.
Consider: sampling methods, frequency, scope, evidence types.
0.0 = identical, 1.0 = completely different
Return ONLY a number between 0.0 and 1.0, nothing else.

Test 1: {test1[:400]}
Test 2: {test2[:400]}"""
            
            test_diff_response = gpt_extract(test_prompt, "duplicate_detection")
            test_difference = float(test_diff_response.strip())
            test_difference = max(0.0, min(1.0, test_difference))
        except Exception as e:
            logging.warning(f"Test procedure difference GPT call failed: {e}")
            # Fallback: exact match check
            test_difference = 0.0 if test1.lower() == test2.lower() else 0.5
            metadata["test_diff_fallback"] = True
    
    metadata["test_difference"] = test_difference
    
    # 4. Compare deviation status
    dev1 = ctrl1.has_deviation or False
    dev2 = ctrl2.has_deviation or False
    deviation_differs = (dev1 != dev2)
    metadata["deviation_differs"] = deviation_differs
    
    # 5. Calculate page distance
    pages1 = ctrl1.control_page_refs or []
    pages2 = ctrl2.control_page_refs or []
    page_distance = 0
    if pages1 and pages2:
        try:
            min1 = min([int(p) for p in pages1 if str(p).isdigit()])
            min2 = min([int(p) for p in pages2 if str(p).isdigit()])
            page_distance = abs(min1 - min2)
        except (ValueError, TypeError):
            pass
    metadata["page_distance"] = page_distance
    
    # CLASSIFICATION LOGIC
    
    # IDENTICAL: Very similar descriptions (>95%), same criteria, test procedures similar (<20% diff)
    if desc_similarity >= 0.95 and criteria_match and test_difference < 0.20:
        confidence = 0.90 + (desc_similarity - 0.95) * 2  # 0.90-1.0
        return ("IDENTICAL", min(confidence, 1.0), metadata)
    
    # CRITERIA_VARIANT: Similar descriptions (>85%), DIFFERENT criteria, tests somewhat different (>30%)
    if desc_similarity >= 0.85 and not criteria_match and test_difference >= 0.30:
        confidence = 0.70 + (desc_similarity - 0.85) * 0.67  # 0.70-0.80
        # Bonus for page distance (suggests different sections)
        if page_distance > 10:
            confidence += 0.05
        return ("CRITERIA_VARIANT", min(confidence, 0.95), metadata)
    
    # TEST_VARIANT: Same criteria, but tests significantly different (>40%) OR different deviation status
    if criteria_match and (test_difference >= 0.40 or deviation_differs):
        confidence = 0.70 + test_difference * 0.15
        if deviation_differs:
            confidence += 0.05
        return ("TEST_VARIANT", min(confidence, 0.90), metadata)
    
    # AMBIGUOUS: Doesn't fit clear patterns
    # Calculate ambiguity confidence based on how unclear the situation is
    ambiguity_confidence = 0.50
    if desc_similarity < 0.85:
        ambiguity_confidence += 0.15  # Lower desc similarity = more ambiguous
    if 0.20 <= test_difference <= 0.40:
        ambiguity_confidence += 0.10  # Mid-range test diff = unclear
    
    return ("AMBIGUOUS", min(ambiguity_confidence, 0.75), metadata)

# REMOVED: @app.get("/report/{scan_id}/controls/suggest-merges") - Duplicate (~190 lines)
# REMOVED: GET /report/{scan_id}/controls/suggest-merges
# Now handled by backend/app/routers/control_router.py line 252

# REMOVED: POST /report/{scan_id}/controls/merge
# Now handled by backend/app/routers/control_router.py line 273

async def split_control(scan_id: int, control_db_id: int, db=Depends(get_db)):
    """
    Undo a control merge by restoring merged controls.
    
    If this control has been merged INTO another control:
    - Clears merged_to_control_id
    - Restores original confidence from annotation backup
    
    If this control HAS other controls merged into it:
    - Returns error (use split on the merged controls instead)
    """
    import json
    try:
        # Get the control
        ctrl = (await db.execute(
            select(Control).where(Control.scan_id == scan_id, Control.id == control_db_id)
        )).scalar_one_or_none()
        
        if not ctrl:
            raise HTTPException(status_code=404, detail="Control not found")
        
        # Check if this control was merged into another
        if not ctrl.merged_to_control_id:
            return JSONResponse({"error": "This control is not merged, nothing to split"}, status_code=400)
        
        # Restore from annotation backup
        original_confidence = 0.5  # Default fallback
        
        if ctrl.annotation:
            try:
                # Try to parse JSON backup
                lines = ctrl.annotation.split("\n")
                for line in lines:
                    if line.strip().startswith("{"):
                        annotation_data = json.loads(line)
                        if "original_confidence" in annotation_data:
                            original_confidence = annotation_data["original_confidence"]
                            break
            except Exception as e:
                logging.warning(f"Could not parse annotation backup for control {control_db_id}: {e}")
        
        # Restore control
        ctrl.merged_to_control_id = None
        ctrl.control_confidence = original_confidence
        
        # Add split note to annotation
        split_note = f"Split/unmerged on {datetime.datetime.now()}, confidence restored to {original_confidence}"
        ctrl.annotation = f"{ctrl.annotation}\n{split_note}" if ctrl.annotation else split_note
        
        db.add(ctrl)
        
        # Mark executive summary stale
        scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if scan_row:
            scan_row.executive_summary_stale = True
            db.add(scan_row)
        
        await db.commit()
        
        return {
            "status": "ok",
            "control_id": ctrl.id,
            "restored_confidence": original_confidence,
            "message": "Control successfully split/unmerged"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"Error splitting control {control_db_id}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

# REMOVED: POST /report/{scan_id}/controls/link_instances
# Now handled by backend/app/routers/control_router.py line 325

# REMOVED: POST /report/{scan_id}/controls/unlink_instance/{control_id}
# Now handled by backend/app/routers/control_router.py line 382

# REMOVED: POST /report/{scan_id}/controls/dismiss_merge_suggestion
# Now handled by backend/app/routers/control_router.py line 412

# REMOVED: GET /report/{scan_id}/controls/duplicate_groups
# Now handled by backend/app/routers/control_router.py line 424

# Now handled by backend/app/routers/cuec_router.py

# REMOVED: PATCH /report/{scan_id}/cuecs/{cuec_id}
# Now handled by backend/app/routers/cuec_router.py

# REMOVED: PATCH /report/{scan_id}/cuecs/tsc/{cuec_tsc_id}
# Now handled by backend/app/routers/cuec_router.py

# REMOVED: POST /report/{scan_id}/cuecs/{cuec_id}/recompute_frameworks
# Now handled by backend/app/routers/cuec_router.py

# REMOVED: POST /report/{scan_id}/controls/id/{control_db_id}/recompute_frameworks
# Now handled by backend/app/routers/control_router.py line 470

# REMOVED: POST /report/{scan_id}/preview-frameworks
# Now handled by backend/app/routers/control_router.py line 525

# REMOVED: POST /report/{scan_id}/controls/batch_recompute_frameworks
# Now handled by backend/app/routers/control_router.py line 488

# VERIFICATION ENDPOINTS
# ============================================================================

@app.post("/verify/{scan_id}")
async def trigger_verification(scan_id: int, db=Depends(get_db)):
    """
    Manually trigger verification for a scan's controls.
    Applies pattern library scoring and multi-factor confidence analysis.
    """
    try:
        from .services.verification_service import ControlVerificationService
        
        # Get organization name from scan
        scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = scan_result.scalar_one_or_none()
        
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        organization = None
        if scan.company_id:
            company_result = await db.execute(
                select(Company).where(Company.id == scan.company_id)
            )
            company = company_result.scalar_one_or_none()
            if company:
                organization = company.name
        
        if not organization:
            organization = "Unknown"
        
        # Run verification
        service = ControlVerificationService()
        stats = await service.start_verification(scan_id, db, organization)
        
        return {
            "status": "completed",
            "stats": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Verification error for scan {scan_id}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/verify/{scan_id}/status")
async def get_verification_status(scan_id: int, db=Depends(get_db)):
    """
    Get verification status and statistics for a scan.
    """
    try:
        from .services.verification_service import ControlVerificationService
        
        service = ControlVerificationService()
        stats = await service.get_verification_status(scan_id, db)
        
        return stats
        
    except Exception as e:
        logging.error(f"Error fetching verification status for scan {scan_id}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/verify/{scan_id}/learn_patterns")
async def learn_patterns(scan_id: int, db=Depends(get_db)):
    """
    Learn patterns from a scan's validated controls.
    Called automatically after extraction, but can be triggered manually.
    """
    try:
        from .services.verification_service import ControlVerificationService
        
        service = ControlVerificationService()
        stats = await service.learn_patterns_from_scan(scan_id, db)
        
        return {
            "status": "completed",
            "stats": stats
        }
        
    except Exception as e:
        logging.error(f"Pattern learning error for scan {scan_id}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/patterns/review-queue")
async def get_pattern_review_queue(organization: Optional[str] = None, db=Depends(get_db)):
    """
    Get pending pattern merge suggestions for manual review.
    """
    try:
        from .models import PatternReviewQueue
        
        query = select(PatternReviewQueue).where(
            PatternReviewQueue.status == 'pending'
        )
        
        if organization:
            query = query.where(PatternReviewQueue.organization == organization)
        
        query = query.order_by(PatternReviewQueue.created_at.desc())
        
        result = await db.execute(query)
        items = result.scalars().all()
        
        return {
            "items": [
                {
                    "id": item.id,
                    "organization": item.organization,
                    "pattern1": item.pattern1,
                    "pattern2": item.pattern2,
                    "merged_pattern": item.merged_pattern,
                    "similarity_score": item.similarity_score,
                    "created_at": item.created_at.isoformat() if item.created_at else None
                }
                for item in items
            ]
        }
        
    except Exception as e:
        logging.error(f"Error fetching pattern review queue: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/patterns/approve-merge/{review_id}")
async def approve_pattern_merge(review_id: int, db=Depends(get_db)):
    """
    Approve a pattern merge suggestion.
    Merges the two patterns into one and updates existing controls.
    """
    try:
        from .models import PatternReviewQueue, ControlPattern
        from datetime import datetime
        
        # Get review item
        result = await db.execute(
            select(PatternReviewQueue).where(PatternReviewQueue.id == review_id)
        )
        review = result.scalar_one_or_none()
        
        if not review:
            raise HTTPException(status_code=404, detail="Review item not found")
        
        if review.status != 'pending':
            raise HTTPException(status_code=400, detail="Review already processed")
        
        # Get both patterns
        patterns_result = await db.execute(
            select(ControlPattern).where(
                sqlalchemy.and_(
                    ControlPattern.organization == review.organization,
                    ControlPattern.pattern.in_([review.pattern1, review.pattern2])
                )
            )
        )
        patterns = patterns_result.scalars().all()
        
        if len(patterns) != 2:
            raise HTTPException(status_code=400, detail="Patterns not found in database")
        
        # Merge patterns: combine frequencies and scan_ids
        pattern1 = next(p for p in patterns if p.pattern == review.pattern1)
        pattern2 = next(p for p in patterns if p.pattern == review.pattern2)
        
        combined_frequency = pattern1.frequency + pattern2.frequency
        combined_scan_ids = list(set((pattern1.scan_ids or []) + (pattern2.scan_ids or [])))
        
        # Create merged pattern
        merged = ControlPattern(
            organization=review.organization,
            pattern=review.merged_pattern,
            frequency=combined_frequency,
            first_seen=min(pattern1.first_seen, pattern2.first_seen),
            last_seen=datetime.utcnow(),
            scan_ids=combined_scan_ids
        )
        db.add(merged)
        
        # Delete old patterns
        await db.delete(pattern1)
        await db.delete(pattern2)
        
        # Update review status
        review.status = 'approved'
        review.reviewed_at = datetime.utcnow()
        db.add(review)
        
        await db.commit()
        
        return {
            "status": "approved",
            "merged_pattern": review.merged_pattern,
            "combined_frequency": combined_frequency
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"Error approving pattern merge {review_id}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/patterns/reject-merge/{review_id}")
async def reject_pattern_merge(review_id: int, db=Depends(get_db)):
    """
    Reject a pattern merge suggestion.
    Keeps patterns separate.
    """
    try:
        from .models import PatternReviewQueue
        from datetime import datetime
        
        result = await db.execute(
            select(PatternReviewQueue).where(PatternReviewQueue.id == review_id)
        )
        review = result.scalar_one_or_none()
        
        if not review:
            raise HTTPException(status_code=404, detail="Review item not found")
        
        if review.status != 'pending':
            raise HTTPException(status_code=400, detail="Review already processed")
        
        review.status = 'rejected'
        review.reviewed_at = datetime.utcnow()
        db.add(review)
        
        await db.commit()
        
        return {
            "status": "rejected"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"Error rejecting pattern merge {review_id}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/patterns/organization/{organization}")
async def get_organization_patterns(organization: str, db=Depends(get_db)):
    """
    Get pattern profile for an organization.
    """
    try:
        from .utils.pattern_library import ControlPatternLibrary
        
        pattern_lib = ControlPatternLibrary(db_session=db)
        profile = pattern_lib.get_org_profile(organization)
        
        return profile
        
    except Exception as e:
        logging.error(f"Error fetching patterns for {organization}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

# ============================================================================
# CONFIDENCE WEIGHTS MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/api/confidence-weights")
async def get_global_confidence_weights(db=Depends(get_db)):
    """Get global default confidence weights."""
    try:
        result = await db.execute(
            select(ConfidenceWeights).where(ConfidenceWeights.organization == None)
        )
        weights = result.scalar_one_or_none()
        
        if not weights:
            # Return defaults if not in database
            return {
                "gpt_weight": 0.25,
                "pattern_weight": 0.20,
                "structure_weight": 0.20,
                "framework_weight": 0.20,
                "deviation_weight": 0.15
            }
        
        return {
            "id": weights.id,
            "gpt_weight": weights.gpt_weight,
            "pattern_weight": weights.pattern_weight,
            "structure_weight": weights.structure_weight,
            "framework_weight": weights.framework_weight,
            "deviation_weight": weights.deviation_weight,
            "created_at": weights.created_at.isoformat() if weights.created_at else None,
            "updated_at": weights.updated_at.isoformat() if weights.updated_at else None
        }
    except Exception as e:
        logging.error(f"Error fetching global weights: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/confidence-weights/org/{organization}")
async def get_org_confidence_weights(organization: str, db=Depends(get_db)):
    """Get organization-specific confidence weights (falls back to global if not found)."""
    try:
        # Try org-specific first
        result = await db.execute(
            select(ConfidenceWeights).where(ConfidenceWeights.organization == organization)
        )
        weights = result.scalar_one_or_none()
        
        # Fall back to global
        if not weights:
            result = await db.execute(
                select(ConfidenceWeights).where(ConfidenceWeights.organization == None)
            )
            weights = result.scalar_one_or_none()
        
        if not weights:
            return {
                "organization": None,
                "gpt_weight": 0.25,
                "pattern_weight": 0.20,
                "structure_weight": 0.20,
                "framework_weight": 0.20,
                "deviation_weight": 0.15,
                "is_default": True
            }
        
        return {
            "id": weights.id,
            "organization": weights.organization,
            "gpt_weight": weights.gpt_weight,
            "pattern_weight": weights.pattern_weight,
            "structure_weight": weights.structure_weight,
            "framework_weight": weights.framework_weight,
            "deviation_weight": weights.deviation_weight,
            "created_at": weights.created_at.isoformat() if weights.created_at else None,
            "updated_at": weights.updated_at.isoformat() if weights.updated_at else None,
            "is_default": weights.organization is None
        }
    except Exception as e:
        logging.error(f"Error fetching weights for {organization}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.put("/api/confidence-weights")
async def update_global_confidence_weights(data: dict, db=Depends(get_db)):
    """Update global confidence weights with validation."""
    try:
        # Extract weights
        gpt = data.get("gpt_weight")
        pattern = data.get("pattern_weight")
        structure = data.get("structure_weight")
        framework = data.get("framework_weight")
        deviation = data.get("deviation_weight")
        
        # Validation: each factor 0.05-0.60, sum = 1.0
        weights_list = [gpt, pattern, structure, framework, deviation]
        
        if any(w is None for w in weights_list):
            return JSONResponse({"error": "All weight fields are required"}, status_code=400)
        
        if any(w < 0.05 or w > 0.60 for w in weights_list):
            return JSONResponse({"error": "Each weight must be between 0.05 and 0.60"}, status_code=400)
        
        total = sum(weights_list)
        if abs(total - 1.0) > 0.001:  # Allow small floating point tolerance
            return JSONResponse({"error": f"Weights must sum to 1.0 (got {total:.3f})"}, status_code=400)
        
        # Get existing global weights
        result = await db.execute(
            select(ConfidenceWeights).where(ConfidenceWeights.organization == None)
        )
        weights = result.scalar_one_or_none()
        
        # Store old weights for audit
        old_weights = None
        if weights:
            old_weights = {
                "gpt_weight": weights.gpt_weight,
                "pattern_weight": weights.pattern_weight,
                "structure_weight": weights.structure_weight,
                "framework_weight": weights.framework_weight,
                "deviation_weight": weights.deviation_weight
            }
        
        # Update or create
        if weights:
            weights.gpt_weight = gpt
            weights.pattern_weight = pattern
            weights.structure_weight = structure
            weights.framework_weight = framework
            weights.deviation_weight = deviation
            weights.updated_at = datetime.utcnow()
            change_type = "update"
        else:
            weights = ConfidenceWeights(
                organization=None,
                gpt_weight=gpt,
                pattern_weight=pattern,
                structure_weight=structure,
                framework_weight=framework,
                deviation_weight=deviation
            )
            db.add(weights)
            change_type = "create"
        
        await db.commit()
        await db.refresh(weights)
        
        # Create audit log
        audit = ConfidenceWeightAudit(
            weight_config_id=weights.id,
            organization=None,
            changed_by_user_id=data.get("user_id"),  # Optional user tracking
            old_weights=old_weights,
            new_weights={
                "gpt_weight": gpt,
                "pattern_weight": pattern,
                "structure_weight": structure,
                "framework_weight": framework,
                "deviation_weight": deviation
            },
            change_reason=data.get("reason", ""),
            change_type=change_type
        )
        db.add(audit)
        await db.commit()
        
        return {
            "status": "success",
            "message": f"Global weights {change_type}d successfully",
            "weights": {
                "gpt_weight": gpt,
                "pattern_weight": pattern,
                "structure_weight": structure,
                "framework_weight": framework,
                "deviation_weight": deviation
            }
        }
        
    except Exception as e:
        logging.error(f"Error updating global weights: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.put("/api/confidence-weights/org/{organization}")
async def update_org_confidence_weights(organization: str, data: dict, db=Depends(get_db)):
    """Create or update organization-specific confidence weights."""
    try:
        # Extract and validate weights (same as global)
        gpt = data.get("gpt_weight")
        pattern = data.get("pattern_weight")
        structure = data.get("structure_weight")
        framework = data.get("framework_weight")
        deviation = data.get("deviation_weight")
        
        weights_list = [gpt, pattern, structure, framework, deviation]
        
        if any(w is None for w in weights_list):
            return JSONResponse({"error": "All weight fields are required"}, status_code=400)
        
        if any(w < 0.05 or w > 0.60 for w in weights_list):
            return JSONResponse({"error": "Each weight must be between 0.05 and 0.60"}, status_code=400)
        
        total = sum(weights_list)
        if abs(total - 1.0) > 0.001:
            return JSONResponse({"error": f"Weights must sum to 1.0 (got {total:.3f})"}, status_code=400)
        
        # Get existing org weights
        result = await db.execute(
            select(ConfidenceWeights).where(ConfidenceWeights.organization == organization)
        )
        weights = result.scalar_one_or_none()
        
        old_weights = None
        if weights:
            old_weights = {
                "gpt_weight": weights.gpt_weight,
                "pattern_weight": weights.pattern_weight,
                "structure_weight": weights.structure_weight,
                "framework_weight": weights.framework_weight,
                "deviation_weight": weights.deviation_weight
            }
        
        if weights:
            weights.gpt_weight = gpt
            weights.pattern_weight = pattern
            weights.structure_weight = structure
            weights.framework_weight = framework
            weights.deviation_weight = deviation
            weights.updated_at = datetime.utcnow()
            change_type = "update"
        else:
            weights = ConfidenceWeights(
                organization=organization,
                gpt_weight=gpt,
                pattern_weight=pattern,
                structure_weight=structure,
                framework_weight=framework,
                deviation_weight=deviation
            )
            db.add(weights)
            change_type = "create"
        
        await db.commit()
        await db.refresh(weights)
        
        # Audit log
        audit = ConfidenceWeightAudit(
            weight_config_id=weights.id,
            organization=organization,
            changed_by_user_id=data.get("user_id"),
            old_weights=old_weights,
            new_weights={
                "gpt_weight": gpt,
                "pattern_weight": pattern,
                "structure_weight": structure,
                "framework_weight": framework,
                "deviation_weight": deviation
            },
            change_reason=data.get("reason", ""),
            change_type=change_type
        )
        db.add(audit)
        await db.commit()
        
        return {
            "status": "success",
            "message": f"Weights for {organization} {change_type}d successfully",
            "organization": organization,
            "weights": {
                "gpt_weight": gpt,
                "pattern_weight": pattern,
                "structure_weight": structure,
                "framework_weight": framework,
                "deviation_weight": deviation
            }
        }
        
    except Exception as e:
        logging.error(f"Error updating weights for {organization}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.delete("/api/confidence-weights/org/{organization}")
async def delete_org_confidence_weights(organization: str, data: dict, db=Depends(get_db)):
    """Delete organization-specific weights (falls back to global default)."""
    try:
        result = await db.execute(
            select(ConfidenceWeights).where(ConfidenceWeights.organization == organization)
        )
        weights = result.scalar_one_or_none()
        
        if not weights:
            return JSONResponse({"error": "No organization-specific weights found"}, status_code=404)
        
        old_weights = {
            "gpt_weight": weights.gpt_weight,
            "pattern_weight": weights.pattern_weight,
            "structure_weight": weights.structure_weight,
            "framework_weight": weights.framework_weight,
            "deviation_weight": weights.deviation_weight
        }
        
        weight_id = weights.id
        
        # Delete weights
        await db.delete(weights)
        await db.commit()
        
        # Audit log
        audit = ConfidenceWeightAudit(
            weight_config_id=None,  # Deleted, no longer exists
            organization=organization,
            changed_by_user_id=data.get("user_id"),
            old_weights=old_weights,
            new_weights={},  # Empty = deleted
            change_reason=data.get("reason", ""),
            change_type="delete"
        )
        db.add(audit)
        await db.commit()
        
        return {
            "status": "success",
            "message": f"Weights for {organization} deleted. Will use global defaults.",
            "organization": organization
        }
        
    except Exception as e:
        logging.error(f"Error deleting weights for {organization}: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/confidence-weights/reset")
async def reset_confidence_weights(data: dict, db=Depends(get_db)):
    """Reset weights to defaults: GPT 25%, Pattern 20%, Structure 20%, Framework 20%, Deviation 15%."""
    try:
        organization = data.get("organization")  # None = global, or specific org
        
        if organization:
            result = await db.execute(
                select(ConfidenceWeights).where(ConfidenceWeights.organization == organization)
            )
        else:
            result = await db.execute(
                select(ConfidenceWeights).where(ConfidenceWeights.organization == None)
            )
        
        weights = result.scalar_one_or_none()
        
        old_weights = None
        if weights:
            old_weights = {
                "gpt_weight": weights.gpt_weight,
                "pattern_weight": weights.pattern_weight,
                "structure_weight": weights.structure_weight,
                "framework_weight": weights.framework_weight,
                "deviation_weight": weights.deviation_weight
            }
        
        # Reset to defaults
        if weights:
            weights.gpt_weight = 0.25
            weights.pattern_weight = 0.20
            weights.structure_weight = 0.20
            weights.framework_weight = 0.20
            weights.deviation_weight = 0.15
            weights.updated_at = datetime.utcnow()
        else:
            weights = ConfidenceWeights(
                organization=organization,
                gpt_weight=0.25,
                pattern_weight=0.20,
                structure_weight=0.20,
                framework_weight=0.20,
                deviation_weight=0.15
            )
            db.add(weights)
        
        await db.commit()
        await db.refresh(weights)
        
        # Audit log
        audit = ConfidenceWeightAudit(
            weight_config_id=weights.id,
            organization=organization,
            changed_by_user_id=data.get("user_id"),
            old_weights=old_weights,
            new_weights={
                "gpt_weight": 0.25,
                "pattern_weight": 0.20,
                "structure_weight": 0.20,
                "framework_weight": 0.20,
                "deviation_weight": 0.15
            },
            change_reason=data.get("reason", "Reset to defaults"),
            change_type="reset"
        )
        db.add(audit)
        await db.commit()
        
        return {
            "status": "success",
            "message": f"Weights reset to defaults for {organization or 'global'}",
            "weights": {
                "gpt_weight": 0.25,
                "pattern_weight": 0.20,
                "structure_weight": 0.20,
                "framework_weight": 0.20,
                "deviation_weight": 0.15
            }
        }
        
    except Exception as e:
        logging.error(f"Error resetting weights: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/confidence-weights/audit-log")
async def get_confidence_weights_audit_log(
    organization: str = None,
    limit: int = 50,
    db=Depends(get_db)
):
    """Get audit log of confidence weight changes for compliance tracking."""
    try:
        query = select(ConfidenceWeightAudit).order_by(ConfidenceWeightAudit.changed_at.desc())
        
        if organization:
            query = query.where(ConfidenceWeightAudit.organization == organization)
        
        query = query.limit(limit)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        return {
            "logs": [
                {
                    "id": log.id,
                    "organization": log.organization,
                    "changed_by_user_id": log.changed_by_user_id,
                    "old_weights": log.old_weights,
                    "new_weights": log.new_weights,
                    "change_reason": log.change_reason,
                    "change_type": log.change_type,
                    "changed_at": log.changed_at.isoformat()
                }
                for log in logs
            ],
            "total": len(logs)
        }
        
    except Exception as e:
        logging.error(f"Error fetching audit log: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

# ============================================================================
# END VERIFICATION ENDPOINTS
# ============================================================================

# REMOVED: PATCH /report/{scan_id}/suborgs/{suborg_id}/annotation
# Now handled by backend/app/routers/suborg_router.py

# REMOVED: PATCH /report/{scan_id}/suborgs/id/{suborg_id}
# Now handled by backend/app/routers/suborg_router.py

# REMOVED: PATCH /report/{scan_id}/suborgs/{suborg_name}
# Now handled by backend/app/routers/suborg_router.py

# ---- Create endpoints: allow adding rows missed by extraction ----

# Utility functions moved to services/utils.py
_norm_pct_like = utils.normalize_percent_like
_as_float_or_none = utils.as_float_or_none

# REMOVED: POST /report/{scan_id}/suborgs
# Now handled by backend/app/routers/suborg_router.py

# REMOVED: POST /report/{scan_id}/cuecs
# Now handled by backend/app/routers/cuec_router.py

@app.post("/report/{scan_id}/controls")
async def create_control(scan_id: int, data: dict, db=Depends(get_db)):
    """Create a new Control row for a scan."""
    try:
        desc = str(data.get("control_desc", "")).strip()
        if not desc and not str(data.get("control_id", "")).strip():
            raise HTTPException(status_code=400, detail="control_desc or control_id is required")
        conf = _norm_pct_like(data.get("control_confidence"))
        ctrl = Control(
            scan_id=scan_id,
            control_id=(str(data.get("control_id") or "").strip() or None),
            control_desc=(desc or None),
            control_test=(str(data.get("control_test") or "").strip() or None),
            control_test_results=(str(data.get("control_test_results") or "").strip() or None),
            has_deviation=data.get("has_deviation"),
            deviation_desc=(str(data.get("deviation_desc") or "").strip() or None),
            control_tsc_id=(str(data.get("control_tsc_id") or "").strip() or None),
            control_coso_id=(str(data.get("control_coso_id") or "").strip() or None),
            control_confidence=conf,
            control_page_refs=_parse_page_refs(data.get("control_page_refs") or data.get("control_page_ref")),
            control_line_ref=_as_float_or_none(data.get("control_line_ref")),
            control_seq=_as_float_or_none(data.get("control_seq")),
            annotation=data.get("annotation"),
        )
        db.add(ctrl)
        scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if scan_row:
            scan_row.executive_summary_stale = True
            db.add(scan_row)
        await db.commit()
        await db.refresh(ctrl)
        return {
            "id": ctrl.id,
            "control_id": ctrl.control_id,
            "control_desc": ctrl.control_desc,
            "control_test": ctrl.control_test,
            "control_test_results": ctrl.control_test_results,
            "has_deviation": ctrl.has_deviation,
            "deviation_desc": ctrl.deviation_desc,
            "control_tsc_id": ctrl.control_tsc_id,
            "control_coso_id": ctrl.control_coso_id,
            "control_confidence": ctrl.control_confidence,
            "control_page_refs": ctrl.control_page_refs,
            "control_line_ref": ctrl.control_line_ref,
            "control_seq": ctrl.control_seq,
            "annotation": ctrl.annotation,
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"create_control error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/report/{scan_id}/extract-entity")
async def extract_entity(
    scan_id: int, 
    data: dict, 
    db=Depends(get_db)
):
    """
    Extract entity information from the report text using GPT.
    Searches for the specified text and extracts structured data from surrounding context.
    """
    import asyncio
    import json as json_lib
    from .gpt_client import gpt_extract
    from .config import ENTITY_EXTRACTION_FROM_CONTEXT_PROMPT, MAX_SEARCH_OCCURRENCES, ENTITY_EXTRACTION_TIMEOUT
    
    try:
        entity_type = data.get("entity_type", "").lower()
        search_text = (data.get("search_text") or "").strip()
        force_multi_extract = data.get("force_multi_extract", False)
        
        # Validate inputs
        if not search_text:
            raise HTTPException(status_code=400, detail="search_text is required")
        
        if entity_type not in ["control", "cuec", "subservice_org"]:
            raise HTTPException(status_code=400, detail="entity_type must be 'control', 'cuec', or 'subservice_org'")
        
        # Load the scan's extracted_text
        result = await db.execute(select(Scan).filter(Scan.id == scan_id))
        scan_row = result.scalars().first()
        
        if not scan_row:
            raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")
        
        if not scan_row.extracted_text:
            raise HTTPException(status_code=404, detail=f"Extracted text not available for scan {scan_id}")
        
        full_text = scan_row.extracted_text
        
        # Find all occurrences (case-insensitive)
        occurrences = []
        start_idx = 0
        search_lower = search_text.lower()
        text_lower = full_text.lower()
        
        while True:
            idx = text_lower.find(search_lower, start_idx)
            if idx == -1:
                break
            occurrences.append(idx)
            start_idx = idx + 1
        
        if not occurrences:
            return {
                "error": f"Search term '{search_text}' not found in report",
                "occurrence_count": 0
            }
        
        # Check occurrence count and warn if needed
        if len(occurrences) > MAX_SEARCH_OCCURRENCES and not force_multi_extract:
            return {
                "warning": f"Found {len(occurrences)} occurrences. Consider refining your search term or enable 'force_multi_extract'.",
                "occurrence_count": len(occurrences),
                "requires_force": True
            }
        
        # Extract context windows (±2000 chars) for each occurrence
        CONTEXT_WINDOW = 2000
        contexts = []
        
        for occ_idx in occurrences[:MAX_SEARCH_OCCURRENCES if not force_multi_extract else None]:
            start = max(0, occ_idx - CONTEXT_WINDOW)
            end = min(len(full_text), occ_idx + len(search_text) + CONTEXT_WINDOW)
            context = full_text[start:end]
            contexts.append(context)
        
        # Concatenate contexts with separators
        combined_context = "\n\n=== OCCURRENCE SEPARATOR ===\n\n".join(contexts)
        
        # Build prompt
        prompt = ENTITY_EXTRACTION_FROM_CONTEXT_PROMPT.format(
            entity_type=entity_type,
            search_text=search_text,
            occurrence_count=len(contexts),
            text_context=combined_context
        )
        
        # Call GPT synchronously in thread pool (gpt_extract is synchronous)
        def call_gpt_sync():
            return gpt_extract(prompt, f"entity_extraction_{entity_type}")
        
        loop = asyncio.get_event_loop()
        try:
            result_text = await asyncio.wait_for(
                loop.run_in_executor(None, call_gpt_sync),
                timeout=ENTITY_EXTRACTION_TIMEOUT
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail=f"Entity extraction timed out after {ENTITY_EXTRACTION_TIMEOUT}s")
        
        # Extract JSON from markdown code blocks if present
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', result_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
        else:
            # Try to find raw JSON object
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            json_text = json_match.group(0) if json_match else result_text
        
        # Parse JSON response
        result_data = json_lib.loads(json_text)
        
        return {
            "entity_type": entity_type,
            "search_text": search_text,
            "occurrence_count": len(contexts),
            "extracted_data": result_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"extract_entity error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Entity extraction failed: {e}")

@app.get("/test/gpt-models")
async def test_gpt_models():
    """
    Test which GPT models are available in the Dataiku environment.
    Attempts to call GPT-4o, GPT-5 (if available), and reports results.
    """
    results = {}
    test_prompt = "What is 2+2? Answer with just the number."
    
    # Test GPT-4o (known working)
    try:
        from .gpt_client import _chat_completion
        start_time = time.time()
        response_4o = _chat_completion(test_prompt, "test_extractor", override_model="gpt-4o")
        duration_4o = time.time() - start_time
        results["gpt-4o"] = {
            "available": True,
            "response": response_4o[:200],  # Truncate for safety
            "duration_seconds": round(duration_4o, 2),
            "error": None
        }
    except Exception as e:
        results["gpt-4o"] = {
            "available": False,
            "response": None,
            "duration_seconds": None,
            "error": str(e)
        }
    
    # Test GPT-5
    try:
        from .gpt_client import _chat_completion
        start_time = time.time()
        response_5 = _chat_completion(test_prompt, "test_extractor", override_model="gpt-5")
        duration_5 = time.time() - start_time
        results["gpt-5"] = {
            "available": True,
            "response": response_5[:200],  # Truncate for safety
            "duration_seconds": round(duration_5, 2),
            "error": None
        }
    except Exception as e:
        results["gpt-5"] = {
            "available": False,
            "response": None,
            "duration_seconds": None,
            "error": str(e)
        }
    
    # Test o1 (reasoning model)
    try:
        from .gpt_client import _chat_completion
        start_time = time.time()
        response_o1 = _chat_completion(test_prompt, "test_extractor", override_model="o1")
        duration_o1 = time.time() - start_time
        results["o1"] = {
            "available": True,
            "response": response_o1[:200],
            "duration_seconds": round(duration_o1, 2),
            "error": None
        }
    except Exception as e:
        results["o1"] = {
            "available": False,
            "response": None,
            "duration_seconds": None,
            "error": str(e)
        }
    
    return {
        "test_time": datetime.datetime.utcnow().isoformat(),
        "provider": cfg.LLM_PROVIDER,
        "dataiku_host": cfg.DATAIKU_DSS_HOST,
        "results": results
    }


# ============================================================================
# VALIDATION BASELINE ENDPOINTS
# ============================================================================

from .baseline_manager import BaselineManager

@app.post("/baseline/create")
async def create_validation_baseline(
    scan_id: int,
    extractor_version: str,
    reviewer_notes: Optional[str] = None,
    db = Depends(get_db)
):
    """
    Create a validation baseline from an approved scan.
    Used for regression testing and accuracy monitoring.
    """
    try:
        # Fetch scan data
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan_row = result.scalar_one_or_none()
        if not scan_row:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Fetch all related data
        controls = (await db.execute(select(Control).where(Control.scan_id == scan_id))).scalars().all()
        cuecs = (await db.execute(select(CUEC).where(CUEC.scan_id == scan_id))).scalars().all()
        suborgs = (await db.execute(select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id))).scalars().all()
        
        # Build scan data dict
        scan_data = {
            "scan_id": scan_id,
            "report_type": getattr(scan_row, "report_type", "SOC2"),
            "filename": scan_row.pdf_filename,
            "scan_date": scan_row.scan_date.isoformat() if scan_row.scan_date else None,
            "controls": [
                {k: getattr(ctrl, k, None) for k in [
                    "id", "control_id", "control_desc", "control_confidence",
                    "financial_assertions", "framework_category", "control_tsc_mappings"
                ]} for ctrl in controls
            ],
            "cuecs": [
                {k: getattr(c, k, None) for k in [
                    "id", "cuec_tsc_id", "cuec_description", "cuec_confidence"
                ]} for c in cuecs
            ],
            "subservice_orgs": [
                {k: getattr(s, k, None) for k in [
                    "id", "name", "confidence", "likely_so"
                ]} for s in suborgs
            ]
        }
        
        # Extract report name from filename
        report_name = scan_row.pdf_filename.rsplit('.', 1)[0] if scan_row.pdf_filename else f"scan_{scan_id}"
        
        # Create baseline
        baseline_info = BaselineManager.create_baseline(
            scan_data=scan_data,
            report_name=report_name,
            extractor_version=extractor_version,
            reviewer_notes=reviewer_notes
        )
        
        return baseline_info
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to create baseline: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Baseline creation failed: {e}")


@app.get("/baseline/list")
async def list_baselines(report_name: Optional[str] = None):
    """List all validation baselines, optionally filtered by report name."""
    try:
        baselines = BaselineManager.list_baselines(report_name)
        return {"baselines": baselines, "count": len(baselines)}
    except Exception as e:
        logging.error(f"Failed to list baselines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/baseline/{baseline_id}")
async def get_baseline(baseline_id: str):
    """Get a specific baseline by ID."""
    try:
        baseline = BaselineManager.get_baseline(baseline_id)
        if not baseline:
            raise HTTPException(status_code=404, detail="Baseline not found")
        return baseline
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to get baseline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/baseline/compare")
async def compare_to_baseline(
    scan_id: int,
    baseline_id: str,
    db = Depends(get_db)
):
    """Compare current scan results to a baseline for regression detection."""
    try:
        # Fetch current scan data (same as create_baseline)
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan_row = result.scalar_one_or_none()
        if not scan_row:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        controls = (await db.execute(select(Control).where(Control.scan_id == scan_id))).scalars().all()
        
        current_scan = {
            "scan_id": scan_id,
            "controls": [
                {k: getattr(ctrl, k, None) for k in [
                    "id", "control_id", "control_desc", "control_confidence",
                    "financial_assertions", "framework_category"
                ]} for ctrl in controls
            ]
        }
        
        # Compare
        comparison = BaselineManager.compare_to_baseline(current_scan, baseline_id)
        return comparison
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to compare baseline: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/baseline/{baseline_id}")
async def delete_baseline(baseline_id: str):
    """Delete a baseline by ID."""
    try:
        success = BaselineManager.delete_baseline(baseline_id)
        if not success:
            raise HTTPException(status_code=404, detail="Baseline not found")
        return {"message": "Baseline deleted", "baseline_id": baseline_id}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to delete baseline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PHASE 2: Framework Mappings Migration Endpoint
# ============================================================================

@app.post("/report/{scan_id}/migrate_framework_mappings")
async def migrate_scan_framework_mappings(scan_id: int, db=Depends(get_db)):
    """
    Migrate legacy framework mapping columns to unified framework_mappings structure.
    
    Phase 2: Consolidates control_tsc_mappings, control_coso_mappings, and
    financial_assertions into the new framework_mappings JSON column.
    
    This is a one-time migration endpoint that can be run on existing scans
    to populate the new Phase 1 columns.
    """
    from .frameworks.migration_helper import migrate_scan_frameworks
    
    logging.info(f"[MIGRATE_ENDPOINT] Starting migration for scan_id={scan_id}")
    
    try:
        # Verify scan exists
        scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if not scan_row:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Run migration
        result = await migrate_scan_frameworks(db, scan_id)
        
        logging.info(f"[MIGRATE_ENDPOINT] Migration complete for scan_id={scan_id}: {result}")
        
        return {
            "status": "success",
            "message": f"Migrated scan {scan_id} to unified framework_mappings",
            "statistics": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logging.error(f"[MIGRATE_ENDPOINT] Migration failed for scan_id={scan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")



