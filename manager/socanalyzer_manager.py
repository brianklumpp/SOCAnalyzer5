"""
SOCAnalyzer Manager - Desktop GUI for managing SOCAnalyzer Docker services.

Provides simple one-click service management for non-technical users.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, Menu
import threading
import subprocess
import time
import sys
import os
import socket
import webbrowser
from pathlib import Path
from typing import Optional, Dict
import requests

try:
    import docker
    from docker.errors import DockerException
except ImportError:
    docker = None
    DockerException = Exception

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None


class SOCAnalyzerManager:
    """Main application window for SOCAnalyzer service management."""
    
    # Service configuration
    SERVICES = {
        'frontend': {'container': 'socanalyzer-frontend', 'port': 3000, 'name': 'Frontend'},
        'backend': {'container': 'socanalyzer-backend', 'port': 8000, 'name': 'Backend'},
        'postgres': {'container': 'socanalyzer-postgres', 'port': 5433, 'name': 'Database'},
        'redis': {'container': 'socanalyzer-redis', 'port': 6379, 'name': 'Redis'}
    }
    
    SHAREPOINT_VERSION_URL = "https://nandps.sharepoint.com/teams/GRC/Shared%20Documents/8%20-%20Tools/SOC%20Analyzer/VERSION.txt"
    FRONTEND_URL = "http://localhost:3000"
    BACKEND_HEALTH_URL = "http://localhost:8000/health"
    
    # Colors
    COLOR_GREEN = "#28a745"
    COLOR_RED = "#dc3545"
    COLOR_YELLOW = "#ffc107"
    COLOR_GRAY = "#6c757d"
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SOCAnalyzer Manager")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # Try to set icon if available
        icon_path = Path(__file__).parent.parent / "logos" / "icon.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except:
                pass
        
        # State
        self.docker_client: Optional[docker.DockerClient] = None
        self.project_root = Path(__file__).parent.parent
        self.version = self._load_version()
        self.log_thread: Optional[threading.Thread] = None
        self.log_running = False
        self.tray_icon: Optional[pystray.Icon] = None
        
        # Initialize Docker client
        self._init_docker()
        
        # Build UI
        self._build_ui()
        
        # Start initial status check
        self.root.after(500, self.refresh_status)
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _load_version(self) -> str:
        """Load version from VERSION.txt."""
        version_file = self.project_root / "VERSION.txt"
        if version_file.exists():
            return version_file.read_text().strip()
        return "1.0.0"
    
    def _init_docker(self):
        """Initialize Docker client."""
        if docker is None:
            return
        
        try:
            self.docker_client = docker.from_env()
            # Test connection
            self.docker_client.ping()
        except Exception as e:
            self.docker_client = None
    
    def _build_ui(self):
        """Build the main UI."""
        # Top frame - Title and version
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)
        
        title_label = ttk.Label(
            top_frame,
            text="SOCAnalyzer Manager",
            font=("Segoe UI", 16, "bold")
        )
        title_label.pack(side=tk.LEFT)
        
        version_label = ttk.Label(
            top_frame,
            text=f"v{self.version}",
            font=("Segoe UI", 10),
            foreground=self.COLOR_GRAY
        )
        version_label.pack(side=tk.LEFT, padx=10)
        
        # Status frame - Service indicators
        status_frame = ttk.LabelFrame(self.root, text="Service Status", padding="10")
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.status_indicators = {}
        for service_key, service_info in self.SERVICES.items():
            frame = ttk.Frame(status_frame)
            frame.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
            
            canvas = tk.Canvas(frame, width=20, height=20, bg='white', highlightthickness=0)
            canvas.pack()
            circle = canvas.create_oval(2, 2, 18, 18, fill=self.COLOR_GRAY, outline=self.COLOR_GRAY)
            
            label = ttk.Label(frame, text=service_info['name'], font=("Segoe UI", 9))
            label.pack()
            
            self.status_indicators[service_key] = {'canvas': canvas, 'circle': circle, 'label': label}
        
        # Control buttons frame
        button_frame = ttk.Frame(self.root, padding="10")
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.start_button = ttk.Button(
            button_frame,
            text="▶ Start Services",
            command=self._on_start,
            width=20
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(
            button_frame,
            text="■ Stop Services",
            command=self._on_stop,
            width=20
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.restart_button = ttk.Button(
            button_frame,
            text="↻ Restart Services",
            command=self._on_restart,
            width=20
        )
        self.restart_button.pack(side=tk.LEFT, padx=5)
        
        self.browser_button = ttk.Button(
            button_frame,
            text="🌐 Open Browser",
            command=self._on_open_browser,
            width=20
        )
        self.browser_button.pack(side=tk.LEFT, padx=5)
        
        # Secondary buttons frame
        button_frame2 = ttk.Frame(self.root, padding="10")
        button_frame2.pack(fill=tk.X, padx=10, pady=5)
        
        self.refresh_button = ttk.Button(
            button_frame2,
            text="🔄 Refresh Status",
            command=self.refresh_status,
            width=20
        )
        self.refresh_button.pack(side=tk.LEFT, padx=5)
        
        self.update_button = ttk.Button(
            button_frame2,
            text="⬇ Check for Updates",
            command=self._on_check_updates,
            width=20
        )
        self.update_button.pack(side=tk.LEFT, padx=5)
        
        self.backup_button = ttk.Button(
            button_frame2,
            text="💾 Backup Database",
            command=self._on_backup,
            width=20
        )
        self.backup_button.pack(side=tk.LEFT, padx=5)
        
        # Tertiary buttons frame
        button_frame3 = ttk.Frame(self.root, padding="10")
        button_frame3.pack(fill=tk.X, padx=10, pady=5)
        
        self.restore_button = ttk.Button(
            button_frame3,
            text="♻ Restore Database",
            command=self._on_restore,
            width=20
        )
        self.restore_button.pack(side=tk.LEFT, padx=5)
        
        self.manual_update_button = ttk.Button(
            button_frame3,
            text="📦 Manual Update",
            command=self._on_manual_update,
            width=20
        )
        self.manual_update_button.pack(side=tk.LEFT, padx=5)
        
        # Log viewer frame
        log_frame = ttk.LabelFrame(self.root, text="Service Logs", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=15,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#d4d4d4"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        log_controls = ttk.Frame(log_frame)
        log_controls.pack(fill=tk.X, pady=(5, 0))
        
        self.tail_button = ttk.Button(
            log_controls,
            text="▶ Start Log Tail",
            command=self._toggle_log_tail
        )
        self.tail_button.pack(side=tk.LEFT, padx=5)
        
        clear_button = ttk.Button(
            log_controls,
            text="Clear Logs",
            command=self._clear_logs
        )
        clear_button.pack(side=tk.LEFT, padx=5)
        
        # Status bar
        self.status_bar = ttk.Label(
            self.root,
            text="Ready",
            relief=tk.SUNKEN,
            anchor=tk.W,
            font=("Segoe UI", 9)
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Menu bar
        self._build_menu()
    
    def _build_menu(self):
        """Build menu bar."""
        menubar = Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Refresh Status", command=self.refresh_status)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_closing)
        
        # Advanced menu
        advanced_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Advanced", menu=advanced_menu)
        advanced_menu.add_command(label="Reset Database", command=self._on_reset_database)
        advanced_menu.add_command(label="View Docker Logs", command=self._on_view_docker_logs)
        advanced_menu.add_separator()
        advanced_menu.add_command(label="Minimize to Tray", command=self._minimize_to_tray)
        
        # Help menu
        help_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)
    
    def _check_docker_running(self) -> bool:
        """Check if Docker is running."""
        if self.docker_client is None:
            self._show_error(
                "Docker Not Available",
                "Docker is not running. Please start Docker from your Windows Start menu and try again."
            )
            return False
        
        try:
            self.docker_client.ping()
            return True
        except Exception:
            self._show_error(
                "Docker Not Running",
                "Docker is not running. Please start Docker from your Windows Start menu and try again."
            )
            return False
    
    def _check_port_conflicts(self) -> bool:
        """Check for port conflicts."""
        conflicts = []
        for service_key, service_info in self.SERVICES.items():
            port = service_info['port']
            if self._is_port_in_use(port):
                # Check if it's our container
                if not self._is_our_container_on_port(service_info['container']):
                    conflicts.append(f"{service_info['name']} (port {port})")
        
        if conflicts:
            self._show_error(
                "Port Conflict",
                f"Port conflict. Close other applications and try again or contact Brian.\n\n"
                f"Conflicting services: {', '.join(conflicts)}"
            )
            return False
        return True
    
    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is in use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0
    
    def _is_our_container_on_port(self, container_name: str) -> bool:
        """Check if our container is using the port."""
        if not self.docker_client:
            return False
        
        try:
            container = self.docker_client.containers.get(container_name)
            return container.status == 'running'
        except:
            return False
    
    def refresh_status(self):
        """Refresh service status indicators."""
        if not self.docker_client:
            for indicator in self.status_indicators.values():
                indicator['canvas'].itemconfig(indicator['circle'], fill=self.COLOR_GRAY, outline=self.COLOR_GRAY)
            self._update_status("Docker not available")
            return
        
        try:
            for service_key, service_info in self.SERVICES.items():
                try:
                    container = self.docker_client.containers.get(service_info['container'])
                    if container.status == 'running':
                        color = self.COLOR_GREEN
                    elif container.status in ['exited', 'dead']:
                        color = self.COLOR_RED
                    else:
                        color = self.COLOR_YELLOW
                except docker.errors.NotFound:
                    color = self.COLOR_GRAY
                except Exception:
                    color = self.COLOR_GRAY
                
                indicator = self.status_indicators[service_key]
                indicator['canvas'].itemconfig(indicator['circle'], fill=color, outline=color)
            
            self._update_status("Status refreshed")
        except Exception as e:
            self._update_status(f"Error refreshing status: {e}")
    
    def _on_start(self):
        """Start all services."""
        if not self._check_docker_running():
            return
        
        if not self._check_port_conflicts():
            return
        
        self._update_status("Starting services...")
        self._disable_buttons()
        
        threading.Thread(target=self._start_services, daemon=True).start()
    
    def _start_services(self):
        """Start services in background thread."""
        try:
            self._log("Starting SOCAnalyzer services...\n")
            
            # Run docker compose up
            result = subprocess.run(
                ["docker", "compose", "up", "-d"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                self._log("✓ Services started successfully\n")
                self._log(result.stdout)
                
                # Wait for backend health
                self._log("\nWaiting for backend to be healthy...\n")
                if self._wait_for_health():
                    self._log("✓ Backend is healthy\n")
                else:
                    self._log("⚠ Backend health check timed out\n")
                
                self.root.after(0, lambda: self._update_status("Services started"))
            else:
                self._log(f"✗ Error starting services:\n{result.stderr}\n")
                self.root.after(0, lambda: self._update_status("Error starting services"))
        except subprocess.TimeoutExpired:
            self._log("✗ Timeout starting services\n")
            self.root.after(0, lambda: self._update_status("Timeout starting services"))
        except Exception as e:
            self._log(f"✗ Exception: {e}\n")
            self.root.after(0, lambda: self._update_status(f"Error: {e}"))
        finally:
            self.root.after(0, self._enable_buttons)
            self.root.after(100, self.refresh_status)
    
    def _on_stop(self):
        """Stop all services."""
        if not self._check_docker_running():
            return
        
        self._update_status("Stopping services...")
        self._disable_buttons()
        
        threading.Thread(target=self._stop_services, daemon=True).start()
    
    def _stop_services(self):
        """Stop services in background thread."""
        try:
            self._log("Stopping SOCAnalyzer services...\n")
            
            result = subprocess.run(
                ["docker", "compose", "stop"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self._log("✓ Services stopped successfully\n")
                self._log(result.stdout)
                self.root.after(0, lambda: self._update_status("Services stopped"))
            else:
                self._log(f"✗ Error stopping services:\n{result.stderr}\n")
                self.root.after(0, lambda: self._update_status("Error stopping services"))
        except Exception as e:
            self._log(f"✗ Exception: {e}\n")
            self.root.after(0, lambda: self._update_status(f"Error: {e}"))
        finally:
            self.root.after(0, self._enable_buttons)
            self.root.after(100, self.refresh_status)
    
    def _on_restart(self):
        """Restart all services."""
        if not self._check_docker_running():
            return
        
        self._update_status("Restarting services...")
        self._disable_buttons()
        
        threading.Thread(target=self._restart_services, daemon=True).start()
    
    def _restart_services(self):
        """Restart services in background thread."""
        try:
            self._log("Restarting SOCAnalyzer services...\n")
            
            result = subprocess.run(
                ["docker", "compose", "restart"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                self._log("✓ Services restarted successfully\n")
                self._log(result.stdout)
                self.root.after(0, lambda: self._update_status("Services restarted"))
            else:
                self._log(f"✗ Error restarting services:\n{result.stderr}\n")
                self.root.after(0, lambda: self._update_status("Error restarting services"))
        except Exception as e:
            self._log(f"✗ Exception: {e}\n")
            self.root.after(0, lambda: self._update_status(f"Error: {e}"))
        finally:
            self.root.after(0, self._enable_buttons)
            self.root.after(100, self.refresh_status)
    
    def _on_open_browser(self):
        """Open frontend in browser."""
        self._log(f"Opening {self.FRONTEND_URL} in browser...\n")
        webbrowser.open(self.FRONTEND_URL)
        self._update_status("Browser opened")
    
    def _on_backup(self):
        """Run backup script."""
        self._update_status("Running backup...")
        threading.Thread(target=self._run_backup, daemon=True).start()
    
    def _run_backup(self):
        """Run BACKUP.ps1 in background thread."""
        try:
            self._log("Starting database backup...\n")
            
            backup_script = self.project_root / "BACKUP.ps1"
            if not backup_script.exists():
                self.root.after(0, lambda: self._show_error(
                    "Backup Failed",
                    "BACKUP.ps1 script not found in installation folder."
                ))
                return
            
            # Run backup script
            result = subprocess.run(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(backup_script)],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            self._log(result.stdout)
            if result.stderr:
                self._log(result.stderr)
            
            if result.returncode == 0:
                self._log("✓ Backup completed successfully\n")
                self.root.after(0, lambda: messagebox.showinfo(
                    "Backup Complete",
                    "Database backup completed successfully!\n\n"
                    "Backup saved in .\\backups\\ folder."
                ))
            else:
                self._log(f"✗ Backup failed with code {result.returncode}\n")
                self.root.after(0, lambda: self._show_error(
                    "Backup Failed",
                    f"Backup script failed with exit code {result.returncode}.\n\n"
                    f"Check logs for details."
                ))
        except subprocess.TimeoutExpired:
            self._log("✗ Backup timed out after 60 seconds\n")
            self.root.after(0, lambda: self._show_error(
                "Backup Timeout",
                "Backup operation timed out. Database may be too large."
            ))
        except Exception as e:
            self._log(f"✗ Exception during backup: {e}\n")
            self.root.after(0, lambda: self._show_error(
                "Backup Failed",
                f"Failed to run backup: {e}"
            ))
        finally:
            self.root.after(0, lambda: self._update_status("Backup complete"))
    
    def _on_restore(self):
        """Open file picker and run restore."""
        from tkinter import filedialog
        
        # Open file picker
        backup_path = filedialog.askopenfilename(
            title="Select Backup File to Restore",
            initialdir=str(self.project_root / "backups"),
            filetypes=[("SQL Backup Files", "*.sql"), ("All Files", "*.*")]
        )
        
        if not backup_path:
            return  # User cancelled
        
        # Confirm restore (warns about data loss)
        response = messagebox.askyesno(
            "Confirm Restore",
            f"This will OVERWRITE all current database data!\n\n"
            f"Restoring from:\n{Path(backup_path).name}\n\n"
            f"Are you sure you want to continue?",
            icon='warning'
        )
        
        if response:
            self._update_status("Restoring database...")
            threading.Thread(target=self._run_restore, args=(backup_path,), daemon=True).start()
    
    def _run_restore(self, backup_path: str):
        """Run RESTORE.ps1 script with selected backup file."""
        try:
            restore_script = self.project_root / "RESTORE.ps1"
            if not restore_script.exists():
                self._log(f"✗ RESTORE.ps1 not found at {restore_script}\n")
                self.root.after(0, lambda: self._show_error(
                    "Restore Failed",
                    "RESTORE.ps1 script not found."
                ))
                return
            
            self._log(f"Restoring from: {backup_path}\n")
            
            # Run PowerShell script with backup path argument
            result = subprocess.run(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(restore_script), "-BackupPath", backup_path],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minutes for restore
                cwd=str(self.project_root),
                input="YES\n"  # Auto-confirm the restore prompt
            )
            
            # Log output
            if result.stdout:
                self._log(result.stdout)
            if result.stderr:
                self._log(f"Errors:\n{result.stderr}\n")
            
            if result.returncode == 0:
                self._log("✓ Restore completed successfully\n")
                self.root.after(0, lambda: messagebox.showinfo(
                    "Restore Complete",
                    "Database restored successfully.\nBackend service was restarted."
                ))
            else:
                self._log(f"✗ Restore failed with code {result.returncode}\n")
                self.root.after(0, lambda: self._show_error(
                    "Restore Failed",
                    f"Restore script failed with exit code {result.returncode}.\n\n"
                    f"Check logs for details."
                ))
        except subprocess.TimeoutExpired:
            self._log("✗ Restore timed out after 120 seconds\n")
            self.root.after(0, lambda: self._show_error(
                "Restore Timeout",
                "Restore operation timed out. Backup file may be too large."
            ))
        except Exception as e:
            self._log(f"✗ Exception during restore: {e}\n")
            self.root.after(0, lambda: self._show_error(
                "Restore Failed",
                f"Failed to run restore: {e}"
            ))
        finally:
            self.root.after(0, lambda: self._update_status("Restore complete"))
    
    def _on_update_now(self):
        """Trigger update check that may lead to automatic update."""
        self._update_status("Checking for updates...")
        threading.Thread(target=self._check_updates, daemon=True).start()
    
    def _on_manual_update(self):
        """Manual update - user selects ZIP file."""
        from tkinter import filedialog
        
        # Ask user to select ZIP file
        zip_path = filedialog.askopenfilename(
            title="Select SOCAnalyzer Update ZIP",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
            initialdir=str(Path.home() / "Downloads")
        )
        
        if not zip_path:
            return  # User cancelled
        
        zip_file = Path(zip_path)
        if not zip_file.exists():
            self._show_error("File Not Found", f"Selected file does not exist:\n{zip_path}")
            return
        
        # Try to extract version from filename (e.g., SOCAnalyzer-Docker-v1.0.12.zip)
        import re
        match = re.search(r'v?(\d+\.\d+\.\d+)', zip_file.name)
        if match:
            new_version = match.group(1)
        else:
            new_version = "unknown"
        
        # Confirm with user
        response = messagebox.askyesno(
            "Manual Update",
            f"Update from selected file?\n\n"
            f"File: {zip_file.name}\n"
            f"Version: {new_version}\n"
            f"Current: {self.version}\n\n"
            f"This will:\n"
            f"1. Backup your database\n"
            f"2. Stop services\n"
            f"3. Install update\n"
            f"4. Restart services\n\n"
            f"Continue?",
            icon='question'
        )
        
        if response:
            self._perform_manual_update(zip_path, new_version)
    
    def _perform_manual_update(self, zip_path: str, new_version: str):
        """Perform manual update from selected ZIP file."""
        threading.Thread(target=self._run_manual_update, args=(zip_path, new_version), daemon=True).start()
    
    def _run_manual_update(self, zip_path: str, new_version: str):
        """Run manual update process."""
        try:
            self._log(f"\n{'='*60}\n")
            self._log(f"Starting manual update to v{new_version}...\n")
            self._log(f"{'='*60}\n\n")
            
            # Step 1: Backup database
            self._log("Step 1/4: Creating backup...\n")
            backup_script = self.project_root / "BACKUP.ps1"
            if not backup_script.exists():
                raise Exception("BACKUP.ps1 not found")
            
            result = subprocess.run(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(backup_script)],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=60
            )
            self._log(result.stdout)
            if result.returncode != 0:
                raise Exception(f"Backup failed with code {result.returncode}")
            self._log("✓ Backup complete\n\n")
            
            # Step 2: Stop services
            self._log("Step 2/4: Stopping services...\n")
            self._stop_services()
            time.sleep(5)
            self._log("✓ Services stopped\n\n")
            
            # Step 3: Extract update
            self._log(f"Step 3/4: Extracting {Path(zip_path).name}...\n")
            import zipfile
            import shutil
            
            # Extract to temp directory
            temp_dir = self.project_root / f"temp_update_{new_version}"
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Find the extracted folder (should contain docker-compose.yml)
            extracted_folders = [d for d in temp_dir.iterdir() if d.is_dir()]
            if extracted_folders:
                source_dir = extracted_folders[0]
            else:
                source_dir = temp_dir
            
            # Copy files (skip data directory to preserve user data)
            for item in source_dir.iterdir():
                if item.name == 'data':
                    continue  # Don't overwrite data directory
                
                dest = self.project_root / item.name
                if item.is_file():
                    shutil.copy2(item, dest)
                    self._log(f"  Copied: {item.name}\n")
                elif item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                    self._log(f"  Copied: {item.name}/\n")
            
            # Update VERSION.txt
            version_file = self.project_root / "VERSION.txt"
            version_file.write_text(new_version)
            self.version = new_version
            
            # Clean up temp directory
            shutil.rmtree(temp_dir)
            self._log("✓ Update extracted\n\n")
            
            # Step 4: Restart services
            self._log("Step 4/4: Starting services...\n")
            self._start_services()
            self._log("✓ Services started\n\n")
            
            # Wait for backend health
            self._log("Waiting for backend to be ready...\n")
            if self._wait_for_health(timeout=60):
                self._log("✓ Backend is healthy\n\n")
            else:
                self._log("⚠ Backend health check timed out\n\n")
            
            self._log(f"{'='*60}\n")
            self._log(f"✓ Manual update to v{new_version} complete!\n")
            self._log(f"{'='*60}\n")
            
            self.root.after(0, lambda: messagebox.showinfo(
                "Update Complete",
                f"Successfully updated to v{new_version}!\n\n"
                f"Services have been restarted."
            ))
            
        except Exception as e:
            self._log(f"\n✗ Manual update failed: {e}\n")
            self.root.after(0, lambda: self._show_error(
                "Update Failed",
                f"Manual update failed:\n\n{e}\n\n"
                f"Your database backup is safe.\n"
                f"Check logs for details."
            ))
        finally:
            self.root.after(0, self.refresh_status)
    
    def _perform_update(self, new_version: str):
        """Perform automated update process."""
        threading.Thread(target=self._run_update, args=(new_version,), daemon=True).start()
    
    def _run_update(self, new_version: str):
        """Run the complete update process."""
        try:
            self._log(f"\n{'='*60}\n")
            self._log(f"Starting automated update to v{new_version}...\n")
            self._log(f"{'='*60}\n\n")
            
            # Step 1: Backup database
            self._log("Step 1/5: Creating backup...\n")
            backup_script = self.project_root / "BACKUP.ps1"
            if not backup_script.exists():
                raise Exception("BACKUP.ps1 not found")
            
            result = subprocess.run(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(backup_script)],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=60
            )
            self._log(result.stdout)
            if result.returncode != 0:
                raise Exception(f"Backup failed with code {result.returncode}")
            self._log("✓ Backup complete\n\n")
            
            # Step 2: Download new version
            self._log(f"Step 2/5: Getting v{new_version}...\n")
            zip_path = self.project_root / f"SOCAnalyzer-Docker-v{new_version}.zip"
            
            # Try to copy from OneDrive sync folder first (much faster)
            onedrive_source = Path.home() / "OneDrive - NANDPS" / "Documents" / "GRC" / "8 - Tools" / "SOC Analyzer" / f"v{new_version}" / f"SOCAnalyzer-Docker-v{new_version}.zip"
            
            if onedrive_source.exists():
                self._log(f"Copying from OneDrive sync folder...\n")
                import shutil
                shutil.copy2(onedrive_source, zip_path)
                total_size = onedrive_source.stat().st_size
                self._log(f"✓ Copied {total_size / (1024*1024):.1f} MB\n\n")
            else:
                # Fallback to download from SharePoint (requires authentication)
                self._log(f"OneDrive sync not found, downloading from SharePoint...\n")
                download_url = f"https://nandps.sharepoint.com/teams/GRC/Shared%20Documents/8%20-%20Tools/SOC%20Analyzer/v{new_version}/SOCAnalyzer-Docker-v{new_version}.zip"
                
                import urllib.request
                with urllib.request.urlopen(download_url, timeout=300) as response:
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    chunk_size = 8192
                    
                    with open(zip_path, 'wb') as f:
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                self._log(f"\rDownloading: {progress:.1f}% ({downloaded / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB)")
                
                self._log("\n✓ Download complete\n\n")
            
            # Step 3: Stop services
            self._log("Step 3/5: Stopping services...\n")
            result = subprocess.run(
                ["docker", "compose", "down"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=60
            )
            self._log(result.stdout)
            if result.returncode != 0:
                self._log(f"Warning: docker compose down returned {result.returncode}\n")
            self._log("✓ Services stopped\n\n")
            
            # Step 4: Extract update
            self._log("Step 4/5: Installing update...\n")
            import zipfile
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Extract to parent directory (overwrites current installation)
                zip_ref.extractall(self.project_root)
            
            # Delete zip file
            zip_path.unlink()
            self._log("✓ Update installed\n\n")
            
            # Step 5: Restart services
            self._log("Step 5/5: Restarting services...\n")
            import_script = self.project_root / "IMPORT.ps1"
            if import_script.exists():
                result = subprocess.run(
                    ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(import_script)],
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                self._log(result.stdout)
            else:
                # Fallback: just run docker compose up
                result = subprocess.run(
                    ["docker", "compose", "up", "-d"],
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                self._log(result.stdout)
            
            self._log("\n✓ Services restarted\n\n")
            self._log(f"{'='*60}\n")
            self._log(f"Update to v{new_version} completed successfully!\n")
            self._log(f"{'='*60}\n")
            
            def show_success():
                messagebox.showinfo(
                    "Update Complete",
                    f"Successfully updated to v{new_version}!\n\n"
                    f"Services have been restarted.\n"
                    f"Please restart the manager to see the new version."
                )
                # Update version display
                self.version = new_version
                self.version_label.config(text=f"Version: {self.version}")
            
            self.root.after(0, show_success)
            
        except Exception as e:
            self._log(f"\n✗ Update failed: {e}\n")
            self.root.after(0, lambda: self._show_error(
                "Update Failed",
                f"Automatic update failed: {e}\n\n"
                f"You can update manually:\n"
                f"1. Run: .\\BACKUP.ps1\n"
                f"2. Download from SharePoint\n"
                f"3. Extract and run: .\\IMPORT.ps1\n\n"
                f"See UPDATE.txt for instructions."
            ))
        finally:
            self.root.after(0, lambda: self._update_status("Update complete"))
    
    def _on_check_updates(self):
        """Check for updates from SharePoint."""
        self._update_status("Checking for updates...")
        threading.Thread(target=self._check_updates, daemon=True).start()
    
    def _check_updates(self):
        """Check for updates in background thread."""
        try:
            self._log("Checking for updates...\n")
            
            # Try to access via OneDrive sync folder first (faster and no auth issues)
            onedrive_path = Path.home() / "OneDrive - NANDPS" / "Documents" / "GRC" / "8 - Tools" / "SOC Analyzer" / "VERSION.txt"
            if onedrive_path.exists():
                self._log("Using OneDrive sync folder...\n")
                remote_version = onedrive_path.read_text().strip()
                response = type('obj', (object,), {'status_code': 200, 'text': remote_version})()
            else:
                # Fallback to SharePoint URL (requires authentication)
                self._log("OneDrive sync not found, trying SharePoint...\n")
                response = requests.get(self.SHAREPOINT_VERSION_URL, timeout=10)
            
            if response.status_code == 200:
                remote_version = response.text.strip()
                self._log(f"Remote version: {remote_version}\n")
                self._log(f"Local version: {self.version}\n")
                
                if remote_version != self.version:
                    # Ask if user wants to update now
                    def ask_update():
                        response = messagebox.askyesno(
                            "Update Available",
                            f"Version {remote_version} is available!\n"
                            f"Current version: {self.version}\n\n"
                            f"Would you like to update now?\n\n"
                            f"This will:\n"
                            f"1. Backup your database\n"
                            f"2. Download v{remote_version}\n"
                            f"3. Stop services\n"
                            f"4. Install update\n"
                            f"5. Restart services\n\n"
                            f"Estimated time: 5-10 minutes",
                            icon='info'
                        )
                        if response:
                            self._perform_update(remote_version)
                    
                    self.root.after(0, ask_update)
                else:
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Up to Date",
                        f"You have the latest version ({self.version})."
                    ))
            else:
                self._log(f"✗ Failed to check updates: HTTP {response.status_code}\n")
                self.root.after(0, lambda: self._show_error(
                    "Update Check Failed",
                    f"Failed to check for updates (HTTP {response.status_code})."
                ))
        except Exception as e:
            self._log(f"✗ Exception checking updates: {e}\n")
            self.root.after(0, lambda: self._show_error(
                "Update Check Failed",
                f"Failed to check for updates: {e}"
            ))
        finally:
            self.root.after(0, lambda: self._update_status("Update check complete"))
    
    def _wait_for_health(self, timeout: int = 30) -> bool:
        """Wait for backend health check."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                response = requests.get(self.BACKEND_HEALTH_URL, timeout=2)
                if response.status_code == 200:
                    return True
            except:
                pass
            time.sleep(2)
        return False
    
    def _toggle_log_tail(self):
        """Toggle log tailing."""
        if self.log_running:
            self.log_running = False
            self.tail_button.config(text="▶ Start Log Tail")
            self._update_status("Log tail stopped")
        else:
            self.log_running = True
            self.tail_button.config(text="■ Stop Log Tail")
            self._update_status("Log tail started")
            self.log_thread = threading.Thread(target=self._tail_logs, daemon=True)
            self.log_thread.start()
    
    def _tail_logs(self):
        """Tail Docker Compose logs."""
        try:
            process = subprocess.Popen(
                ["docker", "compose", "logs", "-f", "--tail=100"],
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            while self.log_running:
                line = process.stdout.readline()
                if not line:
                    break
                self._log(line)
            
            process.terminate()
        except Exception as e:
            self._log(f"✗ Error tailing logs: {e}\n")
    
    def _on_reset_database(self):
        """Reset database (docker compose down -v)."""
        result = messagebox.askyesno(
            "Reset Database",
            "This will delete ALL scan data and reset the database.\n\n"
            "Are you sure you want to continue?",
            icon=messagebox.WARNING
        )
        
        if result:
            self._update_status("Resetting database...")
            self._disable_buttons()
            threading.Thread(target=self._reset_database, daemon=True).start()
    
    def _reset_database(self):
        """Reset database in background thread."""
        try:
            self._log("Resetting database (docker compose down -v)...\n")
            
            result = subprocess.run(
                ["docker", "compose", "down", "-v"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self._log("✓ Database reset successfully\n")
                self._log(result.stdout)
                self.root.after(0, lambda: messagebox.showinfo(
                    "Database Reset",
                    "Database has been reset. Start services to reinitialize."
                ))
            else:
                self._log(f"✗ Error resetting database:\n{result.stderr}\n")
        except Exception as e:
            self._log(f"✗ Exception: {e}\n")
        finally:
            self.root.after(0, self._enable_buttons)
            self.root.after(0, lambda: self._update_status("Ready"))
            self.root.after(100, self.refresh_status)
    
    def _on_view_docker_logs(self):
        """View raw Docker logs."""
        threading.Thread(target=self._view_docker_logs, daemon=True).start()
    
    def _view_docker_logs(self):
        """View Docker logs in background thread."""
        try:
            result = subprocess.run(
                ["docker", "compose", "logs", "--tail=200"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=10
            )
            
            self._log("\n=== Docker Logs ===\n")
            self._log(result.stdout)
            if result.stderr:
                self._log(result.stderr)
            self._log("\n=== End of Logs ===\n")
        except Exception as e:
            self._log(f"✗ Error viewing logs: {e}\n")
    
    def _minimize_to_tray(self):
        """Minimize to system tray."""
        if pystray is None:
            messagebox.showerror("Not Available", "System tray support not available.")
            return
        
        self.root.withdraw()
        self._create_tray_icon()
    
    def _create_tray_icon(self):
        """Create system tray icon."""
        if pystray is None:
            return
        
        # Create simple icon
        image = Image.new('RGB', (64, 64), color='purple')
        draw = ImageDraw.Draw(image)
        draw.rectangle([16, 16, 48, 48], fill='white')
        
        menu = pystray.Menu(
            pystray.MenuItem("Show", self._show_from_tray),
            pystray.MenuItem("Exit", self._exit_from_tray)
        )
        
        self.tray_icon = pystray.Icon("SOCAnalyzer", image, "SOCAnalyzer Manager", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
    
    def _show_from_tray(self):
        """Show window from tray."""
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.root.deiconify()
    
    def _exit_from_tray(self):
        """Exit from tray."""
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()
    
    def _show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About SOCAnalyzer Manager",
            f"SOCAnalyzer Manager v{self.version}\n\n"
            "Desktop application for managing SOCAnalyzer Docker services.\n\n"
            "Contact: Brian Klumpp"
        )
    
    def _log(self, message: str):
        """Add message to log viewer."""
        def append():
            self.log_text.insert(tk.END, message)
            self.log_text.see(tk.END)
        
        if threading.current_thread() == threading.main_thread():
            append()
        else:
            self.root.after(0, append)
    
    def _clear_logs(self):
        """Clear log viewer."""
        self.log_text.delete(1.0, tk.END)
        self._update_status("Logs cleared")
    
    def _update_status(self, message: str):
        """Update status bar."""
        self.status_bar.config(text=message)
    
    def _disable_buttons(self):
        """Disable control buttons."""
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        self.restart_button.config(state=tk.DISABLED)
        self.refresh_button.config(state=tk.DISABLED)
    
    def _enable_buttons(self):
        """Enable control buttons."""
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)
        self.restart_button.config(state=tk.NORMAL)
        self.refresh_button.config(state=tk.NORMAL)
    
    def _show_error(self, title: str, message: str):
        """Show error dialog."""
        messagebox.showerror(title, message)
    
    def _on_closing(self):
        """Handle window close."""
        if self.log_running:
            self.log_running = False
            if self.log_thread:
                self.log_thread.join(timeout=1)
        
        if self.tray_icon:
            self.tray_icon.stop()
        
        self.root.quit()


def main():
    """Main entry point."""
    root = tk.Tk()
    app = SOCAnalyzerManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()
