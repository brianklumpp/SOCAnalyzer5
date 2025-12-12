"""
Router extraction helper - creates router modules from main.py endpoints.

This script reads main.py and extracts endpoint functions into separate router files.
Run this to generate all 9 router modules for v2.0.0 refactoring.
"""

import re
import os
from pathlib import Path

# Define router specifications
ROUTERS = {
    "scan_router": {
        "path": "backend/app/routers/scan_router.py",
        "endpoints": [
            ("analyze_pdf_bg", "POST", "/analyze/"),
            ("cancel_analysis_job", "POST", "/analyze/cancel/{job_id}"),
            ("confirm_report_type", "POST", "/analyze/confirm-type/{job_id}"),
            ("get_job_status", "GET", "/analyze/status/{job_id}"),
            ("get_job_status_min", "GET", "/analyze/status_min/{job_id}"),
            ("get_job_result", "GET", "/analyze/result/{job_id}"),
            ("finalize_job_from_disk", "POST", "/analyze/finalize/{job_id}"),
            ("resume_extractors", "POST", "/analyze/resume/{job_id}"),
            ("get_partial_controls", "GET", "/analyze/controls_partial/{job_id}"),
            ("websocket_progress", "WEBSOCKET", "/ws"),
        ],
    },
}

def extract_function_from_main(main_content: str, func_name: str, method: str, route: str) -> str:
    """Extract a complete function definition from main.py."""
    
    # Build decorator pattern
    if method == "WEBSOCKET":
        decorator_pattern = r'@app\.websocket\('
    else:
        decorator_pattern = rf'@app\.{method.lower()}\('
    
    # Find function start
    pattern = decorator_pattern + r'["\']' + re.escape(route) + r'["\']'
    match = re.search(pattern, main_content, re.MULTILINE)
    
    if not match:
        print(f"WARNING: Could not find endpoint {method} {route}")
        return ""
    
    # Find the full function by looking for the next @app decorator or end of file
    start_pos = match.start()
    
    # Find function end (next @app decorator or EOF)
    next_decorator = re.search(r'\n@app\.', main_content[start_pos + 10:])
    if next_decorator:
        end_pos = start_pos + 10 + next_decorator.start()
    else:
        end_pos = len(main_content)
    
    func_text = main_content[start_pos:end_pos].rstrip()
    
    # Replace @app with @router
    func_text = func_text.replace('@app.', '@router.')
    
    return func_text


def create_router_file(router_name: str, spec: dict, main_content: str):
    """Create a router file with all its endpoints."""
    
    # Build imports
    imports = """\"\"\"
Router for scan and analysis operations.
\"\"\"
import logging
import os
import time
import asyncio
import concurrent.futures
import traceback
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, Form, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.future import select
from pydantic import BaseModel

from ..models import Scan, Control, CUEC, SubserviceOrg
from ..database import get_db
from ..utils.redis_helpers import get_job, set_job, del_job
from ..services import scan_service, merge_service
from .. import config

router = APIRouter()

"""
    
    # Extract all functions
    functions = []
    for func_name, method, route in spec["endpoints"]:
        func_text = extract_function_from_main(main_content, func_name, method, route)
        if func_text:
            functions.append(func_text)
            functions.append("\n\n")
    
    # Write file
    output_path = Path(spec["path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(imports)
        f.write('\n'.join(functions))
    
    print(f"✓ Created {output_path} with {len(spec['endpoints'])} endpoints")


def main():
    """Main extraction process."""
    print("Router Extraction Tool - v2.0.0 Refactoring")
    print("=" * 60)
    
    # Read main.py
    main_path = Path("backend/app/main.py")
    if not main_path.exists():
        print(f"ERROR: {main_path} not found")
        return
    
    with open(main_path, 'r', encoding='utf-8') as f:
        main_content = f.read()
    
    print(f"Loaded main.py ({len(main_content)} characters)")
    print()
    
    # Create each router
    for router_name, spec in ROUTERS.items():
        print(f"Creating {router_name}...")
        create_router_file(router_name, spec, main_content)
    
    print()
    print("=" * 60)
    print(f"✓ Successfully created {len(ROUTERS)} router modules")
    print("\nNext steps:")
    print("1. Review generated routers for correctness")
    print("2. Register routers in main.py with app.include_router()")
    print("3. Test endpoints via frontend")


if __name__ == "__main__":
    main()
