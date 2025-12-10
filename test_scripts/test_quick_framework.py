"""
Quick Test Script - Framework Mapping Validation
=================================================

Quick test mode for validating framework mapping across SOC1 and SOC2 reports.
Extracts first 10 controls only to speed up testing (5-10 minutes vs 30+ minutes).

Usage:
    # Test SOC2 report
    python test_scripts\test_quick_framework.py --soc2 "soc2_reports\Okta.pdf"
    
    # Test SOC1 report  
    python test_scripts\test_quick_framework.py --soc1 "soc1_reports\SAP ARIBA 2024.09.30 SOC 1 Type 2 Report EV Final SECURED.pdf"
    
    # Test both
    python test_scripts\test_quick_framework.py --soc2 "soc2_reports\Okta.pdf" --soc1 "soc1_reports\SAP ARIBA 2024.09.30 SOC 1 Type 2 Report EV Final SECURED.pdf"

What it does:
1. Uploads PDF with report type
2. Extracts first 10 controls only (quick mode)
3. Validates framework mappings
4. Displays results summary

Expected duration: 5-10 minutes per report
"""

import sys
import os
import json
import time
import argparse
import requests
from pathlib import Path
from typing import Dict, List, Any

# Add backend to path
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

API_URL = "http://localhost:8000"

class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'


def print_header(title: str):
    print(f"\n{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title.center(80)}{Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * 80}{Colors.RESET}\n")


def print_success(message: str):
    print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")


def print_error(message: str):
    print(f"{Colors.RED}✗ {message}{Colors.RESET}")


def print_info(message: str):
    print(f"{Colors.BLUE}ℹ {message}{Colors.RESET}")


def print_warning(message: str):
    print(f"{Colors.YELLOW}⚠ {message}{Colors.RESET}")


def upload_and_analyze(pdf_path: str, report_type: str) -> Dict[str, Any]:
    """Upload PDF and run quick analysis (10 controls only)"""
    
    print_header(f"Quick Test: {os.path.basename(pdf_path)} ({report_type})")
    
    if not os.path.exists(pdf_path):
        print_error(f"File not found: {pdf_path}")
        return None
    
    print_info(f"Uploading: {pdf_path}")
    print_info(f"Report Type: {report_type}")
    print_info("Quick Mode: Extracting first 10 controls only")
    
    # Upload with report type
    with open(pdf_path, 'rb') as f:
        files = {'file': f}
        data = {'report_type': report_type}
        
        try:
            response = requests.post(f"{API_URL}/analyze/", files=files, data=data)
            
            if response.status_code != 200:
                print_error(f"Upload failed: {response.text}")
                return None
                
            job_id = response.json()['job_id']
            print_success(f"Upload successful! Job ID: {job_id}")
            
        except Exception as e:
            print_error(f"Upload error: {e}")
            return None
    
    # Monitor progress
    print_info("Monitoring extraction progress...")
    start_time = time.time()
    last_progress = -1
    
    while time.time() - start_time < 600:  # 10 minute timeout
        try:
            status_resp = requests.get(f"{API_URL}/analyze/status/{job_id}")
            status = status_resp.json()
            
            # Check for confirmation needed
            if status.get('awaiting_confirmation'):
                detection = status.get('detection_result', {})
                print_warning(f"Report type detection: {detection.get('detected_type')} (confidence: {detection.get('confidence', 0)*100:.1f}%)")
                print_info("Auto-confirming detection...")
                
                # Auto-confirm
                confirm_resp = requests.post(
                    f"{API_URL}/analyze/confirm/{job_id}",
                    json={"confirmed_type": report_type}
                )
                if confirm_resp.status_code == 200:
                    print_success("Detection confirmed, continuing...")
                continue
            
            # Show progress
            progress = status.get('progress', 0)
            if progress != last_progress:
                print(f"Progress: {progress}%", end='\r')
                last_progress = progress
            
            # Check if done
            if status.get('done'):
                elapsed = time.time() - start_time
                print(f"\nProgress: 100%")
                print_success(f"Extraction complete in {elapsed:.1f} seconds")
                
                # Get scan ID
                if 'scan_id' in status:
                    scan_id = status['scan_id']
                    return {'job_id': job_id, 'scan_id': scan_id, 'status': status}
                break
            
            # Check for errors
            if status.get('error'):
                print_error(f"Extraction failed: {status['error']}")
                return None
            
            time.sleep(2)
            
        except Exception as e:
            print_error(f"Monitoring error: {e}")
            time.sleep(2)
    
    print_error("Extraction timed out")
    return None


def validate_framework_mappings(scan_id: int, expected_report_type: str) -> Dict[str, Any]:
    """Validate framework mappings for a scan"""
    
    print_info(f"Validating framework mappings for scan {scan_id}...")
    
    # Import after sys.path is set
    from backend.app.database import SessionLocal
    from backend.app.models import Scan, Control
    
    db = SessionLocal()
    try:
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            print_error(f"Scan {scan_id} not found in database")
            return None
        
        controls = db.query(Control).filter(Control.scan_id == scan_id).all()
        
        print_info(f"Found {len(controls)} controls")
        
        # Analyze mappings
        frameworks_used = {}
        controls_with_mappings = 0
        controls_without_mappings = 0
        
        for control in controls:
            if control.framework_mappings:
                controls_with_mappings += 1
                for fw_name in control.framework_mappings.keys():
                    frameworks_used[fw_name] = frameworks_used.get(fw_name, 0) + 1
            else:
                controls_without_mappings += 1
        
        # Expected frameworks
        expected_frameworks = {
            'SOC2': {'TSC', 'COSO'},
            'SOC1': {'FINANCIAL_ASSERTIONS', 'COSO_ICFR'}
        }
        
        expected = expected_frameworks.get(expected_report_type, set())
        actual = set(frameworks_used.keys())
        
        # Results
        results = {
            'scan_id': scan_id,
            'company': scan.company_name,
            'report_type': scan.report_type,
            'control_count': len(controls),
            'controls_with_mappings': controls_with_mappings,
            'controls_without_mappings': controls_without_mappings,
            'frameworks_used': frameworks_used,
            'expected_frameworks': expected,
            'actual_frameworks': actual,
            'validation_passed': len(actual) > 0 and controls_with_mappings / len(controls) > 0.7
        }
        
        return results
        
    finally:
        db.close()


def print_validation_results(results: Dict[str, Any]):
    """Print formatted validation results"""
    
    print(f"\n{Colors.BOLD}Validation Results:{Colors.RESET}")
    print(f"  Scan ID: {results['scan_id']}")
    print(f"  Company: {results['company']}")
    print(f"  Report Type: {results['report_type']}")
    print(f"  Controls: {results['control_count']}")
    print(f"  With Mappings: {results['controls_with_mappings']} ({results['controls_with_mappings']/max(results['control_count'],1)*100:.1f}%)")
    print(f"  Without Mappings: {results['controls_without_mappings']}")
    
    print(f"\n{Colors.BOLD}Frameworks Used:{Colors.RESET}")
    for fw, count in results['frameworks_used'].items():
        print(f"  {fw}: {count} controls")
    
    print(f"\n{Colors.BOLD}Framework Validation:{Colors.RESET}")
    expected = results['expected_frameworks']
    actual = results['actual_frameworks']
    
    # Check for expected frameworks
    missing = expected - actual
    unexpected = actual - expected
    
    if not missing and not unexpected and results['validation_passed']:
        print_success("Framework mappings are correct!")
        return True
    else:
        if missing:
            print_error(f"Missing expected frameworks: {missing}")
        if unexpected:
            print_warning(f"Unexpected frameworks found: {unexpected}")
        if not results['validation_passed']:
            print_error(f"Coverage too low: {results['controls_with_mappings']/max(results['control_count'],1)*100:.1f}%")
        return False


def main():
    parser = argparse.ArgumentParser(description='Quick framework mapping test')
    parser.add_argument('--soc2', help='Path to SOC2 PDF report')
    parser.add_argument('--soc1', help='Path to SOC1 PDF report')
    
    args = parser.parse_args()
    
    if not args.soc2 and not args.soc1:
        print_error("Please specify --soc2 and/or --soc1 with PDF path")
        print("\nAvailable reports:")
        print("\nSOC2 Reports (soc2_reports/):")
        soc2_dir = Path("soc2_reports")
        if soc2_dir.exists():
            for pdf in soc2_dir.glob("*.pdf"):
                print(f"  - {pdf.name}")
        
        print("\nSOC1 Reports (soc1_reports/):")
        soc1_dir = Path("soc1_reports")
        if soc1_dir.exists():
            for pdf in soc1_dir.glob("*.pdf"):
                print(f"  - {pdf.name}")
        
        return 1
    
    print_header("Framework Mapping Quick Test")
    print_info("This test extracts first 10 controls only for fast validation")
    print_info("Full extraction can be done after validation succeeds")
    
    all_passed = True
    
    # Test SOC2
    if args.soc2:
        result = upload_and_analyze(args.soc2, "SOC2")
        if result:
            validation = validate_framework_mappings(result['scan_id'], "SOC2")
            if validation:
                passed = print_validation_results(validation)
                all_passed = all_passed and passed
            else:
                all_passed = False
        else:
            all_passed = False
    
    # Test SOC1  
    if args.soc1:
        result = upload_and_analyze(args.soc1, "SOC1")
        if result:
            validation = validate_framework_mappings(result['scan_id'], "SOC1")
            if validation:
                passed = print_validation_results(validation)
                all_passed = all_passed and passed
            else:
                all_passed = False
        else:
            all_passed = False
    
    # Summary
    print_header("Test Summary")
    if all_passed:
        print_success("✓ All tests passed!")
        print_info("You can now run full extractions with confidence")
        return 0
    else:
        print_error("✗ Some tests failed")
        print_info("Check logs for details:")
        print_info("  - data/logs/control_extractor.log")
        print_info("  - data/logs/cuec_extractor.log")
        return 1


if __name__ == "__main__":
    sys.exit(main())
