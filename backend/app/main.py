# --- Report API endpoint ---
from fastapi import HTTPException
from sqlalchemy.future import select
from app.models import ScanHistory, Company, Control, CUEC, SubserviceOrg, Product, Setting

@app.get("/report/{scan_id}")
async def get_report(scan_id: int, db=Depends(get_db)):
    # Fetch scan history (for scan date, filename, and full results JSON)
    scan = await db.execute(select(ScanHistory).where(ScanHistory.id == scan_id))
    scan = scan.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    # Fetch all related entities
    company = (await db.execute(select(Company).where(Company.scan_id == scan_id))).scalars().first()
    controls = (await db.execute(select(Control).where(Control.scan_id == scan_id))).scalars().all()
    cuecs = (await db.execute(select(CUEC).where(CUEC.scan_id == scan_id))).scalars().all()
    suborgs = (await db.execute(select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id))).scalars().all()
    product = (await db.execute(select(Product).where(Product.scan_id == scan_id))).scalars().first()

    # Extract additional fields from the results JSON if present
    results = scan.results or {}
    auditor = results.get("auditor", {})
    coverage_period = results.get("coverage_period", {})
    report_date = results.get("report_date", {})
    bad_chunks = {
        "cuecs": results.get("cuecs", {}).get("bad_chunks", []),
        "controls": results.get("controls", {}).get("bad_chunks", []),
        "subservice_orgs": results.get("subservice_orgs", {}).get("bad_chunks", [])
    }

    # Compose response
    return {
        "scan_id": scan.id,
        "scan_date": scan.timestamp,
        "filename": scan.filename,
        "company": company.name if company else None,
        "parent_company": company.parent_company if company else None,
        "auditor": auditor,
        "coverage_period": coverage_period,
        "report_date": report_date,
        "product": product.name if product else None,
        "subservice_organizations": [
            {"name": org.name} for org in suborgs
        ],
        "cuecs": [
            {"cuec_id": c.cuec_id, "description": c.description} for c in cuecs
        ],
        "controls": [
            {"control_id": ctrl.control_id, "description": ctrl.description} for ctrl in controls
        ],
        "bad_chunks": bad_chunks,
        "raw_results": results
    }
# --- In-memory job system for background extraction jobs ---
import uuid
from threading import Thread


# --- Persistent Job Storage using Redis ---

import redis.asyncio as redis
from app.config import REDIS_URL
import json as _json


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
    logging.error(f"[DEBUG] [run_analysis_job] Thread: {threading.current_thread().name}, job_id={job_id}")
    def progress_callback(percent, status=None):
        import threading
        import redis as sync_redis
        logging.error(f"[DEBUG] [progress_callback:_update] Thread: {threading.current_thread().name}, job_id={job_id}")
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
        logging.error(f"[DEBUG] progress_callback: job_id={job_id}, percent={percent}, status={status}")

    def checklist_callback(extractor_statuses):
        import threading
        import redis as sync_redis
        logging.error(f"[DEBUG] [checklist_callback:_update] Thread: {threading.current_thread().name}, job_id={job_id}")
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
        logging.error(f"[DEBUG] checklist_callback: job_id={job_id}, checklist={extractor_statuses}")
    try:
        from .analyze import analyze_pdf_file
        results = analyze_pdf_file(
            temp_pdf_path,
            progress_callback=progress_callback,
            checklist_callback=checklist_callback
        )
        async def _update():
            redis_client = _get_redis()
            logging.error(f"[DEBUG] [result_update:_update] Thread: {threading.current_thread().name}, job_id={job_id}, redis_client={id(redis_client)}")
            # Merge latest job state to preserve progress, status, checklist
            job = await get_job(job_id, redis_client) or {}
            job["result"] = results
            job["done"] = True
            job["error"] = None
            # Preserve progress, status, checklist if present
            job["progress"] = job.get("progress", 100)
            job["status"] = job.get("status", "Complete")
            job["checklist"] = job.get("checklist", [])
            await set_job(job_id, job, redis_client)
        try:
            loop = asyncio.get_running_loop()
            logging.error(f"[DEBUG] [result_update] Using running loop: {id(loop)}")
            loop.create_task(_update())
        except RuntimeError:
            logging.error(f"[DEBUG] [result_update] No running event loop, creating new one.")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                logging.error(f"[DEBUG] [result_update] Before run_until_complete, loop: {id(loop)}")
                loop.run_until_complete(_update())
                logging.error(f"[DEBUG] [result_update] After run_until_complete, loop: {id(loop)}")
            except Exception as exc:
                logging.error(f"[DEBUG] [result_update] Exception in run_until_complete: {exc}")
                raise
            finally:
                loop.close()
                logging.error(f"[DEBUG] [result_update] Closed event loop: {id(loop)}")
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
            logging.error(f"[DEBUG] [error_update] Using running loop: {id(loop)}")
            loop.create_task(_update())
        except RuntimeError:
            logging.error(f"[DEBUG] [error_update] No running event loop, creating new one.")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                logging.error(f"[DEBUG] [error_update] Before run_until_complete, loop: {id(loop)}")
                loop.run_until_complete(_update())
                logging.error(f"[DEBUG] [error_update] After run_until_complete, loop: {id(loop)}")
            except Exception as exc:
                logging.error(f"[DEBUG] [error_update] Exception in run_until_complete: {exc}")
                raise
            finally:
                loop.close()
                logging.error(f"[DEBUG] [error_update] Closed event loop: {id(loop)}")
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
from app.models import ScanHistory, Setting, Base
from app.database import engine, get_db
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

app = FastAPI()
# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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



# New endpoint: start background analysis job
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
    thread = Thread(target=run_analysis_job, args=(job_id, temp_pdf_path, filename, db))
    thread.start()
    return {"job_id": job_id}

# New endpoint: poll job status
@app.get("/analyze/status/{job_id}")
async def get_job_status(job_id: str):
    import logging
    print(f"[PRINT] get_job_status called for job_id={job_id}")
    logging.error(f"[DEBUG] get_job_status: called for job_id={job_id}")
    job = await get_job(job_id)
    if not job:
        print(f"[PRINT] get_job_status: job_id={job_id} NOT FOUND")
        logging.error(f"[DEBUG] get_job_status: job_id={job_id} NOT FOUND")
        return {"error": "Job not found"}
    # Add detailed logging of the full job state
    print(f"[PRINT] get_job_status: job_id={job_id}, job={job}")
    logging.error(f"[DEBUG] get_job_status: job_id={job_id}, job={job}")
    # Log each field individually for clarity
    print(f"[PRINT] get_job_status fields: progress={job.get('progress')}, checklist={job.get('checklist')}, status={job.get('status')}, done={job.get('done')}, error={job.get('error')}, filename={job.get('filename')}")
    logging.error(f"[DEBUG] get_job_status fields: progress={job.get('progress')}, checklist={job.get('checklist')}, status={job.get('status')}, done={job.get('done')}, error={job.get('error')}, filename={job.get('filename')}")
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
async def get_job_result(job_id: str, db=Depends(get_db)):
    job = await get_job(job_id)
    if not job:
        return {"error": "Job not found"}
    if not job.get("done"):
        return {"error": "Job not finished yet"}
    if job.get("error"):
        return {"error": job.get("error"), "partial_result": job.get("result")}

    # Persist result to DB if not already saved
    if not job.get("db_saved") and job.get("result"):
        try:
            import sqlalchemy, datetime
            from app.models import ScanHistory, Company, Control, CUEC, SubserviceOrg, Product
            result = job.get("result")
            # Insert ScanHistory
            scan_history = ScanHistory(
                timestamp=datetime.datetime.now(),
                filename=job.get("filename"),
                results=result
            )
            db.add(scan_history)
            db.commit()
            db.refresh(scan_history)
            scan_id = scan_history.id
            # --- Insert Company ---
            company_info = result.get("company")
            if company_info and company_info.get("company"):
                db.add(Company(
                    name=company_info["company"],
                    parent_company=company_info.get("parent_company"),
                    confidence=company_info.get("confidence"),
                    scan_id=scan_id
                ))
            # --- Insert Controls ---
            controls = result.get("controls", {}).get("controls", [])
            for ctrl in controls:
                db.add(Control(
                    control_id=ctrl.get("control_id"),
                    description=ctrl.get("control_desc"),
                    scan_id=scan_id
                ))
            # --- Insert CUECs ---
            cuecs = result.get("cuecs", {}).get("cuecs", [])
            for cuec in cuecs:
                db.add(CUEC(
                    cuec_id=cuec.get("cuec_id"),
                    description=cuec.get("cuec_desc"),
                    scan_id=scan_id
                ))
            # --- Insert Subservice Orgs ---
            suborgs = result.get("subservice_orgs", {}).get("subservice_orgs", [])
            for org in suborgs:
                db.add(SubserviceOrg(
                    name=org.get("name") or org,
                    scan_id=scan_id
                ))
            # --- Insert Product ---
            product_info = result.get("product")
            if product_info and isinstance(product_info, dict):
                db.add(Product(
                    name=product_info.get("product") or product_info.get("name"),
                    scan_id=scan_id
                ))
            db.commit()
            job["db_saved"] = True
            await set_job(job_id, job)
        except Exception as db_exc:
            import logging
            logging.error(f"DB error persisting job result: {db_exc}")
    return {"results": job.get("result")}
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Optional
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request, Depends, UploadFile, File
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from app.models import ScanHistory, Setting, Base
from app.database import engine, get_db
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
    settings = {row.key: row.value for row in result.scalars()}
    return settings

@app.post("/settings")
async def update_settings(request: Request, db=Depends(get_db)):
    data = await request.json()
    for key, value in data.items():
        stmt = pg_dialect.insert(Setting).values(key=key, value=str(value)).on_conflict_do_update(
            index_elements=[Setting.key], set_={"value": str(value)}
        )
        await db.execute(stmt)
    await db.commit()
    return {"status": "ok"}

# History endpoints
@app.get("/history")
async def get_history(db=Depends(get_db)):
    result = await db.execute(select(ScanHistory).order_by(ScanHistory.timestamp.desc()).limit(20))
    history = [
        {
            "id": row.id,
            "timestamp": row.timestamp.isoformat(),
            "filename": row.filename,
            "results": row.results
        }
        for row in result.scalars()
    ]
    return history

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
if __name__ == "__main__" and sys.argv[0].endswith("main.py"):
    asyncio.get_event_loop().run_until_complete(init_models())
