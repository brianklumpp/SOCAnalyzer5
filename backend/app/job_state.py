"""
Simplified Redis job state using Redis Hash.

Replaces the JSON blob approach with atomic HSET/HGET/HINCRBY operations.
No locking needed — each field update is atomic at the Redis level.

Progress fields (flat scalars):
  status, phase, progress, done, error, cancelled, paused,
  start_time, scan_id, filename, report_type, report_subtype,
  company, auditor, product, report_date, coverage_period,
  company_logo_url, detected_report_type, detected_subtype,
  detection_confidence, awaiting_confirmation,
  controls_count, controls_total_estimate, controls_percent,
  controls_mapped_count, controls_mapped_percent, total_controls,
  cuecs_count, subservice_orgs_count, objectives_count, objectives_percent,
  logo_fetched, db_uploaded, extraction_partial, gpt_service_warning,
  finalized, db_saved

Complex fields (stored as JSON strings):
  result, checklist, detection_result, extraction_failures
"""

import json
import logging
import redis as _redis
from typing import Optional, Dict, Any, Union

logger = logging.getLogger(__name__)

# Fields that hold complex objects (lists/dicts) — auto JSON-encoded
_JSON_FIELDS = frozenset({
    'result', 'checklist', 'detection_result', 'extraction_failures',
})

# Fields that should be returned as int
_INT_FIELDS = frozenset({
    'progress', 'scan_id',
    'controls_count', 'controls_total_estimate', 'controls_percent',
    'controls_mapped_count', 'controls_mapped_percent', 'total_controls',
    'cuecs_count', 'subservice_orgs_count', 'objectives_count', 'objectives_percent',
})

# Fields that should be returned as float  
_FLOAT_FIELDS = frozenset({
    'start_time', 'detection_confidence',
})

# Fields that should be returned as bool
_BOOL_FIELDS = frozenset({
    'done', 'cancelled', 'paused', 'awaiting_confirmation',
    'logo_fetched', 'db_uploaded', 'extraction_partial',
    'gpt_service_warning', 'finalized', 'db_saved',
})

_KEY_PREFIX = "job:"
_TTL = 86400  # 24 hours


def _key(job_id: str) -> str:
    return f"{_KEY_PREFIX}{job_id}"


def _encode_value(field: str, value: Any) -> str:
    """Encode a value for Redis Hash storage."""
    if field in _JSON_FIELDS:
        return json.dumps(value) if value is not None else ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if value is None:
        return ""
    return str(value)


def _decode_value(field: str, raw: str) -> Any:
    """Decode a Redis Hash value back to the proper Python type."""
    if raw is None or raw == "":
        if field in _JSON_FIELDS:
            return None
        if field in _INT_FIELDS:
            return 0
        if field in _FLOAT_FIELDS:
            return 0.0
        if field in _BOOL_FIELDS:
            return False
        return None
    
    if field in _JSON_FIELDS:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    
    if field in _BOOL_FIELDS:
        return raw in ("1", "True", "true")
    
    if field in _INT_FIELDS:
        try:
            return int(raw)
        except (ValueError, TypeError):
            return 0
    
    if field in _FLOAT_FIELDS:
        try:
            return float(raw)
        except (ValueError, TypeError):
            return 0.0
    
    return raw


# ─── Core CRUD ──────────────────────────────────────────────────────

def job_init(job_id: str, fields: Dict[str, Any], r: _redis.Redis) -> None:
    """Create a new job with initial fields. Uses HSET + EXPIRE."""
    key = _key(job_id)
    encoded = {f: _encode_value(f, v) for f, v in fields.items()}
    if encoded:
        r.hset(key, mapping=encoded)
    r.expire(key, _TTL)


def job_hset(job_id: str, field: str, value: Any, r: _redis.Redis) -> None:
    """Set a single field atomically."""
    r.hset(_key(job_id), field, _encode_value(field, value))


def job_hmset(job_id: str, fields: Dict[str, Any], r: _redis.Redis) -> None:
    """Set multiple fields atomically in one HSET call."""
    if not fields:
        return
    encoded = {f: _encode_value(f, v) for f, v in fields.items()}
    r.hset(_key(job_id), mapping=encoded)


def job_hincrby(job_id: str, field: str, amount: int, r: _redis.Redis) -> int:
    """Atomically increment an integer field. Returns new value."""
    return r.hincrby(_key(job_id), field, amount)


def job_hget(job_id: str, field: str, r: _redis.Redis) -> Any:
    """Get a single field value. Falls back to string-type key for stale data."""
    key = _key(job_id)
    try:
        raw = r.hget(key, field)
    except _redis.exceptions.ResponseError as e:
        if "WRONGTYPE" in str(e):
            try:
                blob = r.get(key)
                if blob:
                    data = json.loads(blob)
                    if isinstance(data, dict):
                        return data.get(field)
            except Exception:
                pass
            return None
        raise
    return _decode_value(field, raw)


def job_hgetall(job_id: str, r: _redis.Redis) -> Optional[Dict[str, Any]]:
    """Get all fields as a decoded dict. Returns None if job doesn't exist.
    
    Falls back to reading string-type keys (pre-migration JSON blobs)
    to avoid WRONGTYPE errors on stale keys.
    """
    key = _key(job_id)
    try:
        raw = r.hgetall(key)
    except _redis.exceptions.ResponseError as e:
        if "WRONGTYPE" in str(e):
            # Stale string-type key from before Redis Hash migration
            try:
                blob = r.get(key)
                if blob:
                    logger.debug(f"[job_hgetall] Migrating stale string key {key} to hash")
                    data = json.loads(blob)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
            return None
        raise
    if not raw:
        return None
    return {f: _decode_value(f, v) for f, v in raw.items()}


def job_exists(job_id: str, r: _redis.Redis) -> bool:
    """Check if a job exists."""
    return r.exists(_key(job_id)) > 0


def job_delete(job_id: str, r: _redis.Redis) -> None:
    """Delete a job."""
    r.delete(_key(job_id))


def job_touch_ttl(job_id: str, r: _redis.Redis) -> None:
    """Reset the TTL to 24 hours."""
    r.expire(_key(job_id), _TTL)


# ─── Flattening helpers ─────────────────────────────────────────────

# Nested keys that callers might pass in a set_job dict
_NESTED_FLATTEN_MAP = {
    'identified_entities': (
        'company', 'auditor', 'product', 'report_date', 'coverage_period',
        'company_logo_url', 'report_type',
    ),
    'counters': (
        'controls_count', 'controls_total_estimate', 'controls_percent',
        'controls_mapped_count', 'controls_mapped_percent', 'total_controls',
        'cuecs_count', 'subservice_orgs_count', 'objectives_count', 'objectives_percent',
    ),
    'phase_completion': (
        'logo_fetched', 'db_uploaded',
    ),
}


def flatten_job_dict(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten a legacy nested job dict into hash-friendly flat fields.

    Pulls known sub-keys out of identified_entities / counters / phase_completion
    and places them at the top level.  Unknown nested dicts are kept as-is
    (they'll be JSON-encoded by _encode_value if they end up in a _JSON_FIELD).
    """
    flat: Dict[str, Any] = {}
    for k, v in job.items():
        if k in _NESTED_FLATTEN_MAP and isinstance(v, dict):
            for sub_key in _NESTED_FLATTEN_MAP[k]:
                if sub_key in v:
                    flat[sub_key] = v[sub_key]
        elif k == 'enhanced_progress':
            # Dead field from ProgressTracker — drop silently
            continue
        else:
            flat[k] = v
    return flat


# ─── Compatibility layer ────────────────────────────────────────────

def get_job_compat(job_id: str, r: _redis.Redis) -> Optional[Dict[str, Any]]:
    """
    Compatibility wrapper that returns a dict matching the old JSON blob format.

    Reconstructs nested dicts (identified_entities, counters, phase_completion)
    from flat hash fields so callers that read nested fields still work.
    """
    flat = job_hgetall(job_id, r)
    if flat is None:
        return None

    # Reconstruct nested structures for backward compatibility
    job = dict(flat)  # shallow copy

    # Reconstruct identified_entities
    job['identified_entities'] = {}
    for f in ('company', 'auditor', 'product', 'report_date', 'coverage_period',
              'company_logo_url', 'report_type'):
        val = job.get(f)
        if val and f == 'report_type':
            # report_type at top-level stays; also mirror into identified_entities
            job['identified_entities']['report_type'] = val
        elif val:
            job['identified_entities'][f] = val

    # Reconstruct counters
    job['counters'] = {
        'controls_count': job.get('controls_count', 0),
        'controls_total_estimate': job.get('controls_total_estimate', 0),
        'controls_percent': job.get('controls_percent', 0),
        'controls_mapped_count': job.get('controls_mapped_count', 0),
        'controls_mapped_percent': job.get('controls_mapped_percent', 0),
        'total_controls': job.get('total_controls', 0),
        'cuecs_count': job.get('cuecs_count', 0),
        'subservice_orgs_count': job.get('subservice_orgs_count', 0),
        'objectives_count': job.get('objectives_count', 0),
        'objectives_percent': job.get('objectives_percent', 0),
    }

    # Reconstruct phase_completion
    job['phase_completion'] = {
        'logo_fetched': job.get('logo_fetched', False),
        'db_uploaded': job.get('db_uploaded', False),
    }

    return job
