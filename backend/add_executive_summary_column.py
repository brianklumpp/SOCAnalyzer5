#!/usr/bin/env python3
"""
Migration script to add executive_summary column to scan table
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.config import DATABASE_URL
import sqlalchemy as sa

def add_executive_summary_column():
    """Add executive_summary column to scan table"""
    engine = sa.create_engine(DATABASE_URL)
    
    # Check if column already exists
    inspector = sa.inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('scan')]
    
    if 'executive_summary' in columns:
        print("Column 'executive_summary' already exists in scan table")
        return
    
    # Add the column
    with engine.connect() as conn:
        try:
            conn.execute(sa.text("ALTER TABLE scan ADD COLUMN executive_summary JSON"))
            conn.commit()
            print("Successfully added 'executive_summary' column to scan table")
        except Exception as e:
            print(f"Error adding column: {e}")
            conn.rollback()
            raise

if __name__ == "__main__":
    add_executive_summary_column() 