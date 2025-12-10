"""
Test script to verify line marker reconstruction of split control IDs
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.extractors.control_extractor import create_aware_chunks, extract_control_with_cot
from app import config
import logging

logging.basicConfig(level=logging.INFO)

# Sample text simulating the SAP Ariba report around line 2971
test_text = """SAP SE 

2.01_
Ariba 

Formal user access 
management procedures have 
been documented and made 
available to relevant 
administrative users. 

Inspected the SAP Ariba Cloud 
Ops — Production Access 
Request document available on 
Ariba Confluence to determine 
whether formal user access 
management procedures were 
documented and made available 
to administrative users. 

No exceptions noted."""

# Create line-based representation
text_lines = test_text.strip().split('\n')

# Add line numbers to simulate actual document
print("=== Original Text (with simulated line numbers) ===")
for i, line in enumerate(text_lines, start=2969):
    print(f"{i}: {line}")

print("\n=== Creating Aware Chunks with Line Markers ===")
chunks = create_aware_chunks(
    text_lines=[''] * 2968 + text_lines,  # Pad to correct line numbers
    start_line=2969,
    end_line=2969 + len(text_lines),
    tokens_per_chunk=500,
    overlap_tokens=100
)

print(f"Generated {len(chunks)} chunk(s)")

if chunks:
    chunk = chunks[0]
    print(f"\nChunk ID: {chunk['chunk_id']}")
    print(f"Start line: {chunk['start_line']}")
    print(f"\n=== Chunk Text (with line markers) ===")
    print(chunk['text'][:1000])  # Show first 1000 chars
    
    print("\n=== Extracting Controls ===")
    result = extract_control_with_cot(chunk)
    
    if result:
        print(f"\nExtracted {len(result)} control(s)")
        for ctrl in result:
            print(f"\nControl ID: {ctrl.get('control_id', 'N/A')}")
            print(f"Description: {ctrl.get('control_desc', 'N/A')[:100]}...")
            print(f"Confidence: {ctrl.get('control_confidence', 0)}")
            print(f"Has Deviation: {ctrl.get('has_deviation', False)}")
    else:
        print("No controls extracted")
