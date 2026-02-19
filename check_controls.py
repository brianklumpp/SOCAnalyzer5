#!/usr/bin/env python3
"""Check control confidence distribution for stuck scan."""

from sqlalchemy import create_engine, text

engine = create_engine('postgresql://soc2analyzer:password@localhost:5433/soc2analyzer')

with engine.connect() as conn:
    # Get latest scan ID
    result = conn.execute(text('SELECT id, company_name FROM scan ORDER BY created_at DESC LIMIT 1'))
    scan = result.fetchone()
    if not scan:
        print("No scans found")
        exit(1)
    
    scan_id, company = scan
    print(f"\n=== Scan: {company} (ID: {scan_id}) ===\n")
    
    # Control confidence stats
    result = conn.execute(text('''
        SELECT 
            COUNT(*) as total_controls,
            COUNT(CASE WHEN control_confidence >= 0.65 THEN 1 END) as high_confidence,
            COUNT(CASE WHEN control_confidence < 0.65 THEN 1 END) as low_confidence,
            MIN(control_confidence) as min_conf,
            MAX(control_confidence) as max_conf,
            AVG(control_confidence) as avg_conf
        FROM control 
        WHERE scan_id = :scan_id
    '''), {'scan_id': scan_id})
    
    row = result.fetchone()
    print(f"Total controls: {row[0]}")
    print(f"High confidence (>=0.65): {row[1]}")
    print(f"Low confidence (<0.65): {row[2]}")
    print(f"Min: {row[3]:.4f}, Max: {row[4]:.4f}, Avg: {row[5]:.4f}")
    
    # Objective stats
    result = conn.execute(text('''
        SELECT 
            COUNT(*) as total_objectives,
            COUNT(CASE WHEN final_confidence >= 0.65 THEN 1 END) as high_confidence
        FROM control_objectives 
        WHERE scan_id = :scan_id
    '''), {'scan_id': scan_id})
    
    row = result.fetchone()
    print(f"\nTotal objectives: {row[0]}")
    print(f"High confidence objectives: {row[1]}")
    
    # Check for mappings
    result = conn.execute(text('''
        SELECT COUNT(*) FROM control_objective_associations WHERE scan_id = :scan_id
    '''), {'scan_id': scan_id})
    
    mappings = result.fetchone()[0]
    print(f"Control-objective mappings created: {mappings}")
    
    if row[1] == 0:
        print("\n❌ PROBLEM: Control filtering removed ALL controls (none >= 0.65 confidence)")
        print("   This would cause objective mapping to skip entirely!")
