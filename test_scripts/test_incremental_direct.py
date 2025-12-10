"""
Test incremental write feature by calling extract_controls directly.
This bypasses the API to test the core checkpoint functionality.
"""

import sys
import os
import json
import time

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.extractors.control_extractor import extract_controls
from app import config

# Test configuration
CHECKPOINT_FILE = str(config.CONTROL_JSON_PATH).replace('.json', '_checkpoint.json')
print(f"Checkpoint file: {CHECKPOINT_FILE}")

# Clean up any existing checkpoint
if os.path.exists(CHECKPOINT_FILE):
    os.remove(CHECKPOINT_FILE)
    print("✓ Cleaned up existing checkpoint file")

# Load sections (must exist from previous run)
with open(config.SECTION_JSON_PATH, 'r', encoding='utf-8') as f:
    sections = json.load(f)

print(f"Loaded {len(sections)} sections from {config.SECTION_JSON_PATH}")

# Start extraction
print("\n=== Starting extraction with incremental checkpoints ===\n")
print("Monitor checkpoint file in real-time:")
print(f"  Get-Content '{CHECKPOINT_FILE}' -Raw | ConvertFrom-Json\n")

start_time = time.time()

# Run extraction (will create checkpoints every 10 controls)
try:
    result = extract_controls(
        sections=sections,
        report_type="SOC2",
        enable_assertion_mapping=False,
        scan_id="test-incremental-write"
    )
    
    elapsed = time.time() - start_time
    print(f"\n=== Extraction Complete ===")
    print(f"Time: {elapsed:.1f} seconds")
    print(f"Controls extracted: {len(result.get('controls', []))}")
    print(f"Checkpoint file should be removed: {not os.path.exists(CHECKPOINT_FILE)}")
    
    if os.path.exists(CHECKPOINT_FILE):
        print("⚠ Warning: Checkpoint file still exists (should be cleaned up)")
    else:
        print("✓ Checkpoint file properly cleaned up")
        
except KeyboardInterrupt:
    print("\n\n=== Interrupted by user ===")
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            checkpoint = json.load(f)
        print(f"✓ Checkpoint preserved with {checkpoint.get('control_count', 0)} controls")
        print(f"  Timestamp: {checkpoint.get('timestamp', 'N/A')}")
        print(f"  Status: {checkpoint.get('status', 'N/A')}")
    else:
        print("✗ No checkpoint file found")
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
