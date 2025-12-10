#!/usr/bin/env python3
"""
Direct PDF Analysis Script (Non-API Approach)

This script runs SOC2 PDF analysis directly without using the FastAPI server,
background threading, or Redis job queues. This is a simpler, more stable approach
that avoids threading-related issues like hanging processes and high CPU usage.

Usage:
    python run_analysis.py <path_to_pdf>
    python run_analysis.py soc2_reports/Okta.pdf
    python run_analysis.py --list-reports  # List available reports
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path

# Add backend directory to Python path
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.analyze import analyze_pdf_file
from app.explicit_sql_insert import insert_extracted_data


def setup_logging(verbose=False):
    """Configure logging for the analysis run."""
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def progress_printer(percent, status=None):
    """Simple progress callback that prints to console."""
    if status:
        print(f"[{percent:3d}%] {status}")
    else:
        print(f"[{percent:3d}%]")


def checklist_printer(checklist):
    """Print checklist status to console."""
    print("\n=== Extraction Checklist ===")
    for item in checklist:
        name = item.get('name', 'unknown')
        status = item.get('status', 'pending')
        icon = {
            'pending': '⏳',
            'done': '✅',
            'partial': '⚠️',
            'error': '❌',
            'done_with_warnings': '⚠️'
        }.get(status, '❓')
        print(f"{icon} {name}: {status}")
    print("=" * 30)


def list_available_reports():
    """List PDF files in the soc2_reports directory."""
    reports_dir = SCRIPT_DIR / "soc2_reports"
    if not reports_dir.exists():
        print(f"Reports directory not found: {reports_dir}")
        return
    
    pdf_files = list(reports_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {reports_dir}")
        return
    
    print(f"\nAvailable reports in {reports_dir}:")
    for i, pdf_file in enumerate(sorted(pdf_files), 1):
        file_size = pdf_file.stat().st_size / (1024 * 1024)  # Convert to MB
        print(f"  {i}. {pdf_file.name} ({file_size:.2f} MB)")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Run SOC2 PDF analysis directly without API/threading overhead"
    )
    parser.add_argument(
        "pdf_path",
        nargs='?',
        help="Path to the PDF file to analyze"
    )
    parser.add_argument(
        "--list-reports",
        action="store_true",
        help="List available PDF reports in soc2_reports/ directory"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging"
    )
    parser.add_argument(
        "--no-db-insert",
        action="store_true",
        help="Skip automatic database insertion after analysis"
    )
    parser.add_argument(
        "--output-dir",
        default="data/json",
        help="Output directory for JSON results (default: data/json)"
    )
    
    args = parser.parse_args()
    
    # Handle --list-reports
    if args.list_reports:
        list_available_reports()
        return 0
    
    # Require PDF path
    if not args.pdf_path:
        parser.print_help()
        print("\nError: Please provide a PDF file path or use --list-reports")
        return 1
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    # Validate PDF path
    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        # Try relative to soc2_reports directory
        alt_path = SCRIPT_DIR / "soc2_reports" / args.pdf_path
        if alt_path.exists():
            pdf_path = alt_path
        else:
            logger.error(f"PDF file not found: {args.pdf_path}")
            return 1
    
    logger.info(f"Starting analysis of: {pdf_path}")
    logger.info(f"File size: {pdf_path.stat().st_size / (1024 * 1024):.2f} MB")
    
    # Clean up previous run artifacts
    logger.info("Cleaning previous run artifacts...")
    
    # Clear checkpoint file
    checkpoint_path = SCRIPT_DIR / "data/json/_extraction_checkpoint.json"
    if checkpoint_path.exists():
        try:
            os.remove(checkpoint_path)
        except Exception as e:
            logger.warning(f"Could not clear checkpoint: {e}")
    
    # Clear previous JSON results
    json_files_to_clear = [
        "data/json/section_results.json",
        "data/json/combined_result.json",
        "data/json/control_result.json",
        "data/json/cuec_result.json",
        "data/json/subservice_orgs_result.json",
        "data/json/product_result.json",
        "data/json/auditor_result.json",
        "data/json/company_result.json",
        "data/json/report_date_result.json",
        "data/json/coverage_period_result.json",
    ]
    for json_file in json_files_to_clear:
        json_path = SCRIPT_DIR / json_file
        if json_path.exists():
            try:
                os.remove(json_path)
            except Exception as e:
                logger.warning(f"Could not clear {json_file}: {e}")
    
    # Clear log files (truncate to keep file structure)
    log_dir = SCRIPT_DIR / "data/logs"
    if log_dir.exists():
        try:
            for log_file in log_dir.glob("*.log"):
                with open(log_file, 'w') as f:
                    pass
        except Exception as e:
            logger.warning(f"Could not clear logs: {e}")
    
    logger.info("Cleanup complete - starting fresh analysis")
    
    try:
        # Run the analysis directly (no threading, no API, no Redis)
        results = analyze_pdf_file(
            str(pdf_path),
            output_json_path=f"{args.output_dir}/section_results.json",
            progress_callback=progress_printer,
            checklist_callback=checklist_printer
        )
        
        logger.info("\n" + "="*60)
        logger.info("Analysis completed successfully!")
        logger.info("="*60)
        
        # Print summary
        if isinstance(results, dict):
            controls_count = len(results.get('controls', []))
            cuecs_count = len(results.get('cuecs', []))
            suborgs_count = len(results.get('subservice_orgs', []))
            
            print("\n=== Analysis Results Summary ===")
            print(f"Controls extracted: {controls_count}")
            print(f"CUECs extracted: {cuecs_count}")
            print(f"Subservice Organizations: {suborgs_count}")
            print(f"Company: {results.get('company', {}).get('name', 'N/A')}")
            print(f"Auditor: {results.get('auditor', {}).get('name', 'N/A')}")
            print(f"Product: {results.get('product', {}).get('product', 'N/A')}")
            print("="*30)
        
        # Save combined results
        combined_path = SCRIPT_DIR / args.output_dir / "combined_result.json"
        combined_path.parent.mkdir(parents=True, exist_ok=True)
        with open(combined_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"Combined results saved to: {combined_path}")
        
        # Insert into database (unless disabled)
        if not args.no_db_insert:
            logger.info("\nInserting results into database...")
            try:
                summary = insert_extracted_data(str(combined_path))
                logger.info("Database insertion completed successfully!")
                logger.info(f"Summary: {summary}")
            except Exception as db_err:
                logger.error(f"Database insertion failed: {db_err}")
                logger.error("Analysis results are still available in JSON files")
                return 2
        else:
            logger.info("Skipping database insertion (--no-db-insert flag)")
        
        logger.info(f"\nAll results available in: {SCRIPT_DIR / args.output_dir}")
        return 0
        
    except KeyboardInterrupt:
        logger.warning("\nAnalysis interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
