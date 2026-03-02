#!/usr/bin/env python3
"""
Quick CUEC extraction test - runs CUEC extractor on an existing scan
SKIPS FRAMEWORK MAPPING for speed
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.extractors.cuec_extractor import extract_cuecs
from app import config
import json

# Use the most recent scan
SCAN_ID = "6d8534eb-9b05-4b49-8087-b3b2085a5fb8"
JOB_ID = 1
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_PATH = PROJECT_ROOT / "data" / "jobs" / str(JOB_ID) / SCAN_ID

print(f"Running CUEC extraction on scan: {SCAN_ID}")
print(f"Base path: {BASE_PATH}")

# Check if paths exist
pdf_txt_path = BASE_PATH / "temp" / "output.txt"
section_json_path = BASE_PATH / "json" / "section_results.json"

if not pdf_txt_path.exists():
    print(f"ERROR: {pdf_txt_path} not found!")
    sys.exit(1)

if not section_json_path.exists():
    print(f"ERROR: {section_json_path} not found!")
    sys.exit(1)

print(f"[OK] Found output.txt")
print(f"[OK] Found section_results.json")

# Set up job paths
job_paths = {
    'output_dir': BASE_PATH / "temp",
    'json_dir': BASE_PATH / "json",
    'logs_dir': PROJECT_ROOT / "data" / "logs",
    'temp_dir': BASE_PATH / "temp"
}

print(f"\nExtracting CUECs (SKIPPING FRAMEWORK MAPPING for speed)...")
print(f"Look for [CUEC DEBUG] output below:\n")

# Run extraction - SKIP FRAMEWORK MAPPING
result = extract_cuecs(
    report_type="SOC2",
    job_paths=job_paths,
    job_id=f"test_{SCAN_ID}",
    disable_chunking=False,
    skip_framework_mapping=True,  # SKIP MAPPING FOR SPEED
    redis_client=None
)

# Check results
cuec_result_path = BASE_PATH / "json" / "cuec_result.json"
if cuec_result_path.exists():
    with open(cuec_result_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    cuecs = data.get('cuecs', [])
    print(f"\n\n[OK] Extracted {len(cuecs)} CUECs")
    
    # Check first few for line refs and page refs
    print(f"\nChecking first 5 CUECs for line_ref and page_refs:")
    for i, cuec in enumerate(cuecs[:5]):
        line_ref = cuec.get('cuec_line_ref')
        page_refs = cuec.get('cuec_page_refs', [])
        desc = cuec.get('cuec_description', '')[:80]
        print(f"\n  CUEC {i+1}:")
        print(f"    Description: {desc}...")
        print(f"    Line Ref: {line_ref}")
        print(f"    Page Refs: {page_refs}")
else:
    print(f"ERROR: {cuec_result_path} not created!")
