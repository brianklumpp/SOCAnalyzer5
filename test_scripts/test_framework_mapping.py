"""
Framework Mapping Integration Test
===================================

Tests the unified extractor's dynamic framework mapping across report types.

Usage:
    # Test specific scan from database
    python test_framework_mapping.py --scan-id 123
    
    # Test most recent scan
    python test_framework_mapping.py --latest
    
    # Test multiple report types
    python test_framework_mapping.py --soc1 "path/to/soc1.pdf" --soc2 "path/to/soc2.pdf"

Tests:
    1. Framework loading based on report type
    2. Control framework mappings (framework_mappings JSONB)
    3. Primary framework selection
    4. Multi-framework coverage
    5. CUEC framework mappings
"""

import sys
import os
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any
from collections import Counter

# Add backend to path
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.database import get_db
from app.models import Scan, Control, CUEC
from app.config import DATABASE_URL


class Colors:
    """ANSI color codes"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'


def print_header(title: str):
    """Print formatted header"""
    print(f"\n{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title.center(80)}{Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * 80}{Colors.RESET}\n")


def print_section(title: str):
    """Print section header"""
    print(f"\n{Colors.BOLD}{Colors.YELLOW}► {title}{Colors.RESET}")
    print(f"{Colors.YELLOW}{'-' * 70}{Colors.RESET}")


def print_success(message: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")


def print_error(message: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {message}{Colors.RESET}")


def print_info(message: str):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ {message}{Colors.RESET}")


def print_warning(message: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {message}{Colors.RESET}")


def get_latest_scan(db) -> Scan:
    """Get the most recent scan from database"""
    return db.query(Scan).order_by(Scan.created_at.desc()).first()


def get_scan_by_id(db, scan_id: int) -> Scan:
    """Get scan by ID"""
    return db.query(Scan).filter(Scan.id == scan_id).first()


def analyze_framework_mappings(scan: Scan, controls: List[Control], cuecs: List[CUEC]) -> Dict[str, Any]:
    """Analyze framework mappings for a scan"""
    
    results = {
        'scan_id': scan.id,
        'company_name': scan.company_name,
        'report_type': scan.report_type,
        'control_count': len(controls),
        'cuec_count': len(cuecs),
        'controls_with_mappings': 0,
        'controls_without_mappings': 0,
        'cuecs_with_mappings': 0,
        'cuecs_without_mappings': 0,
        'frameworks_used': Counter(),
        'primary_frameworks': Counter(),
        'avg_frameworks_per_control': 0,
        'issues': []
    }
    
    # Analyze controls
    total_framework_count = 0
    for control in controls:
        if control.framework_mappings:
            results['controls_with_mappings'] += 1
            fw_mappings = control.framework_mappings
            
            # Count frameworks
            num_frameworks = len(fw_mappings)
            total_framework_count += num_frameworks
            
            # Count each framework used
            for fw_name in fw_mappings.keys():
                results['frameworks_used'][fw_name] += 1
            
            # Count primary framework
            if control.primary_framework:
                results['primary_frameworks'][control.primary_framework] += 1
        else:
            results['controls_without_mappings'] += 1
            results['issues'].append(f"Control {control.control_id} has no framework mappings")
    
    # Calculate average
    if results['controls_with_mappings'] > 0:
        results['avg_frameworks_per_control'] = total_framework_count / results['controls_with_mappings']
    
    # Analyze CUECs
    for cuec in cuecs:
        if cuec.framework_mappings:
            results['cuecs_with_mappings'] += 1
        else:
            results['cuecs_without_mappings'] += 1
            results['issues'].append(f"CUEC {cuec.cuec_id} has no framework mappings")
    
    return results


def validate_frameworks_for_report_type(report_type: str, frameworks_used: Counter, issues: List[str]) -> bool:
    """Validate that correct frameworks are used for report type"""
    
    expected_frameworks = {
        'SOC2': {'TSC', 'COSO', 'ISO27001', 'NIST'},
        'SOC1': {'FINANCIAL_ASSERTIONS', 'COSO_ICFR', 'ISAE3402', 'CSAE3416', 'AAF0106', 'GS007'},
        'COMBINED': {'TSC', 'COSO', 'ISO27001', 'NIST', 'FINANCIAL_ASSERTIONS', 'COSO_ICFR', 'ISAE3402', 'CSAE3416', 'AAF0106', 'GS007'}
    }
    
    expected = expected_frameworks.get(report_type, set())
    actual = set(frameworks_used.keys())
    
    # Check for unexpected frameworks
    unexpected = actual - expected
    if unexpected:
        issues.append(f"Unexpected frameworks for {report_type}: {unexpected}")
        return False
    
    # Check that at least some expected frameworks are used
    if not actual:
        issues.append(f"No frameworks found for {report_type} report")
        return False
    
    return True


def print_analysis_report(results: Dict[str, Any]):
    """Print formatted analysis report"""
    
    print_header("Framework Mapping Analysis Report")
    
    # Basic info
    print_section("Scan Information")
    print(f"Scan ID:      {results['scan_id']}")
    print(f"Company:      {results['company_name']}")
    print(f"Report Type:  {results['report_type']}")
    print(f"Controls:     {results['control_count']}")
    print(f"CUECs:        {results['cuec_count']}")
    
    # Control mappings
    print_section("Control Framework Mappings")
    print(f"With mappings:    {results['controls_with_mappings']} ({results['controls_with_mappings']/max(results['control_count'],1)*100:.1f}%)")
    print(f"Without mappings: {results['controls_without_mappings']}")
    print(f"Avg frameworks:   {results['avg_frameworks_per_control']:.2f} per control")
    
    if results['controls_with_mappings'] > 0:
        print_success(f"Framework mapping coverage: {results['controls_with_mappings']/max(results['control_count'],1)*100:.1f}%")
    else:
        print_error("No controls have framework mappings!")
    
    # CUEC mappings
    if results['cuec_count'] > 0:
        print_section("CUEC Framework Mappings")
        print(f"With mappings:    {results['cuecs_with_mappings']} ({results['cuecs_with_mappings']/results['cuec_count']*100:.1f}%)")
        print(f"Without mappings: {results['cuecs_without_mappings']}")
    
    # Frameworks used
    print_section("Frameworks Used")
    for framework, count in results['frameworks_used'].most_common():
        print(f"  {framework:20s} : {count:4d} controls ({count/max(results['control_count'],1)*100:.1f}%)")
    
    # Primary frameworks
    if results['primary_frameworks']:
        print_section("Primary Framework Distribution")
        for framework, count in results['primary_frameworks'].most_common():
            print(f"  {framework:20s} : {count:4d} controls ({count/max(results['control_count'],1)*100:.1f}%)")
    
    # Validate frameworks for report type
    validation_issues = []
    is_valid = validate_frameworks_for_report_type(
        results['report_type'], 
        results['frameworks_used'],
        validation_issues
    )
    
    print_section("Validation Results")
    if is_valid:
        print_success(f"Frameworks match expected set for {results['report_type']} report type")
    else:
        print_error(f"Framework validation failed for {results['report_type']} report type")
        for issue in validation_issues:
            print_warning(f"  • {issue}")
    
    # Issues
    if results['issues']:
        print_section(f"Issues Found ({len(results['issues'])})")
        for i, issue in enumerate(results['issues'][:10], 1):
            print(f"  {i}. {issue}")
        if len(results['issues']) > 10:
            print(f"  ... and {len(results['issues']) - 10} more issues")
    else:
        print_success("No issues found!")


def test_scan(db, scan: Scan):
    """Test framework mappings for a scan"""
    
    if not scan:
        print_error("Scan not found")
        return False
    
    print_info(f"Testing scan {scan.id}: {scan.company_name} ({scan.report_type})")
    
    # Load controls and CUECs
    controls = db.query(Control).filter(Control.scan_id == scan.id).all()
    cuecs = db.query(CUEC).filter(CUEC.scan_id == scan.id).all()
    
    # Analyze
    results = analyze_framework_mappings(scan, controls, cuecs)
    
    # Print report
    print_analysis_report(results)
    
    # Return success if no critical issues
    success = (
        results['controls_with_mappings'] > 0 and
        results['controls_with_mappings'] / max(results['control_count'], 1) > 0.8  # 80% coverage
    )
    
    return success


def test_framework_registry():
    """Test that framework registry is properly configured"""
    print_section("Testing Framework Registry")
    
    try:
        from app.frameworks.registry import FRAMEWORK_REGISTRY
        
        print_info(f"Loaded {len(FRAMEWORK_REGISTRY)} frameworks:")
        for fw_name in FRAMEWORK_REGISTRY.keys():
            print(f"  • {fw_name}")
        
        # Test framework loader
        from app.frameworks.loader import get_available_frameworks
        
        for report_type in ['SOC1', 'SOC2', 'COMBINED']:
            frameworks = get_available_frameworks(report_type=report_type)
            print_success(f"{report_type}: {len(frameworks)} frameworks loaded")
        
        return True
        
    except Exception as e:
        print_error(f"Framework registry test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description='Test framework mapping functionality')
    parser.add_argument('--scan-id', type=int, help='Test specific scan by ID')
    parser.add_argument('--latest', action='store_true', help='Test latest scan')
    parser.add_argument('--all-recent', type=int, metavar='N', help='Test N most recent scans')
    parser.add_argument('--registry', action='store_true', help='Test framework registry only')
    
    args = parser.parse_args()
    
    print_header("Framework Mapping Integration Test")
    
    # Test framework registry first
    if not test_framework_registry():
        print_error("Framework registry test failed - aborting")
        return 1
    
    if args.registry:
        print_success("Framework registry test complete!")
        return 0
    
    # Connect to database
    try:
        from app.database import SessionLocal
        db = SessionLocal()
    except Exception as e:
        print_error(f"Database connection failed: {e}")
        return 1
    
    try:
        success = True
        
        if args.scan_id:
            # Test specific scan
            scan = get_scan_by_id(db, args.scan_id)
            success = test_scan(db, scan)
            
        elif args.latest:
            # Test latest scan
            scan = get_latest_scan(db)
            success = test_scan(db, scan)
            
        elif args.all_recent:
            # Test multiple recent scans
            scans = db.query(Scan).order_by(Scan.created_at.desc()).limit(args.all_recent).all()
            print_info(f"Testing {len(scans)} most recent scans\n")
            
            results = []
            for scan in scans:
                test_result = test_scan(db, scan)
                results.append((scan, test_result))
                print("\n" + "="*80 + "\n")
            
            # Summary
            print_section("Summary")
            passed = sum(1 for _, result in results if result)
            total = len(results)
            print(f"Passed: {passed}/{total}")
            
            if passed < total:
                print_warning("Some tests failed:")
                for scan, result in results:
                    if not result:
                        print(f"  • Scan {scan.id}: {scan.company_name}")
            
            success = passed == total
        else:
            # Default: test latest
            print_info("No scan specified, testing latest scan")
            scan = get_latest_scan(db)
            success = test_scan(db, scan)
        
        if success:
            print_success("\n🎉 All tests passed!")
            return 0
        else:
            print_error("\n❌ Some tests failed")
            return 1
            
    except Exception as e:
        print_error(f"Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
