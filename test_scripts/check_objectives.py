#!/usr/bin/env python3
"""Check objectives extracted from most recent scan"""
from sqlalchemy import create_engine, text
import os

os.environ['DATABASE_URL'] = 'postgresql://soc2_analyzer:puntitforthewin@localhost:5432/soc2analyzer'
engine = create_engine(os.getenv('DATABASE_URL'))

with engine.connect() as conn:
    # Get most recent scan ID
    scan_result = conn.execute(text('SELECT MAX(id) FROM scans'))
    scan_id = scan_result.fetchone()[0]
    print(f"Most recent scan_id: {scan_id}\n")
    
    # Get objectives
    result = conn.execute(text('''
        SELECT objective_id, final_confidence, extraction_method 
        FROM control_objectives 
        WHERE scan_id = :scan_id 
        ORDER BY objective_id
    '''), {'scan_id': scan_id})
    
    rows = result.fetchall()
    print(f"Total objectives extracted: {len(rows)}\n")
    print("objective_id | confidence | method")
    print("-" * 60)
    
    # Track series
    cc_series = []
    c_series = []
    a_series = []
    p_series = []
    pi_series = []
    
    for row in rows:
        obj_id = row[0] or "NULL"
        print(f"{obj_id:<15} | {row[1]:>6.2f} | {row[2]}")
        
        if obj_id and obj_id.startswith('CC'):
            cc_series.append(obj_id)
        elif obj_id and obj_id.startswith('C') and not obj_id.startswith('CC'):
            c_series.append(obj_id)
        elif obj_id and obj_id.startswith('A'):
            a_series.append(obj_id)
        elif obj_id and obj_id.startswith('P') and not obj_id.startswith('PI'):
            p_series.append(obj_id)
        elif obj_id and obj_id.startswith('PI'):
            pi_series.append(obj_id)
    
    print("\n" + "="*60)
    print("SERIES BREAKDOWN:")
    print("="*60)
    print(f"CC series ({len(cc_series)}): {', '.join(sorted(cc_series)) if cc_series else 'NONE'}")
    print(f"C series ({len(c_series)}): {', '.join(sorted(c_series)) if c_series else 'NONE'}")
    print(f"A series ({len(a_series)}): {', '.join(sorted(a_series)) if a_series else 'NONE'}")
    print(f"P series ({len(p_series)}): {', '.join(sorted(p_series)) if p_series else 'NONE'}")
    print(f"PI series ({len(pi_series)}): {', '.join(sorted(pi_series)) if pi_series else 'NONE'}")
