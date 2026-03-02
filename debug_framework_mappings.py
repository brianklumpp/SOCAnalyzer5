"""
Debug script to trace framework_mappings through the data pipeline.
"""
import json
import os

# Paths - resolved relative to this script's location
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONTROL_RESULT_PATH = os.path.join(PROJECT_ROOT, 'data', 'json', 'control_result.json')
COMBINED_RESULT_PATH = os.path.join(PROJECT_ROOT, 'data', 'json', 'combined_result.json')

print("=" * 80)
print("FRAMEWORK_MAPPINGS DEBUG TRACE")
print("=" * 80)

# Check control_result.json
print("\n1. Checking control_result.json...")
with open(CONTROL_RESULT_PATH, 'r', encoding='utf-8') as f:
    control_result = json.load(f)

first_control = control_result['controls'][0]
print(f"   First control ID: {first_control.get('control_id')}")
print(f"   Has framework_mappings: {' framework_mappings' in first_control}")
print(f"   Has primary_framework: {'primary_framework' in first_control}")
print(f"   Has primary_criterion_id: {'primary_criterion_id' in first_control}")
print(f"   Has primary_confidence: {'primary_confidence' in first_control}")

if 'framework_mappings' in first_control:
    fm = first_control['framework_mappings']
    print(f"   framework_mappings type: {type(fm)}")
    if isinstance(fm, dict):
        print(f"   framework_mappings keys: {list(fm.keys())}")

# Simulate the analyze.py flattening logic
print("\n2. Simulating analyze.py flattening (line 1677)...")
val = control_result
inner_key = 'controls'
simulated_standardized = [dict(c) for c in val[inner_key]]

first_simulated = simulated_standardized[0]
print(f"   After dict(c) - control ID: {first_simulated.get('control_id')}")
print(f"   After dict(c) - Has framework_mappings: {'framework_mappings' in first_simulated}")
print(f"   After dict(c) - Has primary_framework: {'primary_framework' in first_simulated}")

# Check combined_result.json
print("\n3. Checking combined_result.json...")
with open(COMBINED_RESULT_PATH, 'r', encoding='utf-8') as f:
    combined_result = json.load(f)

first_combined_control = combined_result['controls'][0]
print(f"   First control ID: {first_combined_control.get('control_id')}")
print(f"   Has framework_mappings: {'framework_mappings' in first_combined_control}")
print(f"   Has primary_framework: {'primary_framework' in first_combined_control}")

# Compare keys
print("\n4. Comparing control keys...")
control_result_keys = set(first_control.keys())
combined_result_keys = set(first_combined_control.keys())

print(f"   Keys in control_result.json: {len(control_result_keys)}")
print(f"   Keys in combined_result.json: {len(combined_result_keys)}")

missing_keys = control_result_keys - combined_result_keys
if missing_keys:
    print(f"\n   ❌ MISSING KEYS in combined_result.json:")
    for key in sorted(missing_keys):
        print(f"      - {key}")

extra_keys = combined_result_keys - control_result_keys
if extra_keys:
    print(f"\n   ➕ EXTRA KEYS in combined_result.json:")
    for key in sorted(extra_keys):
        print(f"      - {key}")

if not missing_keys and not extra_keys:
    print("   ✅ Keys match exactly!")

print("\n" + "=" * 80)
