"""
Quick script to check database schema for required columns
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import text, create_engine

# Create synchronous engine (using credentials from docker-compose.yml)
engine = create_engine('postgresql://socuser:socpass@localhost:5433/socanalyzer')

print("Checking control table schema...")
print("-" * 60)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name='control' 
        ORDER BY column_name
    """))
    
    all_columns = {row[0]: row[1] for row in result}
    
    # Check for required columns
    required_columns = [
        'financial_assertions',
        'framework_category',
        'framework_mappings',
        'primary_framework',
        'primary_criterion_id',
        'primary_confidence',
        'control_tsc_mappings',
        'control_coso_mappings'
    ]
    
    print("\nRequired columns status:")
    for col in required_columns:
        if col in all_columns:
            print(f"✓ {col}: {all_columns[col]}")
        else:
            print(f"✗ {col}: MISSING")

print("\n" + "-" * 60)
print("\nChecking scan table schema...")
print("-" * 60)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name='scan' 
        ORDER BY column_name
    """))
    
    scan_columns = {row[0]: row[1] for row in result}
    
    # Check for report_type
    if 'report_type' in scan_columns:
        print(f"✓ report_type: {scan_columns['report_type']}")
    else:
        print("✗ report_type: MISSING")

print("\n" + "-" * 60)
