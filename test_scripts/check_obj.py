#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app/backend')
from sqlalchemy import create_engine, text
import os

DB_URL = "postgresql://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"
engine = create_engine(DB_URL)
conn = engine.connect()

# Get latest scan
scan_result = conn.execute(text('SELECT MAX(id) FROM scans'))
scan_id = scan_result.fetchone()[0]
print(f"Latest scan_id: {scan_id}\n")

# Get objectives
result = conn.execute(text('SELECT objective_id, extraction_method FROM control_objectives WHERE scan_id = :sid ORDER BY objective_id'), {'sid': scan_id})
rows = result.fetchall()

cc = [r[0] for r in rows if r[0] and r[0].startswith('CC')]
c = [r[0] for r in rows if r[0] and r[0].startswith('C') and not r[0].startswith('CC')]
a = [r[0] for r in rows if r[0] and r[0].startswith('A')]
p = [r[0] for r in rows if r[0] and r[0].startswith('P') and not r[0].startswith('PI')]
pi = [r[0] for r in rows if r[0] and r[0].startswith('PI')]

print(f"Total objectives: {len(rows)}")
print(f"\nCC series ({len(cc)}): {', '.join(sorted(cc)) if cc else 'NONE'}")
print(f"C series ({len(c)}): {', '.join(sorted(c)) if c else 'NONE'}")
print(f"A series ({len(a)}): {', '.join(sorted(a)) if a else 'NONE'}")
print(f"P series ({len(p)}): {', '.join(sorted(p)) if p else 'NONE'}")
print(f"PI series ({len(pi)}): {', '.join(sorted(pi)) if pi else 'NONE'}")

# Check extraction methods
gpt = len([r for r in rows if r[1] == 'gpt_inferred'])
gap = len([r for r in rows if r[1] == 'gap_search'])
other = len([r for r in rows if r[1] not in ['gpt_inferred', 'gap_search']])
print(f"\nExtraction methods:")
print(f"  GPT inferred: {gpt}")
print(f"  Gap search: {gap}")
print(f"  Other: {other}")
