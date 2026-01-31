"""
Router for control objective operations including CRUD, mapping, and workflow operations.
"""
import logging
import json
import datetime
import re
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, Body, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.future import select
from sqlalchemy import and_, func

from ..models import ControlObjective, ControlObjectiveMapping, Control, Scan, User
from ..database import get_db
from ..services.scan_service import mark_executive_summary_stale
from ..auth.dependencies import get_current_active_user
from ..utils.redis_helpers import _get_redis
from ..extractors.objective_extractor import calculate_alignment_score, _proximity_score, _page_proximity_score, _min_page_ref
from .. import config
from ..gpt_client import gpt_extract

router = APIRouter()

logger = logging.getLogger(__name__)


def _append_edit_log(ctrl: Control, message: str) -> None:
    prev = getattr(ctrl, "edit_log", "") or ""
    sep = "\n" if prev else ""
    ctrl.edit_log = f"{prev}{sep}{message}"


def _normalize_objective_key(obj: ControlObjective) -> Optional[str]:
    if obj.objective_id and str(obj.objective_id).strip():
        return f"id:{str(obj.objective_id).strip().lower()}"
    if obj.objective_text and str(obj.objective_text).strip():
        return f"text:{str(obj.objective_text).strip().lower()}"
    return None


def _select_merge_target(candidates: List[ControlObjective], mapping_counts: Dict[int, int]) -> ControlObjective:
    def _score(obj: ControlObjective) -> tuple:
        conf = obj.final_confidence or 0.0
        mappings = mapping_counts.get(obj.id, 0)
        return (conf, mappings)

    return sorted(candidates, key=_score, reverse=True)[0]


def _auto_ignore_controls_matching_objective_ids(sync_db_session, scan_id_val: int) -> int:
    objectives = sync_db_session.execute(
        select(ControlObjective).where(ControlObjective.scan_id == scan_id_val)
    ).scalars().all()
    objective_ids = {
        str(obj.objective_id).strip().lower()
        for obj in objectives
        if obj.objective_id and str(obj.objective_id).strip()
    }
    if not objective_ids:
        return 0

    controls = sync_db_session.execute(
        select(Control).where(Control.scan_id == scan_id_val)
    ).scalars().all()

    updated = 0
    now = datetime.datetime.utcnow()
    timestamp = now.strftime("%Y-%m-%d %I:%M %p")
    for ctrl in controls:
        ctrl_id = str(ctrl.control_id or "").strip().lower()
        if not ctrl_id or ctrl_id not in objective_ids:
            continue

        ctrl.control_confidence = 0.0
        if hasattr(ctrl, "final_confidence"):
            ctrl.final_confidence = 0.0
        note = "Auto-ignored (control ID matches objective ID)"
        existing_calc = ctrl.confidence_calc or ""
        separator = "\n" if existing_calc and not existing_calc.endswith("\n") else ""
        ctrl.confidence_calc = f"{existing_calc}{separator}{note}"
        _append_edit_log(ctrl, f"{note} ({timestamp})")
        ctrl.updated_at = now
        updated += 1

    if updated > 0:
        sync_db_session.commit()

    return updated


def _objective_job_id(scan_id: int) -> str:
    return f"objective_extract:{scan_id}"


def _objective_gap_job_id(scan_id: int) -> str:
    return f"objective_gap_extract:{scan_id}"


def _get_objective_status(redis_client, scan_id: int) -> Dict[str, Any]:
    job_id = _objective_job_id(scan_id)
    try:
        data = redis_client.hgetall(f"job:{job_id}") or {}
    except Exception as e:
        logger.warning(f"Failed to read objective status from Redis: {e}")
        return {}
    return data


def _decode_redis_payload(data: Dict[Any, Any]) -> Dict[str, Any]:
    decoded: Dict[str, Any] = {}
    for key, value in (data or {}).items():
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        decoded[str(key)] = value
    return decoded


def _parse_json_field(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def _parse_int_field(value: Any) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _parse_float_field(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _get_objective_gap_status(redis_client, scan_id: int) -> Dict[str, Any]:
    job_id = _objective_gap_job_id(scan_id)
    try:
        raw = redis_client.hgetall(f"job:{job_id}") or {}
    except Exception as e:
        logger.warning(f"Failed to read objective gap status from Redis: {e}")
        return {}

    data = _decode_redis_payload(raw)
    if not data:
        return {}

    data["log"] = _parse_json_field(data.get("log"), [])
    data["pattern_output"] = _parse_json_field(data.get("pattern_output"), None)
    data["extracted_ids"] = _parse_json_field(data.get("extracted_ids"), [])
    data["total_probed"] = _parse_int_field(data.get("total_probed"))
    data["total_found"] = _parse_int_field(data.get("total_found"))
    data["total_extracted"] = _parse_int_field(data.get("total_extracted"))
    data["duration_seconds"] = _parse_float_field(data.get("duration_seconds"))
    if isinstance(data.get("cancel_requested"), str):
        data["cancel_requested"] = data.get("cancel_requested") == "true"
    return data


def _set_objective_status(redis_client, scan_id: int, payload: Dict[str, Any]) -> None:
    job_id = _objective_job_id(scan_id)
    try:
        redis_client.hset(f"job:{job_id}", mapping=payload)
        redis_client.expire(f"job:{job_id}", 60 * 60 * 24)
    except Exception as e:
        logger.warning(f"Failed to write objective status to Redis: {e}")


def _set_objective_gap_status(redis_client, scan_id: int, payload: Dict[str, Any]) -> None:
    job_id = _objective_gap_job_id(scan_id)
    encoded: Dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            encoded[key] = json.dumps(value)
        elif isinstance(value, bool):
            encoded[key] = "true" if value else "false"
        elif value is None:
            continue
        else:
            encoded[key] = str(value)
    try:
        redis_client.hset(f"job:{job_id}", mapping=encoded)
        redis_client.expire(f"job:{job_id}", 60 * 60 * 24 * config.OBJECTIVE_GAP_LOG_TTL_DAYS)
    except Exception as e:
        logger.warning(f"Failed to write objective gap status to Redis: {e}")


def _delete_objective_gap_status(redis_client, scan_id: int) -> None:
    """Delete the Redis key for objective gap extraction status."""
    job_id = _objective_gap_job_id(scan_id)
    try:
        redis_client.delete(f"job:{job_id}")
        logger.info(f"[objective_gap] Cleared stale status for scan_id={scan_id}")
    except Exception as e:
        logger.warning(f"Failed to delete objective gap status from Redis: {e}")


def _letter_to_index(value: str) -> Optional[int]:
    if not value:
        return None
    value = value.strip().upper()
    if not value.isalpha():
        return None
    total = 0
    for ch in value:
        total = total * 26 + (ord(ch) - 64)
    return total


def _index_to_letter(value: int, min_width: int = 1) -> str:
    if value <= 0:
        return ""
    letters = []
    current = value
    while current > 0:
        current, rem = divmod(current - 1, 26)
        letters.append(chr(rem + 65))
    result = "".join(reversed(letters))
    if min_width > 1 and len(result) < min_width:
        result = "A" * (min_width - len(result)) + result
    return result


def _extract_json_from_gpt(text: str) -> Dict[str, Any]:
    if text is None:
        raise ValueError("Empty GPT response")
    if isinstance(text, (dict, list)):
        return text

    raw = str(text).strip()
    if not raw:
        raise ValueError("Empty GPT response")

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1).strip()

    first_obj = raw.find("{")
    first_arr = raw.find("[")
    start_positions = [pos for pos in (first_obj, first_arr) if pos != -1]
    if start_positions:
        raw = raw[min(start_positions):]

    decoder = json.JSONDecoder()
    try:
        parsed, _ = decoder.raw_decode(raw)
        return parsed
    except Exception:
        end_obj = raw.rfind("}")
        end_arr = raw.rfind("]")
        end_pos = max(end_obj, end_arr)
        if end_pos != -1:
            parsed, _ = decoder.raw_decode(raw[: end_pos + 1])
            return parsed
        raise


def _append_gap_log(log_entries: List[Dict[str, Any]], entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    log_entries.append(entry)
    if len(log_entries) > config.OBJECTIVE_GAP_LOG_LIMIT:
        log_entries = log_entries[-config.OBJECTIVE_GAP_LOG_LIMIT:]
    return log_entries


def _gap_cancel_requested(redis_client, scan_id: int) -> bool:
    status = _get_objective_gap_status(redis_client, scan_id)
    return bool(status.get("cancel_requested"))


# ============================================================================
# CRUD Operations for Control Objectives
# ============================================================================

@router.post("/report/{scan_id}/objectives")
async def create_objective(
    scan_id: int,
    data: Dict[str, Any] = Body(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a control objective manually.

    Required fields:
    - objective_text

    Optional fields:
    - objective_id
    - status (pending/approved/rejected)
    """
    try:
        objective_text = (data.get("objective_text") or "").strip()
        if not objective_text:
            raise HTTPException(status_code=400, detail="objective_text is required")

        status = data.get("status", "pending")
        if status == "converted_to_control":
            status = "approved"
        valid_statuses = ['pending', 'approved', 'rejected']
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )

        final_confidence_value = float(data.get("final_confidence") or 0.0)
        if status == "approved":
            final_confidence_value = 1.0

        obj = ControlObjective(
            scan_id=scan_id,
            objective_id=data.get("objective_id"),
            objective_text=objective_text,
            status=status,
            extraction_method="manual",
            keyword_confidence=0.0,
            distance_confidence=0.0,
            gpt_confidence=0.0,
            alignment_confidence=0.0,
            format_confidence=0.0,
            final_confidence=final_confidence_value,
            gpt_reasoning=data.get("gpt_reasoning", ""),
            page_refs=data.get("page_refs"),
            line_ref=data.get("line_ref"),
            source_context=data.get("source_context", objective_text[:500]),
            section_heading=data.get("section_heading"),
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow(),
            updated_by_user_id=current_user.id
        )

        db.add(obj)
        await db.commit()
        await db.refresh(obj)

        await mark_executive_summary_stale(scan_id, db)

        status_value = obj.status
        if status_value == "converted_to_control":
            status_value = "approved"

        return {
            "id": obj.id,
            "objective_id": obj.objective_id,
            "objective_text": obj.objective_text,
            "status": status_value,
            "final_confidence": obj.final_confidence,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create objective for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/report/{scan_id}/objectives")
async def get_objectives(
    scan_id: int,
    status: Optional[str] = Query(None, description="Filter by status (pending/approved/rejected)"),
    min_confidence: Optional[float] = Query(None, description="Minimum confidence threshold"),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all control objectives for a scan.
    
    Query Parameters:
    - status: Filter by status (pending, approved, rejected)
    - min_confidence: Minimum confidence threshold (0.0-1.0)
    """
    try:
        # Build query with filters
        query = select(ControlObjective).where(ControlObjective.scan_id == scan_id)
        
        if status:
            if status == "converted_to_control":
                status = "approved"
            query = query.where(ControlObjective.status == status)
        
        if min_confidence is not None:
            query = query.where(ControlObjective.final_confidence >= min_confidence)
        
        query = query.order_by(ControlObjective.final_confidence.desc())
        
        result = await db.execute(query)
        objectives = result.scalars().all()
        
        # Convert to dict with mapping counts
        objectives_data = []
        for obj in objectives:
            # Count linked controls
            mapping_count_query = select(func.count(ControlObjectiveMapping.id)).where(
                ControlObjectiveMapping.objective_id == obj.id
            )
            mapping_count_result = await db.execute(mapping_count_query)
            mapping_count = mapping_count_result.scalar()
            
            status_value = obj.status
            if status_value == "converted_to_control":
                status_value = "approved"

            objectives_data.append({
                "id": obj.id,
                "scan_id": obj.scan_id,
                "objective_id": obj.objective_id,
                "objective_text": obj.objective_text,
                "keyword_confidence": obj.keyword_confidence,
                "distance_confidence": obj.distance_confidence,
                "gpt_confidence": obj.gpt_confidence,
                "alignment_confidence": obj.alignment_confidence,
                "format_confidence": obj.format_confidence,
                "final_confidence": obj.final_confidence,
                "confidence_calc": obj.confidence_calc,
                "gpt_reasoning": obj.gpt_reasoning,
                "page_refs": obj.page_refs,
                "line_ref": obj.line_ref,
                "source_context": obj.source_context,
                "extraction_method": obj.extraction_method,
                "section_heading": obj.section_heading,
                "status": status_value,
                "created_at": obj.created_at.isoformat() if obj.created_at else None,
                "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
                "linked_controls_count": mapping_count
            })
        
        return {"objectives": objectives_data, "total": len(objectives_data)}
        
    except Exception as e:
        logger.error(f"Failed to fetch objectives for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{scan_id}/objectives/{objective_id}")
async def get_objective(
    scan_id: int,
    objective_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a single control objective with its linked controls."""
    try:
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        # Get linked controls
        mappings_result = await db.execute(
            select(ControlObjectiveMapping, Control).join(
                Control, ControlObjectiveMapping.control_id == Control.id
            ).where(ControlObjectiveMapping.objective_id == objective_id)
        )
        mappings = mappings_result.all()
        
        linked_controls = []
        for mapping, control in mappings:
            linked_controls.append({
                "control_id": control.control_id,
                "control_db_id": control.id,
                "control_desc": control.control_desc,
                "mapping_confidence": mapping.mapping_confidence,
                "mapping_method": mapping.mapping_method,
                "is_primary": mapping.is_primary,
                "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
                "page_proximity_score": getattr(mapping, "page_proximity_score", None),
                "line_proximity_score": getattr(mapping, "line_proximity_score", None),
                "gpt_alignment_score": getattr(mapping, "gpt_alignment_score", None),
                "id_alignment_score": getattr(mapping, "id_alignment_score", None),
            })
        
        return {
            "id": obj.id,
            "scan_id": obj.scan_id,
            "objective_id": obj.objective_id,
            "objective_text": obj.objective_text,
            "keyword_confidence": obj.keyword_confidence,
            "distance_confidence": obj.distance_confidence,
            "gpt_confidence": obj.gpt_confidence,
            "alignment_confidence": obj.alignment_confidence,
            "format_confidence": obj.format_confidence,
            "final_confidence": obj.final_confidence,
            "confidence_calc": obj.confidence_calc,
            "gpt_reasoning": obj.gpt_reasoning,
            "page_refs": obj.page_refs,
            "line_ref": obj.line_ref,
            "source_context": obj.source_context,
            "extraction_method": obj.extraction_method,
            "section_heading": obj.section_heading,
            "status": obj.status,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
            "linked_controls": linked_controls
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch objective {objective_id} for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/report/{scan_id}/objectives/{objective_id}")
async def update_objective(
    scan_id: int,
    objective_id: int,
    data: Dict[str, Any] = Body(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update a control objective.
    
    Allowed fields:
    - objective_id: Identifier string
    - objective_text: Full objective description
    - status: pending/approved/rejected
    """
    try:
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        # Update allowed fields
        if "objective_id" in data:
            obj.objective_id = data["objective_id"]
        
        if "objective_text" in data:
            obj.objective_text = data["objective_text"]
        
        if "status" in data:
            status_value = data["status"]
            if status_value == "converted_to_control":
                status_value = "approved"
            valid_statuses = ['pending', 'approved', 'rejected']
            if status_value not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
                )
            obj.status = status_value
            if status_value == "approved":
                obj.final_confidence = 1.0
        
        # Update audit fields
        obj.updated_at = datetime.datetime.utcnow()
        obj.updated_by_user_id = current_user.id
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        
        return {
            "id": obj.id,
            "objective_id": obj.objective_id,
            "objective_text": obj.objective_text,
            "status": obj.status,
            "final_confidence": obj.final_confidence,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/report/{scan_id}/objectives/{objective_id}")
async def delete_objective(
    scan_id: int,
    objective_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a control objective and all its mappings (cascade)."""
    try:
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        # Delete (cascades to mappings)
        await db.delete(obj)
        await db.commit()
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        
        return {"status": "deleted", "objective_id": objective_id}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/objectives/merge-duplicates")
async def merge_duplicate_objectives(
    scan_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Merge duplicate objectives by objective_id (preferred) or objective_text."""
    try:
        result = await db.execute(
            select(ControlObjective).where(ControlObjective.scan_id == scan_id)
        )
        objectives = result.scalars().all()

        grouped: Dict[str, List[ControlObjective]] = {}
        for obj in objectives:
            key = _normalize_objective_key(obj)
            if not key:
                continue
            grouped.setdefault(key, []).append(obj)

        if not grouped:
            return {"merged": 0, "deleted": 0, "status": "no_duplicates"}

        mapping_counts: Dict[int, int] = {}
        mapping_count_rows = await db.execute(
            select(ControlObjectiveMapping.objective_id, func.count(ControlObjectiveMapping.id))
            .group_by(ControlObjectiveMapping.objective_id)
        )
        for obj_id, count in mapping_count_rows.all():
            mapping_counts[int(obj_id)] = int(count)

        merged = 0
        deleted = 0

        for _, group in grouped.items():
            if len(group) <= 1:
                continue

            target = _select_merge_target(group, mapping_counts)
            duplicates = [obj for obj in group if obj.id != target.id]

            for dup in duplicates:
                mappings_result = await db.execute(
                    select(ControlObjectiveMapping).where(ControlObjectiveMapping.objective_id == dup.id)
                )
                mappings = mappings_result.scalars().all()

                for mapping in mappings:
                    existing_mapping = (await db.execute(
                        select(ControlObjectiveMapping).where(
                            and_(
                                ControlObjectiveMapping.objective_id == target.id,
                                ControlObjectiveMapping.control_id == mapping.control_id
                            )
                        )
                    )).scalar_one_or_none()

                    if existing_mapping:
                        if mapping.is_primary and not existing_mapping.is_primary:
                            existing_mapping.is_primary = True
                        if mapping.mapping_confidence and (
                            existing_mapping.mapping_confidence is None
                            or mapping.mapping_confidence > existing_mapping.mapping_confidence
                        ):
                            existing_mapping.mapping_confidence = mapping.mapping_confidence
                        await db.delete(mapping)
                    else:
                        mapping.objective_id = target.id
                        db.add(mapping)
                    merged += 1

                await db.delete(dup)
                deleted += 1

            target.updated_at = datetime.datetime.utcnow()
            target.updated_by_user_id = current_user.id
            db.add(target)

        await db.commit()
        await mark_executive_summary_stale(scan_id, db)

        return {"merged": merged, "deleted": deleted, "status": "merged"}

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to merge duplicate objectives for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Extraction & Mapping Operations
# ============================================================================

@router.get("/report/{scan_id}/objectives/extract/status")
async def get_objective_extract_status(
    scan_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Get status for objective extraction for a scan."""
    redis_client = _get_redis()
    status = _get_objective_status(redis_client, scan_id)
    if not status:
        return {"status": "idle"}
    return status


@router.get("/report/{scan_id}/objectives/gap-extract/status")
async def get_objective_gap_extract_status(
    scan_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Get status for objective gap extraction for a scan."""
    redis_client = _get_redis()
    status = _get_objective_gap_status(redis_client, scan_id)
    if not status:
        return {"status": "idle"}
    return status


def run_gap_extraction_sync(scan_id: int, extracted_text: str) -> Dict[str, Any]:
    """
    Standalone synchronous function to run gap extraction.
    Can be called from objective extractor or other modules.
    Returns status dict with results.
    """
    from sqlalchemy import create_engine, select, and_, func
    from sqlalchemy.orm import sessionmaker
    from .. import config
    from ..models import Scan, ControlObjective
    
    logger.info(f"[objective_gap_sync] Starting gap extraction for scan_id={scan_id}")
    
    try:
        redis_client = _get_redis()
        _delete_objective_gap_status(redis_client, scan_id)
        
        # Use synchronous database session
        sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
        sync_engine = create_engine(sync_db_url, echo=False)
        SessionLocal = sessionmaker(bind=sync_engine)
        sync_db_session = SessionLocal()
        
        try:
            # Query existing objective IDs
            id_rows = sync_db_session.execute(
                select(ControlObjective.objective_id).where(
                    and_(
                        ControlObjective.scan_id == scan_id,
                        ControlObjective.objective_id.isnot(None)
                    )
                )
            ).scalars().all()
            
            objective_ids = [str(val).strip() for val in id_rows if val]
            
            if not objective_ids:
                logger.info(f"[objective_gap_sync] No objective IDs found, skipping")
                return {"status": "skipped", "message": "No objectives found"}
            
            # Import the nested function's logic (we'll inline it here)
            # This is a simplified version - for production, extract the full logic
            logger.info(f"[objective_gap_sync] Found {len(objective_ids)} objectives")
            
            # Make HTTP call to the endpoint to trigger it properly
            # This ensures all the logic runs correctly
            import requests
            try:
                response = requests.post(
                    f"http://localhost:8000/report/{scan_id}/objectives/gap-extract",
                    json={},
                    timeout=600
                )
                if response.status_code == 200:
                    logger.info(f"[objective_gap_sync] Gap extraction triggered successfully")
                    return response.json()
                else:
                    logger.warning(f"[objective_gap_sync] Unexpected status: {response.status_code}")
                    return {"status": "error", "message": f"HTTP {response.status_code}"}
            except Exception as req_err:
                logger.error(f"[objective_gap_sync] HTTP request failed: {req_err}")
                return {"status": "error", "message": str(req_err)}
                
        finally:
            sync_db_session.close()
            
    except Exception as e:
        logger.error(f"[objective_gap_sync] Failed: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/report/{scan_id}/objectives/gap-extract")
async def start_objective_gap_extract(
    scan_id: int,
    background_tasks: BackgroundTasks = None,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Detect objective ID gaps using GPT and extract missing objectives."""
    logger.info(f"[objective_gap] POST endpoint hit for scan_id={scan_id}, user={current_user.username if current_user else 'None'}")
    try:
        logger.info(f"[objective_gap] Getting Redis client")
        redis_client = _get_redis()
        logger.info(f"[objective_gap] Redis client obtained: {redis_client}")
        
        # Clear any stale status before starting new extraction
        _delete_objective_gap_status(redis_client, scan_id)
        
        existing_status = _get_objective_gap_status(redis_client, scan_id)
        if existing_status.get("status") == "running":
            return {
                "status": "running",
                "message": "Objective gap extraction already running",
                **existing_status
            }

        # Fetch existing objective IDs
        existing_ids_result = await db.execute(
            select(ControlObjective.objective_id).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.objective_id.isnot(None)
                )
            )
        )
        existing_ids = [str(row[0]).strip() for row in existing_ids_result if row[0]]

        if not existing_ids:
            payload = {
                "status": "skipped",
                "message": "No objective IDs available to infer patterns.",
                "total_probed": 0,
                "total_found": 0,
                "total_extracted": 0,
                "started_at": datetime.datetime.utcnow().isoformat(),
                "ended_at": datetime.datetime.utcnow().isoformat(),
                "duration_seconds": 0.0,
                "log": [],
                "extracted_ids": [],
                "pattern_output": None
            }
            _set_objective_gap_status(redis_client, scan_id, payload)
            return payload

        # Get scan to verify it exists and load extracted text
        scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")

        if not scan.extracted_text:
            raise HTTPException(status_code=404, detail="Extracted text not available for this scan")

        extracted_text = scan.extracted_text

        def _run_gap_extraction(text: str, scan_id_val: int) -> None:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
            sync_engine = create_engine(sync_db_url, echo=False)
            SessionLocal = sessionmaker(bind=sync_engine)
            sync_db_session = SessionLocal()

            started_at = datetime.datetime.utcnow()
            status_payload: Dict[str, Any] = {
                "status": "running",
                "progress_status": "Inferring objective ID patterns...",
                "total_probed": 0,
                "total_found": 0,
                "total_extracted": 0,
                "started_at": started_at.isoformat(),
                "updated_at": started_at.isoformat(),
                "log": [],
                "extracted_ids": [],
                "pattern_output": None,
                "cancel_requested": False
            }
            _set_objective_gap_status(redis_client, scan_id_val, status_payload)
            logger.info(f"[objective_gap] starting gap extraction for scan_id={scan_id_val}")

            log_entries: List[Dict[str, Any]] = []
            extracted_ids: List[str] = []
            total_probed = 0
            total_found = 0
            total_extracted = 0

            try:
                logger.info(f"[objective_gap] Querying objective IDs from database for scan_id={scan_id_val}")
                id_rows = sync_db_session.execute(
                    select(ControlObjective.objective_id).where(
                        and_(
                            ControlObjective.scan_id == scan_id_val,
                            ControlObjective.objective_id.isnot(None)
                        )
                    )
                ).scalars().all()
                logger.info(f"[objective_gap] Database query returned {len(id_rows) if id_rows else 0} rows")
                objective_ids = [str(val).strip() for val in id_rows if val]
                logger.info(f"[objective_gap] Processed {len(objective_ids)} objective IDs. Sample: {objective_ids[:5]}")
                if not objective_ids:
                    status_payload.update({
                        "status": "skipped",
                        "progress_status": "No objective IDs available to infer patterns.",
                        "total_probed": 0,
                        "total_found": 0,
                        "total_extracted": 0,
                        "ended_at": datetime.datetime.utcnow().isoformat(),
                        "duration_seconds": 0.0,
                        "log": [],
                        "extracted_ids": [],
                        "pattern_output": None
                    })
                    _set_objective_gap_status(redis_client, scan_id_val, status_payload)
                    return

                logger.info(f"[objective_gap] Preparing prompt. Total IDs: {len(objective_ids)}")
                max_ids = min(len(objective_ids), 200)
                logger.info(f"[objective_gap] Formatting prompt with {max_ids} IDs")
                try:
                    prompt = config.OBJECTIVE_GAP_PATTERN_PROMPT.format(
                        objective_ids=json.dumps(objective_ids[:max_ids], ensure_ascii=False),
                        total_ids=len(objective_ids)
                    )
                    logger.info(f"[objective_gap] Prompt formatted successfully. Length: {len(prompt)} chars")
                except Exception as fmt_err:
                    logger.error(f"[objective_gap] Prompt formatting failed: {type(fmt_err).__name__}: {fmt_err}")
                    raise
                logger.info(f"[objective_gap] Sending pattern detection prompt. Prompt length: {len(prompt)} chars, {len(objective_ids)} objective IDs")
                logger.debug(f"[objective_gap] Prompt preview: {prompt[:500]}...")

                pattern_raw = ""
                try:
                    primary_model = getattr(config, "OBJECTIVE_PATTERN_LEARNER_MODEL", None)
                    fallback_model = getattr(config, "CONTROL_OBJECTIVES_MODEL", None) or getattr(config, "DEFAULT_GPT_MODEL", None)
                    logger.info(f"[objective_gap] Calling gpt_extract with primary_model={primary_model}, fallback_model={fallback_model}")
                    pattern_raw = gpt_extract(prompt, "objective_gap_pattern", override_model=primary_model)
                    logger.info(f"[objective_gap] GPT response received. Type: {type(pattern_raw).__name__}, Length: {len(str(pattern_raw)) if pattern_raw is not None else 0}")
                    logger.debug(f"[objective_gap] GPT response preview: {str(pattern_raw)[:500]!r}")
                    if not (pattern_raw or "").strip() and fallback_model and fallback_model != primary_model:
                        logger.warning(f"[objective_gap] Primary model returned empty response, trying fallback model {fallback_model}")
                        status_payload["progress_status"] = "Empty GPT response; retrying with fallback model..."
                        _set_objective_gap_status(redis_client, scan_id_val, status_payload)
                        pattern_raw = gpt_extract(prompt, "objective_gap_pattern_fallback", override_model=fallback_model)
                        logger.info(f"[objective_gap] Fallback GPT response. Type: {type(pattern_raw).__name__}, Length: {len(str(pattern_raw)) if pattern_raw is not None else 0}")
                except Exception as gpt_err:
                    logger.error(f"[objective_gap] GPT call failed: {type(gpt_err).__name__}: {gpt_err}")
                    status_payload["pattern_output"] = f"GPT error: {type(gpt_err).__name__}: {gpt_err}"
                    status_payload["status"] = "failed"
                    status_payload["error"] = str(gpt_err)
                    _set_objective_gap_status(redis_client, scan_id_val, status_payload)
                    raise
                if pattern_raw is None:
                    logger.warning(f"[objective_gap] pattern_raw is None, converting to empty string")
                    pattern_raw = ""
                pattern_raw = str(pattern_raw)
                logger.info(f"[objective_gap] pattern_raw after str(): type={type(pattern_raw).__name__}, len={len(pattern_raw)}, stripped_len={len(pattern_raw.strip())}")
                if not pattern_raw.strip():
                    logger.error(f"[objective_gap] GPT returned empty/whitespace response")
                    status_payload["pattern_output"] = "<empty GPT response>"
                    status_payload["status"] = "failed"
                    status_payload["error"] = "GPT returned empty response for pattern detection"
                    status_payload["updated_at"] = datetime.datetime.utcnow().isoformat()
                    _set_objective_gap_status(redis_client, scan_id_val, status_payload)
                    raise RuntimeError("GPT returned empty response for pattern detection")
                else:
                    logger.info(f"[objective_gap] Storing pattern_raw in status. Preview: {pattern_raw[:200]!r}")
                    status_payload["pattern_output"] = pattern_raw
                status_payload["updated_at"] = datetime.datetime.utcnow().isoformat()
                _set_objective_gap_status(redis_client, scan_id_val, status_payload)
                logger.info(f"[objective_gap] pattern_raw length={len(pattern_raw)} preview={pattern_raw[:200]!r}")

                def _safe_parse_pattern(raw_text: str) -> Dict[str, Any]:
                    try:
                        parsed = _extract_json_from_gpt(raw_text)
                        if isinstance(parsed, dict):
                            return parsed
                        raise ValueError(f"Parsed pattern is not a JSON object: {type(parsed).__name__}")
                    except Exception:
                        candidate_text = raw_text.strip()
                        if (candidate_text.startswith("\"") and candidate_text.endswith("\"")) or (
                            candidate_text.startswith("'") and candidate_text.endswith("'")
                        ):
                            candidate_text = candidate_text[1:-1].strip()

                        if candidate_text.startswith("\"groups\"") or candidate_text.startswith("'groups'"):
                            candidate_text = "{" + candidate_text + "}"
                        else:
                            match = re.search(r'"groups"\s*:\s*(\[.*\])', candidate_text, re.DOTALL)
                            if match:
                                candidate_text = "{" + match.group(0) + "}"

                        try:
                            parsed = json.loads(candidate_text)
                            if isinstance(parsed, dict):
                                return parsed
                            raise ValueError(f"Parsed pattern is not a JSON object: {type(parsed).__name__}")
                        except Exception:
                            repair_prompt = (
                                "You will be given content that should be JSON. "
                                "Return ONLY a valid JSON object that matches this schema: "
                                "{\"groups\":[{\"prefix\":string,\"segment_type\":\"number\"|\"letter\","
                                "\"separator\":string,\"examples\":[string],\"notes\":string}],\"notes\":string}. "
                                "If the content cannot be repaired, return {\"groups\":[],\"notes\":\"unparseable\"}.\n\n"
                                f"Content:\n{raw_text}"
                            )
                            repaired = gpt_extract(repair_prompt, "objective_gap_pattern_fix")
                            status_payload["pattern_output"] = str(repaired)
                            parsed = _extract_json_from_gpt(str(repaired))
                            if isinstance(parsed, dict):
                                return parsed
                            raise ValueError(f"Repaired pattern is not a JSON object: {type(parsed).__name__}")

                try:
                    logger.info(f"[objective_gap] Attempting to parse pattern_raw (len={len(pattern_raw)})")
                    pattern_data = _safe_parse_pattern(pattern_raw)
                    logger.info(f"[objective_gap] Pattern parsed successfully. Groups: {len(pattern_data.get('groups', []))}")
                except Exception as parse_err:
                    logger.error(f"[objective_gap] Pattern parse error: {type(parse_err).__name__}: {parse_err}")
                    logger.error(f"[objective_gap] pattern_raw that failed to parse (len={len(pattern_raw)}): {pattern_raw[:1000]!r}")
                    if not status_payload.get("pattern_output") and (pattern_raw or "").strip():
                        logger.info(f"[objective_gap] Restoring pattern_raw to pattern_output in status")
                        status_payload["pattern_output"] = pattern_raw
                    if not status_payload.get("pattern_output"):
                        logger.warning(f"[objective_gap] No pattern_output available, setting to '<no output>'")
                        status_payload["pattern_output"] = "<no output>"
                    status_payload["error"] = f"Pattern parse failed: {type(parse_err).__name__}: {parse_err}"
                    status_payload["status"] = "failed"
                    status_payload["updated_at"] = datetime.datetime.utcnow().isoformat()
                    _set_objective_gap_status(redis_client, scan_id_val, status_payload)
                    raise

                if not isinstance(pattern_data, dict) or not pattern_data.get("groups"):
                    raise ValueError("GPT did not return any pattern groups")

                status_payload["pattern_output"] = pattern_data
                status_payload["progress_status"] = "Scanning for missing objectives..."
                status_payload["updated_at"] = datetime.datetime.utcnow().isoformat()
                _set_objective_gap_status(redis_client, scan_id_val, status_payload)

                existing_ids_lower = {val.lower() for val in objective_ids}

                def _record_log(objective_id: str, status: str, message: str, extracted_id: Optional[str] = None) -> None:
                    nonlocal log_entries
                    entry = {
                        "timestamp": datetime.datetime.utcnow().isoformat(),
                        "objective_id": objective_id,
                        "status": status,
                        "message": message,
                    }
                    if extracted_id:
                        entry["extracted_id"] = extracted_id
                    log_entries = _append_gap_log(log_entries, entry)

                def _update_status(progress: Optional[str] = None) -> None:
                    status_payload.update({
                        "total_probed": total_probed,
                        "total_found": total_found,
                        "total_extracted": total_extracted,
                        "log": log_entries,
                        "extracted_ids": extracted_ids,
                        "updated_at": datetime.datetime.utcnow().isoformat()
                    })
                    if progress:
                        status_payload["progress_status"] = progress
                    _set_objective_gap_status(redis_client, scan_id_val, status_payload)

                def _extract_objective_from_text(search_text: str) -> Dict[str, Any]:
                    occurrences = []
                    start_idx = 0
                    search_lower = search_text.lower()
                    text_lower = text.lower()
                    while True:
                        idx = text_lower.find(search_lower, start_idx)
                        if idx == -1:
                            break
                        occurrences.append(idx)
                        start_idx = idx + 1

                    if not occurrences:
                        return {"found": False}

                    # For gap extraction, always try to extract even with many occurrences
                    # Cap at 20 occurrences to avoid massive prompts
                    if len(occurrences) > 20:
                        # Take first 10 and last 10 occurrences
                        occurrences = occurrences[:10] + occurrences[-10:]

                    context_window = 2000
                    contexts = []
                    for occ_idx in occurrences:
                        start = max(0, occ_idx - context_window)
                        end = min(len(text), occ_idx + len(search_text) + context_window)
                        context = text[start:end]
                        contexts.append(context)

                    combined_context = "\n\n=== OCCURRENCE SEPARATOR ===\n\n".join(contexts)
                    prompt_text = config.ENTITY_EXTRACTION_FROM_CONTEXT_PROMPT.format(
                        entity_type="objective",
                        search_text=search_text,
                        occurrence_count=len(contexts),
                        text_context=combined_context
                    )

                    try:
                        result_text = gpt_extract(prompt_text, "entity_extraction_objective")
                        extracted_data = _extract_json_from_gpt(result_text)
                        return {"found": True, "extracted": extracted_data}
                    except Exception as e:
                        return {"found": True, "error": str(e)}

                def _create_objective_from_extraction(search_id: str, extracted: Dict[str, Any]) -> Dict[str, Any]:
                    objective_text = (extracted.get("objective_text") or "").strip()
                    objective_id = (extracted.get("objective_id") or search_id or "").strip()
                    if not objective_text:
                        return {"created": False, "message": "Extraction returned no objective_text"}

                    if objective_id:
                        existing = sync_db_session.execute(
                            select(ControlObjective).where(
                                and_(
                                    ControlObjective.scan_id == scan_id_val,
                                    func.lower(ControlObjective.objective_id) == objective_id.lower()
                                )
                            )
                        ).scalars().first()
                        if existing:
                            return {"created": False, "message": "Objective ID already exists"}

                    now = datetime.datetime.utcnow()
                    new_obj = ControlObjective(
                        scan_id=scan_id_val,
                        objective_id=objective_id or None,
                        objective_text=objective_text,
                        status="pending",
                        extraction_method="gap_search",
                        keyword_confidence=0.0,
                        distance_confidence=0.0,
                        gpt_confidence=0.0,
                        alignment_confidence=0.0,
                        format_confidence=0.0,
                        final_confidence=1.0,
                        gpt_reasoning=extracted.get("gpt_reasoning", ""),
                        page_refs=extracted.get("page_refs"),
                        line_ref=extracted.get("line_ref"),
                        source_context=extracted.get("source_context", objective_text[:500]),
                        section_heading=extracted.get("section_heading"),
                        created_at=now,
                        updated_at=now
                    )
                    sync_db_session.add(new_obj)
                    sync_db_session.commit()
                    sync_db_session.refresh(new_obj)
                    return {"created": True, "objective_id": new_obj.objective_id or objective_id, "db_id": new_obj.id}

                def _process_candidate(candidate_id: str, allow_miss_count: bool = False) -> bool:
                    nonlocal total_probed, total_found, total_extracted, extracted_ids, existing_ids_lower
                    total_probed += 1
                    if candidate_id.lower() in existing_ids_lower:
                        _record_log(candidate_id, "Skipped", "Objective already exists")
                        return False

                    extraction_result = _extract_objective_from_text(candidate_id)
                    if not extraction_result.get("found"):
                        _record_log(candidate_id, "Not Found", "No occurrences found")
                        return True if allow_miss_count else False

                    total_found += 1
                    if extraction_result.get("error"):
                        _record_log(candidate_id, "Failed", extraction_result.get("error"))
                        return False

                    extracted = extraction_result.get("extracted") or {}
                    create_result = _create_objective_from_extraction(candidate_id, extracted)
                    if create_result.get("created"):
                        total_extracted += 1
                        created_id = create_result.get("objective_id") or candidate_id
                        extracted_ids.append(created_id)
                        existing_ids_lower.add(created_id.lower())
                        _record_log(candidate_id, "Extracted", "Objective created", created_id)
                    else:
                        _record_log(candidate_id, "Skipped", create_result.get("message", "Skipped"))
                    return False

                groups = pattern_data.get("groups") or []

                for group in groups:
                    prefix = (group.get("prefix") or "").strip()
                    segment_type = (group.get("segment_type") or "").strip().lower()
                    separator = (group.get("separator") or "").strip()
                    examples = group.get("examples") or []

                    if not prefix or segment_type not in {"number", "letter"}:
                        _record_log(prefix or "(unknown)", "Skipped", "Invalid or missing pattern group")
                        _update_status()
                        continue

                    # CRITICAL: Use examples to determine the actual format pattern
                    # Extract the format template from the first example if available
                    format_template = None
                    if examples:
                        first_example = str(examples[0]).strip()
                        # Extract everything before the segment (the actual prefix as it appears)
                        # For "CC 6.1", we want "CC " and "."; for "ID-23", we want "ID-"
                        # Find where the variable segment starts by looking at all examples
                        import re
                        
                        # Try to find the pattern: extract prefix part and separator pattern
                        if segment_type == "number":
                            # Match everything up to the last number sequence
                            match = re.match(r'^(.*?)(\d+)$', first_example)
                            if match:
                                format_template = match.group(1)  # Everything before the number
                        else:  # letter
                            # Match everything up to the last letter sequence
                            match = re.match(r'^(.*?)([A-Za-z]+)$', first_example)
                            if match:
                                format_template = match.group(1)
                    
                    # Fallback to constructed prefix if no examples or can't parse
                    if not format_template:
                        format_template = prefix
                        if separator and not format_template.endswith(separator):
                            format_template = f"{format_template}{separator}"
                    
                    # For matching existing IDs, normalize both to remove spaces/special chars
                    # This allows flexible matching regardless of format variations
                    format_template_normalized = re.sub(r'[^A-Za-z0-9]', '', format_template)

                    segment_strings: List[str] = []
                    for obj_id in objective_ids:
                        # Normalize both for comparison
                        obj_id_normalized = re.sub(r'[^A-Za-z0-9]', '', obj_id)
                        if not obj_id_normalized.lower().startswith(format_template_normalized.lower()):
                            continue
                        remainder = obj_id_normalized[len(format_template_normalized):]
                        if not remainder:
                            continue
                        if segment_type == "number" and not remainder.isdigit():
                            continue
                        if segment_type == "letter" and not remainder.isalpha():
                            continue
                        segment_strings.append(remainder)

                    if not segment_strings:
                        _record_log(format_template, "Skipped", "No matching IDs for this pattern")
                        _update_status()
                        continue

                    width = max(len(seg) for seg in segment_strings)
                    if segment_type == "number":
                        values = [int(seg) for seg in segment_strings]
                    else:
                        values = [val for seg in segment_strings if (val := _letter_to_index(seg)) is not None]

                    if not values:
                        _record_log(normalized_prefix, "Skipped", "Unable to parse segment values")
                        _update_status()
                        continue

                    min_val, max_val = min(values), max(values)
                    existing_values = set(values)
                    gap_values = [val for val in range(min_val, max_val + 1) if val not in existing_values]

                    def _format_segment(val: int) -> str:
                        if segment_type == "number":
                            segment = str(val)
                            return segment.zfill(width) if width > len(segment) else segment
                        return _index_to_letter(val, width)

                    # Use format_template (from examples) for generating gap IDs
                    gap_ids = [f"{format_template}{_format_segment(val)}" for val in gap_values]
                    
                    # Probe backwards from min_val
                    probe_backward_ids = [
                        f"{format_template}{_format_segment(val)}"
                        for val in range(min_val - 1, max(0 if segment_type == "number" else 1, min_val - config.OBJECTIVE_GAP_PROBE_LIMIT) - 1, -1)
                    ]
                    
                    # Probe forward from max_val
                    probe_forward_ids = [
                        f"{format_template}{_format_segment(val)}"
                        for val in range(max_val + 1, max_val + config.OBJECTIVE_GAP_PROBE_LIMIT + 1)
                    ]

                    # Process backward probes first
                    miss_streak = 0
                    for idx, candidate_id in enumerate(probe_backward_ids):
                        if miss_streak >= 2:
                            remaining = probe_backward_ids[idx:]
                            for rem_id in remaining:
                                total_probed += 1
                                _record_log(rem_id, "Skipped", "Backward range ended after consecutive misses")
                            break

                        was_miss = _process_candidate(candidate_id, allow_miss_count=True)
                        _update_status(f"Searching {candidate_id} (backward)...")
                        if was_miss:
                            miss_streak += 1
                        else:
                            miss_streak = 0

                        if _gap_cancel_requested(redis_client, scan_id_val):
                            remaining = probe_backward_ids[idx + 1:] + gap_ids + probe_forward_ids
                            for rem_id in remaining:
                                total_probed += 1
                                _record_log(rem_id, "Cancelled", "Cancelled by user")
                            _update_status("Cancelled by user")
                            raise RuntimeError("cancelled")

                    # Process gap fills
                    # Process gap fills
                    for idx, candidate_id in enumerate(gap_ids):
                        _process_candidate(candidate_id)
                        _update_status(f"Searching {candidate_id}...")
                        if _gap_cancel_requested(redis_client, scan_id_val):
                            remaining = gap_ids[idx + 1:] + probe_forward_ids
                            for rem_id in remaining:
                                total_probed += 1
                                _record_log(rem_id, "Cancelled", "Cancelled by user")
                            _update_status("Cancelled by user")
                            raise RuntimeError("cancelled")

                    # Process forward probes
                    miss_streak = 0
                    for idx, candidate_id in enumerate(probe_forward_ids):
                        if miss_streak >= 2:
                            remaining = probe_forward_ids[idx:]
                            for rem_id in remaining:
                                total_probed += 1
                                _record_log(rem_id, "Skipped", "Forward range ended after consecutive misses")
                            _update_status("Forward range ended after consecutive misses")
                            break

                        was_miss = _process_candidate(candidate_id, allow_miss_count=True)
                        _update_status(f"Searching {candidate_id} (forward)...")
                        if was_miss:
                            miss_streak += 1
                        else:
                            miss_streak = 0

                        if _gap_cancel_requested(redis_client, scan_id_val):
                            remaining = probe_forward_ids[idx + 1:]
                            for rem_id in remaining:
                                total_probed += 1
                                _record_log(rem_id, "Cancelled", "Cancelled by user")
                            _update_status("Cancelled by user")
                            raise RuntimeError("cancelled")

                # Second pass: Re-check for new gaps after extractions
                if total_extracted > 0:
                    _update_status("Running second pass to check for newly revealed gaps...")
                    
                    # Re-query database to get updated objective IDs
                    updated_id_rows = sync_db_session.execute(
                        select(ControlObjective.objective_id).where(
                            and_(
                                ControlObjective.scan_id == scan_id_val,
                                ControlObjective.objective_id.isnot(None)
                            )
                        )
                    ).scalars().all()
                    updated_objective_ids = [str(val).strip() for val in updated_id_rows if val]
                    updated_existing_ids_lower = {val.lower() for val in updated_objective_ids}
                    
                    logger.info(f"[objective_gap] Second pass: found {len(updated_objective_ids)} total objectives")
                    
                    # Re-process each group to find newly revealed gaps
                    for group in groups:
                        prefix = (group.get("prefix") or "").strip()
                        segment_type = (group.get("segment_type") or "").strip().lower()
                        separator = (group.get("separator") or "").strip()
                        examples = group.get("examples") or []
                        
                        if not prefix or segment_type not in {"number", "letter"}:
                            continue
                        
                        # Extract format template from examples (same logic as first pass)
                        format_template = None
                        if examples:
                            first_example = str(examples[0]).strip()
                            if segment_type == "number":
                                match = re.match(r'^(.*?)(\d+)$', first_example)
                                if match:
                                    format_template = match.group(1)
                            else:  # letter
                                match = re.match(r'^(.*?)([A-Za-z]+)$', first_example)
                                if match:
                                    format_template = match.group(1)
                        
                        if not format_template:
                            format_template = prefix
                            if separator and not format_template.endswith(separator):
                                format_template = f"{format_template}{separator}"
                        
                        format_template_normalized = re.sub(r'[^A-Za-z0-9]', '', format_template)
                        
                        # Extract segments for this group
                        segment_strings: List[str] = []
                        for obj_id in updated_objective_ids:
                            obj_id_normalized = re.sub(r'[^A-Za-z0-9]', '', obj_id)
                            if not obj_id_normalized.lower().startswith(format_template_normalized.lower()):
                                continue
                            remainder = obj_id_normalized[len(format_template_normalized):]
                            if not remainder:
                                continue
                            if segment_type == "number" and not remainder.isdigit():
                                continue
                            if segment_type == "letter" and not remainder.isalpha():
                                continue
                            segment_strings.append(remainder)
                        
                        if not segment_strings:
                            continue
                        
                        width = max(len(seg) for seg in segment_strings)
                        if segment_type == "number":
                            values = [int(seg) for seg in segment_strings]
                        else:
                            values = [val for seg in segment_strings if (val := _letter_to_index(seg)) is not None]
                        
                        if not values:
                            continue
                        
                        min_val, max_val = min(values), max(values)
                        existing_values = set(values)
                        new_gap_values = [val for val in range(min_val, max_val + 1) if val not in existing_values]
                        
                        def _format_segment_pass2(val: int) -> str:
                            if segment_type == "number":
                                segment = str(val)
                                return segment.zfill(width) if width > len(segment) else segment
                            return _index_to_letter(val, width)
                        
                        new_gap_ids = [f"{format_template}{_format_segment_pass2(val)}" for val in new_gap_values]
                        
                        for candidate_id in new_gap_ids:
                            if candidate_id.lower() not in updated_existing_ids_lower:
                                _process_candidate(candidate_id)
                                _update_status(f"Second pass: Searching {candidate_id}...")
                                if _gap_cancel_requested(redis_client, scan_id_val):
                                    _update_status("Cancelled by user during second pass")
                                    raise RuntimeError("cancelled")

                status_payload.update({
                    "status": "completed",
                    "progress_status": "Gap extraction completed",
                    "total_probed": total_probed,
                    "total_found": total_found,
                    "total_extracted": total_extracted,
                    "log": log_entries,
                    "extracted_ids": extracted_ids,
                    "ended_at": datetime.datetime.utcnow().isoformat()
                })
                duration = datetime.datetime.utcnow() - started_at
                status_payload["duration_seconds"] = round(duration.total_seconds(), 2)
                _set_objective_gap_status(redis_client, scan_id_val, status_payload)

                # Mark executive summary stale
                scan_row = sync_db_session.execute(
                    select(Scan).where(Scan.id == scan_id_val)
                ).scalars().first()
                if scan_row:
                    scan_row.executive_summary_stale = True
                    sync_db_session.add(scan_row)
                    sync_db_session.commit()

            except RuntimeError as e:
                if str(e) == "cancelled":
                    status_payload.update({
                        "status": "cancelled",
                        "progress_status": "Cancelled by user",
                        "total_probed": total_probed,
                        "total_found": total_found,
                        "total_extracted": total_extracted,
                        "log": log_entries,
                        "extracted_ids": extracted_ids,
                        "ended_at": datetime.datetime.utcnow().isoformat()
                    })
                    duration = datetime.datetime.utcnow() - started_at
                    status_payload["duration_seconds"] = round(duration.total_seconds(), 2)
                    _set_objective_gap_status(redis_client, scan_id_val, status_payload)
                else:
                    raise
            except Exception as e:
                import traceback
                error_traceback = traceback.format_exc()
                logger.error(f"Objective gap extraction failed for scan {scan_id_val}")
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(f"Exception message: {e}")
                logger.error(f"Exception repr: {repr(e)}")
                logger.error(f"Full traceback:\n{error_traceback}")
                if not status_payload.get("pattern_output"):
                    pattern_output_value = pattern_raw if "pattern_raw" in locals() else "<no output>"
                    logger.info(f"[objective_gap] Setting pattern_output to: {pattern_output_value[:100]}")
                    status_payload["pattern_output"] = pattern_output_value
                error_message = f"{type(e).__name__}: {e}"
                logger.info(f"[objective_gap] Setting error message: {error_message}")
                status_payload.update({
                    "status": "failed",
                    "error": error_message,
                    "total_probed": total_probed,
                    "total_found": total_found,
                    "total_extracted": total_extracted,
                    "log": log_entries,
                    "extracted_ids": extracted_ids,
                    "ended_at": datetime.datetime.utcnow().isoformat()
                })
                duration = datetime.datetime.utcnow() - started_at
                status_payload["duration_seconds"] = round(duration.total_seconds(), 2)
                _set_objective_gap_status(redis_client, scan_id_val, status_payload)
            finally:
                sync_db_session.close()

        if background_tasks is not None:
            background_tasks.add_task(_run_gap_extraction, extracted_text, scan_id)
        else:
            _run_gap_extraction(extracted_text, scan_id)

        return {
            "status": "started",
            "message": "Objective gap extraction started",
            "job_id": _objective_gap_job_id(scan_id)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start objective gap extraction for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/objectives/gap-extract/cancel")
async def cancel_objective_gap_extract(
    scan_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Request cancellation of the gap extraction job."""
    redis_client = _get_redis()
    status = _get_objective_gap_status(redis_client, scan_id)
    if not status:
        return {"status": "idle", "message": "No gap extraction job found"}
    status.update({
        "cancel_requested": True,
        "progress_status": "Cancel requested",
        "updated_at": datetime.datetime.utcnow().isoformat()
    })
    _set_objective_gap_status(redis_client, scan_id, status)
    return {"status": "cancelling", "message": "Cancel requested"}

@router.post("/report/{scan_id}/objectives/extract")
async def extract_objectives_endpoint(
    scan_id: int,
    force: bool = False,
    background_tasks: BackgroundTasks = None,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Extract control objectives from the report text for this scan.
    
    Query Parameters:
    - force: If True, re-extract even if objectives already exist
    """
    try:
        from ..extractors.objective_extractor import extract_objectives
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from .. import config

        redis_client = _get_redis()
        existing_status = _get_objective_status(redis_client, scan_id)
        if existing_status.get("status") == "running" and not force:
            return {
                "status": "running",
                "message": "Objective extraction already running",
                **existing_status
            }
        
        # Check if objectives already exist
        existing_count = await db.execute(
            select(func.count(ControlObjective.id)).where(ControlObjective.scan_id == scan_id)
        )
        count = existing_count.scalar()
        
        if count > 0 and not force:
            return {
                "status": "skipped",
                "message": f"{count} objectives already exist. Use force=true to re-extract.",
                "objectives_count": count
            }
        
        # Get scan to verify it exists
        scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Try to get extracted text from scan.extracted_text first (database field)
        if scan.extracted_text:
            extracted_text = scan.extracted_text
            logger.info(f"Using extracted_text from database for scan {scan_id}")
        else:
            # Fallback: Try to load from file system (legacy support)
            import os
            import pathlib
            PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
            
            # Try multiple possible locations for extracted text
            possible_paths = [
                PROJECT_ROOT / 'data' / 'output' / 'output.txt',  # Legacy global path
            ]
            
            # Try to find user-specific job directories
            jobs_dir = PROJECT_ROOT / 'data' / 'jobs'
            if jobs_dir.exists():
                for user_dir in jobs_dir.iterdir():
                    if user_dir.is_dir():
                        for job_dir in user_dir.iterdir():
                            if job_dir.is_dir():
                                txt_path = job_dir / 'temp' / 'output.txt'
                                if txt_path.exists():
                                    possible_paths.insert(0, txt_path)
            
            # Try each path
            extracted_text = None
            for txt_path in possible_paths:
                if txt_path.exists():
                    try:
                        with open(txt_path, 'r', encoding='utf-8') as f:
                            extracted_text = f.read()
                        logger.info(f"Loaded extracted text from {txt_path}")
                        break
                    except Exception as e:
                        logger.warning(f"Failed to read {txt_path}: {e}")
                        continue
            
            if not extracted_text:
                raise HTTPException(status_code=404, detail="Extracted text not found for this scan. Text may only be available in database for newer scans.")
        
        def _run_extraction(text: str, scan_id_val: int, sections_payload: List[Dict[str, Any]]) -> None:
            sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
            sync_engine = create_engine(sync_db_url, echo=False)
            SessionLocal = sessionmaker(bind=sync_engine)
            sync_db_session = SessionLocal()

            try:
                objectives = extract_objectives(
                    extracted_text=text,
                    scan_id=scan_id_val,
                    db_session=sync_db_session,
                    sections=sections_payload,
                    job_id=_objective_job_id(scan_id_val),
                    redis_client=redis_client
                )

                logger.info(f"Extracted {len(objectives)} objectives for scan {scan_id_val}")
                ignored_count = _auto_ignore_controls_matching_objective_ids(sync_db_session, scan_id_val)
                if ignored_count > 0:
                    logger.info(f"Auto-ignored {ignored_count} controls matching objective IDs for scan {scan_id_val}")
            except Exception as e:
                _set_objective_status(redis_client, scan_id_val, {
                    "status": "failed",
                    "error": str(e),
                    "updated_at": datetime.datetime.utcnow().isoformat()
                })
                logger.error(f"Objective extraction failed for scan {scan_id_val}: {e}")
            finally:
                sync_db_session.close()

        _set_objective_status(redis_client, scan_id, {
            "status": "running",
            "progress_status": "Extracting control objectives...",
            "processed_chunks": 0,
            "total_chunks": 0,
            "objectives_found": 0,
            "started_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat()
        })

        sections_payload: List[Dict[str, Any]] = []
        result_json = scan.result_json
        if isinstance(result_json, str):
            try:
                result_json = json.loads(result_json)
            except Exception:
                result_json = {}
        if isinstance(result_json, dict):
            sections_payload = result_json.get("sections") or []

        if background_tasks is not None:
            background_tasks.add_task(_run_extraction, extracted_text, scan_id, sections_payload)
        else:
            _run_extraction(extracted_text, scan_id, sections_payload)

        return {
            "status": "started",
            "message": "Objective extraction started",
            "job_id": _objective_job_id(scan_id)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to extract objectives for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/objectives/map")
async def map_objectives_to_controls_endpoint(
    scan_id: int,
    force: bool = False,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Map extracted objectives to controls for this scan.
    
    Query Parameters:
    - force: If True, re-map even if mappings already exist
    """
    try:
        from ..extractors.objective_extractor import map_controls_to_objectives
        
        # Check if objectives exist
        objectives_count = await db.execute(
            select(func.count(ControlObjective.id)).where(ControlObjective.scan_id == scan_id)
        )
        obj_count = objectives_count.scalar()
        
        if obj_count == 0:
            return {
                "status": "error",
                "message": "No objectives found. Extract objectives first.",
                "mappings_created": 0
            }
        
        # Check if mappings already exist
        existing_mappings = await db.execute(
            select(func.count(ControlObjectiveMapping.id))
            .join(ControlObjective, ControlObjectiveMapping.objective_id == ControlObjective.id)
            .where(ControlObjective.scan_id == scan_id)
        )
        mappings_count = existing_mappings.scalar()
        
        # Create sync session for mapping
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from .. import config
        
        sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
        sync_engine = create_engine(sync_db_url, echo=False)
        SessionLocal = sessionmaker(bind=sync_engine)
        sync_db_session = SessionLocal()
        
        try:
            # Map objectives to controls
            mappings_created = map_controls_to_objectives(
                scan_id=scan_id,
                db_session=sync_db_session,
                job_id=None,
                redis_client=None,
                force=force
            )
            
            logger.info(f"Created {mappings_created} objective-control mappings for scan {scan_id}")
            
            message = f"Created {mappings_created} control-objective mappings"
            if mappings_created == 0 and mappings_count > 0 and not force:
                message = f"{mappings_count} mappings already exist. No new mappings were created."

            return {
                "status": "success",
                "message": message,
                "mappings_created": mappings_created
            }
            
        finally:
            sync_db_session.close()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to map objectives for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Control-Objective Mapping Operations
# ============================================================================

@router.get("/report/{scan_id}/controls/{control_db_id}/objectives")
async def get_control_objectives(
    scan_id: int,
    control_db_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all objectives linked to a control (includes mapping details)."""
    try:
        control = (await db.execute(
            select(Control).where(
                and_(
                    Control.scan_id == scan_id,
                    Control.id == control_db_id
                )
            )
        )).scalar_one_or_none()

        if not control:
            raise HTTPException(status_code=404, detail="Control not found")

        result = await db.execute(
            select(ControlObjectiveMapping, ControlObjective)
            .join(ControlObjective, ControlObjectiveMapping.objective_id == ControlObjective.id)
            .where(ControlObjectiveMapping.control_id == control_db_id)
            .order_by(ControlObjectiveMapping.is_primary.desc(), ControlObjectiveMapping.mapping_confidence.desc())
        )
        rows = result.all()

        objectives = []
        for mapping, objective in rows:
            objectives.append({
                "mapping_id": mapping.id,
                "mapping_confidence": mapping.mapping_confidence,
                "mapping_method": mapping.mapping_method,
                "is_primary": mapping.is_primary,
                "page_proximity_score": getattr(mapping, "page_proximity_score", None),
                "line_proximity_score": getattr(mapping, "line_proximity_score", None),
                "gpt_alignment_score": getattr(mapping, "gpt_alignment_score", None),
                "id_alignment_score": getattr(mapping, "id_alignment_score", None),
                "objective": {
                    "id": objective.id,
                    "scan_id": objective.scan_id,
                    "objective_id": objective.objective_id,
                    "objective_text": objective.objective_text,
                    "status": "approved" if objective.status == "converted_to_control" else objective.status,
                    "final_confidence": objective.final_confidence,
                    "page_refs": objective.page_refs,
                    "line_ref": objective.line_ref,
                    "extraction_method": objective.extraction_method,
                }
            })

        return {
            "control_db_id": control_db_id,
            "control_id": control.control_id,
            "objectives": objectives,
            "total": len(objectives)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch objectives for control {control_db_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{scan_id}/controls/{control_db_id}/primary-objective/criteria")
async def get_primary_objective_criteria(
    scan_id: int,
    control_db_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get mapping criteria for the primary objective linked to a control."""
    try:
        control = (await db.execute(
            select(Control).where(
                and_(
                    Control.scan_id == scan_id,
                    Control.id == control_db_id
                )
            )
        )).scalar_one_or_none()

        if not control:
            raise HTTPException(status_code=404, detail="Control not found")

        mapping_result = await db.execute(
            select(ControlObjectiveMapping, ControlObjective)
            .join(ControlObjective, ControlObjectiveMapping.objective_id == ControlObjective.id)
            .where(
                and_(
                    ControlObjectiveMapping.control_id == control_db_id,
                    ControlObjectiveMapping.is_primary.is_(True),
                    ControlObjective.scan_id == scan_id
                )
            )
        )
        mapping_row = mapping_result.first()

        if not mapping_row:
            raise HTTPException(status_code=404, detail="Primary objective mapping not found")

        mapping, objective = mapping_row

        alignment_score, alignment_reasoning = calculate_alignment_score(
            objective.objective_text,
            control.control_desc or ""
        )

        control_page = _min_page_ref(control.control_page_refs)
        objective_page = _min_page_ref(objective.page_refs)
        if control_page is not None and objective_page is not None:
            proximity_score = _page_proximity_score(control_page, objective_page)
        else:
            proximity_score = _proximity_score(control.control_line_ref, objective.line_ref)

        stored_page_score = getattr(mapping, "page_proximity_score", None)
        stored_line_score = getattr(mapping, "line_proximity_score", None)
        stored_gpt_score = getattr(mapping, "gpt_alignment_score", None)
        stored_id_score = getattr(mapping, "id_alignment_score", None)

        return {
            "control": {
                "id": control.id,
                "control_id": control.control_id,
                "control_desc": control.control_desc,
                "page_refs": control.control_page_refs,
                "line_ref": control.control_line_ref
            },
            "objective": {
                "id": objective.id,
                "objective_id": objective.objective_id,
                "objective_text": objective.objective_text,
                "final_confidence": objective.final_confidence,
                "page_refs": objective.page_refs,
                "line_ref": objective.line_ref
            },
            "mapping": {
                "id": mapping.id,
                "is_primary": mapping.is_primary,
                "mapping_method": mapping.mapping_method,
                "mapping_confidence": mapping.mapping_confidence,
                "alignment_score": alignment_score,
                "alignment_reasoning": alignment_reasoning,
                "proximity_score": proximity_score,
                "page_proximity_score": stored_page_score,
                "line_proximity_score": stored_line_score,
                "gpt_alignment_score": stored_gpt_score,
                "id_alignment_score": stored_id_score,
                "objective_confidence": objective.final_confidence,
                "weights": {
                    "page_proximity": 0.3,
                    "line_proximity": 0.0,
                    "gpt_alignment": 0.2,
                    "id_alignment": 0.3
                }
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to compute primary objective criteria for control {control_db_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/report/{scan_id}/controls/primary-objectives")
async def get_primary_objective_mappings(
    scan_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get primary objective mapping for all controls in a scan."""
    try:
        mappings_result = await db.execute(
            select(ControlObjectiveMapping, ControlObjective, Control)
            .join(ControlObjective, ControlObjectiveMapping.objective_id == ControlObjective.id)
            .join(Control, ControlObjectiveMapping.control_id == Control.id)
            .where(
                and_(
                    Control.scan_id == scan_id,
                    ControlObjectiveMapping.is_primary.is_(True)
                )
            )
        )
        rows = mappings_result.all()

        mappings = []
        for mapping, objective, control in rows:
            mappings.append({
                "control_db_id": control.id,
                "control_id": control.control_id,
                "objective": {
                    "id": objective.id,
                    "objective_id": objective.objective_id,
                    "objective_text": objective.objective_text,
                    "final_confidence": objective.final_confidence,
                    "status": objective.status,
                    "page_refs": objective.page_refs,
                    "line_ref": objective.line_ref
                },
                "mapping_confidence": mapping.mapping_confidence,
                "mapping_method": mapping.mapping_method,
                "is_primary": mapping.is_primary
            })

        return {
            "mappings": mappings,
            "total": len(mappings)
        }

    except Exception as e:
        logger.error(f"Failed to fetch primary objective mappings for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/report/{scan_id}/objectives/{objective_id}/controls")
async def get_objective_controls(
    scan_id: int,
    objective_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all controls linked to an objective."""
    try:
        # Verify objective exists
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        # Get mappings with control details
        mappings_result = await db.execute(
            select(ControlObjectiveMapping, Control).join(
                Control, ControlObjectiveMapping.control_id == Control.id
            ).where(ControlObjectiveMapping.objective_id == objective_id)
            .order_by(ControlObjectiveMapping.is_primary.desc(), ControlObjectiveMapping.mapping_confidence.desc())
        )
        mappings = mappings_result.all()
        
        controls = []
        for mapping, control in mappings:
            controls.append({
                "mapping_id": mapping.id,
                "control_id": control.control_id,
                "control_db_id": control.id,
                "control_desc": control.control_desc,
                "control_confidence": control.control_confidence,
                "mapping_confidence": mapping.mapping_confidence,
                "mapping_method": mapping.mapping_method,
                "is_primary": mapping.is_primary,
                "page_proximity_score": getattr(mapping, "page_proximity_score", None),
                "line_proximity_score": getattr(mapping, "line_proximity_score", None),
                "gpt_alignment_score": getattr(mapping, "gpt_alignment_score", None),
                "id_alignment_score": getattr(mapping, "id_alignment_score", None),
                "created_at": mapping.created_at.isoformat() if mapping.created_at else None
            })
        
        return {
            "objective_id": objective_id,
            "objective_text": obj.objective_text,
            "controls": controls,
            "total": len(controls)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch controls for objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/objectives/{objective_id}/controls/{control_db_id}")
async def link_control_to_objective(
    scan_id: int,
    objective_id: int,
    control_db_id: int,
    data: Dict[str, Any] = Body(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Link a control to an objective (create mapping).
    
    Body:
    - mapping_confidence: Optional confidence score (0.0-1.0), defaults to 1.0
    - is_primary: Optional bool, defaults to False
    """
    try:
        # Verify objective exists
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        # Verify control exists
        control = (await db.execute(
            select(Control).where(
                and_(
                    Control.scan_id == scan_id,
                    Control.id == control_db_id
                )
            )
        )).scalar_one_or_none()
        
        if not control:
            raise HTTPException(status_code=404, detail="Control not found")
        
        # Check if mapping already exists
        existing_result = await db.execute(
            select(ControlObjectiveMapping).where(
                and_(
                    ControlObjectiveMapping.objective_id == objective_id,
                    ControlObjectiveMapping.control_id == control_db_id
                )
            )
        )
        existing = existing_result.scalars().first()
        
        if existing:
            raise HTTPException(status_code=409, detail="Mapping already exists")
        
        # Create mapping
        mapping = ControlObjectiveMapping(
            control_id=control_db_id,
            objective_id=objective_id,
            mapping_confidence=data.get("mapping_confidence", 1.0),
            mapping_method='manual',
            is_primary=data.get("is_primary", False),
            created_at=datetime.datetime.utcnow(),
            created_by_user_id=current_user.id
        )
        
        db.add(mapping)
        await db.commit()
        await db.refresh(mapping)
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        
        return {
            "status": "linked",
            "mapping_id": mapping.id,
            "objective_id": objective_id,
            "control_id": control.control_id,
            "control_db_id": control_db_id,
            "mapping_confidence": mapping.mapping_confidence,
            "is_primary": mapping.is_primary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to link control {control_db_id} to objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/report/{scan_id}/objectives/{objective_id}/controls/{control_db_id}")
async def unlink_control_from_objective(
    scan_id: int,
    objective_id: int,
    control_db_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Remove a control-objective mapping."""
    try:
        # Find all mappings (handle potential duplicates)
        result = await db.execute(
            select(ControlObjectiveMapping).where(
                and_(
                    ControlObjectiveMapping.objective_id == objective_id,
                    ControlObjectiveMapping.control_id == control_db_id
                )
            )
        )
        mappings = result.scalars().all()
        
        if not mappings:
            raise HTTPException(status_code=404, detail="Mapping not found")
        
        # Delete all matching mappings (in case of duplicates)
        for mapping in mappings:
            await db.delete(mapping)
        
        await db.commit()
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        
        return {
            "status": "unlinked",
            "objective_id": objective_id,
            "control_db_id": control_db_id,
            "deleted_count": len(mappings)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to unlink control {control_db_id} from objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/report/{scan_id}/mappings/{mapping_id}")
async def update_mapping(
    scan_id: int,
    mapping_id: int,
    data: Dict[str, Any] = Body(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update a control-objective mapping.
    
    Allowed fields:
    - mapping_confidence: Confidence score (0.0-1.0)
    - is_primary: Whether this is the primary objective for the control
    """
    try:
        mapping = (await db.execute(
            select(ControlObjectiveMapping).where(ControlObjectiveMapping.id == mapping_id)
        )).scalar_one_or_none()
        
        if not mapping:
            raise HTTPException(status_code=404, detail="Mapping not found")
        
        # Update allowed fields
        if "mapping_confidence" in data:
            confidence = data["mapping_confidence"]
            if not (0.0 <= confidence <= 1.0):
                raise HTTPException(status_code=400, detail="mapping_confidence must be between 0.0 and 1.0")
            mapping.mapping_confidence = confidence
        
        if "is_primary" in data:
            mapping.is_primary = data["is_primary"]
        
        db.add(mapping)
        await db.commit()
        await db.refresh(mapping)
        
        # Mark executive summary stale
        await mark_executive_summary_stale(scan_id, db)
        
        return {
            "id": mapping.id,
            "mapping_confidence": mapping.mapping_confidence,
            "is_primary": mapping.is_primary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update mapping {mapping_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Workflow Operations
# ============================================================================

@router.post("/report/{scan_id}/objectives/{objective_id}/approve")
async def approve_objective(
    scan_id: int,
    objective_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Approve an objective (set status to 'approved')."""
    try:
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        obj.status = 'approved'
        obj.final_confidence = 1.0
        obj.updated_at = datetime.datetime.utcnow()
        obj.updated_by_user_id = current_user.id
        
        db.add(obj)
        await db.commit()
        
        return {"status": "approved", "objective_id": objective_id}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to approve objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/objectives/{objective_id}/reject")
async def reject_objective(
    scan_id: int,
    objective_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Reject an objective (set status to 'rejected')."""
    try:
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        obj.status = 'rejected'
        obj.updated_at = datetime.datetime.utcnow()
        obj.updated_by_user_id = current_user.id
        
        db.add(obj)
        await db.commit()
        
        return {"status": "rejected", "objective_id": objective_id}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to reject objective {objective_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/objectives/{objective_id}/convert-to-control")
async def convert_objective_to_control(
    scan_id: int,
    objective_id: int,
    data: Dict[str, Any] = Body(default=None),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Convert an objective to a control.
    
    This creates or updates a control from the objective text and deletes the
    objective to avoid duplicates. Control confidence is set to 100%.
    """
    try:
        obj = (await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id == objective_id
                )
            )
        )).scalar_one_or_none()
        
        if not obj:
            raise HTTPException(status_code=404, detail="Objective not found")
        
        payload = data or {}
        control_id_val = (payload.get("control_id") or obj.objective_id or f"OBJ-{objective_id}")
        control_desc_val = payload.get("control_desc") or obj.objective_text
        control_test_val = payload.get("control_test") or "[Converted from control objective]"
        control_test_results_val = payload.get("control_test_results") or ""
        deviation_desc_val = payload.get("deviation_desc")
        has_deviation_val = bool(deviation_desc_val)
        control_page_refs_val = payload.get("control_page_refs") or payload.get("control_page_ref") or obj.page_refs
        control_line_ref_val = payload.get("control_line_ref") or obj.line_ref

        existing_controls = (await db.execute(
            select(Control).where(
                and_(
                    Control.scan_id == scan_id,
                    Control.control_id == control_id_val
                )
            )
        )).scalars().all()

        now = datetime.datetime.utcnow()
        timestamp = now.strftime("%Y-%m-%d %I:%M %p")

        if len(existing_controls) > 1:
            await db.delete(obj)
            await db.commit()

            await mark_executive_summary_stale(scan_id, db)

            return {
                "status": "exists",
                "objective_id": objective_id,
                "control_id": control_id_val,
                "control_count": len(existing_controls)
            }

        if len(existing_controls) == 1:
            existing_control = existing_controls[0]
            existing_control.control_desc = control_desc_val
            existing_control.control_test = control_test_val
            existing_control.control_test_results = control_test_results_val
            existing_control.deviation_desc = deviation_desc_val
            existing_control.has_deviation = has_deviation_val
            existing_control.control_page_refs = control_page_refs_val
            existing_control.control_line_ref = control_line_ref_val
            existing_control.control_confidence = 1.0
            if hasattr(existing_control, "final_confidence"):
                existing_control.final_confidence = 1.0
            existing_control.confidence_calc = f"Converted from objective {objective_id} ({timestamp})"
            _append_edit_log(existing_control, f"Objective converted to control ({timestamp})")
            existing_control.annotation = (existing_control.annotation or "") + f"\nConverted from control objective (ID: {objective_id})"
            existing_control.updated_at = now
            existing_control.updated_by_user_id = current_user.id
            db.add(existing_control)
            new_control = existing_control
            action = "updated"
        else:
            max_seq_result = await db.execute(
                select(func.max(Control.control_seq)).where(Control.scan_id == scan_id)
            )
            max_seq = max_seq_result.scalar() or 0

            new_control = Control(
                scan_id=scan_id,
                control_id=control_id_val,
                control_desc=control_desc_val,
                control_test=control_test_val,
                control_test_results=control_test_results_val,
                has_deviation=has_deviation_val,
                deviation_desc=deviation_desc_val,
                control_page_refs=control_page_refs_val,
                control_line_ref=control_line_ref_val,
                control_seq=max_seq + 1,
                control_confidence=1.0,
                confidence_calc=f"Converted from objective {objective_id} ({timestamp})",
                control_gpt_opinion="converted_from_objective",
                control_gpt_reasoning=f"Converted from objective by {current_user.username}",
                annotation=f"Converted from control objective (ID: {objective_id})",
                created_at=now,
                updated_at=now,
                updated_by_user_id=current_user.id
            )

            db.add(new_control)
            action = "created"

        await db.delete(obj)
        await db.commit()
        await db.refresh(new_control)

        await mark_executive_summary_stale(scan_id, db)

        return {
            "status": action,
            "objective_id": objective_id,
            "control_id": new_control.control_id,
            "control_db_id": new_control.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to convert objective {objective_id} to control: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/controls/{control_db_id}/convert-to-objective")
async def convert_control_to_objective(
    scan_id: int,
    control_db_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Convert a control to a control objective.

    This creates a new objective from the control or links to an existing
    objective. The control is preserved and auto-ignored for audit purposes.
    """
    try:
        control = (await db.execute(
            select(Control).where(
                and_(
                    Control.scan_id == scan_id,
                    Control.id == control_db_id
                )
            )
        )).scalar_one_or_none()

        if not control:
            raise HTTPException(status_code=404, detail="Control not found")

        base_text = (control.control_desc or '').strip()
        if not base_text:
            parts = [
                (control.control_test or '').strip(),
                (control.control_test_results or '').strip()
            ]
            base_text = "\n".join([p for p in parts if p])

        if not base_text:
            base_text = f"Converted from control {control.control_id or control.id}"

        objective_id = (control.control_id or '').strip() or f"CTRL-{control_db_id}"
        confidence = control.final_confidence if control.final_confidence is not None else control.control_confidence

        existing_objective = None
        if objective_id:
            existing_objective = (await db.execute(
                select(ControlObjective).where(
                    and_(
                        ControlObjective.scan_id == scan_id,
                        func.lower(ControlObjective.objective_id) == objective_id.lower()
                    )
                )
            )).scalar_one_or_none()

        if existing_objective is None and base_text:
            existing_objective = (await db.execute(
                select(ControlObjective).where(
                    and_(
                        ControlObjective.scan_id == scan_id,
                        func.lower(ControlObjective.objective_text) == base_text.lower()
                    )
                )
            )).scalar_one_or_none()

        now = datetime.datetime.utcnow()
        timestamp = now.strftime("%Y-%m-%d %I:%M %p")

        if existing_objective:
            mapping = (await db.execute(
                select(ControlObjectiveMapping).where(
                    and_(
                        ControlObjectiveMapping.objective_id == existing_objective.id,
                        ControlObjectiveMapping.control_id == control.id
                    )
                )
            )).scalar_one_or_none()

            if not mapping:
                mapping = ControlObjectiveMapping(
                    objective_id=existing_objective.id,
                    control_id=control.id,
                    mapping_confidence=1.0,
                    is_primary=True,
                    mapping_method="manual"
                )
                db.add(mapping)

            existing_objective.status = "approved"
            existing_objective.updated_at = now
            existing_objective.updated_by_user_id = current_user.id
            db.add(existing_objective)

            action = "exists"
            objective_db_id = existing_objective.id
            objective_identifier = existing_objective.objective_id
        else:
            new_objective = ControlObjective(
                scan_id=scan_id,
                objective_id=objective_id,
                objective_text=base_text,
                page_refs=control.control_page_refs,
                line_ref=control.control_line_ref,
                final_confidence=confidence,
                confidence_calc=f"Converted from control: {control.confidence_calc}",
                status='approved',
                created_at=now,
                updated_at=now,
                updated_by_user_id=current_user.id
            )

            db.add(new_objective)
            await db.flush()

            mapping = ControlObjectiveMapping(
                objective_id=new_objective.id,
                control_id=control.id,
                mapping_confidence=1.0,
                is_primary=True,
                mapping_method="manual"
            )
            db.add(mapping)

            action = "created"
            objective_db_id = new_objective.id
            objective_identifier = new_objective.objective_id

        control.control_confidence = 0.0
        if hasattr(control, "final_confidence"):
            control.final_confidence = 0.0
        ignore_note = "Converted to control objective; control auto-ignored (confidence set to 0)"
        existing_calc = control.confidence_calc or ""
        separator = "\n" if existing_calc and not existing_calc.endswith("\n") else ""
        control.confidence_calc = f"{existing_calc}{separator}{ignore_note}"
        _append_edit_log(control, f"{ignore_note} ({timestamp})")
        control.annotation = (control.annotation or '') + f"\nConverted to control objective by {current_user.username}"
        control.updated_at = now
        control.updated_by_user_id = current_user.id

        db.add(control)
        await db.commit()

        await mark_executive_summary_stale(scan_id, db)

        return {
            "status": action,
            "control_db_id": control_db_id,
            "objective_db_id": objective_db_id,
            "objective_id": objective_identifier,
            "ignored": True
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to convert control {control_db_id} to objective: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Bulk Operations
# ============================================================================

@router.post("/report/{scan_id}/objectives/bulk-approve")
async def bulk_approve_objectives(
    scan_id: int,
    data: Dict[str, List[int]] = Body(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Approve multiple objectives at once.
    
    Body:
    - objective_ids: List of objective IDs to approve
    """
    try:
        objective_ids = data.get("objective_ids", [])
        if not objective_ids:
            raise HTTPException(status_code=400, detail="objective_ids required")
        
        # Update all objectives
        result = await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id.in_(objective_ids)
                )
            )
        )
        objectives = result.scalars().all()
        
        if len(objectives) != len(objective_ids):
            raise HTTPException(status_code=404, detail="Some objectives not found")
        
        for obj in objectives:
            obj.status = 'approved'
            obj.final_confidence = 1.0
            obj.updated_at = datetime.datetime.utcnow()
            obj.updated_by_user_id = current_user.id
            db.add(obj)
        
        await db.commit()
        
        return {"status": "approved", "count": len(objectives), "objective_ids": objective_ids}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to bulk approve objectives: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/{scan_id}/objectives/bulk-reject")
async def bulk_reject_objectives(
    scan_id: int,
    data: Dict[str, List[int]] = Body(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Reject multiple objectives at once.
    
    Body:
    - objective_ids: List of objective IDs to reject
    """
    try:
        objective_ids = data.get("objective_ids", [])
        if not objective_ids:
            raise HTTPException(status_code=400, detail="objective_ids required")
        
        # Update all objectives
        result = await db.execute(
            select(ControlObjective).where(
                and_(
                    ControlObjective.scan_id == scan_id,
                    ControlObjective.id.in_(objective_ids)
                )
            )
        )
        objectives = result.scalars().all()
        
        if len(objectives) != len(objective_ids):
            raise HTTPException(status_code=404, detail="Some objectives not found")
        
        for obj in objectives:
            obj.status = 'rejected'
            obj.updated_at = datetime.datetime.utcnow()
            obj.updated_by_user_id = current_user.id
            db.add(obj)
        
        await db.commit()
        
        return {"status": "rejected", "count": len(objectives), "objective_ids": objective_ids}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to bulk reject objectives: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Statistics & Summary
# ============================================================================

@router.get("/report/{scan_id}/objectives/stats")
async def get_objectives_stats(
    scan_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get statistics about objectives for a scan."""
    try:
        # Count by status
        total_result = await db.execute(
            select(func.count(ControlObjective.id)).where(ControlObjective.scan_id == scan_id)
        )
        total = total_result.scalar()
        
        pending_result = await db.execute(
            select(func.count(ControlObjective.id)).where(
                and_(ControlObjective.scan_id == scan_id, ControlObjective.status == 'pending')
            )
        )
        pending = pending_result.scalar()
        
        approved_result = await db.execute(
            select(func.count(ControlObjective.id)).where(
                and_(ControlObjective.scan_id == scan_id, ControlObjective.status == 'approved')
            )
        )
        approved = approved_result.scalar()
        
        rejected_result = await db.execute(
            select(func.count(ControlObjective.id)).where(
                and_(ControlObjective.scan_id == scan_id, ControlObjective.status == 'rejected')
            )
        )
        rejected = rejected_result.scalar()
        
        converted_result = await db.execute(
            select(func.count(ControlObjective.id)).where(
                and_(ControlObjective.scan_id == scan_id, ControlObjective.status == 'converted_to_control')
            )
        )
        converted = converted_result.scalar()
        approved = (approved or 0) + (converted or 0)
        
        # Average confidence
        avg_confidence_result = await db.execute(
            select(func.avg(ControlObjective.final_confidence)).where(ControlObjective.scan_id == scan_id)
        )
        avg_confidence = avg_confidence_result.scalar() or 0.0
        
        # Count objectives with mappings
        mapped_result = await db.execute(
            select(func.count(func.distinct(ControlObjectiveMapping.objective_id))).where(
                ControlObjectiveMapping.objective_id.in_(
                    select(ControlObjective.id).where(ControlObjective.scan_id == scan_id)
                )
            )
        )
        mapped = mapped_result.scalar()
        
        return {
            "scan_id": scan_id,
            "total": total,
            "by_status": {
                "pending": pending,
                "approved": approved,
                "rejected": rejected
            },
            "average_confidence": round(avg_confidence, 3),
            "with_control_mappings": mapped,
            "without_mappings": total - mapped
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch objectives stats for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
