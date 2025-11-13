"""
Analyze V4 control extraction to understand why only 31 controls were found instead of 138
"""
import json
import sys
sys.path.insert(0, 'backend')

from app import config

print("=" * 80)
print("V4 CONTROL EXTRACTION ANALYSIS")
print("=" * 80)

# Load the extraction results
with open('data/json/control_result.json', encoding='utf-8') as f:
    result = json.load(f)

controls = result.get('controls', [])
diagnostics = result.get('diagnostics', {})
rejected = result.get('rejected_controls', [])

print(f"\n📊 EXTRACTION RESULTS")
print(f"   Extractor version: {diagnostics.get('extractor_version')}")
print(f"   Total chunks processed: {diagnostics.get('total_chunks')}")
print(f"   Raw controls extracted: {diagnostics.get('raw_controls_extracted')}")
print(f"   Controls merged: {diagnostics.get('controls_merged')}")
print(f"   Final control count: {diagnostics.get('final_control_count')}")
print(f"   Controls rejected: {diagnostics.get('controls_rejected_confidence')}")
print(f"   Average confidence: {diagnostics.get('avg_confidence'):.1%}")
print(f"   Processing time: {diagnostics.get('processing_time_seconds')}s")

# Load extracted text to analyze
with open('data/json/combined_result.json', encoding='utf-8') as f:
    combined = json.load(f)

text = combined.get('extracted_text', '')
lines = text.split('\n')
total_chars = len(text)
approx_tokens = total_chars // 4  # Rough estimate

print(f"\n📄 DOCUMENT ANALYSIS")
print(f"   Total lines: {len(lines):,}")
print(f"   Total characters: {total_chars:,}")
print(f"   Approximate tokens: {approx_tokens:,}")

# V4 Configuration
print(f"\n⚙️  V4 CONFIGURATION")
print(f"   Tokens per chunk: {config.CONTROL_V4_TOKENS_PER_CHUNK}")
print(f"   Overlap tokens: {config.CONTROL_V4_OVERLAP_TOKENS}")
print(f"   Effective tokens per chunk: {config.CONTROL_V4_TOKENS_PER_CHUNK - config.CONTROL_V4_OVERLAP_TOKENS}")
print(f"   Min confidence threshold: {config.CONTROL_V4_MIN_CONFIDENCE}")

# Calculate expected chunks
effective_chunk_tokens = config.CONTROL_V4_TOKENS_PER_CHUNK - config.CONTROL_V4_OVERLAP_TOKENS
expected_chunks = approx_tokens // effective_chunk_tokens

print(f"\n🔢 CHUNK ANALYSIS")
print(f"   Expected chunks (theoretical): ~{expected_chunks}")
print(f"   Actual chunks created: {diagnostics.get('total_chunks')}")
print(f"   Difference: {expected_chunks - diagnostics.get('total_chunks', 0)}")

# Analyze control coverage
control_line_ranges = []
for ctrl in controls:
    start = ctrl.get('source_start_line', 0)
    end = ctrl.get('end_line', start)
    control_line_ranges.append((start, end, ctrl.get('control_id', 'N/A')))

control_line_ranges.sort()

print(f"\n📋 CONTROL COVERAGE ANALYSIS")
print(f"   First control starts at line: {control_line_ranges[0][0] if control_line_ranges else 'N/A'}")
print(f"   Last control ends at line: {control_line_ranges[-1][1] if control_line_ranges else 'N/A'}")
print(f"   Document ends at line: {len(lines)}")

if control_line_ranges:
    covered_lines = control_line_ranges[-1][1] - control_line_ranges[0][0]
    coverage_pct = (covered_lines / len(lines)) * 100
    print(f"   Line coverage: {covered_lines:,} / {len(lines):,} ({coverage_pct:.1f}%)")

# Check for gaps
print(f"\n🔍 GAP ANALYSIS (first 10 gaps)")
gaps = []
for i in range(len(control_line_ranges) - 1):
    curr_end = control_line_ranges[i][1]
    next_start = control_line_ranges[i+1][0]
    gap_size = next_start - curr_end
    if gap_size > 50:  # Significant gap
        gaps.append((curr_end, next_start, gap_size, control_line_ranges[i][2], control_line_ranges[i+1][2]))

gaps.sort(key=lambda x: x[2], reverse=True)  # Sort by gap size

for i, (end, start, gap, prev_id, next_id) in enumerate(gaps[:10], 1):
    print(f"   {i}. Gap of {gap:,} lines between {prev_id} (ends line {end}) and {next_id} (starts line {start})")

# Check control IDs
control_ids = [c.get('control_id') for c in controls if c.get('control_id')]
print(f"\n🏷️  CONTROL IDs FOUND ({len(control_ids)} with IDs)")
print(f"   Sample IDs: {', '.join(str(x) for x in control_ids[:10])}")
if len(control_ids) > 10:
    print(f"   ... and {len(control_ids) - 10} more")

# Expected vs actual
print(f"\n⚠️  ISSUE IDENTIFICATION")
print(f"   Expected controls: ~138")
print(f"   Found controls: {len(controls)}")
print(f"   Missing: ~{138 - len(controls)} ({((138 - len(controls)) / 138 * 100):.1f}% of expected)")

print(f"\n🔬 ROOT CAUSE ANALYSIS")
if diagnostics.get('total_chunks', 0) < expected_chunks:
    print(f"   ❌ PROBLEM: Only {diagnostics.get('total_chunks')} chunks created vs {expected_chunks} expected")
    print(f"      → Chunking logic may be stopping early")
    print(f"      → Check create_aware_chunks() function")
else:
    print(f"   ❌ PROBLEM: V4 extracts 1 control per chunk by design")
    print(f"      → Need to either:")
    print(f"         1. Reduce chunk size to ~500 tokens (more chunks = more controls)")
    print(f"         2. Change prompt to extract ALL controls in chunk")
    print(f"         3. Use iterative extraction within each chunk")

print("\n" + "=" * 80)
