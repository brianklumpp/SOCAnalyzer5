"""
Run SOC 1 validation extraction tests for CI/CD pipeline.
"""
import asyncio
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.database import get_db, init_db
from app.models import Scan, Control
from app.analyze import analyze_soc_report
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def run_extraction(pdf_path: Path, db: AsyncSession) -> dict:
    """Run extraction on a single PDF and return results."""
    print(f"\n{'='*60}")
    print(f"Processing: {pdf_path.name}")
    print(f"{'='*60}")
    
    try:
        # Run analysis
        scan_id = await analyze_soc_report(str(pdf_path))
        
        # Wait for completion
        max_wait = 300  # 5 minutes
        elapsed = 0
        while elapsed < max_wait:
            result = await db.execute(
                select(Scan).where(Scan.scan_id == scan_id)
            )
            scan = result.scalar_one_or_none()
            
            if not scan:
                return {
                    "error": f"Scan {scan_id} not found",
                    "pdf_name": pdf_path.name
                }
            
            if scan.progress_status in ["completed", "failed"]:
                break
            
            await asyncio.sleep(5)
            elapsed += 5
        
        if scan.progress_status != "completed":
            return {
                "error": f"Scan did not complete (status: {scan.progress_status})",
                "pdf_name": pdf_path.name,
                "scan_id": scan_id
            }
        
        # Fetch controls
        controls_result = await db.execute(
            select(Control).where(Control.scan_id == scan_id)
        )
        controls = controls_result.scalars().all()
        
        # Calculate metrics
        total_controls = len(controls)
        framework_breakdown = {
            "SOC1": sum(1 for c in controls if c.framework_category == "SOC1"),
            "SOC2": sum(1 for c in controls if c.framework_category == "SOC2"),
            "COMBINED": sum(1 for c in controls if c.framework_category == "COMBINED"),
            "AMBIGUOUS": sum(1 for c in controls if c.framework_category == "AMBIGUOUS"),
            "PARTIAL_EXTRACTION": sum(1 for c in controls if c.framework_category == "PARTIAL_EXTRACTION")
        }
        
        controls_with_assertions = sum(
            1 for c in controls 
            if c.financial_assertions and len(c.financial_assertions) > 0
        )
        
        total_assertions = sum(
            len(c.financial_assertions) 
            for c in controls 
            if c.financial_assertions
        )
        
        return {
            "success": True,
            "pdf_name": pdf_path.name,
            "scan_id": scan_id,
            "report_name": scan.report_name,
            "report_type": scan.report_type,
            "as_of_date": scan.as_of_date.isoformat() if scan.as_of_date else None,
            "elapsed_seconds": scan.elapsed_seconds,
            "metrics": {
                "total_controls": total_controls,
                "framework_breakdown": framework_breakdown,
                "controls_with_assertions": controls_with_assertions,
                "total_assertions": total_assertions,
                "ambiguous_count": framework_breakdown["AMBIGUOUS"],
                "partial_extraction_count": framework_breakdown["PARTIAL_EXTRACTION"]
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "pdf_name": pdf_path.name
        }


async def main():
    parser = argparse.ArgumentParser(description="Run SOC 1 validation tests")
    parser.add_argument(
        "--report-filter",
        type=str,
        default="",
        help="Filter reports by name (case-insensitive substring match)"
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output JSON file path"
    )
    args = parser.parse_args()
    
    # Initialize database
    await init_db()
    
    # Find test reports
    reports_dir = Path(__file__).parent.parent / "soc1_reports"
    pdf_files = list(reports_dir.glob("*.pdf"))
    
    if args.report_filter:
        pdf_files = [
            p for p in pdf_files 
            if args.report_filter.lower() in p.name.lower()
        ]
    
    if not pdf_files:
        print(f"❌ No PDF files found in {reports_dir}")
        sys.exit(1)
    
    print(f"Found {len(pdf_files)} test report(s)")
    
    # Run extractions
    results = []
    async for db in get_db():
        for pdf_path in pdf_files:
            result = await run_extraction(pdf_path, db)
            results.append(result)
            
            if result.get("success"):
                print(f"✅ {pdf_path.name}: {result['metrics']['total_controls']} controls")
            else:
                print(f"❌ {pdf_path.name}: {result.get('error', 'Unknown error')}")
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump({
            "test_run": {
                "timestamp": datetime.utcnow().isoformat(),
                "total_reports": len(results),
                "successful": sum(1 for r in results if r.get("success")),
                "failed": sum(1 for r in results if not r.get("success"))
            },
            "results": results
        }, f, indent=2)
    
    print(f"\n📄 Results saved to {output_path}")
    
    # Exit with error if any failed
    failed_count = sum(1 for r in results if not r.get("success"))
    if failed_count > 0:
        print(f"\n❌ {failed_count} extraction(s) failed")
        sys.exit(1)
    else:
        print(f"\n✅ All {len(results)} extraction(s) succeeded")


if __name__ == "__main__":
    asyncio.run(main())
