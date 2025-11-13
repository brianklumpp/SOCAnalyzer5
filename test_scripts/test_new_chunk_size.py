"""Test smaller chunk size configuration."""

import sys
sys.path.insert(0, 'backend')

from app import config

# Load section info
import json
with open('data/json/section_results.json', 'r') as f:
    sections = json.load(f)

control_section = next((s for s in sections if s["topic"] == "Control_Descriptions"), None)
section_start = control_section["start_line"]
section_end = control_section["end_line"]

# Load text
with open('data/output/output.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()

section_text = ''.join(lines[section_start-1:section_end])
section_chars = len(section_text)
section_tokens = section_chars // 4

# Get V4 config
tokens_per_chunk = config.CONTROL_V4_TOKENS_PER_CHUNK
overlap_tokens = config.CONTROL_V4_OVERLAP_TOKENS
effective_tokens = tokens_per_chunk - overlap_tokens

# Calculate expected chunks
expected_chunks = (section_tokens // effective_tokens) + 1

print("=" * 80)
print("V4 CONFIGURATION TEST - SMALLER CHUNKS")
print("=" * 80)

print(f"\n📄 SECTION INFO")
print(f"   Lines: {section_start}-{section_end} ({section_end - section_start} lines)")
print(f"   Characters: {section_chars:,}")
print(f"   Tokens: ~{section_tokens:,}")

print(f"\n⚙️  NEW V4 CONFIG")
print(f"   Tokens per chunk: {tokens_per_chunk}")
print(f"   Overlap tokens: {overlap_tokens}")
print(f"   Effective tokens per chunk: {effective_tokens}")

print(f"\n🔢 EXPECTED RESULTS")
print(f"   Expected chunks: ~{expected_chunks}")
print(f"   Previous chunks: 79")
print(f"   Increase: +{expected_chunks - 79} chunks ({((expected_chunks / 79) - 1) * 100:.1f}%)")

print(f"\n📊 CONTROL PREDICTION")
print(f"   If 1 control per chunk:")
print(f"      Expected controls: ~{expected_chunks}")
print(f"      Previous controls: 72")
print(f"      Target controls: 138")

if expected_chunks >= 138:
    print(f"\n   ✅ Should extract enough controls to reach target!")
    print(f"      {expected_chunks} chunks >= 138 target controls")
else:
    print(f"\n   ⚠️  May still fall short")
    print(f"      {expected_chunks} chunks < 138 target controls")
    print(f"      Would need {138 - expected_chunks} more chunks")

print(f"\n💡 RECOMMENDATION")
print(f"   Run V4 extraction with new config (250 tokens/chunk)")
print(f"   Expected: ~{expected_chunks} controls extracted")
