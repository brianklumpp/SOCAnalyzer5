#!/usr/bin/env python3
"""Check scan table schema."""

import sys
import os
sys.path.insert(0, '/app/backend')

from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'scan'
        ORDER BY ordinal_position
    """))
    
    print("Scan table columns:")
    for row in result:
        print(f"  {row[0]}: {row[1]}")
