"""
Router for settings, configuration, and utility operations.

Handles settings CRUD, runtime config introspection, quick test mode, help system, and Docker controls.
"""
import logging
import time
import subprocess
from typing import Dict, Any
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, Response
from sqlalchemy.future import select
from sqlalchemy.dialects import postgresql as pg_dialect

from ..models import Setting
from ..models import User
from ..database import get_db
from ..auth.dependencies import require_admin, get_current_active_user
from .. import config as cfg

router = APIRouter()

# Docker control feature flag
DOCKER_CONTROL_ENABLED = cfg.DOCKER_CONTROL_ENABLED
PROJECT_ROOT = Path(__file__).resolve().parents[3]


@router.get("/settings")
async def get_settings(request: Request, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Get all settings with HTML content negotiation for SPA routing."""
    # Content negotiation: if browser expects HTML, serve SPA index
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        FRONTEND_INDEX = PROJECT_ROOT / 'frontend' / 'build' / 'index.html'
        if FRONTEND_INDEX.exists():
            return FileResponse(str(FRONTEND_INDEX))
        return JSONResponse({"error": "UI build not found"}, status_code=404)
    
    # API JSON response
    result = await db.execute(select(Setting))
    rows = result.scalars().all()
    return {row.key: row.value for row in rows}


@router.post("/settings")
async def update_settings(request: Request, db=Depends(get_db), current_user: User = Depends(require_admin)):
    """Update settings with upsert logic."""
    data = await request.json()
    logging.debug(f"/settings payload: {data}")
    
    try:
        for key, value in data.items():
            stmt = pg_dialect.insert(Setting).values(
                key=key, 
                value=str(value)
            ).on_conflict_do_update(
                index_elements=[Setting.key], 
                set_={"value": str(value)}
            )
            await db.execute(stmt)
        await db.commit()
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        logging.error(f"/settings DB error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/config/runtime")
async def get_runtime_config(current_user: User = Depends(get_current_active_user)):
    """Get runtime configuration snapshot from config module."""
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
        },
        "queue": {
            "max_concurrent_scans": cfg.MAX_CONCURRENT_SCANS,
        }
    }


@router.get("/config/budgets")
async def get_budget_snapshot(current_user: User = Depends(get_current_active_user)):
    """Get token budget snapshot for debugging."""
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


@router.post("/config/quick-test-mode")
async def toggle_quick_test_mode(request: Request, current_user: User = Depends(require_admin)):
    """Toggle quick test mode by updating .env file."""
    import os
    import re
    
    try:
        data = await request.json()
        enabled = data.get("enabled", False)
        max_controls = data.get("max_controls", 10)
        
        # Find .env file
        env_file = Path(os.getenv("ENV_FILE_PATH", ".env"))
        if not env_file.is_absolute():
            env_file = PROJECT_ROOT / ".env"
        
        if not env_file.exists():
            return JSONResponse({"error": ".env file not found"}, status_code=404)
        
        # Read current content
        content = env_file.read_text(encoding='utf-8')
        
        # Remove existing settings
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


@router.post("/config/max-concurrent-scans")
async def update_max_concurrent_scans(request: Request, current_user: User = Depends(require_admin)):
    """Update maximum concurrent scans by updating .env file"""
    import os
    import re
    
    try:
        data = await request.json()
        max_concurrent = int(data.get("max_concurrent", 1))
        
        if max_concurrent < 1 or max_concurrent > 10:
            return JSONResponse({"error": "max_concurrent must be between 1 and 10"}, status_code=400)
        
        # Find .env file
        env_file = Path(os.getenv("ENV_FILE_PATH", ".env"))
        if not env_file.is_absolute():
            env_file = PROJECT_ROOT / ".env"
        
        if not env_file.exists():
            return JSONResponse({"error": ".env file not found"}, status_code=404)
        
        # Read current content
        content = env_file.read_text(encoding='utf-8')
        
        # Update or add MAX_CONCURRENT_SCANS
        if re.search(r'(?m)^MAX_CONCURRENT_SCANS=', content):
            # Update existing
            content = re.sub(r'(?m)^MAX_CONCURRENT_SCANS=.*$', f'MAX_CONCURRENT_SCANS={max_concurrent}', content)
        else:
            # Add new (under Queue Settings section if it exists, otherwise at end)
            if '# --- Queue Settings ---' in content:
                content = re.sub(
                    r'(# --- Queue Settings ---\n)',
                    f'\\1MAX_CONCURRENT_SCANS={max_concurrent}\n',
                    content
                )
            else:
                content += f"\n\n# --- Queue Settings ---\nMAX_CONCURRENT_SCANS={max_concurrent}\n"
        
        # Write back
        env_file.write_text(content, encoding='utf-8')
        
        # Update runtime config
        cfg.MAX_CONCURRENT_SCANS = max_concurrent
        logging.info(f"[CONFIG] Updated cfg.MAX_CONCURRENT_SCANS to {max_concurrent}")
        
        # Update scan queue max_concurrent (live update - no restart needed)
        queue_updated = False
        old_value = None
        try:
            from ..threading.scan_queue import get_scan_queue
            queue = get_scan_queue()
            old_value = queue.max_concurrent
            queue.max_concurrent = max_concurrent
            queue_updated = True
            logging.info(f"[CONFIG] Updated scan queue max_concurrent: {old_value} → {max_concurrent}")
        except Exception as queue_err:
            logging.warning(f"[CONFIG] Could not update scan queue: {queue_err}")
        
        message = f"Max concurrent scans updated: {old_value or 'unknown'} → {max_concurrent}" if queue_updated else f"Max concurrent scans set to {max_concurrent} (will apply on next restart)"
        
        return {
            "status": "ok",
            "max_concurrent": max_concurrent,
            "old_value": old_value,
            "queue_updated": queue_updated,
            "message": message,
            "requires_restart": False  # Queue is updated immediately when queue_updated=True
        }
    except Exception as e:
        logging.error(f"Error updating max concurrent scans: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/help/index")
async def get_help_index(current_user: User = Depends(get_current_active_user)):
    """Get help topics index/manifest."""
    import json
    
    try:
        help_index_path = PROJECT_ROOT / "docs" / "help" / "index.json"
        with open(help_index_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading help index: {e}")
        raise HTTPException(status_code=500, detail="Help index not found")


@router.get("/help/content/{topic_id}")
async def get_help_content(topic_id: str, current_user: User = Depends(get_current_active_user)):
    """Get markdown content for a specific help topic."""
    import json
    
    try:
        help_dir = PROJECT_ROOT / "docs" / "help"
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


def _run_docker_cmd(args):
    """Helper to run Docker commands with timeout."""
    try:
        out = subprocess.check_output(
            args, 
            stderr=subprocess.STDOUT, 
            timeout=12
        ).decode("utf-8", errors="replace")
        return {"ok": True, "output": out}
    except subprocess.CalledProcessError as e:
        return {
            "ok": False, 
            "output": e.output.decode("utf-8", errors="replace"), 
            "code": e.returncode
        }
    except Exception as e:
        return {"ok": False, "output": str(e)}


@router.get("/docker/status")
async def docker_status(current_user: User = Depends(get_current_active_user)):
    """Get Docker container status (requires DOCKER_CONTROL_ENABLED)."""
    if not DOCKER_CONTROL_ENABLED:
        return JSONResponse({"error": "Docker control disabled"}, status_code=403)
    
    result = _run_docker_cmd(["docker", "ps", "-a", "--format", "{{.Names}}::{{.Status}}"])
    if not result["ok"]:
        return JSONResponse({"error": result["output"]}, status_code=500)
    
    services = []
    for line in result["output"].strip().splitlines():
        if "::" in line:
            name, status = line.split("::", 1)
            services.append({"name": name, "status": status})
    
    return {"services": services}


@router.post("/docker/stop/{container}")
async def docker_stop(container: str, current_user: User = Depends(require_admin)):
    """Stop a Docker container."""
    if not DOCKER_CONTROL_ENABLED:
        return JSONResponse({"error": "Docker control disabled"}, status_code=403)
    
    result = _run_docker_cmd(["docker", "stop", container])
    if not result["ok"]:
        return JSONResponse({"error": result["output"]}, status_code=500)
    
    return {"status": "stopped", "container": container}


@router.post("/docker/restart/{container}")
async def docker_restart(container: str, current_user: User = Depends(require_admin)):
    """Restart a Docker container."""
    if not DOCKER_CONTROL_ENABLED:
        return JSONResponse({"error": "Docker control disabled"}, status_code=403)
    
    result = _run_docker_cmd(["docker", "restart", container])
    if not result["ok"]:
        return JSONResponse({"error": result["output"]}, status_code=500)
    
    return {"status": "restarted", "container": container}


@router.post("/docker/start/{container}")
async def docker_start(container: str, current_user: User = Depends(require_admin)):
    """Start a Docker container."""
    if not DOCKER_CONTROL_ENABLED:
        return JSONResponse({"error": "Docker control disabled"}, status_code=403)
    
    result = _run_docker_cmd(["docker", "start", container])
    if not result["ok"]:
        return JSONResponse({"error": result["output"]}, status_code=500)
    
    return {"status": "started", "container": container}
