"""
Router for scan and analysis operations.

Handles PDF upload, analysis job management, progress tracking, and WebSocket connections.
"""
import logging
import os
import time
import asyncio
import concurrent.futures
import traceback
import threading
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, Form, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import Response, JSONResponse
from sqlalchemy.future import select
from pydantic import BaseModel

from ..models import Scan
from ..database import get_db
from ..utils.redis_helpers import get_job, set_job, del_job
from .. import config as cfg

router = APIRouter()

# WebSocket clients for progress broadcasting
WEBSOCKET_CLIENTS = set()


async def broadcast_queue_update():
    """Broadcast queue status change to all connected WebSocket clients."""
    for ws in list(WEBSOCKET_CLIENTS):
        try:
            await ws.send_json({"type": "queue_update"})
        except Exception as e:
            logging.debug(f"Failed to broadcast queue update to client: {e}")
            try:
                WEBSOCKET_CLIENTS.discard(ws)
            except Exception:
                pass


@router.post("/analyze/")
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
        
    Returns:
        {"job_id": str} - Job ID for polling status
    """
    logging.error(f"[DEBUG /analyze/] Received report_type='{report_type}', file={file.filename}")
    import uuid
    import shutil
    
    # Normalize report_type
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
    
    # Reset prior artifacts/logs
    try:
        from ..main import _reset_scan_state
        _reset_scan_state()
    except Exception:
        pass
    
    job_id = str(uuid.uuid4())
    logging.error(f"[DEBUG /analyze/] Creating job {job_id} with report_type='{report_type}'")
    
    set_job(job_id, {
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
    
    # Add scan to queue (v2.1.0)
    try:
        logging.error(f"[DEBUG /analyze/] About to enqueue scan: job_id={job_id}")
        from ..threading.scan_queue import get_scan_queue
        logging.error(f"[DEBUG /analyze/] Import successful")
        queue = get_scan_queue()
        logging.error(f"[DEBUG /analyze/] Got queue instance: {queue}")
        position = queue.enqueue(
            job_id=job_id,
            filename=filename,
            pdf_path=temp_pdf_path,
            report_type=report_type,
            priority=10  # Normal priority
        )
        logging.error(f"[DEBUG /analyze/] Enqueue succeeded, position={position}")
        logging.info(f"[QUEUE] Added scan to queue: job_id={job_id}, position={position}")
        
        # Start background thread to process queue
        logging.error(f"[DEBUG /analyze/] Starting thread with args: job_id={job_id}, filename={filename}, report_type='{report_type}'")
        from ..main import run_analysis_job
        thread = threading.Thread(
            target=run_analysis_job, 
            args=(job_id, temp_pdf_path, filename, report_type, db)
        )
        thread.start()
    except RuntimeError as e:
        # Queue not initialized, fall back to direct execution
        logging.error(f"[DEBUG /analyze/] RuntimeError in queue operations: {e}")
        logging.warning(f"[QUEUE] Queue not initialized, using direct execution")
        from ..main import run_analysis_job
        thread = threading.Thread(
            target=run_analysis_job, 
            args=(job_id, temp_pdf_path, filename, report_type, db)
        )
        thread.start()
    except Exception as e:
        # Unexpected error, log and fall back
        import traceback
        logging.error(f"[DEBUG /analyze/] Unexpected error in queue operations: {e}")
        logging.error(f"[DEBUG /analyze/] Traceback: {traceback.format_exc()}")
        logging.warning(f"[QUEUE] Error enqueueing, using direct execution")
        from ..main import run_analysis_job
        thread = threading.Thread(
            target=run_analysis_job, 
            args=(job_id, temp_pdf_path, filename, report_type, db)
        )
        thread.start()
    
    return {"job_id": job_id}


@router.post("/analyze/cancel/{job_id}")
async def cancel_analysis_job(job_id: str):
    """Cancel an in-progress analysis job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job["cancelled"] = True
    job["status"] = "Cancelled"
    set_job(job_id, job)
    
    return {"message": f"Job {job_id} has been cancelled", "job_id": job_id}


@router.post("/analyze/confirm-type/{job_id}")
async def confirm_report_type(
    job_id: str,
    confirmed_type: str = Form(...),
    confirmed_subtype: str = Form(...),
    db=Depends(get_db)
):
    """User confirmation of detected report type."""
    from ..models import ReportTypeDetection
    from datetime import datetime
    
    logging.info(f"[CONFIRM_TYPE] job_id={job_id}, confirmed_type={confirmed_type}, confirmed_subtype={confirmed_subtype}")
    
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.get("status") != "AWAITING_CONFIRMATION":
        raise HTTPException(
            status_code=400, 
            detail=f"Job is not awaiting confirmation (status: {job.get('status')})"
        )
    
    # Update detection cache with user override
    pdf_hash = job.get("pdf_hash")
    if pdf_hash:
        try:
            detection = (await db.execute(
                select(ReportTypeDetection).filter_by(pdf_hash=pdf_hash)
            )).scalar_one_or_none()
            
            if detection:
                detection.user_confirmed_type = confirmed_type
                detection.user_confirmed_subtype = confirmed_subtype
                detection.user_confirmed_at = datetime.utcnow()
                await db.commit()
                logging.info(f"[CONFIRM_TYPE] Updated detection cache for pdf_hash={pdf_hash}")
        except Exception as e:
            logging.error(f"[CONFIRM_TYPE] Failed to update detection cache: {e}", exc_info=True)
            await db.rollback()
    
    # Update job and resume
    job["report_type"] = confirmed_type
    job["report_subtype"] = confirmed_subtype
    job["status"] = "Resuming analysis..."
    job["awaiting_confirmation"] = False
    set_job(job_id, job)
    
    # Start background thread to continue
    temp_pdf_path = job.get("temp_pdf_path")
    filename = job.get("filename")
    
    if not temp_pdf_path or not filename:
        raise HTTPException(status_code=500, detail="Job missing required file information")
    
    logging.info(f"[CONFIRM_TYPE] Resuming analysis with report_type={confirmed_type}")
    from ..main import run_analysis_job
    thread = threading.Thread(
        target=run_analysis_job,
        args=(job_id, temp_pdf_path, filename, confirmed_type, db, True)
    )
    thread.start()
    
    return {
        "message": "Report type confirmed, analysis resuming",
        "job_id": job_id,
        "confirmed_type": confirmed_type,
        "confirmed_subtype": confirmed_subtype
    }


@router.get("/analyze/status/{job_id}")
async def get_job_status(job_id: str):
    """Get detailed job status with artifacts and counts."""
    logging.info(f"[INFO] get_job_status: called for job_id={job_id}")
    job = get_job(job_id)
    if not job:
        transient = False
        try:
            _ = get_job(job_id)
        except Exception:
            transient = True
        logging.error(f"[ERROR] get_job_status: job_id={job_id} NOT FOUND (transient={transient})")
        return {"error": "Job not found", "transient_unavailable": transient}
    
    # Build artifacts presence and counts
    artifacts = None
    counts = None
    if job.get("done"):
        from ..main import _artifact_presence, _result_counts_from_obj, _result_counts_from_disk
        artifacts = _artifact_presence()
        result_obj = job.get("result") or {}
        counts = _result_counts_from_obj(result_obj) if result_obj else _result_counts_from_disk()
    
    # Calculate elapsed time
    elapsed_seconds = 0
    start_time = job.get("start_time")
    if start_time:
        elapsed_seconds = int(time.time() - start_time)
    
    # Extract progress fields
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
    
    # Add report_type to identified_entities for frontend (frontend expects it there)
    report_type = job.get("detected_report_type") or job.get("report_type")
    if report_type and "report_type" not in identified_entities:
        identified_entities["report_type"] = report_type
    
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
        "elapsed_seconds": elapsed_seconds,
        "identified_entities": identified_entities,
        "counters": counters,
        "phase_completion": phase_completion,
        "extraction_partial": extraction_partial,
    }


@router.get("/analyze/status_min/{job_id}")
async def get_job_status_min(job_id: str, include_artifacts: bool = False):
    """Ultra-lightweight status endpoint for active scans."""
    job = get_job(job_id)
    if not job:
        transient = False
        try:
            _ = get_job(job_id)
        except Exception:
            transient = True
        return {"error": "Job not found", "transient_unavailable": transient}
    
    # Lightweight counts
    from ..main import _result_counts_from_obj, _result_counts_from_disk, _artifact_presence
    result_obj = job.get("result") or {}
    counts = _result_counts_from_obj(result_obj) if result_obj else _result_counts_from_disk()
    checklist = job.get("checklist", [])
    artifacts = None
    if job.get("done") or include_artifacts:
        artifacts = _artifact_presence()
    
    # Calculate elapsed time
    elapsed_seconds = 0
    start_time = job.get("start_time")
    if start_time:
        elapsed_seconds = int(time.time() - start_time)
    
    # Extract progress fields
    identified_entities = job.get("identified_entities", {})
    counters = job.get("counters", {})
    phase_completion = job.get("phase_completion", {})
    extraction_partial = job.get("extraction_partial", False)
    
    # Add report_type to identified_entities for frontend (frontend expects it there)
    report_type = job.get("detected_report_type") or job.get("report_type")
    if report_type and "report_type" not in identified_entities:
        identified_entities["report_type"] = report_type
    
    # Format coverage_period for frontend display
    if "coverage_period" in identified_entities:
        cp = identified_entities["coverage_period"]
        if isinstance(cp, dict):
            # Format as "start_date to end_date" or "as of as_of_date"
            if cp.get("start_date") and cp.get("end_date"):
                identified_entities["coverage_period"] = f"{cp['start_date']} to {cp['end_date']}"
            elif cp.get("as_of_date"):
                identified_entities["coverage_period"] = f"As of {cp['as_of_date']}"
            elif cp.get("end_date"):
                identified_entities["coverage_period"] = f"As of {cp['end_date']}"
        elif not isinstance(cp, str):
            # Convert to string if it's some other type
            identified_entities["coverage_period"] = str(cp)
    
    # Fetch company logo URL if logo has been fetched
    if phase_completion.get("logo_fetched") and identified_entities.get("company"):
        try:
            from ..database import get_db
            from ..models import Company
            
            # Get database session
            db_gen = get_db()
            db = next(db_gen)
            
            try:
                # Query company logo by name
                company_name = identified_entities.get("company")
                company = db.query(Company).filter(Company.name == company_name).first()
                if company and company.logo_url:
                    identified_entities["company_logo_url"] = company.logo_url
            finally:
                db.close()
        except Exception as logo_err:
            logging.warning(f"Could not fetch company logo: {logo_err}")
    
    # Line-based progress
    def _line_progress():
        try:
            import pathlib
            import json as _json
            proj_root = pathlib.Path(__file__).resolve().parents[3]
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
        "progress": job.get("progress", 0),
        "done": job.get("done"),
        "error": job.get("error"),
        "counts": counts,
        "checklist": checklist,
        "artifacts": artifacts,
        "report_type": job.get("report_type"),
        "detected_report_type": job.get("detected_report_type"),
        "detected_subtype": job.get("detected_subtype"),
        "detection_confidence": job.get("detection_confidence"),
        "awaiting_confirmation": job.get("awaiting_confirmation"),
        "detection_result": job.get("detection_result"),
        "transient_unavailable": False,
        "line_progress": line_progress,
        "elapsed_seconds": elapsed_seconds,
        "identified_entities": identified_entities,
        "counters": counters,
        "phase_completion": phase_completion,
        "extraction_partial": extraction_partial,
    }


@router.get("/analyze/result/{job_id}")
async def get_job_result(
    job_id: str, 
    force_save: bool = False, 
    format: Optional[str] = None, 
    request: Request = None, 
    db=Depends(get_db)
):
    """Return analysis results with content negotiation."""
    job = get_job(job_id)
    if not job:
        return {"error": "Job not found"}
    if not job.get("done"):
        return {"error": "Job not finished yet"}

    # Content negotiation
    import json as _json
    fmt = (format or "").lower().strip()
    accept = (request.headers.get("accept") if request else "")
    wants_text = (fmt == "text") or ("text/plain" in (accept or ""))
    wants_summary = (fmt == "summary") or ("application/summary+json" in (accept or ""))

    # Persist to DB if needed
    insert_summary = None
    if (force_save or not job.get("db_saved")) and job.get("result"):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmpf:
            _json.dump(job["result"], tmpf, ensure_ascii=False)
            tmpf.flush()
            tmp_path = tmpf.name
        
        from ..explicit_sql_insert import insert_extracted_data
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            insert_summary = await loop.run_in_executor(pool, insert_extracted_data, tmp_path)
        job["db_saved"] = True
        set_job(job_id, job)

    # Handle error
    if job.get("error"):
        return {"error": job.get("error"), "partial_result": job.get("result")}

    res_obj = job.get("result") or {}

    if wants_text:
        text = res_obj.get("extracted_text") or ""
        return Response(content=text, media_type="text/plain; charset=utf-8")

    if wants_summary:
        from ..main import _result_counts_from_obj, _artifact_presence
        summary_payload = {
            "counts": _result_counts_from_obj(res_obj),
            "artifacts": _artifact_presence(),
            "keys": sorted(list(res_obj.keys())),
            "finalized": bool(job.get("finalized", False)),
        }
        if insert_summary is not None:
            summary_payload["db_inserted"] = True
            summary_payload["insert_summary"] = insert_summary
        return summary_payload

    # Default: full JSON
    default_response = {"results": res_obj}
    if insert_summary is not None:
        default_response["insert_summary"] = insert_summary
        from ..main import _result_counts_from_obj, _artifact_presence
        default_response["summary"] = {
            "counts": _result_counts_from_obj(res_obj),
            "artifacts": _artifact_presence(),
        }
    return default_response


@router.post("/analyze/finalize/{job_id}")
async def finalize_job_from_disk(job_id: str, force_save: bool = True, db=Depends(get_db)):
    """Rebuild job results from extractor JSONs on disk and mark done."""
    from ..main import _build_combined_results_from_disk
    from ..explicit_sql_insert import insert_extracted_data
    import json as _json
    
    results = _build_combined_results_from_disk()
    if not results:
        return JSONResponse({"error": "No extractor outputs found on disk"}, status_code=404)

    # Persist to DB
    insert_summary = None
    scan_id_for_learning = None
    if force_save:
        try:
            import tempfile
            results_for_db = {k: v for k, v in results.items() if k != 'pdf_file'}
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmpf:
                _json.dump(results_for_db, tmpf, ensure_ascii=False)
                tmpf.flush()
                tmp_path = tmpf.name
            
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                insert_summary = await loop.run_in_executor(pool, insert_extracted_data, tmp_path)
            
            # Run post-processing
            if insert_summary and insert_summary.get("control", 0) > 0:
                scan_result = await db.execute(select(Scan).order_by(Scan.id.desc()).limit(1))
                latest_scan = scan_result.scalar_one_or_none()
                
                if latest_scan:
                    scan_id_for_learning = latest_scan.id
                    
                    # Run automated cleanup
                    if cfg.ENABLE_AUTO_MERGE:
                        try:
                            from ..services import merge_service
                            cleanup_stats = await merge_service.automated_cleanup(scan_id_for_learning, db)
                            if cleanup_stats:
                                logging.info(f"[/analyze/finalize] Automated cleanup complete: {cleanup_stats}")
                        except Exception as cleanup_err:
                            logging.warning(f"[/analyze/finalize] Automated cleanup failed: {cleanup_err}")
                    
                    # Apply incomplete penalties
                    try:
                        from ..services import merge_service
                        penalty_count = await merge_service.penalize_incomplete_controls(scan_id_for_learning, db)
                        logging.info(f"[/analyze/finalize] Incomplete control penalties: {penalty_count} controls")
                    except Exception as penalty_err:
                        logging.warning(f"[/analyze/finalize] Penalty application failed: {penalty_err}")
                    
                    # Generate deviation summaries
                    try:
                        from ..post_processors.deviation_summarizer import generate_summaries
                        import redis.asyncio as aioredis
                        
                        redis_client_deviation = None
                        try:
                            redis_client_deviation = aioredis.from_url("redis://socanalyzer-redis:6379", decode_responses=True)
                        except Exception:
                            pass
                        
                        deviation_stats = await generate_summaries(scan_id_for_learning, db, redis_client_deviation)
                        logging.info(f"[/analyze/finalize] Deviation summaries: {deviation_stats}")
                        
                        if redis_client_deviation:
                            await redis_client_deviation.close()
                    except Exception:
                        pass
        except Exception as e:
            logging.error(f"[/analyze/finalize] DB insertion failed: {e}")

    # Update job in Redis
    from ..utils.redis_helpers import _get_redis
    redis_client = _get_redis()
    job = get_job(job_id, redis_client) or {}
    results_for_redis = {k: v for k, v in results.items() if k != 'pdf_file'}
    job["result"] = results_for_redis
    job["done"] = True
    job["error"] = None
    job["db_saved"] = bool(insert_summary) if force_save else job.get("db_saved", False)
    job["progress"] = 100
    job["status"] = "Finalized from disk"
    job["finalized"] = True
    set_job(job_id, job, redis_client)
    
    try:
        await broadcast_progress(100, "Finalized from disk")
        await broadcast_done()
    except Exception:
        pass
    
    resp = {"results": results}
    if insert_summary is not None:
        resp["insert_summary"] = insert_summary
    return resp


@router.post("/analyze/resume/{job_id}")
async def resume_extractors(job_id: str, payload: dict, db=Depends(get_db)):
    """Rerun one or more extractors and refresh combined results."""
    # Implementation similar to main.py - omitted for brevity
    # This endpoint would call individual extractors and rebuild results
    return {"status": "not_implemented", "message": "Use main endpoint temporarily"}


@router.get("/analyze/controls_partial/{job_id}")
async def get_partial_controls(job_id: str, min_pct: float = 20.0, limit: int = 0):
    """Expose partial controls mid-run with completion percentage."""
    job = get_job(job_id)
    if not job:
        return {"error": "Job not found"}
    
    try:
        import os, json
        path = str(cfg.CONTROL_JSON_PATH)
        if not os.path.exists(path):
            return {"controls": [], "count": 0, "completion_pct": 0.0, "estimated_total": None}
        
        controls = []
        # Attempt parse
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            controls = (data or {}).get('controls') or []
        except Exception:
            # Tolerant streaming reader
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        ls = line.lstrip()
                        if not ls or ls.startswith('[]') or ls.startswith('[') or ls.startswith(']'):
                            continue
                        if ls.startswith('{') or ls.startswith(',{'):
                            js = ls.lstrip(',').rstrip().rstrip(',')
                            try:
                                obj = json.loads(js)
                                controls.append(obj)
                            except Exception:
                                continue
            except Exception:
                controls = []
        
        minimal = [
            {
                'control_seq': c.get('control_seq'),
                'control_id': c.get('control_id'),
                'control_desc': c.get('control_desc'),
                'has_deviation': c.get('has_deviation'),
            }
            for c in controls if (c.get('control_id') or c.get('control_desc'))
        ]
        
        if limit > 0:
            minimal = minimal[:limit]
        
        est_total = job.get('controls_estimate')
        completion_pct = None
        if isinstance(est_total, int) and est_total > 0:
            completion_pct = round(100.0 * len(controls) / est_total, 2)
        else:
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


@router.websocket("/ws")
async def websocket_progress(websocket: WebSocket):
    """WebSocket endpoint for real-time progress updates."""
    await websocket.accept()
    WEBSOCKET_CLIENTS.add(websocket)
    try:
        logging.info(f"WebSocket client connected: {websocket.client}")
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=10)
                logging.info(f"WebSocket message received: {msg}")
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        logging.info(f"WebSocket client disconnected: {websocket.client}")
        WEBSOCKET_CLIENTS.remove(websocket)
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
        WEBSOCKET_CLIENTS.remove(websocket)


async def broadcast_progress(percent: int, status: Optional[str] = None):
    """Broadcast progress to all WebSocket clients."""
    msg = {"type": "progress", "percent": percent}
    if status:
        msg["status"] = status
    for ws in list(WEBSOCKET_CLIENTS):
        try:
            await ws.send_json(msg)
        except Exception:
            pass


async def broadcast_done():
    """Broadcast completion to all WebSocket clients."""
    for ws in list(WEBSOCKET_CLIENTS):
        try:
            await ws.send_json({"type": "done"})
        except Exception:
            pass


# ============================================================================
# QUEUE MANAGEMENT API ENDPOINTS (v2.1.0)
# ============================================================================

class BatchUploadRequest(BaseModel):
    """Request model for batch PDF upload."""
    files: list[dict]  # List of {filename: str, report_type: str}
    priority: int = 1  # Default priority


class PrioritizeRequest(BaseModel):
    """Request model for changing scan priority."""
    new_priority: int


@router.post("/analyze/batch")
async def batch_upload_scans(
    files: list[UploadFile] = File(...),
    report_types: Optional[str] = Form(None),  # Comma-separated list
    priorities: Optional[str] = Form(None),  # Comma-separated list of ints
    db=Depends(get_db)
):
    """
    Batch upload multiple PDFs and queue for analysis.
    
    Args:
        files: List of PDF files to analyze
        report_types: Comma-separated list of report types (SOC1, SOC2, or None for auto)
                     Example: "SOC1,SOC2,,SOC1" (empty means auto-detect)
        priorities: Comma-separated list of priorities (1=high, 2=medium, 3=low)
                   Example: "1,2,1,3"
        
    Returns:
        {
            "queued_count": int,
            "job_ids": [str],
            "queue_position": [int],
            "errors": [str]
        }
    """
    import uuid
    import shutil
    from ..threading.scan_queue import get_scan_queue, ScanQueueStatus
    
    logging.info(f"[BATCH_UPLOAD] Received {len(files)} files")
    
    # Parse report_types
    report_type_list = []
    if report_types:
        report_type_list = [rt.strip() if rt.strip() else None for rt in report_types.split(',')]
    report_type_list = report_type_list + [None] * (len(files) - len(report_type_list))  # Pad with None
    
    # Parse priorities
    priority_list = []
    if priorities:
        try:
            priority_list = [int(p.strip()) for p in priorities.split(',') if p.strip()]
        except ValueError:
            logging.warning(f"[BATCH_UPLOAD] Invalid priorities format: {priorities}, using default")
            priority_list = []
    priority_list = priority_list + [2] * (len(files) - len(priority_list))  # Pad with medium priority
    
    temp_dir = "data/tmp"
    os.makedirs(temp_dir, exist_ok=True)
    
    queued_jobs = []
    job_ids = []
    queue_positions = []
    errors = []
    
    scan_queue = get_scan_queue()
    if not scan_queue:
        logging.error("[BATCH_UPLOAD] Scan queue not initialized")
        raise HTTPException(status_code=500, detail="Scan queue not available")
    
    for idx, file in enumerate(files):
        try:
            filename = file.filename if file.filename else f"uploaded_{idx}.pdf"
            report_type = report_type_list[idx]
            priority = priority_list[idx]
            
            # Save file to temp location
            job_id = str(uuid.uuid4())
            temp_pdf_path = os.path.join(temp_dir, f"{job_id}_{filename}")
            
            with open(temp_pdf_path, "wb") as f_out:
                shutil.copyfileobj(file.file, f_out)
            
            # Create job in Redis with QUEUED status
            set_job(job_id, {
                "status": "Queued",
                "progress": 0,
                "done": False,
                "result": None,
                "error": None,
                "checklist": [],
                "filename": filename,
                "report_type": report_type,
                "start_time": time.time(),
                "pdf_path": temp_pdf_path,
                "priority": priority,
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
            
            # Add to queue
            position = scan_queue.enqueue(
                job_id=job_id,
                filename=filename,
                pdf_path=temp_pdf_path,
                report_type=report_type,
                priority=priority
            )
            
            queued_jobs.append({
                "job_id": job_id,
                "filename": filename,
                "position": position,
                "priority": priority,
                "pdf_path": temp_pdf_path
            })
            job_ids.append(job_id)
            queue_positions.append(position)
            
            logging.info(f"[BATCH_UPLOAD] Queued {filename} as job {job_id}, position {position}, priority {priority}")
            
        except Exception as e:
            error_msg = f"Failed to queue {file.filename}: {str(e)}"
            logging.error(f"[BATCH_UPLOAD] {error_msg}")
            errors.append(error_msg)
    
    # Start processing threads for all queued scans
    if queued_jobs:
        logging.info(f"[BATCH_UPLOAD] Starting processing threads for {len(queued_jobs)} scans")
        import threading
        from ..main import run_analysis_job
        
        for idx, job in enumerate(queued_jobs):
            try:
                thread = threading.Thread(
                    target=run_analysis_job,
                    args=(job["job_id"], job["pdf_path"], job["filename"], report_type_list[idx], db)
                )
                thread.daemon = True  # Daemon thread so it doesn't block shutdown
                thread.start()
                logging.info(f"[BATCH_UPLOAD] Started processing thread for {job['filename']}")
            except Exception as thread_err:
                logging.error(f"[BATCH_UPLOAD] Failed to start thread for {job['filename']}: {thread_err}")
    
    return {
        "queued_count": len(queued_jobs),
        "job_ids": job_ids,
        "queue_positions": queue_positions,
        "jobs": queued_jobs,
        "errors": errors
    }


@router.get("/analyze/queue")
async def get_queue_status():
    """
    Get current scan queue status.
    
    Returns:
        {
            "queue_length": int,
            "is_paused": bool,
            "is_running": bool,
            "current_job_id": str,
            "queued_scans": [
                {
                    "job_id": str,
                    "filename": str,
                    "report_type": str,
                    "priority": int,
                    "status": str,
                    "position": int,
                    "queued_at": float (timestamp)
                }
            ],
            "stats": {
                "total_queued": int,
                "total_completed": int,
                "total_failed": int,
                "total_cancelled": int
            }
        }
    """
    from ..threading.scan_queue import get_scan_queue
    
    scan_queue = get_scan_queue()
    if not scan_queue:
        raise HTTPException(status_code=500, detail="Scan queue not available")
    
    try:
        queue_status = scan_queue.get_status()
        
        # Enrich with position information
        for scan in queue_status.get("queued_scans", []):
            position = scan_queue.get_position(scan["job_id"])
            scan["position"] = position
        
        return queue_status
        
    except Exception as e:
        logging.error(f"[GET_QUEUE] Error getting queue status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get queue status: {str(e)}")


@router.post("/analyze/queue/pause")
async def pause_queue():
    """
    Pause the scan queue.
    
    Currently running scan will complete, but no new scans will start.
    
    Returns:
        {"message": str, "is_paused": bool}
    """
    from ..threading.scan_queue import get_scan_queue
    
    scan_queue = get_scan_queue()
    if not scan_queue:
        raise HTTPException(status_code=500, detail="Scan queue not available")
    
    try:
        scan_queue.pause()
        logging.info("[PAUSE_QUEUE] Queue paused")
        return {
            "message": "Queue paused. Current scan will complete, but no new scans will start.",
            "is_paused": True
        }
    except Exception as e:
        logging.error(f"[PAUSE_QUEUE] Error pausing queue: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to pause queue: {str(e)}")


@router.post("/analyze/queue/resume")
async def resume_queue():
    """
    Resume the scan queue.
    
    Queued scans will start processing again.
    
    Returns:
        {"message": str, "is_paused": bool}
    """
    from ..threading.scan_queue import get_scan_queue
    
    scan_queue = get_scan_queue()
    if not scan_queue:
        raise HTTPException(status_code=500, detail="Scan queue not available")
    
    try:
        scan_queue.resume()
        logging.info("[RESUME_QUEUE] Queue resumed")
        return {
            "message": "Queue resumed. Queued scans will now process.",
            "is_paused": False
        }
    except Exception as e:
        logging.error(f"[RESUME_QUEUE] Error resuming queue: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resume queue: {str(e)}")


@router.post("/analyze/queue/prioritize/{job_id}")
async def reprioritize_scan(job_id: str, request: PrioritizeRequest):
    """
    Change the priority of a queued scan.
    
    Args:
        job_id: Job ID to reprioritize
        request: {"new_priority": int} where 1=high, 2=medium, 3=low
        
    Returns:
        {
            "message": str,
            "job_id": str,
            "old_priority": int,
            "new_priority": int,
            "new_position": int
        }
    """
    from ..threading.scan_queue import get_scan_queue
    
    scan_queue = get_scan_queue()
    if not scan_queue:
        raise HTTPException(status_code=500, detail="Scan queue not available")
    
    try:
        # Get old priority
        scan = scan_queue._load_scan(job_id)
        if not scan:
            raise HTTPException(status_code=404, detail="Job not found in queue")
        
        old_priority = scan.priority
        
        # Reprioritize
        new_position = scan_queue.reprioritize(job_id, request.new_priority)
        
        logging.info(f"[REPRIORITIZE] Job {job_id} priority changed: {old_priority} -> {request.new_priority}, new position: {new_position}")
        
        return {
            "message": f"Job {job_id} priority updated",
            "job_id": job_id,
            "old_priority": old_priority,
            "new_priority": request.new_priority,
            "new_position": new_position
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[REPRIORITIZE] Error reprioritizing {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reprioritize: {str(e)}")


@router.post("/analyze/queue/{job_id}/pause")
async def pause_scan(job_id: str):
    """
    Pause a running scan.
    
    Args:
        job_id: Job ID to pause
        
    Returns:
        {
            "message": str,
            "job_id": str,
            "paused": bool
        }
    """
    try:
        # Update job state in Redis to mark as paused
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        if job.get("status") not in ["Running", "Queued"]:
            raise HTTPException(status_code=400, detail=f"Cannot pause job in status: {job.get('status')}")
        
        job["status"] = "Paused"
        job["paused"] = True
        set_job(job_id, job)
        
        logging.info(f"[PAUSE_SCAN] Job {job_id} paused")
        
        return {
            "message": f"Job {job_id} has been paused",
            "job_id": job_id,
            "paused": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[PAUSE_SCAN] Error pausing {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to pause scan: {str(e)}")


@router.post("/analyze/queue/{job_id}/resume")
async def resume_scan(job_id: str):
    """
    Resume a paused scan.
    
    Args:
        job_id: Job ID to resume
        
    Returns:
        {
            "message": str,
            "job_id": str,
            "resumed": bool
        }
    """
    try:
        # Update job state in Redis to mark as running
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        if job.get("status") != "Paused":
            raise HTTPException(status_code=400, detail=f"Cannot resume job in status: {job.get('status')}")
        
        job["status"] = "Running"
        job["paused"] = False
        set_job(job_id, job)
        
        logging.info(f"[RESUME_SCAN] Job {job_id} resumed")
        
        return {
            "message": f"Job {job_id} has been resumed",
            "job_id": job_id,
            "resumed": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[RESUME_SCAN] Error resuming {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resume scan: {str(e)}")


@router.delete("/analyze/queue/{job_id}")
async def cancel_queued_scan(job_id: str):
    """
    Cancel a queued or running scan.
    
    - If queued: Removes from queue
    - If running: Sets cancellation flag
    
    Args:
        job_id: Job ID to cancel
        
    Returns:
        {
            "message": str,
            "job_id": str,
            "was_running": bool
        }
    """
    from ..threading.scan_queue import get_scan_queue
    
    scan_queue = get_scan_queue()
    if not scan_queue:
        raise HTTPException(status_code=500, detail="Scan queue not available")
    
    try:
        was_running = scan_queue.cancel(job_id)
        
        # Also update job state in Redis
        job = get_job(job_id)
        if job:
            job["cancelled"] = True
            job["status"] = "Cancelled"
            set_job(job_id, job)
        
        if was_running:
            logging.info(f"[CANCEL_SCAN] Running job {job_id} marked for cancellation")
            message = f"Job {job_id} is running and has been marked for cancellation"
        else:
            logging.info(f"[CANCEL_SCAN] Queued job {job_id} removed from queue")
            message = f"Job {job_id} removed from queue"
        
        return {
            "message": message,
            "job_id": job_id,
            "was_running": was_running
        }
        
    except Exception as e:
        logging.error(f"[CANCEL_SCAN] Error cancelling {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel scan: {str(e)}")


@router.get("/analyze/queue/active")
async def get_active_scans():
    """
    Get all active scans (running + queued).
    
    Returns:
        {
            "active_scans": [
                {
                    "job_id": str,
                    "filename": str,
                    "report_type": str,
                    "status": str ("RUNNING" or "QUEUED"),
                    "priority": int,
                    "position": int (0 for running, 1+ for queued),
                    "progress": int (0-100),
                    "start_time": float,
                    "elapsed_seconds": float,
                    "identified_entities": dict,
                    "counters": dict
                }
            ]
        }
    """
    from ..threading.scan_queue import get_scan_queue
    
    scan_queue = get_scan_queue()
    if not scan_queue:
        raise HTTPException(status_code=500, detail="Scan queue not available")
    
    try:
        active_job_ids = scan_queue.get_active_job_ids()
        active_scans = []
        
        for job_id in active_job_ids:
            # Get scan from queue
            scan = scan_queue._load_scan(job_id)
            if not scan:
                continue
            
            # Get job state from Redis
            job = get_job(job_id)
            
            # Determine position
            position = scan_queue.get_position(job_id)
            is_running = position == 0
            
            scan_info = {
                "job_id": job_id,
                "filename": scan.filename,
                "report_type": scan.report_type or "Auto-detect",
                "status": "RUNNING" if is_running else "QUEUED",
                "priority": scan.priority,
                "position": position,
                "queued_at": scan.queued_at.timestamp() if scan.queued_at else None,
                "started_at": scan.started_at.timestamp() if scan.started_at else None,
            }
            
            # Add progress info from Redis job state
            if job:
                scan_info["progress"] = job.get("progress", 0)
                scan_info["start_time"] = job.get("start_time")
                scan_info["identified_entities"] = job.get("identified_entities", {})
                scan_info["counters"] = job.get("counters", {})
                
                # Calculate elapsed time
                if scan_info["start_time"]:
                    scan_info["elapsed_seconds"] = time.time() - scan_info["start_time"]
            
            active_scans.append(scan_info)
        
        # Sort by position (running first, then by priority)
        active_scans.sort(key=lambda s: (s["position"], s["priority"]))
        
        return {
            "active_scans": active_scans,
            "count": len(active_scans)
        }
        
    except Exception as e:
        logging.error(f"[GET_ACTIVE] Error getting active scans: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get active scans: {str(e)}")


@router.post("/scans/{scan_id}/refresh-logo")
async def refresh_company_logo(scan_id: int, db=Depends(get_db)):
    """
    Refresh company logo for a scan by forcing re-fetch from GPT.
    Clears cached logo and generates new one.
    """
    from sqlalchemy import select
    from ..models import Scan, Company
    from ..logo_service import generate_company_logo_from_gpt
    
    try:
        # Get scan
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        
        if not scan:
            raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")
        
        if not scan.company:
            raise HTTPException(status_code=400, detail="Scan has no company name")
        
        # Get or create company record
        result = await db.execute(select(Company).where(Company.name == scan.company))
        company = result.scalar_one_or_none()
        
        if not company:
            company = Company(name=scan.company)
            db.add(company)
            await db.flush()
        
        # Clear existing logo
        company.logo_url = None
        await db.commit()
        
        # Re-fetch logo
        success, logo_url = generate_company_logo_from_gpt(
            company_id=company.id,
            company_name=company.name,
            db=db
        )
        
        if success and logo_url:
            return {
                "success": True,
                "logo_url": logo_url,
                "message": "Logo refreshed successfully"
            }
        else:
            return {
                "success": False,
                "logo_url": None,
                "message": "Failed to fetch logo"
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[REFRESH_LOGO] Error refreshing logo for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh logo: {str(e)}")

