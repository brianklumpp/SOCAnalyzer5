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

def insert_extracted_data(json_path: str):
    # Load environment variables from .env
    load_dotenv()
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
    def sanitize_value(val):
        if isinstance(val, (list, dict)):
            return json.dumps(val, ensure_ascii=False)
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
        coverage_period = data.get("coverage_period")
        start_date = coverage_period.get("start_date") if isinstance(coverage_period, dict) else None
        end_date = coverage_period.get("end_date") if isinstance(coverage_period, dict) else None
        scan_fields = [
            "product", "report_date", "coverage_start", "coverage_end", "auditor", "result_json", "scan_date",
            "gpt_cost", "gpt_model", "estimated_time_seconds", "gpt_usage_details", "extracted_text", "pdf_filename", "pdf_file", "company_id"
        ]
        scan_values = [
            sanitize_value(data.get("product")),
            sanitize_value(data.get("report_date")),
            sanitize_value(start_date),
            sanitize_value(end_date),
            sanitize_value(data.get("auditor")),
            json.dumps(data, ensure_ascii=False),
            datetime.utcnow(),
            sanitize_value(data.get("gpt_cost")),
            sanitize_value(data.get("gpt_model")),
            sanitize_value(data.get("estimated_time_seconds")),
            sanitize_value(data.get("gpt_usage_details")),
            sanitize_value(data.get("extracted_text")),
            sanitize_value(data.get("pdf_filename")),
            sanitize_value(data.get("pdf_file")),
            sanitize_value(data.get("company_id")),
        ]
        scan_sql = f"INSERT INTO scan ({', '.join(scan_fields)}) VALUES ({', '.join(['%s']*len(scan_fields))}) RETURNING id"
        logging.info(f"SQL: {scan_sql} | Values: {scan_values}")
        cur.execute(scan_sql, scan_values)
        scan_id = cur.fetchone()[0]
        logging.info(f"Inserted new scan row with scan_id: {scan_id}")
        # Insert company and update scan with company_id
        company = data.get("company")
        company_id = None
        if company:
            try:
                name = company if isinstance(company, str) else company.get("company") or company.get("name")
                parent_company = company.get("parent_company") if isinstance(company, dict) else None
                confidence = company.get("confidence") if isinstance(company, dict) else None
                values = [sanitize_value(name), sanitize_value(parent_company), sanitize_value(confidence), scan_id]
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
                summary["company"] += 1
                logging.info(f"Inserted into company: {values}")
            except Exception as e:
                summary["errors"].append(f"Company insert error: {e}")
                logging.error(f"Company insert error: {e}")
                conn.rollback()
        # Insert controls
        controls = data.get("controls")
        if controls:
            for ctrl in controls:
                try:
                    values = [sanitize_value(ctrl.get(f)) for f in config.TABLE_FIELD_MAP["control"][:-1]] + [scan_id]
                    fields = config.TABLE_FIELD_MAP["control"]
                    sql = f"INSERT INTO control ({', '.join(fields)}) VALUES ({', '.join(['%s']*len(fields))})"
                    logging.info(f"SQL: {sql} | Values: {values}")
                    cur.execute(sql, values)
                    summary["control"] += 1
                    logging.info(f"Inserted into control: {values}")
                except Exception as e:
                    summary["errors"].append(f"Control insert error: {e}")
                    logging.error(f"Control insert error: {e}")
                    conn.rollback()
        # Insert cuecs
        cuecs = data.get("cuecs")
        if cuecs:
            for cuec in cuecs:
                try:
                    values = [sanitize_value(cuec.get(f)) for f in config.TABLE_FIELD_MAP["cuec"][:-1]] + [scan_id]
                    fields = config.TABLE_FIELD_MAP["cuec"]
                    sql = f"INSERT INTO cuec ({', '.join(fields)}) VALUES ({', '.join(['%s']*len(fields))})"
                    logging.info(f"SQL: {sql} | Values: {values}")
                    cur.execute(sql, values)
                    summary["cuec"] += 1
                    logging.info(f"Inserted into cuec: {values}")
                except Exception as e:
                    summary["errors"].append(f"CUEC insert error: {e}")
                    logging.error(f"CUEC insert error: {e}")
                    conn.rollback()
        # Insert subservice orgs
        suborgs = data.get("subservice_orgs")
        if suborgs:
            for org in suborgs:
                try:
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
                    summary["subservice_org"] += 1
                    logging.info(f"Inserted into subservice_org: {values}")
                except Exception as e:
                    summary["errors"].append(f"SubserviceOrg insert error: {e}")
                    logging.error(f"SubserviceOrg insert error: {e}")
                    conn.rollback()
        # Insert product
        product = data.get("product")
        if product:
            try:
                name = product if isinstance(product, str) else product.get("product") or product.get("name")
                values = [sanitize_value(name), scan_id]
                fields = config.TABLE_FIELD_MAP["product"]
                sql = f"INSERT INTO product ({', '.join(fields)}) VALUES ({', '.join(['%s']*len(fields))}) ON CONFLICT DO NOTHING"
                logging.info(f"SQL: {sql} | Values: {values}")
                cur.execute(sql, values)
                summary["product"] += 1
                logging.info(f"Inserted into product: {values}")
            except Exception as e:
                summary["errors"].append(f"Product insert error: {e}")
                logging.error(f"Product insert error: {e}")
                conn.rollback()
        conn.commit()
    finally:
        cur.close()
        conn.close()
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