"""
Router for report CRUD and file serving operations.
"""
import logging
import traceback
from typing import Optional

from fastapi import APIRouter, Depends, Body, HTTPException, BackgroundTasks
from fastapi.responses import Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy.future import select
from sqlalchemy import and_

from ..models import Scan, Control, CUEC, SubserviceOrg, Company, Product, ControlObjective, ControlObjectiveMapping, CUECObjectiveMapping
from ..models import User
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

        # Build primary objective mapping for controls
        primary_objective_by_control_id = {}
        try:
            mappings_result = await db.execute(
                select(ControlObjectiveMapping, ControlObjective)
                .join(ControlObjective, ControlObjectiveMapping.objective_id == ControlObjective.id)
                .join(Control, ControlObjectiveMapping.control_id == Control.id)
                .where(
                    and_(
                        Control.scan_id == scan_id,
                        ControlObjectiveMapping.is_primary.is_(True)
                    )
                )
            )
            for mapping, objective in mappings_result.all():
                primary_objective_by_control_id[mapping.control_id] = {
                    "id": objective.id,
                    "objective_id": objective.objective_id,
                    "objective_text": objective.objective_text,
                    "final_confidence": objective.final_confidence,
                    "mapping_confidence": mapping.mapping_confidence,
                    "page_proximity_score": getattr(mapping, "page_proximity_score", None),
                    "line_proximity_score": getattr(mapping, "line_proximity_score", None),
                    "gpt_alignment_score": getattr(mapping, "gpt_alignment_score", None),
                    "id_alignment_score": getattr(mapping, "id_alignment_score", None),
                    "page_refs": objective.page_refs,
                    "line_ref": objective.line_ref,
                    "status": objective.status
                }
        except Exception as e:
            logging.error(f"[REPORT] Failed to build primary objective map for scan_id={scan_id}: {e}")

        # Build primary objective mapping for CUECs
        primary_objective_by_cuec_id = {}
        try:
            cuec_mappings_result = await db.execute(
                select(CUECObjectiveMapping, ControlObjective)
                .join(ControlObjective, CUECObjectiveMapping.objective_id == ControlObjective.id)
                .join(CUEC, CUECObjectiveMapping.cuec_id == CUEC.id)
                .where(
                    and_(
                        CUEC.scan_id == scan_id,
                        CUECObjectiveMapping.is_primary.is_(True)
                    )
                )
            )
            for mapping, objective in cuec_mappings_result.all():
                primary_objective_by_cuec_id[mapping.cuec_id] = {
                    "id": objective.id,
                    "objective_id": objective.objective_id,
                    "objective_text": objective.objective_text,
                    "final_confidence": objective.final_confidence,
                    "mapping_confidence": mapping.mapping_confidence,
                    "page_proximity_score": getattr(mapping, "page_proximity_score", None),
                    "line_proximity_score": getattr(mapping, "line_proximity_score", None),
                    "gpt_alignment_score": getattr(mapping, "gpt_alignment_score", None),
                    "page_refs": objective.page_refs,
                    "line_ref": objective.line_ref,
                    "status": objective.status
                }
        except Exception as e:
            logging.error(f"[REPORT] Failed to build primary CUEC objective map for scan_id={scan_id}: {e}")

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
        
        if controls:
            sample_control_id = getattr(controls[0], "id", None)
            sample_objective = primary_objective_by_control_id.get(sample_control_id)
            logging.error(
                f"[REPORT] primary objective map size={len(primary_objective_by_control_id)} "
                f"sample_control_id={sample_control_id} has_sample={bool(sample_objective)}"
            )
        else:
            logging.error("[REPORT] primary objective map size=0 (no controls)")

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
                    "edit_log": getattr(s, "edit_log", None),
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
                    "framework_mappings": getattr(c, "framework_mappings", None),
                    "primary_framework": getattr(c, "primary_framework", None),
                    "primary_criterion_id": getattr(c, "primary_criterion_id", None),
                    "primary_confidence": getattr(c, "primary_confidence", None),
                    "annotation": getattr(c, "annotation", None),
                    "analyst_notes": getattr(c, "analyst_notes", None),
                    "control_strength": getattr(c, "control_strength", None),
                    "edit_log": getattr(c, "edit_log", None),
                    "pdf_snippet": getattr(c, "pdf_snippet", None),
                    "cuec_primary_objective": primary_objective_by_cuec_id.get(getattr(c, "id", None)),
                    "cuec_primary_objective_text": (primary_objective_by_cuec_id.get(getattr(c, "id", None)) or {}).get("objective_text"),
                    "cuec_primary_objective_confidence": (primary_objective_by_cuec_id.get(getattr(c, "id", None)) or {}).get("mapping_confidence"),
                    "cuec_primary_objective_scores": {
                        "page_proximity_score": (primary_objective_by_cuec_id.get(getattr(c, "id", None)) or {}).get("page_proximity_score"),
                        "line_proximity_score": (primary_objective_by_cuec_id.get(getattr(c, "id", None)) or {}).get("line_proximity_score"),
                        "gpt_alignment_score": (primary_objective_by_cuec_id.get(getattr(c, "id", None)) or {}).get("gpt_alignment_score"),
                        "total": (primary_objective_by_cuec_id.get(getattr(c, "id", None)) or {}).get("mapping_confidence"),
                    },
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
                ]} | {
                    "primary_objective": primary_objective_by_control_id.get(getattr(ctrl, "id", None)),
                    "primary_objective_text": (primary_objective_by_control_id.get(getattr(ctrl, "id", None)) or {}).get("objective_text"),
                    "primary_objective_confidence": (primary_objective_by_control_id.get(getattr(ctrl, "id", None)) or {}).get("mapping_confidence"),
                    "primary_objective_scores": {
                        "page_proximity_score": (primary_objective_by_control_id.get(getattr(ctrl, "id", None)) or {}).get("page_proximity_score"),
                        "line_proximity_score": (primary_objective_by_control_id.get(getattr(ctrl, "id", None)) or {}).get("line_proximity_score"),
                        "gpt_alignment_score": (primary_objective_by_control_id.get(getattr(ctrl, "id", None)) or {}).get("gpt_alignment_score"),
                        "id_alignment_score": (primary_objective_by_control_id.get(getattr(ctrl, "id", None)) or {}).get("id_alignment_score"),
                        "total": (primary_objective_by_control_id.get(getattr(ctrl, "id", None)) or {}).get("mapping_confidence"),
                    }
                }) for ctrl in controls
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
async def get_pdf(scan_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Serve PDF file for a scan. Returns embedded PDF if available (from consent agreements), otherwise returns main PDF."""
    try:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan_row = result.scalar_one_or_none()
        
        if not scan_row:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Prefer embedded PDF if available (from consent agreement wrapper)
        pdf_bytes = getattr(scan_row, "embedded_pdf_file", None)
        pdf_filename = getattr(scan_row, "embedded_pdf_filename", None)
        
        if pdf_bytes:
            logging.info(f"[PDF_SERVE] Serving embedded PDF for scan {scan_id}: {pdf_filename} ({len(pdf_bytes)} bytes)")
        else:
            # Fall back to main PDF if no embedded PDF
            pdf_bytes = getattr(scan_row, "pdf_file", None)
            pdf_filename = scan_row.pdf_filename
            if pdf_bytes:
                logging.info(f"[PDF_SERVE] Serving main PDF for scan {scan_id}: {pdf_filename} ({len(pdf_bytes)} bytes)")
        
        if not pdf_bytes:
            raise HTTPException(status_code=404, detail="PDF not stored for this scan")
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{pdf_filename or "report.pdf"}"',
                "Cache-Control": "public, max-age=31536000"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"/pdf/{scan_id} failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/excel/{scan_id}")
async def export_to_excel(scan_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Export SOC analysis data to Excel template for a scan.
    Returns Excel file with populated control objectives, exceptions, CUECs, and subservice orgs.
    """
    try:
        logging.info(f"Excel export requested for scan {scan_id}")
        
        # Generate Excel report
        service = ExcelExportService()
        excel_file = await service.generate_report(scan_id, db, current_user)
        
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
async def get_report_pdf(scan_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
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
        from datetime import datetime
        
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Update allowed fields
        allowed_fields = ["company", "product", "auditor", "coverage_start", "coverage_end", 
                         "report_type", "as_of_date", "is_sox_vendor", "report_date"]
        
        # Date fields that need parsing
        date_fields = ["coverage_start", "coverage_end", "report_date", "as_of_date"]
        
        for field in allowed_fields:
            if field in data:
                value = data[field]
                # Parse date strings to datetime objects
                if field in date_fields and isinstance(value, str) and value:
                    try:
                        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    except ValueError:
                        # Try parsing as date-only string (YYYY-MM-DD)
                        try:
                            value = datetime.strptime(value, '%Y-%m-%d')
                        except ValueError:
                            pass  # Keep as string if parsing fails
                setattr(scan, field, value)
        
        await db.commit()
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating report overview for scan {scan_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{scan_id}/reload_text")
async def reload_extracted_text(scan_id: int, db=Depends(get_db), current_user: User = Depends(get_current_active_user)):
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


@router.post("/report/{scan_id}/manual-extract")
async def manual_extract(
    scan_id: int,
    background_tasks: BackgroundTasks,
    data: dict = Body(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Manually extract CUECs or Subservice Organizations from specific PDF pages."""
    print(f"[MANUAL_EXTRACT PRINT] Function entered! scan_id={scan_id}, data={data}")
    logging.info(f"[MANUAL_EXTRACT] Endpoint called for scan {scan_id} by {current_user.username}, data: {data}")
    try:
        from ..services.manual_extraction_service import (
            parse_page_ranges, 
            manual_extract_cuecs, 
            manual_extract_subservice_orgs
        )
        
        entity_type = data.get("entity_type")
        pages_str = data.get("pages")
        
        print(f"[MANUAL_EXTRACT PRINT] entity_type={entity_type}, pages={pages_str}")
        logging.info(f"[MANUAL_EXTRACT] entity_type={entity_type}, pages={pages_str}")
        
        if not entity_type or not pages_str:
            raise HTTPException(status_code=400, detail="entity_type and pages are required")
        
        if entity_type not in ["cuec", "subservice_org"]:
            raise HTTPException(status_code=400, detail="entity_type must be 'cuec' or 'subservice_org'")
        
        # Parse and validate page ranges
        try:
            pages = parse_page_ranges(pages_str)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Run extraction immediately (without background task for now to maintain existing behavior)
        # TODO: Consider moving to background task if extractions take too long
        if entity_type == "cuec":
            result = await manual_extract_cuecs(scan_id, pages, db, current_user.username)
        else:
            result = await manual_extract_subservice_orgs(scan_id, pages, db, current_user.username)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in manual extraction for scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
