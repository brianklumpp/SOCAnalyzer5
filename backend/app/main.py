

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
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request, UploadFile, File, APIRouter
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from dataclasses import dataclass
from .models import ScanHistory, Company, Control, CUEC, SubserviceOrg, Product, Setting, Base
from .database import engine, get_db
from .analyze import analyze_pdf_file
from .config import REDIS_URL

@dataclass
class FieldMapping:
    json_field: str
    orm_field: str
    db_column: str

# Company mapping
COMPANY_FIELD_MAPPINGS = [
    FieldMapping("company", "name", "name"),
    FieldMapping("name", "name", "name"),
    FieldMapping("parent_company", "parent_company", "parent_company"),
    FieldMapping("confidence", "confidence", "confidence"),
]

# Control mapping
CONTROL_FIELD_MAPPINGS = [
    FieldMapping("control_id", "control_id", "control_id"),
    FieldMapping("control_desc", "control_desc", "control_desc"),
    FieldMapping("control_test", "control_test", "control_test"),
    FieldMapping("control_test_results", "control_test_results", "control_test_results"),
    FieldMapping("control_page_ref", "control_page_ref", "control_page_ref"),
    FieldMapping("control_line_ref", "control_line_ref", "control_line_ref"),
    FieldMapping("control_seq", "control_seq", "control_seq"),
    FieldMapping("control_tsc_id", "control_tsc_id", "control_tsc_id"),
    FieldMapping("control_coso_id", "control_coso_id", "control_coso_id"),
    FieldMapping("control_tsc_similarity", "control_tsc_similarity", "control_tsc_similarity"),
    FieldMapping("control_coso_similarity", "control_coso_similarity", "control_coso_similarity"),
    FieldMapping("control_tsc_confidence_pct", "control_tsc_confidence_pct", "control_tsc_confidence_pct"),
    FieldMapping("control_coso_confidence_pct", "control_coso_confidence_pct", "control_coso_confidence_pct"),
    FieldMapping("control_closest_framework", "control_closest_framework", "control_closest_framework"),
    FieldMapping("control_tsc_section", "control_tsc_section", "control_tsc_section"),
    FieldMapping("control_coso_section", "control_coso_section", "control_coso_section"),
    FieldMapping("control_soc_domain", "control_soc_domain", "control_soc_domain"),
    FieldMapping("control_status", "control_status", "control_status"),
    FieldMapping("merged_to_control_id", "merged_to_control_id", "merged_to_control_id"),
    FieldMapping("control_gpt_opinion", "control_gpt_opinion", "control_gpt_opinion"),
    FieldMapping("control_gpt_reasoning", "control_gpt_reasoning", "control_gpt_reasoning"),
]

# CUEC mapping
CUEC_FIELD_MAPPINGS = [
    FieldMapping("cuec_seq", "cuec_seq", "cuec_seq"),
    FieldMapping("cuec_id", "cuec_tsc_id", "cuec_tsc_id"),
    FieldMapping("cuec_tsc_id", "cuec_tsc_id", "cuec_tsc_id"),
    FieldMapping("cuec_description", "cuec_description", "cuec_description"),
    FieldMapping("cuec_desc", "cuec_description", "cuec_description"),
    FieldMapping("description", "cuec_description", "cuec_description"),
    FieldMapping("cuec_line_ref", "cuec_line_ref", "cuec_line_ref"),
    FieldMapping("cuec_confidence", "cuec_confidence", "cuec_confidence"),
    FieldMapping("cuec_gpt_opinion", "cuec_gpt_opinion", "cuec_gpt_opinion"),
    FieldMapping("cuec_distance_from_cuec_keywords", "cuec_distance_from_cuec_keywords", "cuec_distance_from_cuec_keywords"),
    FieldMapping("cuec_gpt_reasoning", "cuec_gpt_reasoning", "cuec_gpt_reasoning"),
    FieldMapping("cuec_framework_alignment", "cuec_framework_alignment", "cuec_framework_alignment"),
    FieldMapping("cuec_framework_alignment_id", "cuec_framework_alignment_id", "cuec_framework_alignment_id"),
    FieldMapping("cuec_justification", "cuec_justification", "cuec_justification"),
    FieldMapping("cuec_coso_id", "cuec_coso_id", "cuec_coso_id"),
    FieldMapping("cuec_tsc_similarity", "cuec_tsc_similarity", "cuec_tsc_similarity"),
    FieldMapping("cuec_coso_similarity", "cuec_coso_similarity", "cuec_coso_similarity"),
    FieldMapping("cuec_tsc_confidence_pct", "cuec_tsc_confidence_pct", "cuec_tsc_confidence_pct"),
    FieldMapping("cuec_coso_confidence_pct", "cuec_coso_confidence_pct", "cuec_coso_confidence_pct"),
    FieldMapping("cuec_closest_framework", "cuec_closest_framework", "cuec_closest_framework"),
    FieldMapping("cuec_confidence_justification", "cuec_confidence_justification", "cuec_confidence_justification"),
]

# SubserviceOrg mapping
SUBORG_FIELD_MAPPINGS = [
    FieldMapping("third_party_name", "name", "name"),
    FieldMapping("name", "name", "name"),
    FieldMapping("third_party_confidence", "confidence", "confidence"),
    FieldMapping("confidence", "confidence", "confidence"),
]

# Product mapping
PRODUCT_FIELD_MAPPINGS = [
    FieldMapping("product", "name", "name"),
    FieldMapping("name", "name", "name"),
]

# --- Mapping print/validation functions ---
def print_entity_mapping(entity_name, mappings, json_data, scan_id=None):
    msg_lines = [f"\n[{entity_name} Mapping]"]
    for mapping in mappings:
        value = json_data.get(mapping.json_field)
        msg_lines.append(f"JSON: {mapping.json_field} → ORM: {mapping.orm_field} → DB: {mapping.db_column} | Value: {value}")
    if scan_id is not None:
        msg_lines.append(f"scan_id → scan_id → scan_id | Value: {scan_id}")
    msg = "\n".join(msg_lines)
    print(msg)
    logging.error(msg)

def log_db_verification(entity_name, db_objs):
    if not db_objs:
        logging.error(f"[DB VERIFY] {entity_name}: No records found after insert.")
        print(f"[DB VERIFY] {entity_name}: No records found after insert.")
        return
    for obj in db_objs:
        fields = vars(obj)
        # Remove SQLAlchemy internal state
        fields = {k: v for k, v in fields.items() if not k.startswith('_')}
        msg = f"[DB VERIFY] {entity_name}: " + ", ".join(f"{k}={v}" for k, v in fields.items())
        logging.error(msg)
        print(msg)

def build_kwargs_from_mapping(mappings, json_data, scan_id=None):
    kwargs = {}
    for mapping in mappings:
        if mapping.orm_field not in kwargs:
            value = json_data.get(mapping.json_field)
            if value is not None:
                kwargs[mapping.orm_field] = value
    if scan_id is not None:
        kwargs["scan_id"] = scan_id
    return kwargs

app = FastAPI()

# Enable CORS for frontend (move this up to the first app instance)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# --- TEST: Insert combined_result.json into DB for fast iteration ---
test_router = APIRouter()

@test_router.post("/test/insert_combined_result")
async def test_insert_combined_result(db=Depends(get_db)):
    """
    Loads data/json/combined_result.json and inserts a ScanHistory and all related entities.
    Returns a summary of what was inserted.
    """
    # Load the combined result (always resolve from project root)
    project_root = pathlib.Path(__file__).resolve().parents[2]
    combined_path = project_root / "data" / "json" / "combined_result.json"
    with open(combined_path, "r", encoding="utf-8") as f:
        result = _json.load(f)

    # --- PATCH: Normalize all relevant entities for backend compatibility ---
    # Company normalization
    if "company" in result:
        if isinstance(result["company"], str):
            result["company"] = {"name": result["company"]}
        for key in ["parent_company", "confidence"]:
            if key in result:
                result["company"][key] = result[key]
                del result[key]

    # Product normalization
    if "product" in result:
        if isinstance(result["product"], str):
            result["product"] = {"name": result["product"]}
        for key in ["confidence"]:
            if key in result:
                if isinstance(result["product"], dict):
                    result["product"][key] = result[key]
                    del result[key]

    # Auditor normalization
    if "auditor" in result:
        if isinstance(result["auditor"], str):
            result["auditor"] = {"name": result["auditor"]}
        for key in ["confidence"]:
            if key in result:
                if isinstance(result["auditor"], dict):
                    result["auditor"][key] = result[key]
                    del result[key]

    # Subservice orgs/third_parties normalization
    if "subservice_orgs" in result and isinstance(result["subservice_orgs"], list):
        for idx, org in enumerate(result["subservice_orgs"]):
            if isinstance(org, str):
                result["subservice_orgs"][idx] = {"name": org}
            for key in ["confidence"]:
                if key in result and isinstance(result["subservice_orgs"][idx], dict):
                    result["subservice_orgs"][idx][key] = result[key]
        for key in ["confidence"]:
            if key in result:
                del result[key]

    # Insert Company first, get company_id
    from .models import Scan
    company_id = None
    company_obj = None
    company_info = result.get("company")
    if company_info:
        if isinstance(company_info, str):
            company_info = {"name": company_info}
        for key in ["parent_company", "confidence"]:
            if key in result and key not in company_info:
                company_info[key] = result[key]
        if company_info.get("company") or company_info.get("name"):
            print_entity_mapping("Company", COMPANY_FIELD_MAPPINGS, company_info)
            company_kwargs = build_kwargs_from_mapping(COMPANY_FIELD_MAPPINGS, company_info)
            company_kwargs["scan_id"] = None  # Will update after scan insert
            company_obj = Company(**company_kwargs)
            db.add(company_obj)
            await db.commit()
            await db.refresh(company_obj)
            company_id = company_obj.id
            # Post-insert verification
            from sqlalchemy.future import select as _select
            company_db = (await db.execute(_select(Company).where(Company.id == company_id))).scalars().all()
            log_db_verification("Company", company_db)

    # Insert ScanHistory
    scan_history = ScanHistory(
        timestamp=datetime.datetime.now(),
        filename="test_combined_result.json",
        results=result
    )
    db.add(scan_history)
    await db.commit()
    await db.refresh(scan_history)
    scan_history_id = scan_history.id
    from typing import Dict, Any
    summary: Dict[str, Any] = {"scan_id": scan_history_id}

    # Extract product name
    product = None
    product_info = result.get("product")
    if product_info and isinstance(product_info, dict):
        product = product_info.get("product") or product_info.get("name")

    # Extract report_date
    report_date = None
    report_date_info = result.get("report_date")
    if report_date_info:
        if isinstance(report_date_info, dict):
            report_date = report_date_info.get("report_date")
        elif isinstance(report_date_info, str):
            report_date = report_date_info
        if report_date:
            try:
                report_date = datetime.datetime.fromisoformat(report_date)
            except Exception:
                report_date = None

    # Extract coverage_start and coverage_end (robust to both top-level and nested)
    coverage_start = None
    coverage_end = None
    # Prefer top-level if present
    if "start_date" in result:
        coverage_start = result["start_date"]
    elif "coverage_period" in result and isinstance(result["coverage_period"], dict):
        coverage_start = result["coverage_period"].get("start_date")
    if "end_date" in result:
        coverage_end = result["end_date"]
    elif "coverage_period" in result and isinstance(result["coverage_period"], dict):
        coverage_end = result["coverage_period"].get("end_date")
    # Parse to datetime if present
    if coverage_start:
        try:
            coverage_start = datetime.datetime.fromisoformat(coverage_start)
        except Exception:
            coverage_start = None
    if coverage_end:
        try:
            coverage_end = datetime.datetime.fromisoformat(coverage_end)
        except Exception:
            coverage_end = None

    # Get extracted text (if available)
    extracted_text = None
    if "sections" in result and isinstance(result["sections"], list) and result["sections"]:
        extracted_text = result["sections"][0].get("snippet")

    # pdf_file: set to None or a placeholder for now
    pdf_file = None
    pdf_filename = scan_history.filename

    # gpt_cost, gpt_model, estimated_time_seconds
    gpt_cost = result.get("gpt_cost")
    gpt_model = result.get("gpt_model")
    estimated_time_seconds = result.get("estimated_time_seconds")

    # Insert Scan row with company_id, force id to match scan_history_id
    scan_row = Scan(
        id=scan_history_id,  # Force Scan.id to match ScanHistory.id
        company_id=company_id,
        product=product,
        scan_date=scan_history.timestamp,
        report_date=report_date,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        pdf_file=pdf_file,
        pdf_filename=pdf_filename,
        extracted_text=extracted_text,
        result_json=result,
        gpt_cost=gpt_cost,
        gpt_model=gpt_model,
        estimated_time_seconds=estimated_time_seconds
    )
    db.add(scan_row)
    await db.commit()
    await db.refresh(scan_row)
    scan_id = scan_row.id
    summary["scan_table_id"] = scan_id

    # Update company.scan_id to point to this scan (if company was inserted)
    if company_obj is not None and company_id is not None:
        company_obj.scan_id = scan_id
        db.add(company_obj)
        await db.commit()
    # --- Insert Company (centralized mapping) ---
    company_info = result.get("company")
    # PATCH: Accept both string and dict for company_info, and move top-level fields if present
    if company_info:
        if isinstance(company_info, str):
            company_info = {"name": company_info}
        # Move top-level parent_company/confidence into company_info if present
        for key in ["parent_company", "confidence"]:
            if key in result and key not in company_info:
                company_info[key] = result[key]
        if company_info.get("company") or company_info.get("name"):
            print_entity_mapping("Company", COMPANY_FIELD_MAPPINGS, company_info, scan_id)
            company_kwargs = build_kwargs_from_mapping(COMPANY_FIELD_MAPPINGS, company_info, scan_id)
            db.add(Company(**company_kwargs))
            await db.commit()
            # Post-insert verification
            from sqlalchemy.future import select as _select
            company_db = (await db.execute(_select(Company).where(Company.scan_id == scan_id))).scalars().all()
            log_db_verification("Company", company_db)
            # Only assign if not None, to avoid type errors in summary dict
            company_name = company_kwargs.get("name")
            if company_name is not None:
                summary["company"] = str(company_name)

    # --- Insert Controls ---
    # Support both legacy and nested formats
    controls = []
    if "control_extraction" in result and "controls" in result["control_extraction"]:
        controls = result["control_extraction"]["controls"]
    elif "controls" in result:
        controls_section = result.get("controls", {})
        if isinstance(controls_section, dict):
            controls = controls_section.get("controls", [])
        elif isinstance(controls_section, list):
            controls = controls_section
    # Filter out controls that do not have a control_seq (only keep those with a non-null control_seq)
    controls = [
        c for c in controls
        if isinstance(c, dict) and c.get("control_seq") is not None
    ]
    for ctrl in controls:
        print_entity_mapping("Control", CONTROL_FIELD_MAPPINGS, ctrl, scan_id)
        control_kwargs = build_kwargs_from_mapping(CONTROL_FIELD_MAPPINGS, ctrl, scan_id)
        db.add(Control(**control_kwargs))
    if controls:
        await db.commit()
        from sqlalchemy.future import select as _select
        controls_db = (await db.execute(_select(Control).where(Control.scan_id == scan_id))).scalars().all()
        log_db_verification("Control", controls_db)
    summary["controls_count"] = int(len(controls))  # type: ignore

    # --- Insert CUECs ---
    # Support both legacy and nested formats
    cuecs = []
    if "cuec_extraction" in result and "cuecs" in result["cuec_extraction"]:
        cuecs = result["cuec_extraction"]["cuecs"]
    elif "cuecs" in result:
        cuecs_section = result.get("cuecs", {})
        if isinstance(cuecs_section, dict):
            cuecs = cuecs_section.get("cuecs", [])
        elif isinstance(cuecs_section, list):
            cuecs = cuecs_section
    for cuec in cuecs:
        print_entity_mapping("CUEC", CUEC_FIELD_MAPPINGS, cuec, scan_id)
        cuec_kwargs = build_kwargs_from_mapping(CUEC_FIELD_MAPPINGS, cuec, scan_id)
        # Patch: Ensure cuec_confidence_justification is always a string
        if "cuec_confidence_justification" in cuec_kwargs and isinstance(cuec_kwargs["cuec_confidence_justification"], list):
            cuec_kwargs["cuec_confidence_justification"] = _json.dumps(cuec_kwargs["cuec_confidence_justification"])
        db.add(CUEC(**cuec_kwargs))
    if cuecs:
        await db.commit()
        from sqlalchemy.future import select as _select
        cuecs_db = (await db.execute(_select(CUEC).where(CUEC.scan_id == scan_id))).scalars().all()
        log_db_verification("CUEC", cuecs_db)
    summary["cuecs_count"] = int(len(cuecs))  # type: ignore

    # --- Insert Subservice Orgs ---
    # Support legacy, nested, and flattened formats
    suborgs = []
    if "subservice_orgs_extraction" in result and "subservice_orgs" in result["subservice_orgs_extraction"]:
        suborgs = result["subservice_orgs_extraction"]["subservice_orgs"]
    elif "subservice_orgs" in result:
        suborgs_section = result.get("subservice_orgs", {})
        if isinstance(suborgs_section, dict):
            suborgs = suborgs_section.get("third_parties", [])
        elif isinstance(suborgs_section, list):
            suborgs = suborgs_section
    elif "third_parties" in result and isinstance(result["third_parties"], list):
        suborgs = result["third_parties"]
    for org in suborgs:
        org_data = org if isinstance(org, dict) else {"name": org}
        print_entity_mapping("SubserviceOrg", SUBORG_FIELD_MAPPINGS, org_data, scan_id)
        suborg_kwargs = build_kwargs_from_mapping(SUBORG_FIELD_MAPPINGS, org_data, scan_id)
        db.add(SubserviceOrg(**suborg_kwargs))
    if suborgs:
        await db.commit()
        from sqlalchemy.future import select as _select
        suborgs_db = (await db.execute(_select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id))).scalars().all()
        log_db_verification("SubserviceOrg", suborgs_db)
    summary["subservice_orgs_count"] = int(len(suborgs))

    # --- Insert Product ---
    product_info = result.get("product")
    if product_info and isinstance(product_info, dict):
        print_entity_mapping("Product", PRODUCT_FIELD_MAPPINGS, product_info, scan_id)
        product_kwargs = build_kwargs_from_mapping(PRODUCT_FIELD_MAPPINGS, product_info, scan_id)
        db.add(Product(**product_kwargs))
        await db.commit()
        from sqlalchemy.future import select as _select
        product_db = (await db.execute(_select(Product).where(Product.scan_id == scan_id))).scalars().all()
        log_db_verification("Product", product_db)
        product_name = product_kwargs.get("name")
        if product_name is not None:
            summary["product"] = str(product_name)

    await db.commit()
    return summary

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
            {"name": org.name, "confidence": getattr(org, "confidence", None)} for org in suborgs
        ],
        "cuecs": [
            {
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
            } for c in cuecs
        ],
        "controls": [
            {k: getattr(ctrl, k, None) for k in [
                "control_id",
                "control_desc",
                "control_test",
                "control_test_results",
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
                "control_gpt_reasoning"
            ]} for ctrl in controls
        ],
        "bad_chunks": bad_chunks,
        "raw_results": results
    }


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
from .models import ScanHistory, Setting, Base
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

    # Always try to persist result to DB if not already saved, even for partial/warning/error results
    if not job.get("db_saved") and job.get("result"):
        try:
            import sqlalchemy, datetime
            import logging
            from app.models import ScanHistory, Company, Control, CUEC, SubserviceOrg, Product
            result = job.get("result")
            # Insert ScanHistory
            # Insert ScanHistory (for record, not for scan_id foreign key)
            scan_history = ScanHistory(
                timestamp=datetime.datetime.now(),
                filename=job.get("filename"),
                results=result
            )
            db.add(scan_history)
            await db.commit()
            await db.refresh(scan_history)
            scan_history_id = scan_history.id

            # Insert Scan (get scan_id for all child entities)
            from app.models import Scan
            product = None
            product_info = result.get("product")
            if product_info and isinstance(product_info, dict):
                product = product_info.get("product") or product_info.get("name")
            scan_row = Scan(
                id=scan_history_id,  # Force Scan.id to match ScanHistory.id
                company_id=None,
                product=product,
                scan_date=scan_history.timestamp,
                report_date=None,
                coverage_start=None,
                coverage_end=None,
                pdf_file=None,
                pdf_filename=scan_history.filename,
                extracted_text=None,
                result_json=result,
                gpt_cost=result.get("gpt_cost"),
                gpt_model=result.get("gpt_model"),
                estimated_time_seconds=result.get("estimated_time_seconds")
            )
            db.add(scan_row)
            await db.commit()
            await db.refresh(scan_row)
            scan_id = scan_row.id
            logging.error(f"[DB] Inserted Scan id={scan_id}")

            # --- Insert Company ---
            company_info = result.get("company")
            if company_info and (company_info.get("company") or company_info.get("name")):
                db.add(Company(
                    name=company_info.get("company") or company_info.get("name"),
                    parent_company=company_info.get("parent_company"),
                    scan_id=scan_id
                ))
                logging.error(f"[DB] Inserted Company for scan_id={scan_id}")

            # --- Insert Controls ---
            controls_section = result.get("controls", {})
            logging.error(f"[DB] controls_section: {controls_section}")
            controls = []
            if isinstance(controls_section, dict):
                controls = controls_section.get("controls", [])
            elif isinstance(controls_section, list):
                controls = controls_section
            for ctrl in controls:
                db.add(Control(
                    control_id=ctrl.get("control_id"),
                    control_desc=ctrl.get("control_desc") or ctrl.get("description"),
                    control_test=ctrl.get("control_test"),
                    control_test_results=ctrl.get("control_test_results"),
                    control_page_ref=ctrl.get("control_page_ref"),
                    control_line_ref=ctrl.get("control_line_ref"),
                    control_seq=ctrl.get("control_seq"),
                    control_tsc_id=ctrl.get("control_tsc_id"),
                    control_coso_id=ctrl.get("control_coso_id"),
                    control_tsc_similarity=ctrl.get("control_tsc_similarity"),
                    control_coso_similarity=ctrl.get("control_coso_similarity"),
                    control_tsc_confidence_pct=ctrl.get("control_tsc_confidence_pct"),
                    control_coso_confidence_pct=ctrl.get("control_coso_confidence_pct"),
                    control_closest_framework=ctrl.get("control_closest_framework"),
                    control_tsc_section=ctrl.get("control_tsc_section"),
                    control_coso_section=ctrl.get("control_coso_section"),
                    control_soc_domain=ctrl.get("control_soc_domain"),
                    control_status=ctrl.get("control_status"),
                    merged_to_control_id=ctrl.get("merged_to_control_id"),
                    control_gpt_opinion=ctrl.get("control_gpt_opinion"),
                    control_gpt_reasoning=ctrl.get("control_gpt_reasoning"),
                    scan_id=scan_id
                ))
            if controls:
                logging.error(f"[DB] Inserted {len(controls)} Controls for scan_id={scan_id}")

            # --- Insert CUECs ---
            cuecs_section = result.get("cuecs", {})
            logging.error(f"[DB] cuecs_section: {cuecs_section}")
            cuecs = []
            if isinstance(cuecs_section, dict):
                cuecs = cuecs_section.get("cuecs", [])
            elif isinstance(cuecs_section, list):
                cuecs = cuecs_section
            for cuec in cuecs:
                db.add(CUEC(
                    cuec_id=cuec.get("cuec_id"),
                    description=cuec.get("cuec_desc") or cuec.get("description"),
                    scan_id=scan_id
                ))
            if cuecs:
                logging.error(f"[DB] Inserted {len(cuecs)} CUECs for scan_id={scan_id}")

            # --- Insert Subservice Orgs ---
            suborgs_section = result.get("subservice_orgs", {})
            logging.error(f"[DB] suborgs_section: {suborgs_section}")
            suborgs = []
            # subservice_orgs may be a dict with 'third_parties' or a list
            if isinstance(suborgs_section, dict):
                suborgs = suborgs_section.get("third_parties", [])
            elif isinstance(suborgs_section, list):
                suborgs = suborgs_section
            for org in suborgs:
                db.add(SubserviceOrg(
                    name=org.get("third_party_name") if isinstance(org, dict) else org,
                    scan_id=scan_id
                ))
            if suborgs:
                logging.error(f"[DB] Inserted {len(suborgs)} SubserviceOrgs for scan_id={scan_id}")

            # --- Insert Product ---
            if product_info and isinstance(product_info, dict):
                db.add(Product(
                    name=product_info.get("product") or product_info.get("name"),
                    scan_id=scan_id
                ))
                logging.error(f"[DB] Inserted Product for scan_id={scan_id}")
            await db.commit()
            job["db_saved"] = True
            await set_job(job_id, job)
            logging.error(f"[DB] All entities committed for scan_id={scan_id}")
        except Exception as db_exc:
            import logging
            logging.error(f"DB error persisting job result: {db_exc}\nTraceback: {traceback.format_exc()}")

    # If there was an error, return it along with any partial result
    if job.get("error"):
        return {"error": job.get("error"), "partial_result": job.get("result")}
    return {"results": job.get("result")}
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Optional
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request, Depends, UploadFile, File
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from .models import ScanHistory, Setting, Base
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
if __name__ == "__main__" and sys.argv[0].endswith("main.py") and sys.argv[-1] != "test_insert_combined_result":
    asyncio.get_event_loop().run_until_complete(init_models())
