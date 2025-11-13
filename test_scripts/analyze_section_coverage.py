"""Calculate expected chunks for the ACTUAL control section."""

# Section info
start_line = 1898
end_line = 5612
total_lines = end_line - start_line  # 3714

# Load the text
with open('data/output/output.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()

section_text = ''.join(lines[start_line-1:end_line])
section_chars = len(section_text)
section_tokens = section_chars // 4  # Rough estimate

print("=" * 80)
print("ACTUAL CONTROL SECTION ANALYSIS")
print("=" * 80)
print(f"Start line: {start_line}")
print(f"End line: {end_line}")
print(f"Total lines: {total_lines}")
print(f"Total characters: {section_chars:,}")
print(f"Approximate tokens: {section_tokens:,}")

# Configuration
tokens_per_chunk = 500
overlap_tokens = 100
effective_tokens = tokens_per_chunk - overlap_tokens

print(f"\n⚙️  V4 CONFIGURATION")
print(f"Tokens per chunk: {tokens_per_chunk}")
print(f"Overlap tokens: {overlap_tokens}")
print(f"Effective tokens per chunk: {effective_tokens}")

# Expected chunks
expected_chunks = (section_tokens // effective_tokens) + 1

print(f"\n🔢 EXPECTED CHUNKS")
print(f"Formula: {section_tokens} tokens / {effective_tokens} effective = ~{expected_chunks} chunks")

# Check against actual
import json
with open('data/json/control_result.json', 'r', encoding='utf-8') as f:
    result = json.load(f)

actual_chunks = result.get('diagnostics', {}).get('total_chunks', 0)
actual_controls = len(result.get('controls', []))

print(f"\n✅ ACTUAL RESULTS")
print(f"Chunks created: {actual_chunks}")
print(f"Controls extracted: {actual_controls}")
print(f"Expected chunks: ~{expected_chunks}")
print(f"Difference: {actual_chunks - expected_chunks}")

if abs(actual_chunks - expected_chunks) <= 10:
    print(f"\n✅ CHUNKING IS CORRECT!")
    print(f"   The section boundary ends at line {end_line} (correct)")
    print(f"   Created {actual_chunks} chunks as expected")
else:
    print(f"\n❌ CHUNKING ISSUE!")
    print(f"   Expected ~{expected_chunks} but got {actual_chunks}")

# Check if all 138 controls are in this section
print(f"\n📊 CONTROL COVERAGE")
print(f"Target controls: 138")
print(f"Found controls: {actual_controls}")
print(f"Coverage: {(actual_controls/138)*100:.1f}%")

if actual_controls < 138:
    print(f"\n⚠️  MISSING {138 - actual_controls} CONTROLS")
    print(f"   Possible reasons:")
    print(f"   1. Many controls merged as continuations")
    print(f"   2. Low confidence controls rejected")
    print(f"   3. Parsing failures")
    print(f"   4. GPT didn't detect controls in some chunks")
