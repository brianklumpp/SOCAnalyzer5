"""
Test the fixed chunking logic to verify we get the expected number of chunks
"""
import sys
sys.path.insert(0, 'backend')

from app.extractors.control_extractor_v4 import create_aware_chunks
from app import config
import json

print("=" * 80)
print("V4 CHUNKING TEST")
print("=" * 80)

# Load the extracted text
with open('data/json/combined_result.json', encoding='utf-8') as f:
    data = json.load(f)

text = data.get('extracted_text', '')
lines = text.split('\n')

print(f"\n📄 DOCUMENT INFO")
print(f"   Total lines: {len(lines):,}")
print(f"   Total characters: {len(text):,}")
print(f"   Approximate tokens: {len(text)//4:,}")

print(f"\n⚙️  V4 CONFIGURATION")
print(f"   Tokens per chunk: {config.CONTROL_V4_TOKENS_PER_CHUNK}")
print(f"   Overlap tokens: {config.CONTROL_V4_OVERLAP_TOKENS}")
print(f"   Chars per chunk: {config.CONTROL_V4_TOKENS_PER_CHUNK * 4}")
print(f"   Overlap chars: {config.CONTROL_V4_OVERLAP_TOKENS * 4}")

# Calculate expected chunks
effective_tokens = config.CONTROL_V4_TOKENS_PER_CHUNK - config.CONTROL_V4_OVERLAP_TOKENS
expected_chunks = (len(text) // 4) // effective_tokens

print(f"\n🔢 EXPECTED CHUNKS")
print(f"   Effective tokens per chunk: {effective_tokens}")
print(f"   Expected chunks: ~{expected_chunks}")

# Create chunks
print(f"\n🔨 CREATING CHUNKS...")
chunks = create_aware_chunks(
    text_lines=lines,
    start_line=1,
    end_line=len(lines),
    tokens_per_chunk=config.CONTROL_V4_TOKENS_PER_CHUNK,
    overlap_tokens=config.CONTROL_V4_OVERLAP_TOKENS
)

print(f"\n✅ RESULTS")
print(f"   Chunks created: {len(chunks)}")
print(f"   Expected: ~{expected_chunks}")
print(f"   Difference: {len(chunks) - expected_chunks}")

if len(chunks) >= expected_chunks * 0.9:  # Within 10%
    print(f"   ✅ PASS: Chunking is working correctly!")
else:
    print(f"   ❌ FAIL: Still not creating enough chunks")

# Show first and last chunks
if chunks:
    print(f"\n📋 FIRST CHUNK")
    print(f"   Chunk ID: {chunks[0]['chunk_id']}")
    print(f"   Lines: {chunks[0]['start_line']}-{chunks[0]['end_line']}")
    print(f"   Position: {chunks[0]['position_start']}-{chunks[0]['position_end']}")
    
    print(f"\n📋 LAST CHUNK")
    print(f"   Chunk ID: {chunks[-1]['chunk_id']}")
    print(f"   Lines: {chunks[-1]['start_line']}-{chunks[-1]['end_line']}")
    print(f"   Position: {chunks[-1]['position_start']}-{chunks[-1]['position_end']}")
    
    # Check overlap
    if len(chunks) > 1:
        print(f"\n🔗 OVERLAP CHECK")
        for i in range(min(3, len(chunks)-1)):
            curr_end = chunks[i]['position_end']
            next_start = chunks[i+1]['position_start']
            overlap = curr_end - next_start
            print(f"   Chunk {i+1} → {i+2}: overlap = {overlap} chars (expected: {config.CONTROL_V4_OVERLAP_TOKENS * 4})")

print("\n" + "=" * 80)
