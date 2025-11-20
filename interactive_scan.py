#!/usr/bin/env python3
"""
Interactive SOC2 Analysis TUI (Text User Interface)

A guided, menu-driven interface for running SOC2 PDF analysis with:
- File selection from available reports
- Real-time progress tracking
- Results summary
- Database upload option
- Browser launch to view results

Usage:
    python interactive_scan.py
"""

import os
import sys
import json
import time
import asyncio
import webbrowser
from pathlib import Path
from typing import Optional, List, Dict, Any

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    # Enable ANSI escape sequences on Windows
    os.system('')


def run_async(coroutine):
    """
    Properly run async coroutine with event loop management.
    
    This wrapper fixes asyncio.run() issues on Windows Python 3.13 where
    the ProactorEventLoop is not properly cleaned up between calls,
    causing RuntimeError: Event loop is closed.
    
    Args:
        coroutine: The async coroutine to execute
        
    Returns:
        The result of the coroutine execution
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coroutine)
    finally:
        try:
            loop.close()
        except Exception:
            pass  # Ignore cleanup errors

# Add backend directory to Python path
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Configuration
ENABLE_GPT_CONFIG_SCREEN = False  # Set to True to show GPT model configuration screen


class Colors:
    """ANSI color codes for terminal output"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'


def clear_screen():
    """Clear the terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(title: str):
    """Print a formatted header"""
    width = 80
    print(f"\n{Colors.CYAN}{'=' * width}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title.center(width)}{Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * width}{Colors.RESET}\n")


def print_section(title: str):
    """Print a section header"""
    print(f"\n{Colors.BOLD}{Colors.YELLOW}► {title}{Colors.RESET}")
    print(f"{Colors.YELLOW}{'-' * 60}{Colors.RESET}")


def print_success(message: str):
    """Print a success message"""
    print(f"{Colors.GREEN}[OK] {message}{Colors.RESET}")


def print_error(message: str):
    """Print an error message"""
    print(f"{Colors.RED}[ERROR] {message}{Colors.RESET}")


def print_info(message: str):
    """Print an info message"""
    print(f"{Colors.BLUE}[INFO] {message}{Colors.RESET}")


def print_warning(message: str):
    """Print a warning message"""
    print(f"{Colors.YELLOW}[WARN] {message}{Colors.RESET}")


def prompt_yes_no(message: str, default: str = 'y') -> bool:
    """
    Prompt user for yes/no with a default option.
    
    Args:
        message: The question to ask
        default: Default response ('y' or 'n')
    
    Returns:
        True if yes, False if no
    """
    default_display = 'Y/n' if default == 'y' else 'y/N'
    response = input(f"{Colors.YELLOW}{message} ({default_display}): {Colors.RESET}").strip().lower()
    
    # If user just hits Enter, use default
    if not response:
        response = default
    
    return response == 'y'


def get_available_reports() -> List[Dict[str, Any]]:
    """Get list of available PDF reports"""
    reports_dir = SCRIPT_DIR / "soc2_reports"
    if not reports_dir.exists():
        return []
    
    reports = []
    for pdf_file in sorted(reports_dir.glob("*.pdf")):
        file_size = pdf_file.stat().st_size / (1024 * 1024)  # MB
        reports.append({
            'path': pdf_file,
            'name': pdf_file.name,
            'size_mb': file_size
        })
    
    return reports


def display_menu(title: str, options: List[str], allow_back: bool = False) -> int:
    """Display a menu and get user selection"""
    print_section(title)
    
    for i, option in enumerate(options, 1):
        print(f"  {Colors.BOLD}{i}.{Colors.RESET} {option}")
    
    if allow_back:
        print(f"  {Colors.BOLD}0.{Colors.RESET} {Colors.YELLOW}<< Back{Colors.RESET}")
    
    print()
    
    while True:
        try:
            choice = input(f"{Colors.CYAN}Enter your choice: {Colors.RESET}").strip()
            choice_num = int(choice)
            
            if allow_back and choice_num == 0:
                return 0
            
            if 1 <= choice_num <= len(options):
                return choice_num
            else:
                print_error(f"Please enter a number between 1 and {len(options)}")
        except ValueError:
            print_error("Please enter a valid number")
        except KeyboardInterrupt:
            print("\n")
            return 0


def select_pdf_file() -> Optional[Path]:
    """Interactive file selection"""
    clear_screen()
    print_header("SOC2 PDF Analysis - File Selection")
    
    reports = get_available_reports()
    
    if not reports:
        print_error("No PDF files found in soc2_reports/ directory")
        input("\nPress Enter to continue...")
        return None
    
    print_info(f"Found {len(reports)} PDF report(s)\n")
    
    options = [
        f"{report['name']:<30} ({report['size_mb']:.2f} MB)"
        for report in reports
    ]
    options.append(f"{Colors.MAGENTA}Browse for a different file...{Colors.RESET}")
    
    choice = display_menu("Select a PDF report to analyze:", options, allow_back=True)
    
    if choice == 0:
        return None
    elif choice == len(options):
        # Browse for file
        custom_path = input(f"\n{Colors.CYAN}Enter PDF file path: {Colors.RESET}").strip()
        custom_path = custom_path.strip('"').strip("'")  # Remove quotes
        
        if not custom_path:
            return None
        
        pdf_path = Path(custom_path)
        if not pdf_path.exists():
            print_error(f"File not found: {custom_path}")
            input("\nPress Enter to continue...")
            return None
        
        return pdf_path
    else:
        return reports[choice - 1]['path']


class ProgressTracker:
    """Track and display analysis progress"""
    
    def __init__(self):
        self.current_percent = 0
        self.current_status = ""
        self.checklist = []
        self.start_time = time.time()
    
    def update_progress(self, percent: int, status: Optional[str] = None):
        """Update progress bar"""
        self.current_percent = percent
        if status:
            self.current_status = status
        
        # Draw progress bar
        bar_width = 50
        filled = int(bar_width * percent / 100)
        bar = '█' * filled + '░' * (bar_width - filled)
        
        elapsed = time.time() - self.start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        
        print(f"\r{Colors.CYAN}[{bar}] {percent:3d}%{Colors.RESET} | "
              f"{Colors.YELLOW}{self.current_status:<40}{Colors.RESET} | "
              f"{Colors.BLUE}{mins:02d}:{secs:02d}{Colors.RESET}", end='', flush=True)
    
    def update_checklist(self, checklist: List[Dict[str, str]]):
        """Update extraction checklist"""
        self.checklist = checklist


def run_analysis(pdf_path: Path, tracker: ProgressTracker) -> Optional[Dict[str, Any]]:
    """Run the PDF analysis"""
    from app.analyze import analyze_pdf_file
    import os
    import shutil
    
    print_section("Running Analysis")
    print_info(f"Analyzing: {pdf_path.name}")
    print_info(f"Size: {pdf_path.stat().st_size / (1024 * 1024):.2f} MB\n")
    
    # Clean up previous run artifacts
    print_info("Cleaning previous run artifacts...")
    
    # Clear checkpoint file
    checkpoint_path = Path("data/json/_extraction_checkpoint.json")
    if checkpoint_path.exists():
        try:
            os.remove(checkpoint_path)
        except Exception as e:
            print_warning(f"Could not clear checkpoint: {e}")
    
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
        json_path = Path(json_file)
        if json_path.exists():
            try:
                os.remove(json_path)
            except Exception as e:
                print_warning(f"Could not clear {json_file}: {e}")
    
    # Clear log files (optional - comment out if you want to keep logs)
    log_dir = Path("data/logs")
    if log_dir.exists():
        try:
            for log_file in log_dir.glob("*.log"):
                # Keep the file but truncate it
                with open(log_file, 'w') as f:
                    pass
        except Exception as e:
            print_warning(f"Could not clear logs: {e}")
    
    print_success("Cleanup complete - starting fresh analysis\n")
    
    try:
        results = analyze_pdf_file(
            str(pdf_path),
            output_json_path="data/json/section_results.json",
            progress_callback=tracker.update_progress,
            checklist_callback=tracker.update_checklist
        )
        
        print()  # New line after progress bar
        print_success("Analysis completed successfully!")
        
        return results
        
    except KeyboardInterrupt:
        print("\n")
        print_warning("Analysis interrupted by user")
        return None
    except Exception as e:
        print("\n")
        print_error(f"Analysis failed: {e}")
        return None


def display_results_summary(results: Dict[str, Any]):
    """Display a formatted summary of results"""
    clear_screen()
    print_header("Analysis Results Summary")
    
    # Extract counts - handle both dict and list formats
    controls = results.get('controls', [])
    if isinstance(controls, dict):
        controls = controls.get('controls', [])
    
    cuecs = results.get('cuecs', [])
    if isinstance(cuecs, dict):
        cuecs = cuecs.get('cuecs', [])
    
    subservice_orgs = results.get('subservice_orgs', [])
    if isinstance(subservice_orgs, dict):
        subservice_orgs = subservice_orgs.get('subservice_orgs', [])
    
    # Handle company, auditor, product - they can be strings or dicts
    company = results.get('company', 'N/A')
    if isinstance(company, dict):
        company_name = company.get('name', 'N/A')
        parent_company = company.get('parent_company', 'N/A')
    else:
        company_name = company if company else 'N/A'
        parent_company = 'N/A'
    
    auditor = results.get('auditor', 'N/A')
    auditor_name = auditor.get('name', 'N/A') if isinstance(auditor, dict) else (auditor if auditor else 'N/A')
    
    product = results.get('product', 'N/A')
    product_name = product.get('product', 'N/A') if isinstance(product, dict) else (product if product else 'N/A')
    
    # Company Info
    print_section("Company Information")
    print(f"  Company Name:    {Colors.BOLD}{company_name}{Colors.RESET}")
    print(f"  Parent Company:  {parent_company}")
    print(f"  Product:         {product_name}")
    print(f"  Auditor:         {auditor_name}")
    
    # Extraction Counts
    print_section("Extraction Results")
    print(f"  Controls:               {Colors.GREEN}{Colors.BOLD}{len(controls):3d}{Colors.RESET}")
    print(f"  CUECs:                  {Colors.GREEN}{Colors.BOLD}{len(cuecs):3d}{Colors.RESET}")
    print(f"  Subservice Orgs:        {Colors.GREEN}{Colors.BOLD}{len(subservice_orgs):3d}{Colors.RESET}")
    
    # Control Details
    if controls:
        print_section("Control Breakdown")
        
        # Count by status
        status_counts = {}
        for ctrl in controls:
            status = ctrl.get('control_status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        for status, count in sorted(status_counts.items()):
            status_color = Colors.GREEN if 'pass' in status.lower() else Colors.YELLOW
            print(f"  {status:<20} {status_color}{count:3d}{Colors.RESET}")
        
        # Framework mapping
        tsc_mapped = sum(1 for c in controls if c.get('control_tsc_id'))
        coso_mapped = sum(1 for c in controls if c.get('control_coso_id'))
        
        print(f"\n  TSC Mapped:      {Colors.CYAN}{tsc_mapped:3d}{Colors.RESET} / {len(controls)}")
        print(f"  COSO Mapped:     {Colors.CYAN}{coso_mapped:3d}{Colors.RESET} / {len(controls)}")
    
    # CUEC Details
    if cuecs:
        print_section("CUEC Summary")
        framework_counts = {}
        for cuec in cuecs:
            framework = cuec.get('cuec_framework_alignment', 'unknown')
            framework_counts[framework] = framework_counts.get(framework, 0) + 1
        
        for framework, count in sorted(framework_counts.items()):
            print(f"  {framework:<20} {Colors.MAGENTA}{count:3d}{Colors.RESET}")
    
    # Subservice Orgs
    if subservice_orgs:
        print_section("Subservice Organizations")
        for i, org in enumerate(subservice_orgs[:10], 1):  # Show first 10
            confidence = org.get('third_party_confidence', 0)
            conf_color = Colors.GREEN if confidence > 0.8 else Colors.YELLOW if confidence > 0.5 else Colors.RED
            print(f"  {i:2d}. {org.get('third_party_name', 'Unknown'):<40} "
                  f"{conf_color}({confidence:.0%}){Colors.RESET}")
        
        if len(subservice_orgs) > 10:
            print(f"\n  {Colors.BLUE}... and {len(subservice_orgs) - 10} more{Colors.RESET}")
    
    print()


def upload_to_database(results: Dict[str, Any], pdf_path: Optional[Path] = None) -> bool:
    """Upload results to database"""
    print_section("Database Upload")
    
    # Save combined results first
    combined_path = SCRIPT_DIR / "data" / "json" / "combined_result.json"
    combined_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Deep sanitize to remove bytes objects before JSON serialization
        def sanitize_for_json(obj):
            """Recursively remove or convert non-JSON-serializable objects."""
            if isinstance(obj, bytes):
                # Skip bytes data (like PDF files) - they'll be loaded from pdf_path instead
                return None
            elif isinstance(obj, dict):
                sanitized = {}
                for k, v in obj.items():
                    sanitized_v = sanitize_for_json(v)
                    # Always keep the key, even if value is None (from bytes)
                    sanitized[k] = sanitized_v
                return sanitized
            elif isinstance(obj, list):
                return [sanitize_for_json(item) for item in obj]
            else:
                return obj
        
        sanitized_results = sanitize_for_json(results)
        
        with open(combined_path, 'w', encoding='utf-8') as f:
            json.dump(sanitized_results, f, indent=2, ensure_ascii=False)
        
        print_info(f"Saved combined results to: {combined_path.name}")
        
        # Import and run database insertion
        from app.explicit_sql_insert import insert_extracted_data
        
        print_info("Inserting data into database...")
        pdf_path_str = str(pdf_path) if pdf_path else None
        summary = insert_extracted_data(str(combined_path), pdf_path=pdf_path_str)
        
        print_success("Database upload completed!")
        print_info(f"Summary: {summary}")
        
        return True
        
    except Exception as e:
        print_error(f"Database upload failed: {e}")
        return False


def view_reports():
    """View available reports and select one to open"""
    from app.database import get_db
    from app.models import Scan
    from sqlalchemy.future import select
    
    clear_screen()
    print_header("Available Reports")
    
    async def get_scans():
        async for db in get_db():
            result = await db.execute(
                select(Scan).order_by(Scan.id.desc()).limit(20)
            )
            return result.scalars().all()
    
    try:
        print_info("Loading reports from database...")
        scans = run_async(get_scans())
        
        if not scans:
            print_warning("No reports found in database")
            print_info("Run 'Start New Analysis' to create a report")
            input("\nPress Enter to continue...")
            return
        
        print(f"\n{Colors.GREEN}Found {len(scans)} report(s){Colors.RESET}\n")
        
        # Display scans as menu options
        options = []
        for scan in scans:
            # Format date
            scan_date = scan.scan_date.strftime("%Y-%m-%d %H:%M") if scan.scan_date else "N/A"
            report_date = scan.report_date.strftime("%Y-%m-%d") if scan.report_date else "N/A"
            
            # Create label
            product = scan.product or "Unknown Product"
            pdf_file = f" ({scan.pdf_filename})" if scan.pdf_filename else ""
            label = f"[ID: {scan.id}] {product}{pdf_file} - Scanned: {scan_date}"
            
            options.append(label)
        
        options.append(f"{Colors.YELLOW}Return to Main Menu{Colors.RESET}")
        
        choice = display_menu("Select a report to open:", options)
        
        if choice == 0 or choice == len(options):
            return
        
        # Get selected scan
        selected_scan = scans[choice - 1]
        
        # Show scan details
        clear_screen()
        print_header(f"Report Details - Scan ID {selected_scan.id}")
        
        print(f"{Colors.CYAN}Product:{Colors.RESET} {selected_scan.product or 'N/A'}")
        print(f"{Colors.CYAN}PDF File:{Colors.RESET} {selected_scan.pdf_filename or 'N/A'}")
        print(f"{Colors.CYAN}Scan Date:{Colors.RESET} {selected_scan.scan_date or 'N/A'}")
        print(f"{Colors.CYAN}Report Date:{Colors.RESET} {selected_scan.report_date or 'N/A'}")
        print(f"{Colors.CYAN}Auditor:{Colors.RESET} {selected_scan.auditor or 'N/A'}")
        print(f"{Colors.CYAN}Coverage:{Colors.RESET} {selected_scan.coverage_start or 'N/A'} to {selected_scan.coverage_end or 'N/A'}")
        
        print()
        print(f"{Colors.GREEN}Frontend URL:{Colors.RESET} http://localhost:3000/app/report/{selected_scan.id}")
        print(f"{Colors.BLUE}API URL:{Colors.RESET} http://localhost:8000/report/{selected_scan.id}")
        print()
        
        # Ask if they want to open it
        if prompt_yes_no("Open this report in browser?", default='y'):
            open_report_in_browser(selected_scan.id)
        
        input("\nPress Enter to continue...")
        
    except Exception as e:
        print_error(f"Failed to load reports: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to continue...")


def open_report_in_browser(scan_id: Optional[int] = None):
    """Open the report in a web browser - shows menu if no scan_id provided"""
    # Frontend runs on port 3000, backend API on 8000
    base_url = "http://localhost:3000/app"
    
    if scan_id:
        # Direct open with provided scan_id
        url = f"{base_url}/report/{scan_id}"
        print_info(f"Opening browser to: {url}")
        
        try:
            webbrowser.open(url)
            print_success("Browser opened successfully!")
            return True
        except Exception as e:
            print_error(f"Failed to open browser: {e}")
            print_info(f"Please manually navigate to: {url}")
            return False
    
    # No scan_id provided - show selection menu
    from app.database import get_db
    from app.models import Scan, Company
    from sqlalchemy.future import select
    
    clear_screen()
    print_header("Open Report in Browser")
    
    async def get_recent_scans():
        async for db in get_db():
            result = await db.execute(
                select(Scan).order_by(Scan.id.desc()).limit(9)
            )
            scans = result.scalars().all()
            
            # Get company names for each scan
            scan_data = []
            for scan in scans:
                company_result = await db.execute(
                    select(Company).where(Company.scan_id == scan.id)
                )
                company = company_result.scalar_one_or_none()
                scan_data.append({
                    'scan': scan,
                    'company_name': company.name if company else 'N/A'
                })
            
            return scan_data
    
    try:
        print_info("Loading recent reports...")
        scan_data = run_async(get_recent_scans())
        
        if not scan_data:
            print_warning("No reports found in database")
            print_info("Run 'Start New Analysis' to create a report")
            input("\nPress Enter to continue...")
            return False
        
        print(f"\n{Colors.GREEN}Found {len(scan_data)} recent report(s){Colors.RESET}\n")
        
        # Display scans as menu options with format: Date - Time - Company - Product
        options = []
        for item in scan_data:
            scan = item['scan']
            company = item['company_name']
            
            # Format: "2025-11-12 - 14:30 - Adobe Inc. - Adobe Experience Cloud"
            if scan.scan_date:
                date_str = scan.scan_date.strftime("%Y-%m-%d")
                time_str = scan.scan_date.strftime("%H:%M")
            else:
                date_str = "N/A"
                time_str = "N/A"
            
            product = scan.product or "Unknown Product"
            
            label = f"{date_str} - {time_str} - {company} - {product}"
            options.append(label)
        
        options.append(f"{Colors.YELLOW}Return to Main Menu{Colors.RESET}")
        
        choice = display_menu("Select a report to open:", options)
        
        if choice == 0 or choice == len(options):
            return False
        
        # Get selected scan and open in browser
        selected_item = scan_data[choice - 1]
        selected_scan = selected_item['scan']
        
        url = f"{base_url}/report/{selected_scan.id}"
        print_info(f"Opening browser to: {url}")
        
        try:
            webbrowser.open(url)
            print_success("Browser opened successfully!")
            return True
        except Exception as e:
            print_error(f"Failed to open browser: {e}")
            print_info(f"Please manually navigate to: {url}")
            return False
            
    except Exception as e:
        print_error(f"Failed to load reports: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to continue...")
        return False


def main_menu():
    """Main interactive menu"""
    while True:
        clear_screen()
        print_header("SOC2 Analyzer - Interactive Mode")
        
        print_info("Welcome to the SOC2 Analysis Interactive Interface")
        print_info("This wizard will guide you through the analysis process\n")
        
        options = [
            f"{Colors.GREEN}Start New Analysis{Colors.RESET}",
            f"{Colors.BLUE}Run Individual Extractors{Colors.RESET}",
            f"{Colors.CYAN}View Available Reports{Colors.RESET}",
            f"{Colors.YELLOW}Open Report in Browser{Colors.RESET}",
            f"{Colors.MAGENTA}About / Help{Colors.RESET}",
            f"{Colors.RED}Exit{Colors.RESET}"
        ]
        
        choice = display_menu("What would you like to do?", options)
        
        if choice == 1:
            # Start new analysis workflow
            analysis_workflow()
        elif choice == 2:
            # Run individual extractors
            run_individual_extractors()
        elif choice == 3:
            # View reports
            view_reports()
        elif choice == 4:
            # Open browser
            clear_screen()
            print_header("Open Report in Browser")
            open_report_in_browser()
            input("\nPress Enter to continue...")
        elif choice == 5:
            # About
            show_about()
        elif choice == 6:
            # Exit
            clear_screen()
            print_success("Thank you for using SOC2 Analyzer!")
            print()
            break
        else:
            break


def analysis_workflow():
    """Complete analysis workflow"""
    # Show GPT model configuration (if enabled)
    if ENABLE_GPT_CONFIG_SCREEN:
        clear_screen()
        print_header("GPT Model Configuration")
        
        try:
            from app.config import DATAIKU_CATALOG_MAP, DEFAULT_GPT_MODEL
            actual_model_id = DATAIKU_CATALOG_MAP.get(DEFAULT_GPT_MODEL, "unknown")
            # Extract the actual model name from the catalog ID (e.g., "azureopenai:Azure-OpenAI-Prod:gpt-4o" -> "gpt-4o")
            if ':' in actual_model_id:
                actual_model_name = actual_model_id.split(':')[-1]
            else:
                actual_model_name = actual_model_id
            
            print_info(f"Configured model: {DEFAULT_GPT_MODEL}")
            print_info(f"Actual model being used: {Colors.BOLD}{Colors.GREEN}{actual_model_name}{Colors.RESET}")
            print_info(f"Dataiku LLM ID: {actual_model_id}\n")
        except Exception as e:
            print_warning(f"Could not load model config: {e}\n")
        
        input(f"{Colors.CYAN}Press Enter to continue to file selection...{Colors.RESET}")
    
    # Step 1: Select file
    pdf_path = select_pdf_file()
    if not pdf_path:
        return
    
    # Step 2: Confirm and run
    clear_screen()
    print_header("Confirm Analysis")
    
    print_info(f"Selected file: {pdf_path.name}")
    print_info(f"Size: {pdf_path.stat().st_size / (1024 * 1024):.2f} MB")
    
    print()  # Add blank line before prompt
    if not prompt_yes_no("Proceed with analysis?", default='y'):
        print_warning("Analysis cancelled")
        input("\nPress Enter to continue...")
        return
    
    # Step 3: Run analysis
    clear_screen()
    print_header("Running Analysis")
    
    tracker = ProgressTracker()
    results = run_analysis(pdf_path, tracker)
    
    if not results:
        input("\nPress Enter to continue...")
        return
    
    # Step 4: Display results
    display_results_summary(results)
    input("\nPress Enter to continue...")
    
    # Step 5: Database upload
    clear_screen()
    print_header("Database Upload")
    
    if prompt_yes_no("Upload results to database?", default='y'):
        success = upload_to_database(results, pdf_path=pdf_path)
        
        if success:
            # Step 6: Open browser
            print()
            if prompt_yes_no("Open report in browser?", default='y'):
                open_report_in_browser()
    
    input("\nPress Enter to return to main menu...")


def run_individual_extractors():
    """Run extractors individually for debugging and control"""
    from app.extractors.company import extract_company_from_report
    from app.extractors.auditor import extract_auditor_from_report
    from app.extractors.product import extract_product_from_report
    from app.extractors.report_date import extract_report_date
    from app.extractors.coverage_period import extract_coverage_period
    from app.extractors.control_integration import extract_controls  # V2/V4 unified interface
    from app.extractors.cuec_extractor import extract_cuecs
    from app.extractors.subservice_orgs import extract_subservice_orgs
    from app import config
    
    def load_results(json_path):
        """Load results from JSON file"""
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print_warning(f"Could not load {json_path}: {e}")
        return None
    
    def display_extractor_results(json_path, result_type):
        """Display results from a JSON file"""
        data = load_results(json_path)
        if not data:
            print_warning(f"No results found")
            return
        
        print(f"\n{Colors.BOLD}Results:{Colors.RESET}")
        
        if result_type == "company":
            company = data.get('company', 'N/A')
            parent = data.get('parent_company', 'N/A')
            conf = data.get('confidence', 'N/A')
            print(f"  Company: {Colors.BOLD}{company}{Colors.RESET}")
            print(f"  Parent: {parent}")
            print(f"  Confidence: {conf}")
        
        elif result_type == "auditor":
            auditor = data.get('auditor', 'N/A')
            conf = data.get('confidence', 'N/A')
            print(f"  Auditor: {Colors.BOLD}{auditor}{Colors.RESET}")
            print(f"  Confidence: {conf}")
        
        elif result_type == "product":
            product = data.get('product', 'N/A')
            conf = data.get('confidence', 'N/A')
            print(f"  Product: {Colors.BOLD}{product}{Colors.RESET}")
            print(f"  Confidence: {conf}")
        
        elif result_type == "report_date":
            date = data.get('report_date', 'N/A')
            print(f"  Report Date: {Colors.BOLD}{date}{Colors.RESET}")
        
        elif result_type == "coverage_period":
            rtype = data.get('type', 'N/A')
            start = data.get('start_date', 'N/A')
            end = data.get('end_date', 'N/A')
            print(f"  Type: {Colors.BOLD}{rtype}{Colors.RESET}")
            print(f"  Start Date: {start}")
            print(f"  End Date: {end}")
        
        elif result_type == "controls":
            controls = data.get('controls', [])
            deviations = sum(1 for c in controls if c.get('has_deviation'))
            print(f"  Total Controls: {Colors.BOLD}{len(controls)}{Colors.RESET}")
            print(f"  Deviations: {Colors.RED if deviations > 0 else Colors.GREEN}{deviations}{Colors.RESET}")
        
        elif result_type == "cuec":
            cuecs = data.get('cuecs', [])
            print(f"  Total CUECs: {Colors.BOLD}{len(cuecs)}{Colors.RESET}")
        
        elif result_type == "subservice_orgs":
            orgs = data.get('subservice_orgs', [])
            print(f"  Total Subservice Orgs: {Colors.BOLD}{len(orgs)}{Colors.RESET}")
            if orgs:
                print(f"\n  {Colors.BOLD}Organizations:{Colors.RESET}")
                for org in orgs[:10]:
                    name = org.get('third_party_name', 'N/A')
                    print(f"    • {name}")
                if len(orgs) > 10:
                    print(f"    {Colors.CYAN}... and {len(orgs) - 10} more{Colors.RESET}")
    
    def run_single_extractor(name, func, json_path, result_type):
        """Run a single extractor"""
        clear_screen()
        print_header(f"Running {name}")
        
        print_info(f"Starting {name}...")
        print_info("This may take several minutes depending on the document size...")
        print()
        
        try:
            # Just run the function - let it handle its own output
            func()
            print()
            print_success(f"{name} completed successfully!")
            display_extractor_results(json_path, result_type)
            return True
        except Exception as e:
            print()
            print_error(f"{name} failed: {e}")
            import traceback
            print(f"\n{Colors.RED}Error details:{Colors.RESET}")
            print(traceback.format_exc())
            return False
    
    def run_all_extractors_sequential():
        """Run all extractors in sequence"""
        extractors = [
            ("Company Extractor", extract_company_from_report, 
             str(config.JSON_DIR / "company_result.json"), "company"),
            ("Auditor Extractor", extract_auditor_from_report, 
             str(config.JSON_DIR / "auditor_result.json"), "auditor"),
            ("Product Extractor", extract_product_from_report, 
             str(config.JSON_DIR / "product_result.json"), "product"),
            ("Report Date Extractor", extract_report_date, 
             str(config.JSON_DIR / "report_date_result.json"), "report_date"),
            ("Coverage Period Extractor", extract_coverage_period, 
             str(config.JSON_DIR / "coverage_period_result.json"), "coverage_period"),
            ("Control Extractor", lambda: extract_controls(version=getattr(config, 'CONTROL_EXTRACTOR_VERSION', 'v4')), 
             str(config.JSON_DIR / "control_result.json"), "controls"),
            ("CUEC Extractor", extract_cuecs, 
             str(config.JSON_DIR / "cuec_result.json"), "cuec"),
            ("Subservice Orgs Extractor", extract_subservice_orgs, 
             str(config.JSON_DIR / "subservice_orgs_result.json"), "subservice_orgs"),
        ]
        
        clear_screen()
        print_header("Running All Extractors")
        
        results = []
        for name, func, json_path, result_type in extractors:
            print_section(name)
            print_info(f"Executing {name}...")
            
            try:
                func()
                print_success(f"{name} completed!")
                results.append((name, True))
            except Exception as e:
                print_error(f"{name} failed: {e}")
                results.append((name, False))
                
                print()  # Add blank line before prompt
                if not prompt_yes_no("Continue with remaining extractors?", default='y'):
                    break
            
            print()
        
        # Summary
        print_section("Extraction Summary")
        for name, success in results:
            if success:
                print_success(name)
            else:
                print_error(name)
    
    # Check prerequisites and offer file selection
    clear_screen()
    print_header("Individual Extractor Runner")
    
    print_info("Checking for previously processed files...")
    print()
    
    required_files = [
        ("PDF Text", config.PDF_TXT_PATH),
        ("Sections", config.SECTION_JSON_PATH)
    ]
    
    files_exist = True
    for name, path in required_files:
        if os.path.exists(path):
            print_success(f"{name} file exists")
        else:
            print_warning(f"{name} file not found")
            files_exist = False
    
    print()
    
    # Always offer to process a new file
    if files_exist:
        print_info("You can use the existing processed files or select a new PDF to analyze.")
        print()
        choice = input(f"{Colors.YELLOW}Options:{Colors.RESET}\n"
                      f"  1. Use existing files\n"
                      f"  2. Select a new PDF file\n"
                      f"  0. Return to main menu\n"
                      f"\n{Colors.CYAN}Enter choice (0-2): {Colors.RESET}").strip()
        
        if choice == '0':
            return
        elif choice == '2':
            files_exist = False  # Force new file processing
        # choice == '1' or anything else continues with existing files
    
    # If files don't exist or user chose new file
    if not files_exist:
        clear_screen()
        print_header("Select PDF File")
        
        # Select PDF file
        pdf_path = select_pdf_file()
        if not pdf_path:
            return
        
        # Run initial processing (text extraction + sections)
        clear_screen()
        print_header("Initial Processing")
        
        print_info(f"Processing: {pdf_path.name}")
        print()
        
        try:
            from app.pdf_handler import extract_text_from_pdf, find_section_candidates
            
            # Extract text
            print_section("Extracting PDF Text")
            print_info("Reading PDF and extracting text...")
            extract_text_from_pdf(str(pdf_path), str(config.PDF_TXT_PATH))
            print_success("PDF text extraction complete!")
            
            # Read the extracted text
            with open(str(config.PDF_TXT_PATH), 'r', encoding='utf-8') as f:
                text = f.read()
            
            # Find sections
            print()
            print_section("Identifying Sections")
            print_info("Analyzing document structure...")
            section_results = find_section_candidates(text)
            
            # Write section results to JSON
            with open(str(config.SECTION_JSON_PATH), 'w', encoding='utf-8') as f:
                json.dump(section_results, f, indent=2, ensure_ascii=False)
            
            print_success("Section identification complete!")
            
            print()
            print_success("Initial processing complete! You can now run individual extractors.")
            
        except Exception as e:
            print_error(f"Initial processing failed: {e}")
            import traceback
            print(f"\n{Colors.RED}Error details:{Colors.RESET}")
            print(traceback.format_exc())
            input("\nPress Enter to return to main menu...")
            return
    
    print()
    input(f"{Colors.CYAN}Press Enter to continue to extractor menu...{Colors.RESET}")
    
    # Individual extractor menu
    while True:
        clear_screen()
        print_header("Individual Extractor Runner")
        
        options = [
            f"{Colors.CYAN}Company Extractor{Colors.RESET}",
            f"{Colors.CYAN}Auditor Extractor{Colors.RESET}",
            f"{Colors.CYAN}Product Extractor{Colors.RESET}",
            f"{Colors.CYAN}Report Date Extractor{Colors.RESET}",
            f"{Colors.CYAN}Coverage Period Extractor{Colors.RESET}",
            f"{Colors.CYAN}Control Extractor (v2){Colors.RESET}",
            f"{Colors.CYAN}CUEC Extractor{Colors.RESET}",
            f"{Colors.CYAN}Subservice Orgs Extractor{Colors.RESET}",
            f"{Colors.GREEN}Run All Extractors (Sequential){Colors.RESET}",
            f"{Colors.YELLOW}Return to Main Menu{Colors.RESET}"
        ]
        
        choice = display_menu("Select an extractor to run:", options)
        
        if choice == 0 or choice == 10:
            break
        
        elif choice == 1:
            run_single_extractor(
                "Company Extractor", 
                extract_company_from_report,
                str(config.JSON_DIR / "company_result.json"),
                "company"
            )
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.RESET}")
        
        elif choice == 2:
            run_single_extractor(
                "Auditor Extractor", 
                extract_auditor_from_report,
                str(config.JSON_DIR / "auditor_result.json"),
                "auditor"
            )
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.RESET}")
        
        elif choice == 3:
            run_single_extractor(
                "Product Extractor", 
                extract_product_from_report,
                str(config.JSON_DIR / "product_result.json"),
                "product"
            )
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.RESET}")
        
        elif choice == 4:
            run_single_extractor(
                "Report Date Extractor", 
                extract_report_date,
                str(config.JSON_DIR / "report_date_result.json"),
                "report_date"
            )
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.RESET}")
        
        elif choice == 5:
            run_single_extractor(
                "Coverage Period Extractor", 
                extract_coverage_period,
                str(config.JSON_DIR / "coverage_period_result.json"),
                "coverage_period"
            )
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.RESET}")
        
        elif choice == 6:
            version = getattr(config, 'CONTROL_EXTRACTOR_VERSION', 'v4')
            run_single_extractor(
                f"Control Extractor ({version.upper()})", 
                lambda: extract_controls(version=version),
                str(config.JSON_DIR / "control_result.json"),
                "controls"
            )
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.RESET}")
        
        elif choice == 7:
            run_single_extractor(
                "CUEC Extractor", 
                extract_cuecs,
                str(config.JSON_DIR / "cuec_result.json"),
                "cuec"
            )
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.RESET}")
        
        elif choice == 8:
            run_single_extractor(
                "Subservice Orgs Extractor", 
                extract_subservice_orgs,
                str(config.JSON_DIR / "subservice_orgs_result.json"),
                "subservice_orgs"
            )
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.RESET}")
        
        elif choice == 9:
            run_all_extractors_sequential()
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.RESET}")


def view_reports():
    """View available reports"""
    clear_screen()
    print_header("Available Reports")
    
    reports = get_available_reports()
    
    if not reports:
        print_error("No PDF files found in soc2_reports/ directory")
    else:
        print_info(f"Found {len(reports)} PDF report(s) in soc2_reports/\n")
        
        for i, report in enumerate(reports, 1):
            print(f"  {i:2d}. {Colors.BOLD}{report['name']:<40}{Colors.RESET} "
                  f"{Colors.CYAN}({report['size_mb']:.2f} MB){Colors.RESET}")
    
    input("\nPress Enter to continue...")


def show_about():
    """Show about information"""
    clear_screen()
    print_header("About SOC2 Analyzer")
    
    print(f"{Colors.CYAN}Version:{Colors.RESET} 5.0 (Direct Execution Mode)")
    print(f"{Colors.CYAN}Mode:{Colors.RESET} Interactive TUI")
    print()
    
    print_section("Features")
    print("  * Interactive file selection")
    print("  * Real-time progress tracking")
    print("  * Comprehensive results summary")
    print("  * Automatic database upload")
    print("  * Browser integration")
    print()
    
    print_section("Workflow")
    print("  1. Select a PDF report")
    print("  2. Run analysis with progress tracking")
    print("  3. Review results summary")
    print("  4. Upload to database (optional)")
    print("  5. View report in browser (optional)")
    print()
    
    print_section("Benefits")
    print("  [+] No threading issues")
    print("  [+] Stable execution")
    print("  [+] Clear progress feedback")
    print("  [+] Guided workflow")
    print()
    
    print_info("For command-line usage, see: run_analysis.py --help")
    print_info("For documentation, see: DIRECT_EXECUTION_GUIDE.md")
    
    input("\nPress Enter to continue...")


def main():
    """Main entry point"""
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n")
        print_warning("Interrupted by user")
        print()
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
