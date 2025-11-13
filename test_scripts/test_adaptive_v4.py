"""
Test V4 multi-control extraction with updated prompt.
This tests the new adaptive chunking approach.
"""

import sys
sys.path.insert(0, 'backend')

from app import config

print("=" * 80)
print("V4 MULTI-CONTROL EXTRACTION - ADAPTIVE CHUNKING TEST")
print("=" * 80)

print("\n⚙️  V4 CONFIGURATION")
print(f"   Tokens per chunk: {config.CONTROL_V4_TOKENS_PER_CHUNK}")
print(f"   Overlap tokens: {config.CONTROL_V4_OVERLAP_TOKENS}")
print(f"   Min confidence: {config.CONTROL_V4_MIN_CONFIDENCE}")

print("\n📋 PROMPT ANALYSIS")
prompt_lines = config.CONTROL_EXTRACTION_PROMPT_V4.split('\n')
key_lines = [
    line for line in prompt_lines 
    if any(keyword in line.lower() for keyword in ['extract all', 'multiple', 'array', 'controls', 'chunk'])
]

print("   Key instructions found:")
for line in key_lines[:10]:
    if line.strip():
        print(f"      • {line.strip()[:100]}")

# Check response format
if '"controls": [' in config.CONTROL_EXTRACTION_PROMPT_V4:
    print("\n   ✅ Response format: Array of controls")
    print("      Returns: {\"controls\": [{...}, {...}]}")
else:
    print("\n   ❌ Response format: Single control (old format)")
    print("      Returns: {...}")

# Check backward compatibility
if 'backwards compatibility' in config.CONTROL_EXTRACTION_PROMPT_V4.lower():
    print("   ✅ Backward compatibility noted")
else:
    print("   ℹ️  No explicit backward compatibility mention")

print("\n🎯 ADAPTIVE BEHAVIOR")
print("   The extractor should now:")
print("   • Extract ALL controls found in each chunk")
print("   • Handle sparse reports (1 control/chunk)")
print("   • Handle dense reports (2+ controls/chunk)")
print("   • Handle split controls (continuation=true)")
print("   • Adapt to different auditor formats")

print("\n💡 EXPECTED IMPROVEMENTS")
print(f"   Previous run (500 tokens/chunk):")
print(f"      • 79 chunks created")
print(f"      • 79 controls extracted (1 per chunk)")
print(f"      • 5 merged from continuations")
print(f"      • Final: 72 controls")
print(f"")
print(f"   With multi-control extraction:")
print(f"      • 79 chunks created (same)")
print(f"      • ~120-150 controls extracted (1.5-1.9 per chunk)")
print(f"      • Fewer continuations needed")
print(f"      • Final: ~130-140 controls ✅")

print("\n🔍 CHUNK SIZE ANALYSIS")
# Calculate expected controls per chunk for Adobe
adobe_controls = 138
adobe_section_lines = 3714
controls_per_line = adobe_controls / adobe_section_lines
tokens_per_chunk = config.CONTROL_V4_TOKENS_PER_CHUNK
lines_per_chunk = (tokens_per_chunk * 4) / 40  # Rough estimate

expected_controls_per_chunk = controls_per_line * lines_per_chunk

print(f"   Adobe report density:")
print(f"      • Total controls: {adobe_controls}")
print(f"      • Section lines: {adobe_section_lines}")
print(f"      • Controls per line: {controls_per_line:.4f}")
print(f"")
print(f"   Current chunk size ({tokens_per_chunk} tokens):")
print(f"      • Estimated lines per chunk: ~{lines_per_chunk:.0f}")
print(f"      • Expected controls per chunk: ~{expected_controls_per_chunk:.2f}")
print(f"")
print(f"   This means the extractor should find ~{expected_controls_per_chunk:.1f} controls")
print(f"   in each chunk on average for Adobe-like reports.")

print("\n✅ READY TO TEST")
print("   Run: python interactive_scan.py")
print("        Select option 2: Run Individual Extractors")
print("        Select control extractor")
print("")
print("   Expected: ~130-150 controls extracted from Adobe report")
