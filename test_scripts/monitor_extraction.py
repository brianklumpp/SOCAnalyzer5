"""Monitor control extraction in real-time."""

import sys
sys.path.insert(0, 'backend')

from app.extractors.control_integration import extract_controls
import time

print("=" * 80)
print("CONTROL EXTRACTION MONITOR - V4 with Multi-Control Support")
print("=" * 80)

print("\n⚙️  Starting extraction...")
print("   Version: v4 (AWARE-CHUNK + Chain-of-Thought)")
print("   Multi-control extraction: ENABLED")
print("   Output: data/json/control_result.json")

start_time = time.time()

try:
    # Run extraction
    extract_controls(version='v4')
    
    elapsed = time.time() - start_time
    print(f"\n✅ Extraction completed in {elapsed:.1f}s")
    
    # Load and display results
    import json
    with open('data/json/control_result.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    controls = data.get('controls', [])
    diagnostics = data.get('diagnostics', {})
    
    print(f"\n📊 RESULTS:")
    print(f"   Total controls extracted: {len(controls)}")
    
    if diagnostics:
        print(f"\n   Diagnostics:")
        for key, value in diagnostics.items():
            print(f"      {key}: {value}")
    
    if len(controls) > 0:
        print(f"\n   Sample controls:")
        for i, ctrl in enumerate(controls[:5], 1):
            ctrl_id = ctrl.get('control_id', 'N/A')
            conf = ctrl.get('control_confidence', 0)
            print(f"      {i}. {ctrl_id} (confidence: {conf:.2f})")
    else:
        print(f"\n   ⚠️  WARNING: No controls extracted!")
        
except Exception as e:
    elapsed = time.time() - start_time
    print(f"\n❌ EXTRACTION FAILED after {elapsed:.1f}s")
    print(f"   Error: {type(e).__name__}: {str(e)}")
    print(f"\n   Check logs for details:")
    print(f"      data/logs/control_extractor.log")
    print(f"      data/logs/backend_errors.log")
    
    import traceback
    print(f"\n   Full traceback:")
    traceback.print_exc()

print("\n" + "=" * 80)
