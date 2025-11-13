"""Test a minimal V4 extraction to identify the issue."""

import sys
sys.path.insert(0, 'backend')

from app.extractors import control_extractor_v4
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

print("=" * 80)
print("MINIMAL V4 EXTRACTION TEST")
print("=" * 80)

try:
    print("\n1. Testing extract_controls_v4()...")
    
    # Run extraction with no resume
    result = control_extractor_v4.extract_controls_v4()
    
    if result:
        print(f"\n✅ Extraction completed")
        print(f"   Result type: {type(result)}")
        print(f"   Keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
        
        if 'controls' in result:
            print(f"   Controls: {len(result['controls'])}")
        if 'diagnostics' in result:
            print(f"   Diagnostics: {result['diagnostics']}")
        if 'error' in result:
            print(f"   ❌ ERROR: {result['error']}")
    else:
        print("\n❌ Extraction returned None")
        
except Exception as e:
    print(f"\n❌ EXCEPTION during extraction:")
    print(f"   Type: {type(e).__name__}")
    print(f"   Message: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
