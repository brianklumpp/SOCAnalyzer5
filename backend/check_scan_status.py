#!/usr/bin/env python3
"""Check status of latest scan."""

from app.database import SessionLocal
from app.models import Scan, Control, ControlObjective
from datetime import datetime

db = SessionLocal()

# Get latest scan
scan = db.query(Scan).order_by(Scan.id.desc()).first()

if scan:
    print(f"=== Latest Scan (ID: {scan.id}) ===")
    print(f"Report name: {scan.report_name}")
    print(f"Status: {scan.status}")
    print(f"Created: {scan.created_at}")
    print(f"Updated: {scan.updated_at}")
    print(f"Report type: {scan.report_type}")
    print(f"As of date: {scan.as_of_date}")
    
    # Count extracted data
    control_count = db.query(Control).filter(Control.scan_id == scan.id).count()
    objective_count = db.query(ControlObjective).filter(ControlObjective.scan_id == scan.id).count()
    
    print(f"\n=== Extracted Data ===")
    print(f"Controls: {control_count}")
    print(f"Objectives: {objective_count}")
    
    # Check for any error details
    if hasattr(scan, 'error_message') and scan.error_message:
        print(f"\n=== Errors ===")
        print(f"Error: {scan.error_message}")
    
    # Check executive summary
    if hasattr(scan, 'executive_summary') and scan.executive_summary:
        print(f"\n=== Executive Summary (first 200 chars) ===")
        print(scan.executive_summary[:200])
    else:
        print(f"\n=== Executive Summary ===")
        print("NOT GENERATED")
else:
    print("No scans found")

db.close()
