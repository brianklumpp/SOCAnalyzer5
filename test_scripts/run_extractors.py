#!/usr/bin/env python3
"""
Individual Extractor Runner
Run SOC2 extractors one at a time for better control and debugging
"""

import sys
import os
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from backend.app import config
from backend.app.extractors.company import extract_company
from backend.app.extractors.auditor import extract_auditor
from backend.app.extractors.product import extract_product
from backend.app.extractors.report_date import extract_report_date
from backend.app.extractors.coverage_period import extract_coverage_period
from backend.app.extractors.control_extractor_v2 import extract_controls_v2
from backend.app.extractors.cuec import extract_cuec
from backend.app.extractors.subservice_orgs import extract_subservice_orgs, filter_third_parties_with_gpt


class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text):
    """Print a colored header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 70}{Colors.ENDC}\n")


def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}✓{Colors.ENDC} {text}")


def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}✗{Colors.ENDC} {text}")


def print_info(text):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ{Colors.ENDC} {text}")


def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠{Colors.ENDC} {text}")


def check_prerequisites():
    """Check if required files exist"""
    print_header("Checking Prerequisites")
    
    required_files = [
        ("PDF Text", config.PDF_TXT_PATH),
        ("Sections", config.SECTION_JSON_PATH)
    ]
    
    all_good = True
    for name, path in required_files:
        if os.path.exists(path):
            print_success(f"{name}: {path}")
        else:
            print_error(f"{name} not found: {path}")
            all_good = False
    
    return all_good


def load_results(json_path):
    """Load results from JSON file"""
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            print_warning(f"Could not load {json_path}: {e}")
    return None


def display_results(json_path, result_type):
    """Display results from a JSON file"""
    data = load_results(json_path)
    if not data:
        print_warning(f"No results found in {json_path}")
        return
    
    print(f"\n{Colors.BOLD}Results:{Colors.ENDC}")
    
    if result_type == "company":
        print(f"  Company: {data.get('company', 'N/A')}")
        print(f"  Parent: {data.get('parent_company', 'N/A')}")
        print(f"  Confidence: {data.get('confidence', 'N/A')}")
    
    elif result_type == "auditor":
        print(f"  Auditor: {data.get('auditor', 'N/A')}")
        print(f"  Confidence: {data.get('confidence', 'N/A')}")
    
    elif result_type == "product":
        print(f"  Product: {data.get('product', 'N/A')}")
        print(f"  Confidence: {data.get('confidence', 'N/A')}")
    
    elif result_type == "report_date":
        print(f"  Report Date: {data.get('report_date', 'N/A')}")
    
    elif result_type == "coverage_period":
        print(f"  Type: {data.get('type', 'N/A')}")
        print(f"  Start Date: {data.get('start_date', 'N/A')}")
        print(f"  End Date: {data.get('end_date', 'N/A')}")
    
    elif result_type == "controls":
        controls = data.get('controls', [])
        print(f"  Total Controls: {len(controls)}")
        deviations = sum(1 for c in controls if c.get('has_deviation'))
        print(f"  Deviations: {deviations}")
    
    elif result_type == "cuec":
        cuecs = data.get('cuecs', [])
        print(f"  Total CUECs: {len(cuecs)}")
    
    elif result_type == "subservice_orgs":
        orgs = data.get('subservice_orgs', [])
        print(f"  Total Subservice Orgs: {len(orgs)}")
        if orgs:
            print(f"\n  Organizations:")
            for org in orgs[:10]:  # Show first 10
                print(f"    - {org.get('third_party_name', 'N/A')}")
            if len(orgs) > 10:
                print(f"    ... and {len(orgs) - 10} more")


def run_extractor(name, func, json_path, result_type):
    """Run a single extractor"""
    print_header(f"Running {name}")
    
    try:
        print_info(f"Executing {name}...")
        func()
        print_success(f"{name} completed!")
        
        # Display results
        display_results(json_path, result_type)
        
        return True
    except Exception as e:
        print_error(f"{name} failed: {e}")
        import traceback
        print(f"\n{Colors.RED}{traceback.format_exc()}{Colors.ENDC}")
        return False


def main_menu():
    """Display main menu and get user choice"""
    print_header("SOC2 Individual Extractor Runner")
    
    print(f"{Colors.BOLD}Available Extractors:{Colors.ENDC}")
    print(f"  {Colors.CYAN}1.{Colors.ENDC} Company Extractor")
    print(f"  {Colors.CYAN}2.{Colors.ENDC} Auditor Extractor")
    print(f"  {Colors.CYAN}3.{Colors.ENDC} Product Extractor")
    print(f"  {Colors.CYAN}4.{Colors.ENDC} Report Date Extractor")
    print(f"  {Colors.CYAN}5.{Colors.ENDC} Coverage Period Extractor")
    print(f"  {Colors.CYAN}6.{Colors.ENDC} Control Extractor (v2)")
    print(f"  {Colors.CYAN}7.{Colors.ENDC} CUEC Extractor")
    print(f"  {Colors.CYAN}8.{Colors.ENDC} Subservice Orgs Extractor")
    print(f"  {Colors.CYAN}9.{Colors.ENDC} Run All Extractors (Sequential)")
    print(f"  {Colors.CYAN}0.{Colors.ENDC} Exit")
    
    print()
    choice = input(f"{Colors.BOLD}Select extractor (0-9): {Colors.ENDC}").strip()
    return choice


def run_all_extractors():
    """Run all extractors in sequence"""
    print_header("Running All Extractors")
    
    extractors = [
        ("Company Extractor", extract_company, 
         str(config.JSON_DIR / "company_result.json"), "company"),
        ("Auditor Extractor", extract_auditor, 
         str(config.JSON_DIR / "auditor_result.json"), "auditor"),
        ("Product Extractor", extract_product, 
         str(config.JSON_DIR / "product_result.json"), "product"),
        ("Report Date Extractor", extract_report_date, 
         str(config.JSON_DIR / "report_date_result.json"), "report_date"),
        ("Coverage Period Extractor", extract_coverage_period, 
         str(config.JSON_DIR / "coverage_period_result.json"), "coverage_period"),
        ("Control Extractor", extract_controls_v2, 
         str(config.JSON_DIR / "control_result.json"), "controls"),
        ("CUEC Extractor", extract_cuec, 
         str(config.JSON_DIR / "cuec_result.json"), "cuec"),
        ("Subservice Orgs Extractor", extract_subservice_orgs, 
         str(config.JSON_DIR / "subservice_orgs_result.json"), "subservice_orgs"),
    ]
    
    results = []
    for name, func, json_path, result_type in extractors:
        success = run_extractor(name, func, json_path, result_type)
        results.append((name, success))
        
        if not success:
            print_warning(f"\nExtractor failed. Continue anyway? (y/n): ")
            choice = input().strip().lower()
            if choice != 'y':
                break
    
    # Summary
    print_header("Extraction Summary")
    for name, success in results:
        if success:
            print_success(name)
        else:
            print_error(name)


def main():
    """Main entry point"""
    # Setup encoding for Windows
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass
    
    # Check prerequisites
    if not check_prerequisites():
        print_error("\nMissing required files. Please run text extraction first.")
        input("\nPress Enter to exit...")
        return
    
    while True:
        choice = main_menu()
        
        if choice == '0':
            print_info("Exiting...")
            break
        
        elif choice == '1':
            run_extractor(
                "Company Extractor", 
                extract_company,
                str(config.JSON_DIR / "company_result.json"),
                "company"
            )
        
        elif choice == '2':
            run_extractor(
                "Auditor Extractor", 
                extract_auditor,
                str(config.JSON_DIR / "auditor_result.json"),
                "auditor"
            )
        
        elif choice == '3':
            run_extractor(
                "Product Extractor", 
                extract_product,
                str(config.JSON_DIR / "product_result.json"),
                "product"
            )
        
        elif choice == '4':
            run_extractor(
                "Report Date Extractor", 
                extract_report_date,
                str(config.JSON_DIR / "report_date_result.json"),
                "report_date"
            )
        
        elif choice == '5':
            run_extractor(
                "Coverage Period Extractor", 
                extract_coverage_period,
                str(config.JSON_DIR / "coverage_period_result.json"),
                "coverage_period"
            )
        
        elif choice == '6':
            run_extractor(
                "Control Extractor (v2)", 
                extract_controls_v2,
                str(config.JSON_DIR / "control_result.json"),
                "controls"
            )
        
        elif choice == '7':
            run_extractor(
                "CUEC Extractor", 
                extract_cuec,
                str(config.JSON_DIR / "cuec_result.json"),
                "cuec"
            )
        
        elif choice == '8':
            run_extractor(
                "Subservice Orgs Extractor", 
                extract_subservice_orgs,
                str(config.JSON_DIR / "subservice_orgs_result.json"),
                "subservice_orgs"
            )
        
        elif choice == '9':
            run_all_extractors()
        
        else:
            print_warning("Invalid choice. Please select 0-9.")
        
        input(f"\n{Colors.BOLD}Press Enter to continue...{Colors.ENDC}")


if __name__ == "__main__":
    main()
