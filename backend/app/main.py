import os
import sys
import uuid
import json as _json
import shutil
import threading
import time
import datetime
import logging
import traceback
import pathlib
import asyncio
import sqlalchemy
import sqlalchemy.dialects.postgresql as pg_dialect
import redis.asyncio as redis
import redis as sync_redis
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request, UploadFile, File, APIRouter
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
from sqlalchemy.future import select
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.exc import SQLAlchemyError
from .models import Company, Control, CUEC, SubserviceOrg, Product, Setting, Base
from .models import Scan
from .database import engine, get_db
from .config import AUTO_CREATE_SCHEMA, RUN_MIGRATIONS_ON_START, ALEMBIC_INI_PATH, LOG_LEVEL, EXCLUDE_ACCESS_LOG_PATHS
from .analyze import analyze_pdf_file
from .config import REDIS_URL, TSC_CRITERIA, COSO_2013_CRITERIA, GPT_PROMPTS
from .config import (
    EXEC_SUMMARY_TEST_RESULTS_BUDGET_CHARS,
    EXEC_SUMMARY_PER_CONTROL_MAX_CHARS,
    EXEC_SUMMARY_MAX_NON_DEVIATION_CONTROLS,
)
from .explicit_sql_insert import insert_extracted_data
import concurrent.futures
from .gpt_client import gpt_extract

app = FastAPI()

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



@app.get("/report/{scan_id}")
async def get_report(scan_id: int, diag: bool = False, db=Depends(get_db)):
    try:
        logging.error(f"[REPORT] Enter get_report scan_id={scan_id}, diag={diag}")
        # Fetch scan row for all data
        scan_row = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan_row = scan_row.scalar_one_or_none()
        if not scan_row:
            raise HTTPException(status_code=404, detail="Scan not found")

        # Diagnostic short-circuit to isolate 500s occurring outside main logic
        if diag:
            logging.error(f"[REPORT] DIAG mode active for scan_id={scan_id}")
            minimal = {
                "scan_id": scan_row.id,
                "has_result_json": bool(getattr(scan_row, "result_json", None)),
                "has_company": bool((await db.execute(select(Company).where(Company.scan_id == scan_id))).scalars().first() is not None),
            }
            from starlette.responses import Response
            import json as _json_mod
            logging.error(f"[REPORT] DIAG returning minimal payload for scan_id={scan_id}: {minimal}")
            return Response(content=_json_mod.dumps(minimal), media_type="application/json")

        # Fetch selected related entities (now that schema is aligned)
        company = (await db.execute(select(Company).where(Company.scan_id == scan_id))).scalars().first()
        controls = (await db.execute(select(Control).where(Control.scan_id == scan_id))).scalars().all()
        cuecs = (await db.execute(select(CUEC).where(CUEC.scan_id == scan_id))).scalars().all()
        suborgs = (await db.execute(select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id))).scalars().all()
        product = (await db.execute(select(Product).where(Product.scan_id == scan_id))).scalars().first()

        # Extract additional fields from the results JSON if present
        results = scan_row.result_json or {}
        auditor = scan_row.auditor if getattr(scan_row, 'auditor', None) else results.get("auditor", {})
        coverage_period = results.get("coverage_period", {})
        report_date = results.get("report_date", {})
        def extract_bad_chunks(section):
            if isinstance(section, dict):
                return section.get("bad_chunks", [])
            return []
        bad_chunks = {
            "cuecs": extract_bad_chunks(results.get("cuecs")),
            "controls": extract_bad_chunks(results.get("controls")),
            "subservice_orgs": extract_bad_chunks(results.get("subservice_orgs"))
        }

        # Compose response with all expected fields for frontend tables
        # Extract persisted bad_chunks from result_json (supports both embedded and *_meta variants)
        def get_persisted_bad_chunks(section_key: str):
            sec_val = results.get(section_key)
            meta_val = results.get(f"{section_key}_meta")
            chunks = []
            if isinstance(sec_val, dict) and isinstance(sec_val.get("bad_chunks"), list):
                chunks = sec_val.get("bad_chunks")
            elif isinstance(meta_val, dict) and isinstance(meta_val.get("bad_chunks"), list):
                chunks = meta_val.get("bad_chunks")
            return chunks
        persisted_bad_chunks = {
            "cuecs": get_persisted_bad_chunks("cuecs"),
            "controls": get_persisted_bad_chunks("controls"),
            "subservice_orgs": get_persisted_bad_chunks("subservice_orgs"),
        }
        payload = {
            "scan_id": scan_row.id,
            # Ensure datetimes are JSON-serializable
            "scan_date": (scan_row.scan_date.isoformat() if getattr(scan_row, "scan_date", None) else None),
            "filename": scan_row.pdf_filename,
            "company": company.name if company else None,
            "parent_company": company.parent_company if company else None,
            "auditor": getattr(scan_row, "auditor", None) or auditor,
            "coverage_period": coverage_period,
            "coverage_start": (getattr(scan_row, "coverage_start", None).isoformat() if getattr(scan_row, "coverage_start", None) else None),
            "coverage_end": (getattr(scan_row, "coverage_end", None).isoformat() if getattr(scan_row, "coverage_end", None) else None),
            "report_date": report_date,
            "product": product.name if product else None,
            "gpt_cost": getattr(scan_row, "gpt_cost", None),
            "gpt_model": getattr(scan_row, "gpt_model", None),
            "estimated_time_seconds": getattr(scan_row, "estimated_time_seconds", None),
            # Omit large/unused blobs to keep response lean and avoid serialization issues
            # "gpt_usage_details": getattr(scan_row, "gpt_usage_details", None),
            # "extracted_text": getattr(scan_row, "extracted_text", None),
            "pdf_filename": getattr(scan_row, "pdf_filename", None),
            # Do not include raw PDF bytes in JSON (not JSON-serializable and not needed by UI)
            # "pdf_file": getattr(scan_row, "pdf_file", None),
            "company_id": getattr(scan_row, "company_id", None),
            "executive_summary_stale": getattr(scan_row, "executive_summary_stale", False),
            # Temporarily return empty lists to isolate serialization issues
            "subservice_organizations": [
                {
                    "id": getattr(s, "id", None),
                    "name": getattr(s, "name", None),
                    "confidence": getattr(s, "confidence", None),
                    "third_party_description": getattr(s, "third_party_description", None),
                    "third_party_page_ref": getattr(s, "third_party_page_ref", None),
                    "third_party_confidence": getattr(s, "third_party_confidence", None),
                    "distance_from_so_keywords": getattr(s, "distance_from_so_keywords", None),
                    "likely_so": getattr(s, "likely_so", None),
                    "common_so": getattr(s, "common_so", None),
                    "source_context": getattr(s, "source_context", None),
                    "confidence_justification": getattr(s, "confidence_justification", None),
                    "third_party_controls": getattr(s, "third_party_controls", None),
                    "annotation": getattr(s, "annotation", None),
                } for s in suborgs
            ],
            "cuecs": [
                {
                    "id": getattr(c, "id", None),
                    "cuec_seq": getattr(c, "cuec_seq", None),
                    "cuec_id": getattr(c, "cuec_tsc_id", None),
                    "cuec_tsc_id": getattr(c, "cuec_tsc_id", None),
                    "cuec_description": getattr(c, "cuec_description", None) or getattr(c, "description", None),
                    "cuec_line_ref": getattr(c, "cuec_line_ref", None),
                    "cuec_confidence": getattr(c, "cuec_confidence", None),
                    "cuec_gpt_opinion": getattr(c, "cuec_gpt_opinion", None),
                    "cuec_distance_from_cuec_keywords": getattr(c, "cuec_distance_from_cuec_keywords", None),
                    "cuec_gpt_reasoning": getattr(c, "cuec_gpt_reasoning", None),
                    "cuec_framework_alignment": getattr(c, "cuec_framework_alignment", None),
                    "cuec_framework_alignment_id": getattr(c, "cuec_framework_alignment_id", None),
                    "cuec_justification": getattr(c, "cuec_justification", None),
                    "cuec_coso_id": getattr(c, "cuec_coso_id", None),
                    "cuec_tsc_similarity": getattr(c, "cuec_tsc_similarity", None),
                    "cuec_coso_similarity": getattr(c, "cuec_coso_similarity", None),
                    "cuec_tsc_confidence_pct": getattr(c, "cuec_tsc_confidence_pct", None),
                    "cuec_coso_confidence_pct": getattr(c, "cuec_coso_confidence_pct", None),
                    "cuec_closest_framework": getattr(c, "cuec_closest_framework", None),
                    "cuec_confidence_justification": getattr(c, "cuec_confidence_justification", None),
                    "annotation": getattr(c, "annotation", None),
                    "control_strength": getattr(c, "control_strength", None),
                } for c in cuecs
                ],
            "controls": [
                ({"id": getattr(ctrl, "id", None)} | {k: getattr(ctrl, k, None) for k in [
                    "control_id",
                    "control_desc",
                    "control_test",
                    "control_test_results",
                    "has_deviation",
                    "deviation_desc",
                    "control_page_ref",
                    "control_line_ref",
                    "control_seq",
                    "control_tsc_id",
                    "control_coso_id",
                    "control_tsc_similarity",
                    "control_coso_similarity",
                    "control_tsc_confidence_pct",
                    "control_coso_confidence_pct",
                    "control_closest_framework",
                    "control_tsc_section",
                    "control_coso_section",
                    "control_soc_domain",
                    "control_status",
                    "merged_to_control_id",
                    "control_gpt_opinion",
                    "control_gpt_reasoning",
                    "control_confidence",
                    "confidence_calc",
                    "annotation"
                ]}) for ctrl in controls
            ],
            "bad_chunks": bad_chunks if any(bad_chunks.values()) else persisted_bad_chunks,
            # "raw_results": results,
            "executive_summary": getattr(scan_row, "executive_summary", None)
        }
        # Ensure everything is JSON-serializable
        try:
            encoded = jsonable_encoder(payload)
            import json as _json_mod
            from starlette.responses import Response
            resp_text = _json_mod.dumps(encoded)
            logging.error(f"[REPORT] Returning payload for scan_id={scan_id} (size={len(resp_text)} bytes)")
            return Response(content=resp_text, media_type="application/json")
        except Exception as enc_err:
            logging.error(f"/report/{scan_id} jsonable_encoder error: {enc_err}\n{traceback.format_exc()}")
            # Last-resort: stringify unknown types
            import json as _json_mod
            try:
                text = _json_mod.dumps(payload, default=lambda o: str(o))
                from starlette.responses import Response
                return Response(content=text, media_type="application/json")
            except Exception as dump_err:
                logging.error(f"/report/{scan_id} json dumps fallback error: {dump_err}\n{traceback.format_exc()}")
                raise
    except Exception as e:
        logging.error(f"[REPORT] /report/{scan_id} error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Report retrieval failed: {e}")


async def get_job(job_id, redis_client=None):
    if redis_client is None:
        redis_client = _get_redis()
    job_json = await redis_client.get(f"job:{job_id}")
    if job_json:
        return _json.loads(job_json)
    return None

async def set_job(job_id, job_dict, redis_client=None):
    if redis_client is None:
        redis_client = _get_redis()
    await redis_client.set(f"job:{job_id}", _json.dumps(job_dict), ex=60*60*24)  # 24h expiry

async def del_job(job_id, redis_client=None):
    if redis_client is None:
        redis_client = _get_redis()
    await redis_client.delete(f"job:{job_id}")

def _get_redis():
    return redis.from_url(REDIS_URL, decode_responses=True)

def run_analysis_job(job_id, temp_pdf_path, filename, db):
    import logging
    import asyncio
    import threading
    import time
    start_time = time.time()
    
    # logging.error(f"[DEBUG] [run_analysis_job] Thread: {threading.current_thread().name}, job_id={job_id}")
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
    try:
        from .analyze import analyze_pdf_file
        redis_client = sync_redis.from_url(REDIS_URL, decode_responses=True)
        # Check for cancellation before starting
        job_json = redis_client.get(f"job:{job_id}")
        if job_json and isinstance(job_json, str):
            job = _json.loads(job_json)
            if job.get("cancelled"):
                raise Exception("Scan cancelled by user")
        # Run the analysis, but check for cancellation after each major step
        results = analyze_pdf_file(
            temp_pdf_path,
            progress_callback=progress_callback,
            checklist_callback=checklist_callback
        )
        
        # Add timing and filename metadata to results
        elapsed_time = time.time() - start_time
        results["estimated_time_seconds"] = elapsed_time
        results["pdf_filename"] = filename
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
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmpf:
                _json.dump(results, tmpf, ensure_ascii=False)
                tmpf.flush()
                tmp_path = tmpf.name
            
            # Insert into database
            summary = insert_extracted_data(tmp_path)
            logging.error(f"[SUCCESS] Database insertion completed: {summary}")
            
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
            job["result"] = results
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
        except Exception:
            pass


# --- FastAPI app definition must come before any route decorators ---
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Optional
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request, Depends, UploadFile, File
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from .models import Setting, Base
from .database import engine, get_db
from .analyze import analyze_pdf_file
import threading
import time
import sqlalchemy
import sqlalchemy.dialects.postgresql as pg_dialect
import asyncio
import os
import shutil
import datetime
import logging
import traceback


# ...existing code...

@app.post("/analyze/")
async def analyze_pdf_bg(file: UploadFile = File(...), db=Depends(get_db)):
    temp_dir = "data/tmp"
    os.makedirs(temp_dir, exist_ok=True)
    filename = file.filename if file.filename else "uploaded.pdf"
    temp_pdf_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{filename}")
    with open(temp_pdf_path, "wb") as f_out:
        shutil.copyfileobj(file.file, f_out)
    job_id = str(uuid.uuid4())
    await set_job(job_id, {
        "status": "Queued",
        "progress": 0,
        "done": False,
        "result": None,
        "error": None,
        "checklist": [],
        "filename": filename
    })
    # Start background thread
    thread = threading.Thread(target=run_analysis_job, args=(job_id, temp_pdf_path, filename, db))
    thread.start()
    return {"job_id": job_id}

# New endpoint: poll job status
@app.get("/analyze/status/{job_id}")
async def get_job_status(job_id: str):
    import logging
    # Remove or downgrade excessive logging for status checks
    # print(f"[PRINT] get_job_status called for job_id={job_id}")
    logging.info(f"[INFO] get_job_status: called for job_id={job_id}")
    job = await get_job(job_id)
    if not job:
        # print(f"[PRINT] get_job_status: job_id={job_id} NOT FOUND")
        logging.error(f"[ERROR] get_job_status: job_id={job_id} NOT FOUND")
        return {"error": "Job not found"}
    # Remove detailed job state logging for status checks
    # print(f"[PRINT] get_job_status: job_id={job_id}, job={job}")
    # logging.info(f"[INFO] get_job_status: job_id={job_id}, job={job}")
    # print(f"[PRINT] get_job_status fields: progress={job.get('progress')}, checklist={job.get('checklist')}, status={job.get('status')}, done={job.get('done')}, error={job.get('error')}, filename={job.get('filename')}")
    # logging.info(f"[INFO] get_job_status fields: progress={job.get('progress')}, checklist={job.get('checklist')}, status={job.get('status')}, done={job.get('done')}, error={job.get('error')}, filename={job.get('filename')}")
    return {
        "status": job.get("status"),
        "progress": job.get("progress"),
        "done": job.get("done"),
        "error": job.get("error"),
        "checklist": job.get("checklist", []),
        "filename": job.get("filename"),
        "_debug_job": job  # Include full job state for frontend debugging (remove in prod)
    }

# New endpoint: get job result
@app.get("/analyze/result/{job_id}")
async def get_job_result(job_id: str, force_save: bool = False, db=Depends(get_db)):
    job = await get_job(job_id)
    if not job:
        return {"error": "Job not found"}
    if not job.get("done"):
        return {"error": "Job not finished yet"}

    # Persist to DB if not saved yet or force_save requested
    if (force_save or not job.get("db_saved")) and job.get("result"):
        import pathlib
        import tempfile
        import json as _json
        # Write result to a temp file and call insert_extracted_data
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmpf:
            _json.dump(job["result"], tmpf, ensure_ascii=False)
            tmpf.flush()
            tmp_path = tmpf.name
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            summary = await loop.run_in_executor(pool, insert_extracted_data, tmp_path)
        job["db_saved"] = True
        await set_job(job_id, job)
        # Optionally, you can return the summary in the response
        return {"insert_summary": summary, "results": job.get("result")}
    # If there was an error, return it along with any partial result
    if job.get("error"):
        return {"error": job.get("error"), "partial_result": job.get("result")}
    return {"results": job.get("result")}

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
async def get_settings(db=Depends(get_db)):
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

# History endpoints
@app.get("/history")
async def get_history(db=Depends(get_db)):
    result = await db.execute(select(Scan).order_by(Scan.scan_date.desc()).limit(20))
    history = [
        {
            "id": row.id,
            "timestamp": row.scan_date.isoformat() if row.scan_date else None,
            "filename": row.pdf_filename,
            "results": row.result_json
        }
        for row in result.scalars()
    ]
    return history

@app.get("/report_diag/{scan_id}")
async def report_diag(scan_id: int):
    try:
        logging.error(f"[REPORT_DIAG] Entered report_diag with scan_id={scan_id}")
        return {"ok": True, "scan_id": scan_id}
    except Exception as e:
        logging.error(f"[REPORT_DIAG] error: {e}\n{traceback.format_exc()}")
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

@app.post("/analyze/cancel/{job_id}")
async def cancel_job(job_id: str):
    redis_client = _get_redis()
    job_json = await get_job(job_id, redis_client)
    if not job_json:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    job_json["cancelled"] = True
    await set_job(job_id, job_json, redis_client)
    return {"status": "cancelled"}

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
    # Group TSC by section
    tsc_by_section = {}
    for crit in TSC_CRITERIA:
        section = crit.get("section", "Unspecified")
        if section not in tsc_by_section:
            tsc_by_section[section] = []
        tsc_by_section[section].append({"id": crit["id"], "description": crit["description"]})
    # Group COSO by component/section
    coso_by_section = {}
    for crit in COSO_2013_CRITERIA:
        section = crit.get("component", "Unspecified")
        if section not in coso_by_section:
            coso_by_section[section] = []
        coso_by_section[section].append({"id": crit["id"], "description": crit["description"]})
    return {"tsc": tsc_by_section, "coso": coso_by_section}

@app.get("/executive_summary/{scan_id}")
async def get_executive_summary(scan_id: int, force_refresh: bool = False, db=Depends(get_db)):
    # Force fresh read from database to avoid caching issues
    await db.commit()  # Ensure any pending transactions are committed
    scan_row = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan_row = scan_row.scalar_one_or_none()
    if not scan_row:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    # If we already have a summary and it's not marked stale, return it unless force_refresh is requested
    existing_summary = getattr(scan_row, "executive_summary", None)
    is_stale = bool(getattr(scan_row, "executive_summary_stale", False))
    if not force_refresh and existing_summary is not None and existing_summary != "null" and existing_summary and not is_stale:
        # Get the summary BEFORE rollback to avoid session issues
        summary = existing_summary
        await db.rollback()  # Clean up any pending transaction
        
        # Parse the JSON if it's stored as a string
        if isinstance(summary, str):
            import json
            try:
                summary = json.loads(summary)
            except:
                pass  # If parsing fails, return as-is
        return {"executive_summary": summary}
    
    # Otherwise, generate summary using GPT
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
    prompt = GPT_PROMPTS['executive_summary'].format(
        suborg_count=suborg_count,
        cuec_count=cuec_count,
        tsc_covered=sum(1 for row in tsc_table if row['present']),
        tsc_total=len(tsc_table),
        coso_covered=sum(1 for row in coso_table if row['present']),
        coso_total=len(coso_table),
        tsc_table=tsc_table_str,
        coso_table=coso_table_str,
        control_test_results=control_test_results_str,
        detected_deviations=detected_deviations_str,
        cuec_control_strengths=cuec_control_strengths_str,
        company=company_name,
        product=product_name
    )
    # No heuristic pre-computed deviations; rely on GPT to analyze control_test_results in the prompt
    import json
    

    
    print(f"REGENERATE DEBUG: Generating new executive summary for scan {scan_id}")
    print(f"REGENERATE DEBUG: Calling GPT to generate real summary")
    
    # Log the full prompt being sent to GPT
    print(f"REGENERATE DEBUG: Executive Summary GPT Prompt:")
    print("=" * 80)
    print(prompt)
    print("=" * 80)
    
    # Also log to file for later review (reset file each time)
    import os
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
    scan_row.executive_summary = summary_json
    scan_row.executive_summary_stale = False  # Reset staleness flag
    db.add(scan_row)
    await db.commit()
    
    print(f"REGENERATE DEBUG: Executive summary saved successfully for scan {scan_id}")
    return {"executive_summary": summary_json}

@app.post("/executive_summary/{scan_id}")
async def regenerate_executive_summary(scan_id: int, db=Depends(get_db)):
    """Force regeneration of executive summary by clearing it"""
    print(f"REGENERATE DEBUG: Received request to regenerate executive summary for scan {scan_id}")
    
    scan_row = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan_row = scan_row.scalar_one_or_none()
    if not scan_row:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    print(f"REGENERATE DEBUG: Found scan {scan_id}, clearing existing summary")
    # Clear existing summary to force regeneration
    scan_row.executive_summary = None
    scan_row.executive_summary_stale = True  # Mark as stale
    db.add(scan_row)
    await db.commit()
    
    print(f"REGENERATE DEBUG: Executive summary cleared for scan {scan_id}")
    return {"status": "Executive summary cleared. Refresh the page to regenerate."}

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

@app.patch("/report/{scan_id}/overview")
async def patch_report_overview(scan_id: int, data: dict, db=Depends(get_db)):
    logging.debug(f"/report/{scan_id}/overview payload: {data}")
    try:
        scan_row = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan_row = scan_row.scalar_one_or_none()
        if not scan_row:
            return JSONResponse({"error": "Scan not found"}, status_code=404)
        if "company" in data:
            scan_row.company = data["company"]
        if "product" in data:
            scan_row.product = data["product"]
        if "coverageStart" in data:
            scan_row.coverage_start = data["coverageStart"]
        if "coverageEnd" in data:
            scan_row.coverage_end = data["coverageEnd"]
        if "reportDate" in data:
            scan_row.report_date = data["reportDate"]
        if "auditor" in data:
            scan_row.auditor = data["auditor"]
        if "scanDate" in data:
            scan_row.scan_date = data["scanDate"]
        db.add(scan_row)
        await db.commit()
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/overview DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.patch("/report/{scan_id}/controls/{control_id}/annotation")
async def patch_control_annotation(scan_id: int, control_id: str, data: dict, db=Depends(get_db)):
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

@app.patch("/report/{scan_id}/controls/{control_id}")
async def patch_control(scan_id: int, control_id: str, data: dict, db=Depends(get_db)):
    logging.debug(f"/report/{scan_id}/controls/{control_id} payload: {data}")
    try:
        try:
            ctrl = (await db.execute(select(Control).where(Control.scan_id == scan_id, Control.control_id == control_id))).scalar_one_or_none()
        except MultipleResultsFound:
            return JSONResponse({
                "error": "Multiple controls matched control_id. Use ID endpoint /report/{scan_id}/controls/id/{control_db_id}"
            }, status_code=409)
        if not ctrl:
            return JSONResponse({"error": "Control not found"}, status_code=404)
        # Update allowed fields
        justification_note = None
        if "control_confidence" in data:
            old = getattr(ctrl, "control_confidence", None)
            ctrl.control_confidence = data["control_confidence"]
            justification_note = f"UI edit: control_confidence {old} -> {ctrl.control_confidence}"
        if "confidence_calc" in data:
            ctrl.confidence_calc = data["confidence_calc"]
        if "annotation" in data:
            ctrl.annotation = data["annotation"]
        # New: allow editing control text fields
        if "control_desc" in data:
            ctrl.control_desc = data["control_desc"]
        if "control_test" in data:
            ctrl.control_test = data["control_test"]
        if "control_test_results" in data:
            ctrl.control_test_results = data["control_test_results"]
        if "control_page_ref" in data:
            ctrl.control_page_ref = data["control_page_ref"]
        # New: allow editing deviation fields via API
        if "has_deviation" in data:
            ctrl.has_deviation = data["has_deviation"]
        if "deviation_desc" in data:
            ctrl.deviation_desc = data["deviation_desc"]
        # Append audit note into confidence_calc as an audit trail
        if justification_note:
            prev = getattr(ctrl, "confidence_calc", "") or ""
            sep = "\n" if prev else ""
            ctrl.confidence_calc = f"{prev}{sep}{justification_note}"
        # Mark executive summary stale
        scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if scan_row:
            scan_row.executive_summary_stale = True
            db.add(scan_row)
        db.add(ctrl)
        await db.commit()
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/controls/{control_id} DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.patch("/report/{scan_id}/controls/id/{control_db_id}")
async def patch_control_by_id(scan_id: int, control_db_id: int, data: dict, db=Depends(get_db)):
    """Update a control by its numeric database ID to avoid duplicate control_id ambiguity."""
    logging.debug(f"/report/{scan_id}/controls/{control_db_id} payload: {data}")
    try:
        ctrl = (await db.execute(select(Control).where(Control.scan_id == scan_id, Control.id == control_db_id))).scalar_one_or_none()
        if not ctrl:
            return JSONResponse({"error": "Control not found"}, status_code=404)
        justification_note = None
        if "control_confidence" in data:
            old = getattr(ctrl, "control_confidence", None)
            ctrl.control_confidence = data["control_confidence"]
            justification_note = f"UI edit: control_confidence {old} -> {ctrl.control_confidence}"
        if "confidence_calc" in data:
            ctrl.confidence_calc = data["confidence_calc"]
        if "annotation" in data:
            ctrl.annotation = data["annotation"]
        # New: allow editing control text fields
        if "control_desc" in data:
            ctrl.control_desc = data["control_desc"]
        if "control_test" in data:
            ctrl.control_test = data["control_test"]
        if "control_test_results" in data:
            ctrl.control_test_results = data["control_test_results"]
        if "control_page_ref" in data:
            ctrl.control_page_ref = data["control_page_ref"]
        # New: allow editing deviation fields via API
        if "has_deviation" in data:
            ctrl.has_deviation = data["has_deviation"]
        if "deviation_desc" in data:
            ctrl.deviation_desc = data["deviation_desc"]
        if justification_note:
            prev = getattr(ctrl, "confidence_calc", "") or ""
            sep = "\n" if prev else ""
            ctrl.confidence_calc = f"{prev}{sep}{justification_note}"
        scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if scan_row:
            scan_row.executive_summary_stale = True
            db.add(scan_row)
        db.add(ctrl)
        await db.commit()
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/controls/{control_db_id} DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.patch("/report/{scan_id}/cuecs/{cuec_id}/annotation")
async def patch_cuec_annotation(scan_id: int, cuec_id: str, data: dict, db=Depends(get_db)):
    cuec = (await db.execute(select(CUEC).where(CUEC.scan_id == scan_id, CUEC.cuec_tsc_id == cuec_id))).scalar_one_or_none()
    if not cuec:
        raise HTTPException(status_code=404, detail="CUEC not found")
    cuec.annotation = data.get("annotation", "")
    db.add(cuec)
    await db.commit()
    return {"status": "ok"}

@app.patch("/report/{scan_id}/cuecs/{cuec_id}")
async def patch_cuec(scan_id: int, cuec_id: int, data: dict, db=Depends(get_db)):
    logging.debug(f"/report/{scan_id}/cuecs/{cuec_id} payload: {data}")
    try:
        cuec = (await db.execute(select(CUEC).where(CUEC.scan_id == scan_id, CUEC.id == cuec_id))).scalar_one_or_none()
        if not cuec:
            return JSONResponse({"error": "CUEC not found"}, status_code=404)
        justification_note = None
        if "cuec_confidence" in data:
            old = getattr(cuec, "cuec_confidence", None)
            cuec.cuec_confidence = data["cuec_confidence"]
            justification_note = f"UI edit: cuec_confidence {old} -> {cuec.cuec_confidence}"
        if "cuec_confidence_justification" in data:
            # Always append, never overwrite
            prev = getattr(cuec, "cuec_confidence_justification", "") or ""
            sep = "\n" if prev else ""
            cuec.cuec_confidence_justification = f"{prev}{sep}{data['cuec_confidence_justification']}"
        if "annotation" in data:
            cuec.annotation = data["annotation"]
        if "control_strength" in data:
            cuec.control_strength = data["control_strength"]
        # New: allow editing CUEC text fields
        if "cuec_description" in data:
            cuec.cuec_description = data["cuec_description"]
        if "cuec_gpt_reasoning" in data:
            cuec.cuec_gpt_reasoning = data["cuec_gpt_reasoning"]
        if "cuec_justification" in data:
            cuec.cuec_justification = data["cuec_justification"]
        # Append auto audit note
        if justification_note:
            prev = getattr(cuec, "cuec_confidence_justification", "") or ""
            sep = "\n" if prev else ""
            cuec.cuec_confidence_justification = f"{prev}{sep}{justification_note}"
        # Mark executive summary stale
        scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if scan_row:
            scan_row.executive_summary_stale = True
            db.add(scan_row)
        db.add(cuec)
        await db.commit()
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/cuecs/{cuec_id} DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.patch("/report/{scan_id}/suborgs/{suborg_id}/annotation")
async def patch_suborg_annotation(scan_id: int, suborg_id: int, data: dict, db=Depends(get_db)):
    suborg = (await db.execute(select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id, SubserviceOrg.id == suborg_id))).scalar_one_or_none()
    if not suborg:
        raise HTTPException(status_code=404, detail="SubserviceOrg not found")
    suborg.annotation = data.get("annotation", "")
    db.add(suborg)
    await db.commit()
    return {"status": "ok"}

@app.patch("/report/{scan_id}/suborgs/id/{suborg_id}")
async def patch_suborg_by_id(scan_id: int, suborg_id: int, data: dict, db=Depends(get_db)):
    """Update a subservice org by its numeric ID. Prefer this over name to avoid duplicate-name ambiguity."""
    logging.debug(f"/report/{scan_id}/suborgs/{suborg_id} payload: {data}")
    try:
        suborg = (await db.execute(select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id, SubserviceOrg.id == suborg_id))).scalar_one_or_none()
        if not suborg:
            return JSONResponse({"error": "SubserviceOrg not found"}, status_code=404)
        justification_note = None
        if "confidence" in data:
            old = getattr(suborg, "confidence", None)
            suborg.confidence = data["confidence"]
            justification_note = f"UI edit: confidence {old} -> {suborg.confidence}"
        if "confidence_justification" in data:
            prev = getattr(suborg, "confidence_justification", "") or ""
            sep = "\n" if prev else ""
            suborg.confidence_justification = f"{prev}{sep}{data['confidence_justification']}"
        if "annotation" in data:
            suborg.annotation = data["annotation"]
        # New: allow editing suborg text fields
        if "third_party_description" in data:
            suborg.third_party_description = data["third_party_description"]
        if "third_party_page_ref" in data:
            suborg.third_party_page_ref = data["third_party_page_ref"]
        if justification_note:
            prev = getattr(suborg, "confidence_justification", "") or ""
            sep = "\n" if prev else ""
            suborg.confidence_justification = f"{prev}{sep}{justification_note}"
        # Mark executive summary stale
        scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if scan_row:
            scan_row.executive_summary_stale = True
            db.add(scan_row)
        db.add(suborg)
        await db.commit()
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/suborgs/{suborg_id} DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.patch("/report/{scan_id}/suborgs/{suborg_name}")
async def patch_suborg(scan_id: int, suborg_name: str, data: dict, db=Depends(get_db)):
    logging.debug(f"/report/{scan_id}/suborgs/{suborg_name} payload: {data}")
    try:
        # Name-based update maintained for backward compatibility. Return 409 if duplicates exist.
        try:
            suborg = (await db.execute(select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id, SubserviceOrg.name == suborg_name))).scalar_one_or_none()
        except MultipleResultsFound:
            return JSONResponse({
                "error": "Multiple subservice orgs matched name. Use ID endpoint /report/{scan_id}/suborgs/id/{suborg_id}"
            }, status_code=409)
        if not suborg:
            return JSONResponse({"error": "SubserviceOrg not found"}, status_code=404)
        justification_note = None
        if "confidence" in data:
            old = getattr(suborg, "confidence", None)
            suborg.confidence = data["confidence"]
            justification_note = f"UI edit: confidence {old} -> {suborg.confidence}"
        if "confidence_justification" in data:
            prev = getattr(suborg, "confidence_justification", "") or ""
            sep = "\n" if prev else ""
            suborg.confidence_justification = f"{prev}{sep}{data['confidence_justification']}"
        if "annotation" in data:
            suborg.annotation = data["annotation"]
        # New: allow editing suborg text fields
        if "third_party_description" in data:
            suborg.third_party_description = data["third_party_description"]
        if "third_party_page_ref" in data:
            suborg.third_party_page_ref = data["third_party_page_ref"]
        if justification_note:
            prev = getattr(suborg, "confidence_justification", "") or ""
            sep = "\n" if prev else ""
            suborg.confidence_justification = f"{prev}{sep}{justification_note}"
        # Mark executive summary stale
        scan_row = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if scan_row:
            scan_row.executive_summary_stale = True
            db.add(scan_row)
        db.add(suborg)
        await db.commit()
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        logging.error(f"/report/{scan_id}/suborgs/{suborg_name} DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
