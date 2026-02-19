#!/usr/bin/env python3
"""Check TOC page offset and page markers for latest scan."""

from app.database import SessionLocal
from app.models import Scan, ControlObjective

db = SessionLocal()

# Get latest scan
scan = db.query(Scan).order_by(Scan.id.desc()).first()

if scan:
    print(f"=== Scan {scan.id}: {scan.report_name} ===")
    print(f"TOC page offset: {scan.toc_page_offset}")
    print(f"Report type: {scan.report_type}")
    
    # Get a few objectives with page refs
    objectives = db.query(ControlObjective).filter(
        ControlObjective.scan_id == scan.id,
        ControlObjective.page_refs.isnot(None)
    ).limit(10).all()
    
    print(f"\n=== Sample Objectives (showing first 10) ===")
    for obj in objectives:
        print(f"ID: {obj.objective_id} | Line: {obj.line_ref} | Pages: {obj.page_refs}")
        
    # Check for CC5.1 specifically
    cc51 = db.query(ControlObjective).filter(
        ControlObjective.scan_id == scan.id,
        ControlObjective.objective_id.like('%CC5.1%')
    ).first()
    
    if cc51:
        print(f"\n=== CC5.1 Details ===")
        print(f"Objective ID: {cc51.objective_id}")
        print(f"Line ref: {cc51.line_ref}")
        print(f"Page refs: {cc51.page_refs}")
        print(f"Text preview: {cc51.objective_text[:100]}...")
else:
    print("No scans found")

db.close()
