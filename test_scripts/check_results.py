import json
import pprint

# Load the control extraction results
with open('data/json/control_result.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

controls = data.get('controls', [])
diagnostics = data.get('diagnostics', {})

print("=" * 80)
print("V4 MULTI-CONTROL EXTRACTION RESULTS")
print("=" * 80)
print(f"\n✅ Total Controls Extracted: {len(controls)}")
print(f"\nDiagnostics:")
for key, value in diagnostics.items():
    print(f"  {key}: {value}")

if controls:
    print(f"\n📊 Sample Controls (first 3):")
    print("-" * 80)
    for i, ctrl in enumerate(controls[:3], 1):
        print(f"\n{i}. Control ID: {ctrl.get('control_id', 'N/A')}")
        print(f"   Description: {ctrl.get('control_desc', 'N/A')[:100]}...")
        print(f"   Tests: {len(ctrl.get('control_tests', []))} test(s)")
        print(f"   Results: {len(ctrl.get('control_test_results', []))} result(s)")
        print(f"   Confidence: {ctrl.get('control_confidence', 'N/A')}")
    
    # Control count by confidence
    high_conf = sum(1 for c in controls if c.get('control_confidence', 0) >= 0.8)
    med_conf = sum(1 for c in controls if 0.5 <= c.get('control_confidence', 0) < 0.8)
    low_conf = sum(1 for c in controls if c.get('control_confidence', 0) < 0.5)
    
    print(f"\n📈 Confidence Distribution:")
    print(f"   High (≥0.8): {high_conf} controls")
    print(f"   Medium (0.5-0.8): {med_conf} controls")
    print(f"   Low (<0.5): {low_conf} controls")
    
    # Controls with IDs vs without
    with_id = sum(1 for c in controls if c.get('control_id'))
    without_id = len(controls) - with_id
    
    print(f"\n🏷️  Control IDs:")
    print(f"   With ID: {with_id} controls")
    print(f"   Without ID: {without_id} controls")
else:
    print("\n❌ No controls extracted!")

print("\n" + "=" * 80)
