# Remove all top-level code except function and __main__ block
# Only define insert_extracted_data and (optionally) __main__

import json
import psycopg2
import psycopg2.extras
import os
from datetime import datetime
from dotenv import load_dotenv
import logging
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

def insert_extracted_data(json_path: str, pdf_path: str = None, job_id: str = None):
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
            logging.warning(f"Could not create Redis client for job state updates: {redis_err}")
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
            "gpt_cost", "gpt_model", "estimated_time_seconds", "gpt_usage_details", "extracted_text", "pdf_filename", "pdf_file", "company_id", "report_type", "toc_page_offset", "detected_standards"
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
        
        scan_values = [
            sanitize_value(product_name),
            report_date_norm,
            start_date,
            end_date,
            sanitize_value(auditor_name),
            json.dumps(data_for_json, ensure_ascii=False),
            datetime.utcnow(),
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
            for ctrl in controls:
                try:
                    cur.execute("SAVEPOINT control_insert")
                    # Backward-compatible mapping for new fields
                    if 'has_deviation' not in ctrl:
                        ctrl['has_deviation'] = False
                    if 'deviation_desc' not in ctrl:
                        ctrl['deviation_desc'] = None
                    # Map control_gpt_conf_justification (JSON) → confidence_calc (database)
                    if 'control_gpt_conf_justification' in ctrl and 'confidence_calc' not in ctrl:
                        ctrl['confidence_calc'] = ctrl['control_gpt_conf_justification']
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
                                else:
                                    logging.warning(f"[LOGO_SERVICE] ✗ No logo (GPT): {company_name} ({domain})")
                            except Exception as logo_error:
                                logging.error(f"[LOGO_SERVICE] Error for company {company_id}: {logo_error}")
                    else:
                        logging.info(f"[LOGO_SERVICE] No companies needing logos for scan {scan_id}")
                    
                    db_session.commit()
                    
                    # Update phase_completion.logo_fetched
                    if redis_client and job_id:
                        try:
                            import json as _json
                            job_key = f"job:{job_id}"
                            job_data = redis_client.get(job_key)
                            if job_data:
                                job_dict = _json.loads(job_data)
                                if "phase_completion" not in job_dict:
                                    job_dict["phase_completion"] = {}
                                job_dict["phase_completion"]["logo_fetched"] = True
                                redis_client.setex(job_key, 86400, _json.dumps(job_dict))
                                logging.info(f"[PHASE] Updated phase_completion.logo_fetched=True for job {job_id}")
                        except Exception as phase_err:
                            logging.warning(f"Could not update phase_completion.logo_fetched: {phase_err}")
                    
                sync_engine.dispose()
            except Exception as logo_fetch_error:
                logging.error(f"[LOGO_SERVICE] Logo fetching failed (non-fatal): {logo_fetch_error}")
                # Don't raise - logo fetching is non-critical
                
        except Exception as commit_error:
            print(f"DEBUG: COMMIT FAILED: {commit_error}")
            logging.error(f"COMMIT FAILED: {commit_error}")
            raise
            
        # Update phase_completion.db_uploaded after successful commit
        if redis_client and job_id:
            try:
                import json as _json
                job_key = f"job:{job_id}"
                job_data = redis_client.get(job_key)
                if job_data:
                    job_dict = _json.loads(job_data)
                    if "phase_completion" not in job_dict:
                        job_dict["phase_completion"] = {}
                    job_dict["phase_completion"]["db_uploaded"] = True
                    redis_client.setex(job_key, 86400, _json.dumps(job_dict))
                    logging.info(f"[PHASE] Updated phase_completion.db_uploaded=True for job {job_id}")
            except Exception as phase_err:
                logging.warning(f"Could not update phase_completion.db_uploaded: {phase_err}")
                
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