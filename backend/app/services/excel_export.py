import logging
import traceback
from io import BytesIO
from typing import List
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Border, Side
from openpyxl.cell import MergedCell
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models import Scan, Control, CUEC, SubserviceOrg
from ..gpt_client import gpt_extract
from ..config import GPT_PROMPTS

logger = logging.getLogger(__name__)

class ExcelExportService:
    """
    Service for exporting SOC analysis data to Excel template.
    Populates 6 tabs with database content and GPT-generated descriptions.
    """
    
    TEMPLATE_PATH = Path(__file__).resolve().parents[3] / 'data' / 'template' / 'SOC Evaluation Template - 2024.xlsx'
    HIGH_CONFIDENCE_THRESHOLD = 0.7
    
    # Expected tab names in template
    TAB_BASIC_PROCEDURES = "1. Basic Procedures"
    TAB_CONTROL_OBJECTIVES = "2. Control Objective"
    TAB_EXCEPTIONS = "3. Exceptions Noted"
    TAB_CUECS = "4. Complementary User Controls"
    TAB_SUBSERVICE_ORGS = "5. Subservice Orgs"
    TAB_CONCLUSION = "7. Conclusion"
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def _safe_write_cell(self, ws, row: int, col: int, value: any) -> None:
        """
        Safely write to a cell, handling merged cells by writing only to top-left cell.
        Skips writing to merged cells that aren't the top-left cell of the range.
        """
        try:
            cell = ws.cell(row, col)
            if isinstance(cell, MergedCell):
                # Skip writing to merged cells that aren't the master cell
                self.logger.debug(f"[EXCEL_EXPORT] Skipping write to merged cell at ({row}, {col})")
                return
            cell.value = value
        except AttributeError as e:
            if "MergedCell" in str(e):
                self.logger.debug(f"[EXCEL_EXPORT] Skipping merged cell at ({row}, {col})")
            else:
                raise
    
    async def generate_report(
        self,
        scan_id: int,
        db: AsyncSession
    ) -> BytesIO:
        """
        Main orchestrator: queries database, loads template, populates tabs, returns Excel file.
        
        Args:
            scan_id: ID of scan to export
            db: Database session
            
        Returns:
            BytesIO containing Excel file
            
        Raises:
            FileNotFoundError: Template not found
            ValueError: Invalid scan_id or missing data
            Exception: Any processing errors
        """
        try:
            self.logger.info(f"[EXCEL_EXPORT] Starting export for scan_id={scan_id}")
            
            # Query all required data
            self.logger.info(f"[EXCEL_EXPORT] Querying database for scan {scan_id}")
            scan = await self._get_scan(scan_id, db)
            controls = await self._get_controls(scan_id, db)
            cuecs = await self._get_cuecs(scan_id, db)
            suborgs = await self._get_subservice_orgs(scan_id, db)
            
            self.logger.info(
                f"[EXCEL_EXPORT] Data loaded: {len(controls)} controls, "
                f"{len(cuecs)} CUECs, {len(suborgs)} subservice orgs"
            )
            
            # Verify template exists
            if not self.TEMPLATE_PATH.exists():
                raise FileNotFoundError(f"Template not found: {self.TEMPLATE_PATH}")
            
            self.logger.info(f"[EXCEL_EXPORT] Loading template from {self.TEMPLATE_PATH}")
            wb = load_workbook(self.TEMPLATE_PATH)
            
            # Verify all expected tabs exist
            self._verify_template_tabs(wb)
            
            # Populate each tab
            self.logger.info("[EXCEL_EXPORT] Populating Basic Procedures tab")
            self._populate_basic_procedures(wb[self.TAB_BASIC_PROCEDURES], scan, controls)
            
            self.logger.info("[EXCEL_EXPORT] Populating Control Objectives tab")
            self._populate_control_objectives(wb[self.TAB_CONTROL_OBJECTIVES], controls)
            
            self.logger.info("[EXCEL_EXPORT] Populating Exceptions tab")
            self._populate_exceptions(wb[self.TAB_EXCEPTIONS], controls)
            
            self.logger.info("[EXCEL_EXPORT] Populating CUECs tab")
            self._populate_cuecs(wb[self.TAB_CUECS], cuecs)
            
            self.logger.info("[EXCEL_EXPORT] Populating Subservice Orgs tab")
            self._populate_subservice_orgs(wb[self.TAB_SUBSERVICE_ORGS], suborgs)
            
            self.logger.info("[EXCEL_EXPORT] Populating Conclusion tab")
            self._populate_conclusion(wb[self.TAB_CONCLUSION], scan)
            
            # Save to BytesIO
            output = BytesIO()
            wb.save(output)
            output.seek(0)
            
            self.logger.info(f"[EXCEL_EXPORT] Export completed successfully for scan {scan_id}")
            return output
            
        except Exception as e:
            self.logger.error(
                f"[EXCEL_EXPORT] Export failed for scan {scan_id}: {e}\n{traceback.format_exc()}"
            )
            raise
    
    def _verify_template_tabs(self, wb) -> None:
        """Verify all required tabs exist in template, log warnings for missing tabs."""
        required_tabs = [
            self.TAB_BASIC_PROCEDURES,
            self.TAB_CONTROL_OBJECTIVES,
            self.TAB_EXCEPTIONS,
            self.TAB_CUECS,
            self.TAB_SUBSERVICE_ORGS,
            self.TAB_CONCLUSION
        ]
        
        available_tabs = wb.sheetnames
        missing_tabs = [tab for tab in required_tabs if tab not in available_tabs]
        
        if missing_tabs:
            self.logger.warning(
                f"[EXCEL_EXPORT] Template missing expected tabs: {missing_tabs}. "
                f"Available tabs: {available_tabs}"
            )
            raise ValueError(f"Template missing required tabs: {missing_tabs}")
        
        self.logger.info(f"[EXCEL_EXPORT] All required tabs verified in template")
    
    async def _get_scan(self, scan_id: int, db: AsyncSession) -> Scan:
        """Query scan by ID."""
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        if not scan:
            raise ValueError(f"Scan {scan_id} not found")
        return scan
    
    async def _get_controls(self, scan_id: int, db: AsyncSession) -> List[Control]:
        """Query all controls for scan."""
        result = await db.execute(select(Control).where(Control.scan_id == scan_id))
        return result.scalars().all()
    
    async def _get_cuecs(self, scan_id: int, db: AsyncSession) -> List[CUEC]:
        """Query all CUECs for scan."""
        result = await db.execute(select(CUEC).where(CUEC.scan_id == scan_id))
        return result.scalars().all()
    
    async def _get_subservice_orgs(self, scan_id: int, db: AsyncSession) -> List[SubserviceOrg]:
        """Query all subservice organizations for scan."""
        result = await db.execute(select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id))
        return result.scalars().all()
    
    def _populate_basic_procedures(self, ws, scan: Scan, controls: List[Control]) -> None:
        """
        Populate Basic Procedures tab:
        - C7-C15: Basic metadata from scan
        - C26-C33: GPT-generated descriptions
        """
        try:
            # Basic metadata (cells C7-C15)
            self._safe_write_cell(ws, 7, 3, scan.company or "")
            self._safe_write_cell(ws, 8, 3, str(scan.report_type.value) if scan.report_type else "")
            self._safe_write_cell(ws, 9, 3, f"{scan.coverage_start:%Y-%m-%d} to {scan.coverage_end:%Y-%m-%d}" if scan.coverage_start and scan.coverage_end else "")
            
            # Determine framework
            frameworks = scan.active_frameworks or []
            self._safe_write_cell(ws, 10, 3, ", ".join(frameworks) if frameworks else "TSC")
            
            self._safe_write_cell(ws, 11, 3, scan.auditor or "")
            self._safe_write_cell(ws, 12, 3, f"{scan.report_date:%Y-%m-%d}" if scan.report_date else "")
            self._safe_write_cell(ws, 13, 3, scan.product or "")
            self._safe_write_cell(ws, 14, 3, "")  # Reviewer name - leave blank
            self._safe_write_cell(ws, 15, 3, f"{datetime.now():%Y-%m-%d}")  # Review date
            
            self.logger.info(f"[EXCEL_EXPORT] Basic metadata populated (C7-C15)")
            
            # GPT-generated descriptions (C26-C33)
            self._generate_gpt_descriptions(ws, scan, controls)
            
        except Exception as e:
            self.logger.error(f"[EXCEL_EXPORT] Error populating basic procedures: {e}\n{traceback.format_exc()}")
            raise
    
    def _generate_gpt_descriptions(self, ws, scan: Scan, controls: List[Control]) -> None:
        """Generate 8 GPT descriptions for cells C26-C33."""
        
        # Calculate statistics
        control_count = len(controls)
        deviation_count = sum(1 for c in controls if c.has_deviation)
        high_confidence_count = sum(1 for c in controls if (c.final_confidence or 0) >= self.HIGH_CONFIDENCE_THRESHOLD)
        low_confidence_count = control_count - high_confidence_count
        
        report_type = scan.report_type.value if scan.report_type else "SOC2"
        company = scan.company or "Unknown"
        product = scan.product or "services"
        coverage_start = f"{scan.coverage_start:%Y-%m-%d}" if scan.coverage_start else "N/A"
        coverage_end = f"{scan.coverage_end:%Y-%m-%d}" if scan.coverage_end else "N/A"
        
        # C26: Service description
        self._safe_write_cell(ws, 26, 3, self._call_gpt_safe(
            'excel_export_service_description',
            extractor_name="excel_export_service_desc",
            report_type=report_type,
            company=company,
            product=product,
            coverage_start=coverage_start,
            coverage_end=coverage_end
        ))
        
        # C27: Transaction materiality
        self._safe_write_cell(ws, 27, 3, self._call_gpt_safe(
            'excel_export_transaction_materiality',
            extractor_name="excel_export_materiality",
            report_type=report_type,
            company=company,
            product=product,
            control_count=control_count
        ))
        
        # C28: Interaction with Solidigm
        self._safe_write_cell(ws, 28, 3, self._call_gpt_safe(
            'excel_export_interaction',
            extractor_name="excel_export_interaction",
            company=company,
            product=product,
            report_type=report_type
        ))
        
        # C29: Appropriateness evaluation
        self._safe_write_cell(ws, 29, 3, self._call_gpt_safe(
            'excel_export_appropriateness',
            extractor_name="excel_export_appropriateness",
            report_type=report_type,
            company=company,
            product=product,
            control_count=control_count,
            deviation_count=deviation_count,
            high_confidence_count=high_confidence_count
        ))
        
        # C30: Sufficiency evaluation
        coverage_summary = f"{high_confidence_count}/{control_count} high confidence"
        self._safe_write_cell(ws, 30, 3, self._call_gpt_safe(
            'excel_export_sufficiency',
            extractor_name="excel_export_sufficiency",
            report_type=report_type,
            company=company,
            product=product,
            control_count=control_count,
            high_confidence_count=high_confidence_count,
            deviation_count=deviation_count,
            coverage_summary=coverage_summary
        ))
        
        # C31: Exceptions summary
        exceptions_list = "\n".join([
            f"- {c.control_id}: {c.deviation_desc[:100]}"
            for c in controls if c.has_deviation and c.deviation_desc
        ][:10])  # Limit to 10 exceptions
        
        if deviation_count > 0:
            self._safe_write_cell(ws, 31, 3, self._call_gpt_safe(
                'excel_export_exceptions_summary',
                extractor_name="excel_export_exceptions",
                control_count=control_count,
                deviation_count=deviation_count,
                exceptions_list=exceptions_list or "None listed"
            ))
        else:
            self._safe_write_cell(ws, 31, 3, "No exceptions noted.")
        
        # C32: Management assertion check (standard text)
        self._safe_write_cell(ws, 32, 3, "Management's assertion regarding the design and operating effectiveness of controls has been reviewed.")
        
        # C33: Further evaluation items
        missing_data_summary = f"{low_confidence_count} low confidence controls"
        self._safe_write_cell(ws, 33, 3, self._call_gpt_safe(
            'excel_export_further_evaluation',
            extractor_name="excel_export_further_eval",
            deviation_count=deviation_count,
            low_confidence_count=low_confidence_count,
            missing_data_summary=missing_data_summary
        ))
        
        self.logger.info(f"[EXCEL_EXPORT] GPT descriptions generated for C26-C33")
    
    def _call_gpt_safe(self, prompt_key: str, extractor_name: str, **kwargs) -> str:
        """
        Call GPT with error handling, return empty string on failure.
        Logs warnings for failures but doesn't raise exceptions.
        """
        try:
            prompt_template = GPT_PROMPTS.get(prompt_key, "")
            if not prompt_template:
                self.logger.warning(f"[EXCEL_EXPORT] Prompt key '{prompt_key}' not found in GPT_PROMPTS")
                return ""
            
            prompt = prompt_template.format(**kwargs)
            response = gpt_extract(prompt, extractor_name)
            
            # Clean response
            response = response.strip()
            self.logger.debug(f"[EXCEL_EXPORT] GPT call '{extractor_name}' succeeded: {len(response)} chars")
            return response
            
        except Exception as e:
            self.logger.warning(
                f"[EXCEL_EXPORT] GPT call '{extractor_name}' failed: {e}. Leaving cell blank."
            )
            return ""
    
    def _populate_control_objectives(self, ws, controls: List[Control]) -> None:
        """
        Populate Control Objectives tab with high-confidence controls (≥0.7).
        Starting row 9, columns 1-5, with borders.
        """
        try:
            high_conf_controls = [
                c for c in controls
                if (c.final_confidence or 0) >= self.HIGH_CONFIDENCE_THRESHOLD
            ]
            
            self.logger.info(
                f"[EXCEL_EXPORT] Writing {len(high_conf_controls)} high-confidence controls "
                f"(threshold={self.HIGH_CONFIDENCE_THRESHOLD})"
            )
            
            row = 9
            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            
            for control in high_conf_controls:
                self._safe_write_cell(ws, row, 1, control.control_id or "")
                self._safe_write_cell(ws, row, 2, control.control_desc or "")
                self._safe_write_cell(ws, row, 3, control.control_test or "")
                self._safe_write_cell(ws, row, 4, control.control_test_results or "")
                self._safe_write_cell(ws, row, 5, round(control.final_confidence, 2) if control.final_confidence else "")
                
                # Apply borders
                for col in range(1, 6):
                    cell = ws.cell(row, col)
                    if not isinstance(cell, MergedCell):
                        cell.border = thin_border
                
                row += 1
            
            self.logger.info(f"[EXCEL_EXPORT] Control objectives populated: {row-9} rows written")
            
        except Exception as e:
            self.logger.error(f"[EXCEL_EXPORT] Error populating control objectives: {e}\n{traceback.format_exc()}")
            raise
    
    def _populate_exceptions(self, ws, controls: List[Control]) -> None:
        """
        Populate Exceptions tab with controls that have deviations.
        Starting row 9, columns 1-6, with borders.
        """
        try:
            exception_controls = [c for c in controls if c.has_deviation]
            
            self.logger.info(f"[EXCEL_EXPORT] Writing {len(exception_controls)} controls with deviations")
            
            row = 9
            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            
            for control in exception_controls:
                self._safe_write_cell(ws, row, 1, control.control_id or "")
                self._safe_write_cell(ws, row, 2, control.control_desc or "")
                self._safe_write_cell(ws, row, 3, control.control_test or "")
                self._safe_write_cell(ws, row, 4, control.control_test_results or "")
                self._safe_write_cell(ws, row, 5, control.deviation_desc or "")
                self._safe_write_cell(ws, row, 6, round(control.final_confidence, 2) if control.final_confidence else "")
                
                # Apply borders
                for col in range(1, 7):
                    cell = ws.cell(row, col)
                    if not isinstance(cell, MergedCell):
                        cell.border = thin_border
                
                row += 1
            
            self.logger.info(f"[EXCEL_EXPORT] Exceptions populated: {row-9} rows written")
            
        except Exception as e:
            self.logger.error(f"[EXCEL_EXPORT] Error populating exceptions: {e}\n{traceback.format_exc()}")
            raise
    
    def _populate_cuecs(self, ws, cuecs: List[CUEC]) -> None:
        """
        Populate CUECs tab with high-confidence CUECs (≥0.7).
        Starting row 8, columns 1-5, with borders.
        """
        try:
            high_conf_cuecs = [
                c for c in cuecs
                if (c.cuec_confidence or 0) >= self.HIGH_CONFIDENCE_THRESHOLD
            ]
            
            self.logger.info(
                f"[EXCEL_EXPORT] Writing {len(high_conf_cuecs)} high-confidence CUECs "
                f"(threshold={self.HIGH_CONFIDENCE_THRESHOLD})"
            )
            
            row = 8
            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            
            for cuec in high_conf_cuecs:
                self._safe_write_cell(ws, row, 1, cuec.cuec_description or "")
                self._safe_write_cell(ws, row, 2, cuec.cuec_tsc_id or "")
                self._safe_write_cell(ws, row, 3, cuec.cuec_coso_id or "")
                self._safe_write_cell(ws, row, 4, cuec.cuec_justification or "")
                self._safe_write_cell(ws, row, 5, round(cuec.cuec_confidence, 2) if cuec.cuec_confidence else "")
                
                # Apply borders
                for col in range(1, 6):
                    cell = ws.cell(row, col)
                    if not isinstance(cell, MergedCell):
                        cell.border = thin_border
                
                row += 1
            
            self.logger.info(f"[EXCEL_EXPORT] CUECs populated: {row-8} rows written")
            
        except Exception as e:
            self.logger.error(f"[EXCEL_EXPORT] Error populating CUECs: {e}\n{traceback.format_exc()}")
            raise
    
    def _populate_subservice_orgs(self, ws, suborgs: List[SubserviceOrg]) -> None:
        """
        Populate Subservice Orgs tab with high and low confidence organizations.
        Starting row 9, columns 1-5, separate sections for high/low confidence.
        """
        try:
            high_conf_orgs = [
                s for s in suborgs
                if (s.confidence or 0) >= self.HIGH_CONFIDENCE_THRESHOLD
            ]
            low_conf_orgs = [
                s for s in suborgs
                if (s.confidence or 0) < self.HIGH_CONFIDENCE_THRESHOLD
            ]
            
            self.logger.info(
                f"[EXCEL_EXPORT] Writing {len(high_conf_orgs)} high-confidence and "
                f"{len(low_conf_orgs)} low-confidence subservice orgs"
            )
            
            row = 9
            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            
            # High confidence section
            for org in high_conf_orgs:
                self._safe_write_cell(ws, row, 1, org.name or "")
                self._safe_write_cell(ws, row, 2, org.third_party_description or "")
                self._safe_write_cell(ws, row, 3, org.source_context or "")
                self._safe_write_cell(ws, row, 4, self._format_control_ids(org.third_party_controls))
                self._safe_write_cell(ws, row, 5, round(org.confidence, 2) if org.confidence else "")
                
                # Apply borders
                for col in range(1, 6):
                    cell = ws.cell(row, col)
                    if not isinstance(cell, MergedCell):
                        cell.border = thin_border
                
                row += 1
            
            # Add separator row if we have low confidence orgs
            if low_conf_orgs:
                row += 1
                self._safe_write_cell(ws, row, 1, "--- Low Confidence Orgs ---")
                row += 1
                
                # Low confidence section
                for org in low_conf_orgs:
                    self._safe_write_cell(ws, row, 1, org.name or "")
                    self._safe_write_cell(ws, row, 2, org.third_party_description or "")
                    self._safe_write_cell(ws, row, 3, org.source_context or "")
                    self._safe_write_cell(ws, row, 4, self._format_control_ids(org.third_party_controls))
                    self._safe_write_cell(ws, row, 5, round(org.confidence, 2) if org.confidence else "")
                    
                    # Apply borders
                    for col in range(1, 6):
                        cell = ws.cell(row, col)
                        if not isinstance(cell, MergedCell):
                            cell.border = thin_border
                    
                    row += 1
            
            self.logger.info(f"[EXCEL_EXPORT] Subservice orgs populated: {row-9} rows written")
            
        except Exception as e:
            self.logger.error(f"[EXCEL_EXPORT] Error populating subservice orgs: {e}\n{traceback.format_exc()}")
            raise
    
    def _format_control_ids(self, control_ids) -> str:
        """Format control_ids JSON array as comma-separated string."""
        if not control_ids:
            return ""
        
        try:
            if isinstance(control_ids, list):
                # Extract control_id from dict objects if present
                ids = []
                for item in control_ids:
                    if isinstance(item, dict) and 'control_id' in item:
                        ids.append(item['control_id'])
                    elif isinstance(item, str):
                        ids.append(item)
                return ", ".join(ids[:10])  # Limit to 10 for readability
            elif isinstance(control_ids, str):
                return control_ids
            return str(control_ids)
        except Exception as e:
            self.logger.warning(f"[EXCEL_EXPORT] Error formatting control_ids: {e}")
            return ""
    
    def _populate_conclusion(self, ws, scan: Scan) -> None:
        """
        Populate Conclusion tab with executive summary.
        Writes to named cell 'Exec_Summary'.
        """
        try:
            # Get executive summary text
            if scan.executive_summary:
                # Handle both JSON and plain text formats
                if isinstance(scan.executive_summary, dict):
                    summary_text = scan.executive_summary.get('summary', str(scan.executive_summary))
                else:
                    summary_text = str(scan.executive_summary)
            else:
                summary_text = ""
                self.logger.warning(f"[EXCEL_EXPORT] No executive summary found for scan {scan.id}")
            
            # Try common cell locations for executive summary
            written = False
            for cell_ref in ['B5', 'A5', 'C5', 'B2', 'A1', 'B1', 'C1']:
                try:
                    cell = ws[cell_ref]
                    if not isinstance(cell, MergedCell):
                        cell.value = summary_text
                        self.logger.info(f"[EXCEL_EXPORT] Executive summary written to cell {cell_ref}")
                        written = True
                        break
                except Exception as e:
                    self.logger.debug(f"[EXCEL_EXPORT] Could not write to {cell_ref}: {e}")
                    continue
            
            if not written:
                self.logger.warning(
                    f"[EXCEL_EXPORT] Could not find writable cell for executive summary"
                )
            
            self.logger.info(
                f"[EXCEL_EXPORT] Executive summary processed: {len(summary_text)} chars"
            )
            
        except Exception as e:
            self.logger.error(f"[EXCEL_EXPORT] Error populating conclusion: {e}\n{traceback.format_exc()}")
            # Don't raise - continue with export even if conclusion fails
            self.logger.warning(f"[EXCEL_EXPORT] Continuing export despite conclusion error")
