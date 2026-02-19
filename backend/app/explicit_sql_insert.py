# Remove all top-level code except function and __main__ block
# Only define insert_extracted_data and (optionally) __main__

import json
import psycopg2
import psycopg2.extras
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
import logging
import traceback
from . import config
from .logo_service import fetch_logo_with_gpt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# --- Helpers for safe DB coercion ---
def _extract_name(val, keys=("name", "product", "auditor", "company")):
    """Return a human-readable name from a string or dict; fallback to str(val)."""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, dict):
        for k in keys:
            v = val.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None

def _parse_datetime(val):
    """Best-effort parsing for various date shapes; returns datetime or None.

    Accepts:
    - None/empty -> None
    - dict -> try common keys (value, date, iso, report_date)
    - str -> try common formats, else return None
    """
    if not val:
        return None
    # If dict, try to pull a likely date string
    if isinstance(val, dict):
        for k in ("value", "date", "iso", "report_date", "start_date", "end_date"):
            if k in val and isinstance(val[k], str) and val[k].strip():
                val = val[k].strip()
                break
        else:
            # Empty/unsupported dict
            return None
    if isinstance(val, str):
        s = val.strip()
        if not s or s == "{}":
            return None
        # Try a handful of common formats before giving up
        fmts = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%B %d, %Y",   # October 31, 2023
            "%b %d, %Y",    # Oct 31, 2023
            "%d %B %Y",     # 31 October 2023
            "%d %b %Y",     # 31 Oct 2023
        ]
        for fmt in fmts:
            try:
                dt = datetime.strptime(s, fmt)
                # If parsing a date-only string (no time component), set time to noon UTC
                # to avoid timezone conversion issues that can shift dates by +/- 1 day
                if fmt in ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"]:
                    dt = dt.replace(hour=12, minute=0, second=0, microsecond=0)
                return dt
            except Exception:
                pass
        # Last resort: ISO-ish variations (allow seconds, Z suffix)
        try:
            # Handles strings like 2023-10-31T00:00:00 or 2023-10-31 00:00:00
            s_iso = s.replace("T", " ").rstrip("Z")
            dt = datetime.fromisoformat(s_iso)
            # If no time component was specified (ends at 00:00:00), set to noon
            if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
                dt = dt.replace(hour=12)
            return dt
        except Exception:
            return None
    # Already a datetime?
    if isinstance(val, datetime):
        return val
    return None

def insert_extracted_data(json_path: str, pdf_path: str = None, job_id: str = None, user_id: int = None, start_time: float = None):
    # Validate required parameters for job isolation
    if not job_id or not user_id:
        raise ValueError("[DB_INSERT] job_id and user_id are required for job isolation")
    
    # Get job-specific paths
    job_paths = config.get_job_paths(user_id, job_id)
    combined_json_path = job_paths['json_dir'] / 'combined_result.json'
    
    if not combined_json_path.exists():
        logging.error(f"[JOB {job_id}] Combined JSON not found at {combined_json_path}")
        raise FileNotFoundError(f"Combined result not found for job {job_id}")
    
    logging.info(f"[JOB {job_id}] Reading from isolated path: {combined_json_path}")
    
    # Override json_path to use job-specific path
    json_path = str(combined_json_path)
    
    # Load environment variables from .env
    load_dotenv()
    
    # Create Redis client for phase_completion updates if job_id provided
    redis_client = None
    if job_id:
        try:
            import redis
            redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                db=int(os.getenv('REDIS_DB', 0)),
                decode_responses=True
            )
        except Exception as redis_err:
            logging.warning(f"[JOB {job_id}] Could not create Redis client for job state updates: {redis_err}")
    DATABASE_URL = os.getenv("DATABASE_URL_SYNC")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL_SYNC environment variable is not set. Please set it in your .env file.")
    LOG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/logs/sql_insert.log'))
    logging.basicConfig(
        filename=LOG_PATH,
        filemode='w',
        format='%(asctime)s %(levelname)s: %(message)s',
        level=logging.INFO
    )
    def deep_sanitize(obj):
        """Recursively sanitize nested structures to handle bytes."""
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        elif isinstance(obj, dict):
            return {k: deep_sanitize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [deep_sanitize(item) for item in obj]
        elif isinstance(obj, bool):
            return obj
        elif obj is None:
            return None
        return obj
    
    def sanitize_value(val):
        if isinstance(val, bytes):
            return val.decode('utf-8', errors='replace')
        if isinstance(val, (list, dict)):
            sanitized = deep_sanitize(val)
            return json.dumps(sanitized, ensure_ascii=False)
        if isinstance(val, bool):
            return str(val)
        if val is None:
            return None
        return val
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    try:
        cur.execute("SELECT setval('scan_id_seq', (SELECT COALESCE(MAX(id), 1) FROM scan));")
        conn.commit()
        logging.info("Reset scan_id_seq to max(id) in scan table.")
    except Exception as e:
        logging.error(f"Failed to reset scan_id_seq: {e}")
        conn.rollback()
        cur.close()
        conn.close()
        raise
    summary = {"company": 0, "control": 0, "cuec": 0, "product": 0, "subservice_org": 0, "errors": []}
    try:
        # Insert a new scan row and get scan_id
        # Handle both nested coverage_period dict and top-level start_date/end_date
        coverage_period = data.get("coverage_period")
        start_date = None
        end_date = None
        if isinstance(coverage_period, dict):
            start_date = _parse_datetime(coverage_period.get("start_date"))
            end_date = _parse_datetime(coverage_period.get("end_date"))
        else:
            # Try top-level fields
            start_date = _parse_datetime(data.get("start_date"))
            end_date = _parse_datetime(data.get("end_date"))
        # Report date normalization
        report_date_norm = _parse_datetime(data.get("report_date"))
        # Product and auditor names normalized to plain strings
        product_name = _extract_name(data.get("product"), keys=("name", "product"))
        auditor_name = _extract_name(data.get("auditor"), keys=("name", "auditor", "firm"))
        
        # Read PDF file if path provided
        pdf_filename = data.get("pdf_filename")
        pdf_bytes = None
        if pdf_path and os.path.isfile(pdf_path):
            try:
                with open(pdf_path, 'rb') as f:
                    pdf_bytes = f.read()
                if not pdf_filename:
                    pdf_filename = os.path.basename(pdf_path)
                logging.info(f"Read PDF file: {pdf_filename} ({len(pdf_bytes)} bytes)")
            except Exception as e:
                logging.error(f"Failed to read PDF file {pdf_path}: {e}")
        
        scan_fields = [
            "product", "report_date", "coverage_start", "coverage_end", "auditor", "result_json", "scan_date",
            "gpt_cost", "gpt_model", "estimated_time_seconds", "gpt_usage_details", "extracted_text", "pdf_filename", "pdf_file", "company_id", "report_type", "toc_page_offset", "detected_standards", "user_id", "company", "active_frameworks", "elapsed_seconds"
        ]
        # Filter out pdf_file bytes from data before JSON serialization
        data_for_json = {k: v for k, v in data.items() if k != 'pdf_file'}
        # Deep sanitize to handle nested bytes objects
        data_for_json = deep_sanitize(data_for_json)
        
        # Get report_type from data (detected during analysis), default to SOC2 if not present
        report_type = sanitize_value(data.get("report_type", "SOC2"))
        logging.info(f"Inserting scan with report_type: {report_type}")
        
        # Get detected_standards from data and convert to JSON array for JSONB column
        detected_standards = data.get("detected_standards", [])
        detected_standards_json = json.dumps(detected_standards, ensure_ascii=False) if detected_standards else None
        logging.info(f"Detected standards for scan: {detected_standards}")
        
        # Get company name from nested structure
        company_data = data.get("company")
        company_name = None
        if company_data:
            if isinstance(company_data, str):
                company_name = company_data
            elif isinstance(company_data, dict):
                company_name = company_data.get("company") or company_data.get("name")
        
        # Get active_frameworks from data
        active_frameworks = data.get("active_frameworks", [])
        active_frameworks_json = json.dumps(active_frameworks, ensure_ascii=False) if active_frameworks else None
        
        # Use start_time if provided, otherwise fall back to current time
        # Convert start_time (Unix timestamp) to datetime for scan_date
        if start_time is not None:
            scan_date_value = datetime.fromtimestamp(start_time, tz=timezone.utc)
            logging.info(f"[SCAN_DATE] Using scan start_time: {scan_date_value} (start_time={start_time})")
        else:
            scan_date_value = datetime.utcnow()
            logging.warning(f"[SCAN_DATE] start_time not provided, falling back to utcnow: {scan_date_value}")
        
        scan_values = [
            sanitize_value(product_name),
            report_date_norm,
            start_date,
            end_date,
            sanitize_value(auditor_name),
            json.dumps(data_for_json, ensure_ascii=False),
            scan_date_value,
            sanitize_value(data.get("gpt_cost")),
            sanitize_value(data.get("gpt_model")),
            sanitize_value(data.get("estimated_time_seconds")),
            sanitize_value(data.get("gpt_usage_details")),
            sanitize_value(data.get("extracted_text")),
            pdf_filename,
            pdf_bytes,  # Pass bytes directly, psycopg2 handles BYTEA
            sanitize_value(data.get("company_id")),
            report_type,
            sanitize_value(data.get("toc_page_offset")),  # Store TOC page offset for PDF navigation
            detected_standards_json,  # Store detected standards as JSONB
            user_id,  # User who initiated the scan
            sanitize_value(company_name),  # Company name string
            active_frameworks_json,  # Active frameworks JSONB
            sanitize_value(data.get("elapsed_seconds")),  # Store elapsed time from analysis
        ]
        scan_sql = f"INSERT INTO scan ({', '.join(scan_fields)}) VALUES ({', '.join(['%s']*len(scan_fields))}) RETURNING id"
        logging.info(f"SQL: {scan_sql} | Values: {scan_values}")
        cur.execute(scan_sql, scan_values)
        scan_id = cur.fetchone()[0]
        logging.info(f"Inserted new scan row with scan_id: {scan_id}")
        summary["scan_id"] = scan_id
        # Insert company and update scan with company_id
        company = data.get("company")
        company_id = None
        if company:
            try:
                cur.execute("SAVEPOINT company_insert")
                name = company if isinstance(company, str) else company.get("company") or company.get("name")
                parent_company = company.get("parent_company") if isinstance(company, dict) else None
                confidence = company.get("confidence") if isinstance(company, dict) else None
                company_domain = company.get("company_domain") if isinstance(company, dict) else None
                # Don't fetch logo here - will be fetched at the very end after all extractions complete
                logo_url = None
                
                values = [sanitize_value(name), sanitize_value(parent_company), sanitize_value(confidence), scan_id, sanitize_value(company_domain), sanitize_value(logo_url)]
                fields = config.TABLE_FIELD_MAP["company"]
                sql = f"INSERT INTO company ({', '.join(fields)}) VALUES ({', '.join(['%s']*len(fields))}) ON CONFLICT DO NOTHING RETURNING id"
                logging.info(f"SQL: {sql} | Values: {values}")
                cur.execute(sql, values)
                result = cur.fetchone()
                if result:
                    company_id = result[0]
                    # Update scan record with company_id
                    cur.execute("UPDATE scan SET company_id = %s WHERE id = %s", (company_id, scan_id))
                    logging.info(f"Updated scan {scan_id} with company_id {company_id}")
                cur.execute("RELEASE SAVEPOINT company_insert")
                summary["company"] += 1
                logging.info(f"Inserted into company: {values}")
            except Exception as e:
                summary["errors"].append(f"Company insert error: {e}")
                logging.error(f"Company insert error: {e}")
                cur.execute("ROLLBACK TO SAVEPOINT company_insert")
        # Insert controls
        controls = data.get("controls")
        if controls:
            # ── Pre-insert deduplication ──────────────────────────────────
            # Multiple chunks may extract the same control independently.
            # Deduplicate by control_id (string) before inserting.  For
            # controls that share the same control_id, keep the one with
            # the highest confidence and merge key text fields.
            seen_ctrl: dict = {}  # control_id_str -> best control dict
            deduped_controls: list = []
            for ctrl in controls:
                cid = (ctrl.get("control_id") or "").strip()
                if not cid:
                    # Controls without an ID can't be deduped — keep all
                    deduped_controls.append(ctrl)
                    continue
                if cid not in seen_ctrl:
                    seen_ctrl[cid] = ctrl
                else:
                    existing = seen_ctrl[cid]
                    # Keep higher confidence, merge description/test if needed
                    existing_conf = existing.get("control_confidence") or 0
                    new_conf = ctrl.get("control_confidence") or 0
                    if new_conf > existing_conf:
                        # New one wins, but merge text from old
                        for field in ("control_desc", "control_test", "control_test_results", "deviation_desc"):
                            old_text = (existing.get(field) or "").strip()
                            new_text = (ctrl.get(field) or "").strip()
                            if old_text and not new_text:
                                ctrl[field] = old_text
                            elif old_text and new_text and old_text not in new_text:
                                ctrl[field] = new_text + " " + old_text
                        # Merge page refs
                        old_pages = existing.get("control_page_refs") or []
                        new_pages = ctrl.get("control_page_refs") or []
                        if isinstance(old_pages, list) and isinstance(new_pages, list):
                            ctrl["control_page_refs"] = sorted(set(old_pages + new_pages))
                        # Carry over deviation flag
                        if existing.get("has_deviation"):
                            ctrl["has_deviation"] = True
                            if not ctrl.get("deviation_desc"):
                                ctrl["deviation_desc"] = existing.get("deviation_desc")
                        seen_ctrl[cid] = ctrl
                    else:
                        # Existing wins, but capture any missing text from new
                        for field in ("control_desc", "control_test", "control_test_results", "deviation_desc"):
                            old_text = (existing.get(field) or "").strip()
                            new_text = (ctrl.get(field) or "").strip()
                            if new_text and not old_text:
                                existing[field] = new_text
                        old_pages = existing.get("control_page_refs") or []
                        new_pages = ctrl.get("control_page_refs") or []
                        if isinstance(old_pages, list) and isinstance(new_pages, list):
                            existing["control_page_refs"] = sorted(set(old_pages + new_pages))
                        if ctrl.get("has_deviation"):
                            existing["has_deviation"] = True
                            if not existing.get("deviation_desc"):
                                existing["deviation_desc"] = ctrl.get("deviation_desc")
            deduped_controls.extend(seen_ctrl.values())
            dup_count = len(controls) - len(deduped_controls)
            if dup_count > 0:
                logging.info(f"[DEDUP] Pre-insert deduplication: {len(controls)} -> {len(deduped_controls)} controls ({dup_count} duplicates merged)")
            # ── End deduplication ─────────────────────────────────────────
            
            for idx, ctrl in enumerate(deduped_controls):
                try:
                    cur.execute("SAVEPOINT control_insert")
                    # Backward-compatible mapping for new fields
                    if 'has_deviation' not in ctrl:
                        ctrl['has_deviation'] = False
                    if 'deviation_desc' not in ctrl:
                        ctrl['deviation_desc'] = None
                    
                    # Map JSON fields to database fields
                    if 'control_gpt_conf_justification' in ctrl and 'confidence_calc' not in ctrl:
                        ctrl['confidence_calc'] = ctrl['control_gpt_conf_justification']
                    
                    # Set control_seq if not present (use enumeration index)
                    if 'control_seq' not in ctrl:
                        ctrl['control_seq'] = idx + 1
                    
                    # Ignore obsolete fields - do NOT populate from control_tsc_mappings, control_coso_mappings, control_soc_domain
                    # Only use current framework_mappings, primary_framework, primary_criterion_id, primary_confidence if present
                    
                    values = [sanitize_value(ctrl.get(f)) for f in config.TABLE_FIELD_MAP["control"][:-1]] + [scan_id]
                    fields = config.TABLE_FIELD_MAP["control"]
                    sql = f"INSERT INTO control ({', '.join(fields)}) VALUES ({', '.join(['%s']*len(fields))})"
                    logging.info(f"SQL: {sql} | Values: {values}")
                    cur.execute(sql, values)
                    cur.execute("RELEASE SAVEPOINT control_insert")
                    summary["control"] += 1
                    logging.info(f"Inserted into control: {values}")
                except Exception as e:
                    summary["errors"].append(f"Control insert error: {e}")
                    logging.error(f"Control insert error: {e}")
                    cur.execute("ROLLBACK TO SAVEPOINT control_insert")
        # Insert cuecs
        cuecs = data.get("cuecs")
        if cuecs:
            for cuec in cuecs:
                try:
                    cur.execute("SAVEPOINT cuec_insert")
                    values = [sanitize_value(cuec.get(f)) for f in config.TABLE_FIELD_MAP["cuec"][:-1]] + [scan_id]
                    fields = config.TABLE_FIELD_MAP["cuec"]
                    sql = f"INSERT INTO cuec ({', '.join(fields)}) VALUES ({', '.join(['%s']*len(fields))})"
                    logging.info(f"SQL: {sql} | Values: {values}")
                    cur.execute(sql, values)
                    cur.execute("RELEASE SAVEPOINT cuec_insert")
                    summary["cuec"] += 1
                    logging.info(f"Inserted into cuec: {values}")
                except Exception as e:
                    summary["errors"].append(f"CUEC insert error: {e}")
                    logging.error(f"CUEC insert error: {e}")
                    cur.execute("ROLLBACK TO SAVEPOINT cuborg_insert")
        # Insert subservice orgs
        suborgs_wrapper = data.get("subservice_orgs")
        # Handle nested structure: {"subservice_orgs": {"subservice_orgs": [...]}}
        if suborgs_wrapper:
            if isinstance(suborgs_wrapper, dict) and "subservice_orgs" in suborgs_wrapper:
                suborgs = suborgs_wrapper.get("subservice_orgs", [])
            elif isinstance(suborgs_wrapper, list):
                suborgs = suborgs_wrapper
            else:
                suborgs = []
            for org in suborgs:
                try:
                    cur.execute("SAVEPOINT suborg_insert")
                    name = org.get("third_party_name") if isinstance(org, dict) else org
                    confidence = org.get("third_party_confidence") if isinstance(org, dict) else None
                    third_party_description = org.get("third_party_description") if isinstance(org, dict) else None
                    third_party_page_ref = org.get("third_party_page_ref") if isinstance(org, dict) else None
                    third_party_confidence = org.get("third_party_confidence") if isinstance(org, dict) else None
                    distance_from_so_keywords = org.get("distance_from_so_keywords") if isinstance(org, dict) else None
                    likely_so = org.get("likely_so") if isinstance(org, dict) else None
                    common_so = org.get("common_so") if isinstance(org, dict) else None
                    source_context = org.get("source_context") if isinstance(org, dict) else None
                    confidence_justification = org.get("confidence_justification") if isinstance(org, dict) else None
                    third_party_controls = org.get("third_party_controls") if isinstance(org, dict) else None
                    values = [
                        sanitize_value(name),
                        sanitize_value(confidence),
                        scan_id,
                        sanitize_value(third_party_description),
                        sanitize_value(third_party_page_ref),
                        sanitize_value(third_party_confidence),
                        sanitize_value(distance_from_so_keywords),
                        sanitize_value(likely_so),
                        sanitize_value(common_so),
                        sanitize_value(source_context),
                        sanitize_value(confidence_justification),
                        json.dumps(third_party_controls, ensure_ascii=False) if third_party_controls is not None else None
                    ]
                    fields = [
                        "name", "confidence", "scan_id", "third_party_description", "third_party_page_ref", "third_party_confidence",
                        "distance_from_so_keywords", "likely_so", "common_so", "source_context", "confidence_justification", "third_party_controls"
                    ]
                    sql = f"INSERT INTO subservice_org ({', '.join(fields)}) VALUES ({', '.join(['%s']*len(fields))}) ON CONFLICT DO NOTHING"
                    logging.info(f"SQL: {sql} | Values: {values}")
                    cur.execute(sql, values)
                    cur.execute("RELEASE SAVEPOINT suborg_insert")
                    summary["subservice_org"] += 1
                    logging.info(f"Inserted into subservice_org: {values}")
                except Exception as e:
                    summary["errors"].append(f"SubserviceOrg insert error: {e}")
                    logging.error(f"SubserviceOrg insert error: {e}")
                    cur.execute("ROLLBACK TO SAVEPOINT suborg_insert")
        # Insert product
        product = data.get("product")
        if product:
            try:
                cur.execute("SAVEPOINT product_insert")
                name = product if isinstance(product, str) else product.get("product") or product.get("name")
                values = [sanitize_value(name), scan_id]
                fields = config.TABLE_FIELD_MAP["product"]
                sql = f"INSERT INTO product ({', '.join(fields)}) VALUES ({', '.join(['%s']*len(fields))}) ON CONFLICT DO NOTHING"
                logging.info(f"SQL: {sql} | Values: {values}")
                cur.execute(sql, values)
                cur.execute("RELEASE SAVEPOINT product_insert")
                summary["product"] += 1
                logging.info(f"Inserted into product: {values}")
            except Exception as e:
                summary["errors"].append(f"Product insert error: {e}")
                logging.error(f"Product insert error: {e}")
                cur.execute("ROLLBACK TO SAVEPOINT product_insert")
        print("DEBUG: About to commit transaction...")
        logging.info("About to commit transaction...")
        try:
            conn.commit()
            print("DEBUG: Transaction committed successfully!")
            logging.info("Transaction committed successfully!")
            
            # Fetch logos for companies after successful commit
            try:
                logging.info(f"[LOGO_SERVICE] Starting logo fetching for scan_id={scan_id}")
                # Convert async DATABASE_URL to sync by replacing postgresql+asyncpg with postgresql
                sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
                logging.info(f"[LOGO_SERVICE] Creating sync engine with URL: {sync_db_url[:50]}...")
                sync_engine = create_engine(sync_db_url, echo=False)
                SessionLocal = sessionmaker(bind=sync_engine)
                
                with SessionLocal() as db_session:
                    # Query companies from this scan that have domains but no logos yet
                    query = "SELECT id, company_domain FROM company WHERE scan_id = %s AND company_domain IS NOT NULL AND (logo_url IS NULL OR logo_url = '')"
                    logging.info(f"[LOGO_SERVICE] Executing query: {query} with scan_id={scan_id}")
                    cur.execute(query, (scan_id,))
                    companies_needing_logos = cur.fetchall()
                    logging.info(f"[LOGO_SERVICE] Query returned {len(companies_needing_logos) if companies_needing_logos else 0} companies")
                    
                    if companies_needing_logos:
                        logging.info(f"[LOGO_SERVICE] Found {len(companies_needing_logos)} companies needing logos")
                        for company_id, domain in companies_needing_logos:
                            try:
                                # Get company name for GPT prompt
                                cur.execute("SELECT name FROM company WHERE id = %s", (company_id,))
                                company_name_row = cur.fetchone()
                                company_name = company_name_row[0] if company_name_row else "Unknown"
                                
                                # Try GPT-based logo fetching
                                success, logo_url = fetch_logo_with_gpt(company_id, company_name, domain, db_session)
                                if success:
                                    logging.info(f"[LOGO_SERVICE] ✓ Cached logo (GPT): {company_name} ({domain}): {logo_url}")
                                    summary["logos_fetched"] = summary.get("logos_fetched", 0) + 1
                                    
                                    # Also update scan.company field with the company name
                                    try:
                                        cur.execute("UPDATE scan SET company = %s WHERE id = %s", (company_name, scan_id))
                                        conn.commit()
                                        logging.info(f"[LOGO_SERVICE] Updated scan.company field: {company_name}")
                                    except Exception as update_err:
                                        logging.error(f"[LOGO_SERVICE] Failed to update scan.company: {update_err}")
                                else:
                                    logging.warning(f"[LOGO_SERVICE] ✗ No logo (GPT): {company_name} ({domain})")
                            except Exception as logo_error:
                                logging.error(f"[LOGO_SERVICE] Error for company {company_id}: {logo_error}")
                    else:
                        logging.info(f"[LOGO_SERVICE] No companies needing logos for scan {scan_id}")
                    
                    db_session.commit()
                    
                    # Update logo_fetched phase flag
                    if redis_client and job_id:
                        try:
                            from .job_state import job_hset
                            job_hset(job_id, "logo_fetched", True, redis_client)
                            logging.info(f"[PHASE] Updated logo_fetched=True for job {job_id}")
                        except Exception as phase_err:
                            logging.warning(f"Could not update logo_fetched: {phase_err}")
                    
                sync_engine.dispose()
            except Exception as logo_fetch_error:
                logging.error(f"[LOGO_SERVICE] Logo fetching failed (non-fatal): {logo_fetch_error}")
                # Don't raise - logo fetching is non-critical
                
        except Exception as commit_error:
            print(f"DEBUG: COMMIT FAILED: {commit_error}")
            logging.error(f"COMMIT FAILED: {commit_error}")
            raise
            
        # Update db_uploaded phase flag after successful commit
        if redis_client and job_id:
            try:
                from .job_state import job_hset
                job_hset(job_id, "db_uploaded", True, redis_client)
                logging.info(f"[PHASE] Updated db_uploaded=True for job {job_id}")
            except Exception as phase_err:
                logging.warning(f"Could not update db_uploaded: {phase_err}")

        # Kick off objective extraction + mapping after DB commit
        try:
            if config.ENABLE_OBJECTIVE_EXTRACTION:
                extracted_text_for_objectives = data.get("extracted_text")
                if extracted_text_for_objectives:
                    from .extractors.objective_extractor import extract_objectives
                    import threading

                    def _run_objectives_post_insert(scan_id_val: int, text: str):
                        try:
                            sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
                            sync_engine = create_engine(sync_db_url, echo=False)
                            SessionLocal = sessionmaker(bind=sync_engine)
                            with SessionLocal() as db_session:
                                sections = data.get("sections") or []
                                objectives = extract_objectives(
                                    extracted_text=text,
                                    scan_id=scan_id_val,
                                    db_session=db_session,
                                    sections=sections,
                                    job_id=None,
                                    redis_client=None
                                )
                                logging.info(f"[OBJECTIVES] Extracted {len(objectives)} objectives for scan {scan_id_val}")
                                # NOTE: Control-objective mapping is handled by extract_objectives()
                                # via its _run_gap_and_map background thread. No separate call needed.
                            sync_engine.dispose()
                        except Exception as obj_err:
                            logging.error(f"[OBJECTIVES] Post-insert extraction failed for scan {scan_id_val}: {obj_err}")
                            logging.error(f"[OBJECTIVES] Traceback: {traceback.format_exc()}")

                    threading.Thread(
                        target=_run_objectives_post_insert,
                        args=(scan_id, extracted_text_for_objectives),
                        name=f"objective-extract-{scan_id}",
                        daemon=True
                    ).start()
                else:
                    logging.warning(f"[OBJECTIVES] extracted_text missing; skipping for scan {scan_id}")
        except Exception as obj_init_err:
            logging.error(f"[OBJECTIVES] Failed to start post-insert extraction: {obj_init_err}")
                
    except Exception as outer_error:
        print(f"DEBUG: Outer exception caught: {outer_error}")
        logging.error(f"Outer exception caught: {outer_error}")
        conn.rollback()
        raise
    finally:
        print("DEBUG: In finally block, closing connection")
        cur.close()
        conn.close()
        logging.info("Connection closed.")
    print("DEBUG: Returning summary")
    return summary

if __name__ == "__main__":
    import sys
    json_path = sys.argv[1] if len(sys.argv) > 1 else str(config.JSON_DIR / "combined_result.json")
    summary = insert_extracted_data(json_path)
    print("Insert summary:")
    for k, v in summary.items():
        if k != "errors":
            print(f"  {k}: {v}")
    if summary["errors"]:
        print("Errors:")
        for err in summary["errors"]:
            print(f"  {err}") 
