"""Analyze control density in the Adobe report."""

import json

# Load controls
with open('data/json/control_result.json', 'r') as f:
    data = json.load(f)

controls = data.get('controls', [])

print("=" * 80)
print("CONTROL DENSITY ANALYSIS")
print("=" * 80)

# Section bounds
section_start = 1898
section_end = 5612
section_lines = section_end - section_start  # 3714

print(f"\nSection: lines {section_start}-{section_end} ({section_lines} lines)")
print(f"Controls found: {len(controls)}")
print(f"Average lines per control: {section_lines / len(controls):.1f}")

# Analyze control spacing
control_lines = []
for i, control in enumerate(controls):
    start = control.get('source_start_line', 0)
    end = control.get('end_line', 0)
    lines = end - start
    control_lines.append(lines)
    
avg_control_lines = sum(control_lines) / len(control_lines)
min_control_lines = min(control_lines)
max_control_lines = max(control_lines)

print(f"\nControl size statistics:")
print(f"  Average lines per control: {avg_control_lines:.1f}")
print(f"  Min lines: {min_control_lines}")
print(f"  Max lines: {max_control_lines}")

# Check for large gaps between controls
print(f"\n--- GAPS BETWEEN CONTROLS ---")
gaps = []
for i in range(len(controls) - 1):
    current_end = controls[i].get('end_line', 0)
    next_start = controls[i+1].get('source_start_line', 0)
    gap = next_start - current_end
    if gap > 50:  # Large gap
        gaps.append({
            'after_control': i+1,
            'control_id': controls[i].get('control_id'),
            'gap_lines': gap,
            'from_line': current_end,
            'to_line': next_start
        })

print(f"Found {len(gaps)} large gaps (>50 lines):")
for gap in gaps[:10]:
    print(f"  Gap {gap['gap_lines']} lines after control #{gap['after_control']} ({gap['control_id']}): lines {gap['from_line']}-{gap['to_line']}")

# Chunking analysis
tokens_per_chunk = 500
overlap_tokens = 100
chars_per_token = 4
chars_per_chunk = tokens_per_chunk * chars_per_token  # 2000
lines_per_chunk = 50  # Rough estimate

print(f"\n--- CHUNKING VS CONTROL DENSITY ---")
print(f"Chunk size: ~{lines_per_chunk} lines ({tokens_per_chunk} tokens)")
print(f"Controls per chunk (average): {lines_per_chunk / avg_control_lines:.2f}")
print(f"\nIf Adobe has 138 controls in {section_lines} lines:")
print(f"  Average lines per control: {section_lines / 138:.1f}")
print(f"  Controls per chunk (expected): {lines_per_chunk / (section_lines / 138):.2f}")

print(f"\n⚠️  V4 LIMITATION")
print(f"   V4 extracts 1 control per chunk")
print(f"   79 chunks → max 79 controls")
print(f"   But Adobe has ~138 controls → need ~{138 / 79:.1f} controls per chunk")

print(f"\n💡 SOLUTIONS")
print(f"   1. Reduce chunk size to extract each control individually")
print(f"      Current: 500 tokens/chunk → try 250 tokens/chunk")
print(f"      Would create ~{79 * 2} chunks")
print(f"   ")
print(f"   2. Extract MULTIPLE controls per chunk (requires prompt change)")
print(f"      Change prompt to: 'Extract ALL controls in this chunk'")
print(f"      Parse response as array of controls instead of single control")
