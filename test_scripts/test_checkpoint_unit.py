"""
Unit test for checkpoint functionality - doesn't require full extraction.
Tests the write_checkpoint function directly with mock data.
"""

import sys
import os
import json
import tempfile

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Mock config for testing
class MockConfig:
    CONTROL_JSON_PATH = tempfile.mktemp(suffix='_test_control.json')

# Inject mock config
sys.modules['app.config'] = MockConfig()

# Now import the function we want to test
from app.extractors.control_extractor import write_checkpoint, CHECKPOINT_FILE

# Set checkpoint file path
checkpoint_file = MockConfig.CONTROL_JSON_PATH.replace('.json', '_checkpoint.json')

print("=== Testing Checkpoint Functionality ===\n")
print(f"Checkpoint file: {checkpoint_file}")

# Clean up any existing file
if os.path.exists(checkpoint_file):
    os.remove(checkpoint_file)
    print("Cleaned up existing checkpoint")

# Test 1: Write checkpoint with mock data
print("\n[Test 1] Writing checkpoint with 15 mock controls...")
mock_controls = [
    {
        "control_id": f"TEST-{i:02d}",
        "control_desc": f"Test control description {i}",
        "control_confidence": 0.9,
        "has_deviation": False
    }
    for i in range(1, 16)
]

mock_diagnostics = {
    "status": "extracting",
    "controls_validated": 15,
    "total_raw_controls": 20,
    "elapsed_seconds": 45.2
}

# Import the function's globals
import app.extractors.control_extractor as extractor_module
extractor_module.CHECKPOINT_FILE = checkpoint_file

write_checkpoint(
    validated_controls=mock_controls,
    rejected_controls=[],
    diagnostics=mock_diagnostics,
    scan_id="test-checkpoint-unit"
)

# Test 2: Verify checkpoint was created
print("[Test 2] Verifying checkpoint file was created...")
if os.path.exists(checkpoint_file):
    print("✓ Checkpoint file created successfully")
else:
    print("✗ FAILED: Checkpoint file not created")
    sys.exit(1)

# Test 3: Verify checkpoint contents
print("[Test 3] Verifying checkpoint contents...")
with open(checkpoint_file, 'r', encoding='utf-8') as f:
    checkpoint_data = json.load(f)

assert checkpoint_data["scan_id"] == "test-checkpoint-unit", "scan_id mismatch"
assert checkpoint_data["status"] == "in_progress", "status should be in_progress"
assert checkpoint_data["control_count"] == 15, f"Expected 15 controls, got {checkpoint_data['control_count']}"
assert len(checkpoint_data["controls"]) == 15, "controls array length mismatch"
assert "timestamp" in checkpoint_data, "timestamp missing"
assert checkpoint_data["diagnostics"]["status"] == "extracting", "diagnostics status mismatch"

print("✓ Checkpoint contents verified successfully")
print(f"  - scan_id: {checkpoint_data['scan_id']}")
print(f"  - status: {checkpoint_data['status']}")
print(f"  - control_count: {checkpoint_data['control_count']}")
print(f"  - timestamp: {checkpoint_data['timestamp']}")
print(f"  - diagnostics: {checkpoint_data['diagnostics']['status']}")

# Test 4: Test atomic write (write again to simulate update)
print("[Test 4] Testing atomic write (update scenario)...")
mock_controls.append({
    "control_id": "TEST-16",
    "control_desc": "Additional control",
    "control_confidence": 0.85,
    "has_deviation": False
})

mock_diagnostics["controls_validated"] = 16

write_checkpoint(
    validated_controls=mock_controls,
    rejected_controls=[],
    diagnostics=mock_diagnostics,
    scan_id="test-checkpoint-unit"
)

with open(checkpoint_file, 'r', encoding='utf-8') as f:
    updated_checkpoint = json.load(f)

assert updated_checkpoint["control_count"] == 16, "Update failed"
print("✓ Atomic write/update works correctly")
print(f"  - Updated control_count: {updated_checkpoint['control_count']}")

# Test 5: Verify temp file cleanup
print("[Test 5] Verifying no temp files left behind...")
temp_file = checkpoint_file + ".tmp"
if os.path.exists(temp_file):
    print("✗ FAILED: Temp file not cleaned up")
    sys.exit(1)
print("✓ No temp files remaining")

# Cleanup
os.remove(checkpoint_file)
print("\n=== All Tests Passed! ===")
print("\nCheckpoint functionality is working correctly:")
print("  ✓ Checkpoint file created")
print("  ✓ Correct JSON structure")
print("  ✓ All required fields present")
print("  ✓ Atomic writes working")
print("  ✓ Updates working")
print("  ✓ No temp file leaks")
print("\nThe incremental write feature is ready for production use!")
