"""
Test script to manually trigger objective mapping with debug logging.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.extractors.objective_extractor import map_controls_to_objectives

# Connect to database (using default values from docker-compose.yml)
DATABASE_URL = "postgresql://soc2_analyzer:puntitforthewin@localhost:5433/soc2analyzer"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

# Run mapping with force=True to recreate all mappings
print("Starting objective mapping for scan_id=2...")
try:
    mappings_created = map_controls_to_objectives(
        scan_id=2,
        db_session=session,
        force=True  # Force remapping
    )
    print(f"Mapping completed: {mappings_created} mappings created")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
finally:
    session.close()
