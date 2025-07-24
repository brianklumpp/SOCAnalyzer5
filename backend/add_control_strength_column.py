#!/usr/bin/env python3
"""
Migration script to add control_strength column to cuec table
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.config import DATABASE_URL
import sqlalchemy as sa

def add_control_strength_column():
    """Add control_strength column to cuec table"""
    engine = sa.create_engine(DATABASE_URL)
    
    # Check if column already exists
    inspector = sa.inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('cuec')]
    
    if 'control_strength' in columns:
        print("Column 'control_strength' already exists in cuec table")
        return
    
    # Add the column
    with engine.connect() as conn:
        try:
            conn.execute(sa.text("ALTER TABLE cuec ADD COLUMN control_strength VARCHAR(32)"))
            conn.commit()
            print("Successfully added 'control_strength' column to cuec table")
        except Exception as e:
            print(f"Error adding column: {e}")
            conn.rollback()
            raise

if __name__ == "__main__":
    add_control_strength_column() 