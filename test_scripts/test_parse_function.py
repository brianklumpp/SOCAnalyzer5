"""Test the parse_control_json function with different formats."""

import sys
sys.path.insert(0, 'backend')

from app.extractors.control_extractor_v4 import parse_control_json
import json

print("=" * 80)
print("TEST: parse_control_json() - Multi-Format Support")
print("=" * 80)

# Test 1: New format (array of controls)
print("\n✅ Test 1: New format - Multiple controls")
new_format = {
    "controls": [
        {"control_id": "CC1.1", "control_desc": "Test 1", "control_tests": ["Test"], "control_confidence": 0.9},
        {"control_id": "CC1.2", "control_desc": "Test 2", "control_tests": ["Test"], "control_confidence": 0.95}
    ]
}
result = parse_control_json(json.dumps(new_format), 1)
print(f"   Input: {len(new_format['controls'])} controls in array")
print(f"   Output: {len(result) if result else 0} controls")
print(f"   Result: {'PASS' if result and len(result) == 2 else 'FAIL'}")

# Test 2: New format (single control in array)
print("\n✅ Test 2: New format - Single control in array")
new_format_single = {
    "controls": [
        {"control_id": "CC1.1", "control_desc": "Test 1", "control_tests": ["Test"], "control_confidence": 0.9}
    ]
}
result = parse_control_json(json.dumps(new_format_single), 2)
print(f"   Input: 1 control in array")
print(f"   Output: {len(result) if result else 0} controls")
print(f"   Result: {'PASS' if result and len(result) == 1 else 'FAIL'}")

# Test 3: Old format (single control object)
print("\n✅ Test 3: Old format - Single control object (backward compat)")
old_format = {
    "control_id": "CC1.1",
    "control_desc": "Test 1",
    "control_tests": ["Test"],
    "control_confidence": 0.9
}
result = parse_control_json(json.dumps(old_format), 3)
print(f"   Input: Single control object (old format)")
print(f"   Output: {len(result) if result else 0} controls")
print(f"   Result: {'PASS' if result and len(result) == 1 else 'FAIL'}")

# Test 4: Markdown wrapped
print("\n✅ Test 4: Markdown code block")
markdown_format = f"""```json
{json.dumps(new_format)}
```"""
result = parse_control_json(markdown_format, 4)
print(f"   Input: JSON in markdown code block")
print(f"   Output: {len(result) if result else 0} controls")
print(f"   Result: {'PASS' if result and len(result) == 2 else 'FAIL'}")

# Test 5: Invalid JSON
print("\n✅ Test 5: Invalid JSON")
invalid = "This is not JSON"
result = parse_control_json(invalid, 5)
print(f"   Input: Invalid JSON")
print(f"   Output: {result}")
print(f"   Result: {'PASS' if result is None else 'FAIL'}")

print("\n" + "=" * 80)
print("All tests completed!")
print("=" * 80)
