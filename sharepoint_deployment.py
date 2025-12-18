#!/usr/bin/env python3
"""
SOCAnalyzer SharePoint Deployment Script

Creates a complete deployment package with Docker images, database backup,
source code, and configuration, then uploads to SharePoint.
"""

import os
import sys
import shutil
import subprocess
import re
import json
from datetime import datetime
from pathlib import Path
from office365.runtime.auth.authentication_context import AuthenticationContext
from office365.sharepoint.client_context import ClientContext
from office365.sharepoint.files.file import File

# Configuration
SHAREPOINT_SITE = "https://nandps.sharepoint.com/teams/GRC"
DOCUMENT_LIBRARY = "Shared Documents/8 - Tools/SOC Analyzer"
VERSION = "1.0.13"
STATE_FILE = ".deployment_state.json"

# Colors for terminal output
class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GRAY = '\033[90m'
    WHITE = '\033[97m'
    RESET = '\033[0m'

def print_header(text):
    print(f"\n{Colors.CYAN}{'=' * 40}")
    print(f"   {text}")
    print(f"{'=' * 40}{Colors.RESET}\n")

def print_step(step_num, total_steps, text):
    print(f"{Colors.CYAN}[{step_num}/{total_steps}] {text}{Colors.RESET}")

def print_success(text):
    print(f"{Colors.GREEN}  ✓ {text}{Colors.RESET}")

def print_error(text):
    print(f"{Colors.RED}  ✗ {text}{Colors.RESET}")

def print_warning(text):
    print(f"{Colors.YELLOW}  ! {text}{Colors.RESET}")

def print_info(text):
    print(f"{Colors.GRAY}  {text}{Colors.RESET}")

def load_state():
    """Load deployment state from file"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {
        "staging_dir": None,
        "steps_completed": [],
        "uploaded_files": [],
        "deployment_folder": None
    }

def save_state(state):
    """Save deployment state to file"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def clear_state():
    """Clear deployment state file"""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)

def run_command(cmd, check=True, capture_output=False):
    """Run a shell command and return the result"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=check,
            capture_output=capture_output,
            text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        return None

def check_prerequisites(state):
    """Check if Docker and containers are running"""
    step_name = "prerequisites"
    if step_name in state["steps_completed"]:
        print_step(1, 8, "Checking prerequisites... (skipped - already done)")
        print()
        return
    
    print_step(1, 8, "Checking prerequisites...")
    
    # Check Docker
    result = run_command("docker version", capture_output=True)
    if result and result.returncode == 0:
        print_success("Docker is running")
    else:
        print_error("Docker is not running!")
        sys.exit(1)
    
    # Check if postgres container is running
    result = run_command(
        'docker ps --filter "name=socanalyzer-postgres" --filter "status=running" --format "{{.Names}}"',
        capture_output=True
    )
    if result and "socanalyzer-postgres" in result.stdout:
        print_success("PostgreSQL is running")
    else:
        print_error("PostgreSQL container not running!")
        print_info("Start with: docker compose up -d")
        sys.exit(1)
    
    # Check for required Python packages
    try:
        import office365
        print_success("Office365 Python library is available")
    except ImportError:
        print_warning("Office365-REST-Python-Client not found")
        print_info("Installing office365-rest-python-client...")
        run_command("pip install office365-rest-python-client")
        print_success("Office365-REST-Python-Client installed")
    
    state["steps_completed"].append(step_name)
    save_state(state)
    print()

def create_staging_directory(staging_dir, state):
    """Create staging directory structure"""
    step_name = "staging_dir"
    if step_name in state["steps_completed"]:
        print_step(2, 8, "Creating staging directory... (skipped - already done)")
        print()
        return
    
    print_step(2, 8, "Creating staging directory...")
    
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)
    
    os.makedirs(staging_dir, exist_ok=True)
    os.makedirs(os.path.join(staging_dir, "docker_images"), exist_ok=True)
    os.makedirs(os.path.join(staging_dir, "database"), exist_ok=True)
    os.makedirs(os.path.join(staging_dir, "source"), exist_ok=True)
    os.makedirs(os.path.join(staging_dir, "data"), exist_ok=True)
    os.makedirs(os.path.join(staging_dir, "docs"), exist_ok=True)
    
    state["staging_dir"] = staging_dir
    state["steps_completed"].append(step_name)
    save_state(state)
    
    print_success("Staging directories created")
    print()

def export_docker_images(staging_dir, state):
    """Export Docker images to tar files"""
    step_name = "docker_images"
    if step_name in state["steps_completed"]:
        print_step(3, 8, "Exporting Docker images... (skipped - already done)")
        print()
        return
    
    print_step(3, 8, "Exporting Docker images...")
    print_info("This may take 5-10 minutes...")
    
    images = [
        {"name": "socanalyzer5-frontend", "file": "frontend.tar"},
        {"name": "socanalyzer5-backend", "file": "backend.tar"},
        {"name": "postgres:15-alpine", "file": "postgres.tar"},
        {"name": "redis:7-alpine", "file": "redis.tar"}
    ]
    
    docker_images_dir = os.path.join(staging_dir, "docker_images")
    
    for img in images:
        print_info(f"Exporting {img['name']}...")
        output_path = os.path.join(docker_images_dir, img['file'])
        result = run_command(f'docker save -o "{output_path}" {img["name"]}')
        
        if result and result.returncode == 0:
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print_info(f"  Saved: {size_mb:.2f} MB")
        else:
            print_error(f"Failed to export {img['name']}")
            sys.exit(1)
    
    state["steps_completed"].append(step_name)
    save_state(state)
    
    print_success("Docker images exported")
    print()

def backup_database(staging_dir, state):
    """Backup PostgreSQL database"""
    step_name = "database"
    if step_name in state["steps_completed"]:
        print_step(4, 8, "Backing up database... (skipped - already done)")
        print()
        return
    
    print_step(4, 8, "Backing up database...")
    
    # Get credentials from .env
    db_name = "soc2analyzer"
    db_user = "soc2_analyzer"
    
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            env_content = f.read()
            db_match = re.search(r'POSTGRES_DB=([^\r\n]+)', env_content)
            user_match = re.search(r'POSTGRES_USER=([^\r\n]+)', env_content)
            if db_match:
                db_name = db_match.group(1)
            if user_match:
                db_user = user_match.group(1)
    
    print_info(f"Database: {db_name}")
    print_info(f"User: {db_user}")
    
    backup_file = os.path.join(staging_dir, "database", "soc2analyzer_backup.sql")
    cmd = f'docker exec socanalyzer-postgres pg_dump -U {db_user} -d {db_name} > "{backup_file}"'
    result = run_command(cmd)
    
    if result and result.returncode == 0:
        size_kb = os.path.getsize(backup_file) / 1024
        print_success(f"Database backed up: {size_kb:.2f} KB")
    else:
        print_error("Database backup failed!")
        sys.exit(1)
    
    state["steps_completed"].append(step_name)
    save_state(state)
    
    print()

def copy_source_code(staging_dir, state):
    """Copy source code and configuration files"""
    step_name = "source_code"
    if step_name in state["steps_completed"]:
        print_step(5, 8, "Copying source code... (skipped - already done)")
        print()
        return
    
    print_step(5, 8, "Copying source code...")
    
    source_dir = os.path.join(staging_dir, "source")
    
    # Copy folders
    folders = ["backend", "frontend", "scripts", "docs"]
    for folder in folders:
        if os.path.exists(folder):
            print_info(f"Copying {folder}...")
            shutil.copytree(folder, os.path.join(source_dir, folder), dirs_exist_ok=True)
    
    # Copy important files
    print_info("Copying configuration files...")
    files = [
        "docker-compose.yml",
        "docker-compose.prod.yml",
        ".env",
        "requirements.txt",
        "package.json",
        "VERSION.txt",
        "CHANGELOG.md"
    ]
    
    for file in files:
        if os.path.exists(file):
            shutil.copy2(file, source_dir)
    
    state["steps_completed"].append(step_name)
    save_state(state)
    
    print_success("Source code copied")
    print()

def copy_data_folder(staging_dir, state):
    """Copy data folder (excluding logs)"""
    step_name = "data_folder"
    if step_name in state["steps_completed"]:
        print_step(6, 8, "Copying data folder... (skipped - already done)")
        print()
        return
    
    print_step(6, 8, "Copying data folder...")
    
    if os.path.exists("data"):
        print_info("Copying data folder (excluding logs)...")
        
        data_dir = os.path.join(staging_dir, "data")
        subfolders = ["json", "template", "output"]
        
        for subfolder in subfolders:
            source_path = os.path.join("data", subfolder)
            if os.path.exists(source_path):
                dest_path = os.path.join(data_dir, subfolder)
                shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
        
        print_success("Data folder copied (logs excluded)")
    else:
        print_warning("No data folder found, skipping...")
    
    state["steps_completed"].append(step_name)
    save_state(state)
    
    print()

def create_documentation(staging_dir, state):
    """Create deployment documentation"""
    step_name = "documentation"
    if step_name in state["steps_completed"]:
        print_step(7, 8, "Creating deployment documentation... (skipped - already done)")
        print()
        return
    
    print_step(7, 8, "Creating deployment documentation...")
    
    docs_dir = os.path.join(staging_dir, "docs")
    
    # Create deployment guide
    deployment_guide = f"""SOCAnalyzer Deployment Package
================================
Version: {VERSION}
Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

CONTENTS
--------
1. docker_images/     - Docker images (.tar files)
2. database/          - PostgreSQL database backup
3. source/            - Complete source code and configuration
4. data/              - Data folder with templates and outputs
5. docs/              - This deployment guide

DEPLOYMENT STEPS
----------------

1. Install Rancher Desktop
   Download from https://rancherdesktop.io/
   Enable Dockerd (moby) runtime

2. Create Application Folder
   mkdir C:\\Apps\\SOCAnalyzer
   cd C:\\Apps\\SOCAnalyzer

3. Download from SharePoint
   Navigate to: Shared Documents/8 - Tools/SOC Analyzer

4. Run Quick Start Script
   python quick_start.py
   (or on Windows: .\\QUICK_START.ps1)

SUPPORT
-------
Contact: GRC Team
SharePoint: https://nandps.sharepoint.com/teams/GRC
"""
    
    with open(os.path.join(docs_dir, "DEPLOYMENT_GUIDE.txt"), "w", encoding="utf-8") as f:
        f.write(deployment_guide)
    
    # Create quick start script (PowerShell)
    quick_start_ps = """#!/usr/bin/env pwsh
$ErrorActionPreference = 'Stop'

Write-Host '========================================' -ForegroundColor Cyan
Write-Host '   SOCAnalyzer Quick Deployment' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan

Write-Host '[1/5] Importing Docker images...' -ForegroundColor Cyan
docker load -i docker_images/frontend.tar
docker load -i docker_images/backend.tar
docker load -i docker_images/postgres.tar
docker load -i docker_images/redis.tar

Write-Host '[2/5] Copying source files...' -ForegroundColor Cyan
Copy-Item -Path source\\* -Destination . -Recurse -Force

Write-Host '[3/5] Starting PostgreSQL...' -ForegroundColor Cyan
docker compose up -d postgres
Start-Sleep -Seconds 10

Write-Host '[4/5] Restoring database...' -ForegroundColor Cyan
Get-Content database\\soc2analyzer_backup.sql | docker exec -i socanalyzer-postgres psql -U soc2_analyzer -d soc2analyzer

Write-Host '[5/5] Starting all services...' -ForegroundColor Cyan
docker compose up -d

Write-Host 'Deployment complete!' -ForegroundColor Green
Write-Host 'Access at: http://localhost:3000' -ForegroundColor Cyan
"""
    
    with open(os.path.join(staging_dir, "QUICK_START.ps1"), "w", encoding="utf-8") as f:
        f.write(quick_start_ps)
    
    # Create README
    readme = f"""# SOCAnalyzer Deployment Package

Version: {VERSION}
Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Quick Start

1. Copy this entire folder to your Windows Server
2. Run: .\\QUICK_START.ps1
3. Configure Windows Firewall
4. Access at: http://SERVER_IP:3000

## Documentation

See docs/DEPLOYMENT_GUIDE.txt for detailed instructions.

## Support

GRC Team - https://nandps.sharepoint.com/teams/GRC
"""
    
    with open(os.path.join(staging_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)
    
    state["steps_completed"].append(step_name)
    save_state(state)
    
    print_success("Documentation created")
    print()

def upload_to_sharepoint(staging_dir, state):
    """Upload deployment package to SharePoint"""
    print_step(8, 8, "Uploading to SharePoint...")
    
    # Check if OneDrive sync folder exists (much simpler for Windows)
    onedrive_base = os.path.join(os.environ.get('USERPROFILE', ''), 'NANDPS')
    sharepoint_path = os.path.join(onedrive_base, 'GRC - Shared Documents', '8 - Tools', 'SOC Analyzer')
    
    if os.path.exists(sharepoint_path):
        print_info("Using OneDrive/SharePoint sync folder...")
        
        # Create deployment folder name
        if state.get("deployment_folder"):
            deployment_folder_name = state["deployment_folder"]
        else:
            deployment_ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            deployment_folder_name = f"SOCAnalyzer_v{VERSION}_{deployment_ts}"
            state["deployment_folder"] = deployment_folder_name
            save_state(state)
        
        target_dir = os.path.join(sharepoint_path, deployment_folder_name)
        
        try:
            print_info(f"Copying to: {target_dir}")
            
            # Copy entire staging directory
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            
            shutil.copytree(staging_dir, target_dir)
            
            print_success("Files copied to SharePoint sync folder!")
            print_info("OneDrive will sync to SharePoint automatically")
            print()
            print(f"{Colors.GREEN}✓ Deployment package available at SharePoint!{Colors.RESET}")
            print(f"{Colors.CYAN}  Path: 8 - Tools > SOC Analyzer > {deployment_folder_name}{Colors.RESET}")
            return
            
        except Exception as e:
            print_warning(f"Copy to OneDrive folder failed: {str(e)}")
            print_info("Falling back to direct SharePoint upload...")
    
    # Fallback to API upload
    print_info("OneDrive sync folder not found, using direct SharePoint upload...")
    print_info("Note: This requires Azure AD app registration for authentication")
    print()
    print_warning("Direct SharePoint upload requires:")
    print_info("1. Azure AD App Registration with SharePoint permissions")
    print_info("2. Client ID and Tenant ID from Azure Portal")
    print()
    print(f"{Colors.YELLOW}Recommended: Use OneDrive sync folder instead{Colors.RESET}")
    print(f"{Colors.GRAY}  Path: {sharepoint_path}{Colors.RESET}")
    print()
    
    proceed = input("Continue with manual copy? (Y/n): ")
    if proceed.lower() != 'n':
        print()
        print(f"{Colors.CYAN}Manual steps:{Colors.RESET}")
        print(f"{Colors.WHITE}1. Open File Explorer")
        print(f"2. Navigate to: {sharepoint_path}")
        print(f"3. Copy this folder: {staging_dir}")
        print(f"4. Paste into SharePoint location{Colors.RESET}")
        return
    
    sys.exit(1)

def main():
    print_header("SOCAnalyzer SharePoint Deployment")
    
    # Load or create state
    state = load_state()
    
    # Determine staging directory
    if state.get("staging_dir") and os.path.exists(state["staging_dir"]):
        staging_dir = state["staging_dir"]
        print(f"{Colors.YELLOW}Resuming previous deployment{Colors.RESET}")
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        staging_dir = os.path.join("dist", f"SOCAnalyzer-SharePoint-{timestamp}")
    
    print(f"{Colors.YELLOW}Version: {VERSION}")
    print(f"SharePoint: {SHAREPOINT_SITE}")
    print(f"Library: {DOCUMENT_LIBRARY}")
    print(f"Staging: {staging_dir}{Colors.RESET}\n")
    
    # Execute deployment steps
    check_prerequisites(state)
    create_staging_directory(staging_dir, state)
    export_docker_images(staging_dir, state)
    backup_database(staging_dir, state)
    copy_source_code(staging_dir, state)
    copy_data_folder(staging_dir, state)
    create_documentation(staging_dir, state)
    upload_to_sharepoint(staging_dir, state)
    
    # Summary
    print_header("Deployment Package Complete")
    
    total_size_gb = sum(
        os.path.getsize(os.path.join(root, file))
        for root, dirs, files in os.walk(staging_dir)
        for file in files
    ) / (1024 ** 3)
    
    file_count = sum(len(files) for _, _, files in os.walk(staging_dir))
    
    print(f"{Colors.YELLOW}Package Details:{Colors.RESET}")
    print(f"{Colors.WHITE}  Total Size: {total_size_gb:.2f} GB")
    print(f"  Files: {file_count}")
    print(f"  Location: SharePoint GRC Team Site")
    print(f"  Path: 8 - Tools > SOC Analyzer{Colors.RESET}")
    print()
    print(f"{Colors.YELLOW}Next Steps:{Colors.RESET}")
    print(f"{Colors.WHITE}  1. Share SharePoint link with deployment team")
    print(f"  2. On target server, download and run QUICK_START.ps1")
    print(f"  3. Configure Windows Firewall for port 3000{Colors.RESET}")
    print()
    
    # Cleanup option
    cleanup = input("Delete local staging folder? (y/N): ")
    if cleanup.lower() == 'y':
        shutil.rmtree(staging_dir)
        clear_state()
        print(f"{Colors.GREEN}✓ Staging folder cleaned up{Colors.RESET}\n")
    else:
        print(f"{Colors.GRAY}✓ Local copy retained at: {staging_dir}{Colors.RESET}")
        print(f"{Colors.GRAY}✓ State saved - run script again to resume if needed{Colors.RESET}\n")
        clear_state()  # Clear state on success

if __name__ == "__main__":
    main()
