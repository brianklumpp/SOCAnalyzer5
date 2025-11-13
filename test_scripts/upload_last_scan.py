"""
Upload the last scan from combined_result.json to Docker database
"""
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, 'backend')

# Colors for output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

def upload_combined_result():
    """Upload combined_result.json to database"""
    
    combined_path = Path("data/json/combined_result.json")
    
    if not combined_path.exists():
        print(f"{Colors.RED}❌ Error: {combined_path} not found{Colors.RESET}")
        print(f"{Colors.YELLOW}Please run a scan first to generate the file{Colors.RESET}")
        return False
    
    print(f"{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.CYAN}           Upload Last Scan to Docker Database{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n")
    
    # Load the JSON file
    try:
        with open(combined_path, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        print(f"{Colors.GREEN}✓{Colors.RESET} Loaded: {combined_path}")
        print(f"  File size: {combined_path.stat().st_size:,} bytes")
        
        # Show scan details
        product_data = results.get('product', {})
        company_data = results.get('company', {})
        report_date_data = results.get('report_date', {})
        
        # Handle both dict and string formats
        if isinstance(product_data, dict):
            product = product_data.get('product_name', 'Unknown')
        else:
            product = str(product_data) if product_data else 'Unknown'
        
        if isinstance(company_data, dict):
            company = company_data.get('company_name', 'Unknown')
        else:
            company = str(company_data) if company_data else 'Unknown'
        
        if isinstance(report_date_data, dict):
            report_date = report_date_data.get('report_date', 'Unknown')
        else:
            report_date = str(report_date_data) if report_date_data else 'Unknown'
        
        controls_count = len(results.get('controls', []))
        cuecs_count = len(results.get('cuecs', []))
        
        print(f"\n{Colors.CYAN}Scan Details:{Colors.RESET}")
        print(f"  Company: {company}")
        print(f"  Product: {product}")
        print(f"  Report Date: {report_date}")
        print(f"  Controls: {controls_count}")
        print(f"  CUECs: {cuecs_count}")
        
    except Exception as e:
        print(f"{Colors.RED}❌ Error loading file: {e}{Colors.RESET}")
        return False
    
    # Import database insertion function
    try:
        from app.explicit_sql_insert import insert_extracted_data
    except ImportError as e:
        print(f"{Colors.RED}❌ Error importing database module: {e}{Colors.RESET}")
        return False
    
    # Ask for confirmation
    print(f"\n{Colors.YELLOW}Ready to upload to Docker database (localhost:5433){Colors.RESET}")
    response = input(f"{Colors.YELLOW}Continue? (Y/n): {Colors.RESET}").strip().lower()
    
    if response and response != 'y':
        print(f"{Colors.YELLOW}Upload cancelled{Colors.RESET}")
        return False
    
    # Insert into database
    print(f"\n{Colors.CYAN}Uploading to database...{Colors.RESET}")
    
    try:
        summary = insert_extracted_data(str(combined_path))
        
        print(f"\n{Colors.GREEN}{'='*80}{Colors.RESET}")
        print(f"{Colors.GREEN}✓ Database upload completed!{Colors.RESET}")
        print(f"{Colors.GREEN}{'='*80}{Colors.RESET}\n")
        
        # Parse summary and get the latest scan_id
        if isinstance(summary, dict):
            # Query database to get the latest scan ID
            from app.database import get_db
            from app.models import Scan
            from sqlalchemy.future import select
            import asyncio
            
            async def get_latest_scan_id():
                async for db in get_db():
                    result = await db.execute(
                        select(Scan.id).order_by(Scan.id.desc()).limit(1)
                    )
                    return result.scalar_one_or_none()
            
            scan_id = asyncio.run(get_latest_scan_id()) or 'Unknown'
            
            print(f"{Colors.CYAN}Scan ID:{Colors.RESET} {scan_id}")
            print(f"{Colors.CYAN}Controls inserted:{Colors.RESET} {summary.get('control', 0)}")
            print(f"{Colors.CYAN}CUECs inserted:{Colors.RESET} {summary.get('cuec', 0)}")
            print(f"{Colors.CYAN}Company inserted:{Colors.RESET} {summary.get('company', 0)}")
            print(f"{Colors.CYAN}Products inserted:{Colors.RESET} {summary.get('product', 0)}")
            print(f"{Colors.CYAN}Subservice orgs:{Colors.RESET} {summary.get('subservice_org', 0)}")
            
            if summary.get('errors'):
                print(f"\n{Colors.YELLOW}⚠ Errors encountered:{Colors.RESET}")
                for error in summary['errors']:
                    print(f"  {Colors.YELLOW}• {error}{Colors.RESET}")
            
            print(f"\n{Colors.GREEN}Frontend URL:{Colors.RESET} http://localhost:3000/app/report/{scan_id}")
            print(f"{Colors.CYAN}API URL:{Colors.RESET} http://localhost:8000/report/{scan_id}")
            
            # Offer to open in browser
            print()
            response = input(f"{Colors.YELLOW}Open report in browser? (Y/n): {Colors.RESET}").strip().lower()
            if not response or response == 'y':
                import webbrowser
                webbrowser.open(f"http://localhost:3000/app/report/{scan_id}")
                print(f"{Colors.GREEN}✓ Browser opened{Colors.RESET}")
        else:
            print(f"{Colors.CYAN}Summary:{Colors.RESET} {summary}")
        
        return True
        
    except Exception as e:
        print(f"\n{Colors.RED}{'='*80}{Colors.RESET}")
        print(f"{Colors.RED}❌ Database upload failed!{Colors.RESET}")
        print(f"{Colors.RED}{'='*80}{Colors.RESET}\n")
        print(f"{Colors.RED}Error: {e}{Colors.RESET}")
        
        import traceback
        print(f"\n{Colors.YELLOW}Traceback:{Colors.RESET}")
        traceback.print_exc()
        
        return False

if __name__ == "__main__":
    success = upload_combined_result()
    sys.exit(0 if success else 1)
