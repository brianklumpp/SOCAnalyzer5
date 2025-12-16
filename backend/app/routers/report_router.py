"""
Router for report CRUD and file serving operations.
"""
import logging
import traceback
from typing import Optional

from fastapi import APIRouter, Depends, Body, HTTPException
from fastapi.responses import Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy.future import select

from ..models import Scan, Control, CUEC, SubserviceOrg, Company, Product
from ..models.user import User
from ..database import get_db
from ..services.excel_export import ExcelExportService
from ..auth.dependencies import get_current_active_user

router = APIRouter()


@router.get("/report/{scan_id}")
async def get_report(scan_id: int, diag: bool = False, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Get full report data for a scan including all controls, CUECs, and subservice orgs.
    
    Args:
        scan_id: Scan identifier
        diag: Diagnostic mode - returns minimal payload for troubleshooting
    """
    try:
        logging.error(f"[REPORT] Fetching report for scan_id={scan_id}, diag={diag}")
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan_row = result.scalar_one_or_none()
        logging.error(f"[REPORT] scan_row after scalar_one_or_none: {scan_row}, type: {type(scan_row)}")
        if not scan_row:
            logging.error(f"[REPORT] Scan not found for scan_id={scan_id}")
            raise HTTPException(status_code=404, detail="Scan not found")

        # Diagnostic short-circuit to isolate 500s occurring outside main logic
        if diag:
            logging.error(f"[REPORT] DIAG mode active for scan_id={scan_id}")
            minimal = {
                "scan_id": scan_row.id,
                "has_result_json": bool(getattr(scan_row, "result_json", None)),
                "has_company": bool((await db.execute(select(Company).where(Company.scan_id == scan_id))).scalars().first() is not None),
            }
            import json as _json_mod
            logging.error(f"[REPORT] DIAG returning minimal payload for scan_id={scan_id}: {minimal}")
            return Response(content=_json_mod.dumps(minimal), media_type="application/json")

        # Fetch selected related entities
        company = (await db.execute(select(Company).where(Company.scan_id == scan_id))).scalars().first()
        controls = (await db.execute(select(Control).where(Control.scan_id == scan_id))).scalars().all()
        cuecs = (await db.execute(select(CUEC).where(CUEC.scan_id == scan_id))).scalars().all()
        suborgs = (await db.execute(select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id))).scalars().all()
        product = (await db.execute(select(Product).where(Product.scan_id == scan_id))).scalars().first()

        # Extract additional fields from the results JSON if present
        results = scan_row.result_json or {}
        auditor = scan_row.auditor if getattr(scan_row, 'auditor', None) else results.get("auditor", {})
        coverage_period = results.get("coverage_period", {})
        report_date = results.get("report_date", {})
        
        def extract_bad_chunks(section):
            if isinstance(section, dict):
                return section.get("bad_chunks", [])
            return []

        # Extract persisted bad_chunks from result_json
        def get_persisted_bad_chunks(section_key: str):
            sec_val = results.get(section_key)
            meta_val = results.get(f"{section_key}_meta")
            chunks = []
            if isinstance(sec_val, dict) and isinstance(sec_val.get("bad_chunks"), list):
                chunks = sec_val.get("bad_chunks")
            elif isinstance(meta_val, dict) and isinstance(meta_val.get("bad_chunks"), list):
                chunks = meta_val.get("bad_chunks")
            return chunks
        
        bad_chunks = {
            "cuecs": extract_bad_chunks(results.get("cuecs")),
            "controls": extract_bad_chunks(results.get("controls")),
            "subservice_orgs": extract_bad_chunks(results.get("subservice_orgs"))
        }
        
        persisted_bad_chunks = {
            "cuecs": get_persisted_bad_chunks("cuecs"),
            "controls": get_persisted_bad_chunks("controls"),
            "subservice_orgs": get_persisted_bad_chunks("subservice_orgs"),
        }
        
        # PDF viewer metadata
        has_pdf_stored = bool(getattr(scan_row, "pdf_file", None))
        page_count = None
        sections_data = getattr(scan_row, "sections", None)
        sections_list = []
        
        if sections_data:
            import json as _json
            if isinstance(sections_data, str):
                try:
                    sections_list = _json.loads(sections_data)
                except Exception as e:
                    logging.error(f"Failed to parse sections JSON for scan {scan_id}: {e}")
            elif isinstance(sections_data, list):
                sections_list = sections_data
        
        # Extract page count from sections if available
        if sections_list and len(sections_list) > 0:
            try:
                page_count = max(s.get("end_DOC_page_ref", 0) for s in sections_list if isinstance(s, dict))
            except Exception:
                pass
        
        payload = {
            "scan_id": scan_row.id,
            "scan_date": (scan_row.scan_date.isoformat() if getattr(scan_row, "scan_date", None) else None),
            "filename": scan_row.pdf_filename,
            "company": getattr(scan_row, "company", None) or (company.name if company else None),
            "parent_company": company.parent_company if company else None,
            "auditor": getattr(scan_row, "auditor", None) or auditor,
            "coverage_period": coverage_period,
            "coverage_start": (getattr(scan_row, "coverage_start", None).date().isoformat() if getattr(scan_row, "coverage_start", None) else None),
            "coverage_end": (getattr(scan_row, "coverage_end", None).date().isoformat() if getattr(scan_row, "coverage_end", None) else None),
            "report_date": report_date,
            "product": getattr(scan_row, "product", None) or (product.name if product else None),
            "report_type": getattr(scan_row, "report_type", "SOC2"),
            "as_of_date": (getattr(scan_row, "as_of_date", None).date().isoformat() if getattr(scan_row, "as_of_date", None) else None),
            "gpt_cost": getattr(scan_row, "gpt_cost", None),
            "gpt_model": getattr(scan_row, "gpt_model", None),
            "estimated_time_seconds": getattr(scan_row, "estimated_time_seconds", None),
            "pdf_filename": getattr(scan_row, "pdf_filename", None),
            "company_id": getattr(scan_row, "company_id", None),
            "executive_summary_stale": getattr(scan_row, "executive_summary_stale", False),
            "is_sox_vendor": getattr(scan_row, "is_sox_vendor", False),
            "toc_page_offset": getattr(scan_row, "toc_page_offset", None) or results.get("toc_page_offset", 0),
            "has_pdf_stored": has_pdf_stored,
            "page_count": page_count,
            "sections": sections_list,
            "subservice_organizations": [
                {
                    "id": getattr(s, "id", None),
                    "name": getattr(s, "name", None),
                    "confidence": getattr(s, "confidence", None),
                    "third_party_description": getattr(s, "third_party_description", None),
                    "third_party_page_ref": getattr(s, "third_party_page_ref", None),
                    "third_party_confidence": getattr(s, "third_party_confidence", None),
                    "distance_from_so_keywords": getattr(s, "distance_from_so_keywords", None),
                    "likely_so": getattr(s, "likely_so", None),
                    "common_so": getattr(s, "common_so", None),
                    "source_context": getattr(s, "source_context", None),
                    "confidence_justification": getattr(s, "confidence_justification", None),
                    "third_party_controls": getattr(s, "third_party_controls", None),
                    "annotation": getattr(s, "annotation", None),
                    "analyst_notes": getattr(s, "analyst_notes", None),
                    "pdf_snippet": getattr(s, "pdf_snippet", None),
                } for s in suborgs
            ],
            "cuecs": [
                {
                    "id": getattr(c, "id", None),
                    "cuec_seq": getattr(c, "cuec_seq", None),
                    "cuec_id": getattr(c, "cuec_tsc_id", None),
                    "cuec_tsc_id": getattr(c, "cuec_tsc_id", None),
                    "cuec_description": getattr(c, "cuec_description", None) or getattr(c, "description", None),
                    "cuec_line_ref": getattr(c, "cuec_line_ref", None),
                    "cuec_page_refs": getattr(c, "cuec_page_refs", None),
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
                    "cuec_tsc_mappings": getattr(c, "cuec_tsc_mappings", None),
                    "cuec_coso_mappings": getattr(c, "cuec_coso_mappings", None),
                    "cuec_framework_mappings": getattr(c, "cuec_framework_mappings", None),
                    "cuec_primary_framework": getattr(c, "cuec_primary_framework", None),
                    "cuec_primary_criterion_id": getattr(c, "cuec_primary_criterion_id", None),
                    "cuec_primary_confidence": getattr(c, "cuec_primary_confidence", None),
                    "annotation": getattr(c, "annotation", None),
                    "analyst_notes": getattr(c, "analyst_notes", None),
                    "control_strength": getattr(c, "control_strength", None),
                    "pdf_snippet": getattr(c, "pdf_snippet", None),
                } for c in cuecs
            ],
            "controls": [
                ({"id": getattr(ctrl, "id", None)} | {k: getattr(ctrl, k, None) for k in [
                    "control_id", "control_desc", "control_test", "control_test_results",
                    "has_deviation", "deviation_desc", "control_page_refs", "control_line_ref",
                    "control_seq", "control_soc_domain", "control_status", "merged_to_control_id",
                    "control_gpt_opinion", "control_gpt_reasoning",
                    "control_confidence", "confidence_calc",
                    "verification_status", "verification_metadata",
                    "pattern_confidence", "final_confidence",
                    "annotation", "analyst_notes",
                    "financial_assertions", "framework_category", "pdf_snippet",
                    "framework_mappings", "primary_framework",
                    "primary_criterion_id", "primary_confidence",
                    "is_duplicate_instance", "duplicate_group_id", "instance_differentiator"
                ]}) for ctrl in controls
            ],
            "bad_chunks": bad_chunks if any(bad_chunks.values()) else persisted_bad_chunks,
            "executive_summary": getattr(scan_row, "executive_summary", None)
        }
        
        # Ensure everything is JSON-serializable
        try:
            encoded = jsonable_encoder(payload)
            import json as _json_mod
            resp_text = _json_mod.dumps(encoded)
            logging.error(f"[REPORT] Returning payload for scan_id={scan_id} (size={len(resp_text)} bytes)")
            return Response(content=resp_text, media_type="application/json")
        except Exception as enc_err:
            logging.error(f"/report/{scan_id} jsonable_encoder error: {enc_err}\n{traceback.format_exc()}")
            # Last-resort: stringify unknown types
            import json as _json_mod
            try:
                text = _json_mod.dumps(payload, default=lambda o: str(o))
                return Response(content=text, media_type="application/json")
            except Exception as dump_err:
                logging.error(f"/report/{scan_id} json dumps fallback error: {dump_err}\n{traceback.format_exc()}")
                raise

    except HTTPException:
        # Re-raise HTTPException as-is to preserve status code
        raise
    except Exception as e:
        logging.error(f"/report/{scan_id} failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pdf/{scan_id}")
async def get_pdf(scan_id: int, db=Depends(get_db)):
    """Serve PDF file for a scan. Returns PDF bytes with proper Content-Type."""
    try:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan_row = result.scalar_one_or_none()
        
        if not scan_row:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        pdf_bytes = getattr(scan_row, "pdf_file", None)
        if not pdf_bytes:
            raise HTTPException(status_code=404, detail="PDF not stored for this scan")
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{scan_row.pdf_filename or "report.pdf"}"',
                "Cache-Control": "public, max-age=31536000"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"/pdf/{scan_id} failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/excel/{scan_id}")
async def export_excel(scan_id: int, db=Depends(get_db)):
    """
    Export SOC analysis data to Excel template for a scan.
    Returns Excel file with populated control objectives, exceptions, CUECs, and subservice orgs.
    """
    try:
        logging.info(f"Excel export requested for scan {scan_id}")
        
        # Generate Excel report
        service = ExcelExportService()
        excel_file = await service.generate_report(scan_id, db)
        
        # Get scan for filename
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        
        if not scan:
            raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")
        
        # Generate filename
        company_safe = (scan.company or "Unknown").replace(" ", "_").replace("/", "-")
        report_type = scan.report_type.value if scan.report_type else "SOC2"
        filename = f"SOC_Analysis_{company_safe}_{report_type}_Scan{scan_id}.xlsx"
        
        logging.info(f"Excel export completed for scan {scan_id}: {filename}")
        
        return Response(
            content=excel_file.read(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-cache"
            }
        )
        
    except HTTPException:
        raise
    except FileNotFoundError as e:
        logging.error(f"Excel export failed - template not found: {e}")
        raise HTTPException(status_code=500, detail=f"Export template not found: {str(e)}")
    except ValueError as e:
        logging.error(f"Excel export failed - validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Excel export failed for scan {scan_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/report/{scan_id}/pdf")
async def get_report_pdf(scan_id: int, db=Depends(get_db)):
    """
    Serve the original PDF file for the specified scan.
    Returns the PDF with Content-Disposition: inline to open in browser.
    """
    try:
        result = await db.execute(select(Scan).filter(Scan.id == scan_id))
        scan_row = result.scalars().first()
        
        if not scan_row:
            raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")
        
        if not scan_row.pdf_file:
            raise HTTPException(status_code=404, detail=f"PDF file not available for scan {scan_id}")
        
        # Generate a safe filename from the pdf_filename field
        filename = scan_row.pdf_filename or f"report_{scan_id}.pdf"
        
        return Response(
            content=scan_row.pdf_file,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"get_report_pdf error for scan_id={scan_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve PDF: {e}")


@router.patch("/report/{scan_id}/overview")
async def patch_report_overview(scan_id: int, data: dict = Body(...), db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Update scan overview fields (company, product, dates, etc.)."""
    try:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Update allowed fields
        allowed_fields = ["company", "product", "auditor", "coverage_start", "coverage_end", 
                         "report_type", "as_of_date", "is_sox_vendor"]
        
        for field in allowed_fields:
            if field in data:
                setattr(scan, field, data[field])
        
        await db.commit()
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating report overview for scan {scan_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{scan_id}/reload_text")
async def reload_extracted_text(scan_id: int, db=Depends(get_db)):
    """Reload extracted text from disk for a scan (for debugging/recovery)."""
    try:
        import os
        from pathlib import Path
        
        # Read extracted text from disk
        project_root = Path(__file__).resolve().parents[3]
        text_path = project_root / 'data' / 'output' / 'output.txt'
        
        if not text_path.exists():
            raise HTTPException(status_code=404, detail="Extracted text file not found")
        
        with open(text_path, 'r', encoding='utf-8') as f:
            extracted_text = f.read()
        
        # Update scan
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        scan.extracted_text = extracted_text
        await db.commit()
        
        return {"status": "ok", "text_length": len(extracted_text)}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error reloading extracted text for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
