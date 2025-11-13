"""Check last scan results."""

import json

# Load control results
with open('data/json/control_result.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

controls = data.get('controls', [])
diagnostics = data.get('diagnostics', {})

print("=" * 80)
print("LAST SCAN RESULTS")
print("=" * 80)

print(f"\nTotal controls: {len(controls)}")

if diagnostics:
    print("\nDiagnostics:")
    for key, value in diagnostics.items():
        print(f"  {key}: {value}")
else:
    print("\nNo diagnostics found")

# Check for errors
if len(controls) == 0:
    print("\n⚠️  ISSUE: Zero controls extracted!")
    print("\nPossible causes:")
    print("  1. JSON parsing error (new format not backward compatible)")
    print("  2. GPT returned old format and parser rejected it")
    print("  3. Extraction error occurred")
    print("  4. All controls rejected for low confidence")
    
    # Check rejected controls
    rejected = data.get('rejected_controls', [])
    if rejected:
        print(f"\n  Found {len(rejected)} rejected controls")
        print(f"  First rejected: {rejected[0].get('control_id', 'N/A')}, confidence: {rejected[0].get('control_confidence', 0)}")
