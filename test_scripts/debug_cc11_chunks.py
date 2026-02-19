"""Debug script to trace CC1.1 through the objective extraction chunking pipeline."""
import sys
sys.path.insert(0, '/app')

with open('/tmp/adobe_text.txt', 'r', errors='replace') as f:
    lines = f.readlines()

# Replicate exactly what extract_objectives() does
start_line = 1908
end_line = 5610
filtered_text = '\n'.join([l.rstrip('\n') for l in lines[start_line - 1:end_line]])

# Import the same chunking function
from backend.app.extractors.objective_extractor import chunk_text_by_tokens, find_objective_line_in_chunk
from backend.app import config

chunks = chunk_text_by_tokens(
    filtered_text,
    config.OBJECTIVE_TOKENS_PER_CHUNK,
    config.OBJECTIVE_CHUNK_OVERLAP_TOKENS
)
print(f'Chunk config: {config.OBJECTIVE_TOKENS_PER_CHUNK} tokens/chunk, {config.OBJECTIVE_CHUNK_OVERLAP_TOKENS} overlap')
print(f'Total chunks: {len(chunks)}')
print()

for i, (chunk_text, chunk_start, chunk_end) in enumerate(chunks):
    doc_start = start_line + chunk_start
    chunk_lines = chunk_text.split('\n')
    has_cc11 = any('CC1.1' in line for line in chunk_lines)
    
    if i < 3:
        print(f'  Chunk {i}: section lines {chunk_start}-{chunk_end} (doc {doc_start}-{start_line+chunk_end}), {len(chunk_lines)} lines, {len(chunk_text)} chars')
    
    if has_cc11:
        # Find exactly where
        for j, line in enumerate(chunk_lines):
            if 'CC1.1' in line:
                doc_line = doc_start + j
                print(f'\n  *** CHUNK {i}: CC1.1 found at chunk-relative line {j}, doc line {doc_line}')
                print(f'      Chunk range: section lines {chunk_start}-{chunk_end}, doc lines {doc_start}-{start_line + chunk_end}')
                print(f'      Chunk has {len(chunk_lines)} lines')
                content = line.strip()[:100]
                print(f'      Line content: "{content}"')
        
        # Now simulate find_objective_line_in_chunk
        print(f'\n  --- Simulating find_objective_line_in_chunk for CC1.1 ---')
        result = find_objective_line_in_chunk(
            chunk_text,
            'CC1.1',
            'The entity demonstrates a commitment to integrity and ethical values.',
            None  # Pretend GPT gave no line_ref
        )
        if result is not None:
            final_doc_line = doc_start + result
            print(f'  find_objective_line_in_chunk returned: chunk_line={result}, doc_line={final_doc_line}')
        else:
            print(f'  find_objective_line_in_chunk returned: None')
        print()

print('\n--- All chunks with CC-type objectives ---')
for i, (chunk_text, chunk_start, chunk_end) in enumerate(chunks):
    doc_start = start_line + chunk_start
    chunk_lines = chunk_text.split('\n')
    import re
    for j, line in enumerate(chunk_lines):
        if re.search(r'^CC\d+\.\d+$', line.strip()):
            doc_line = doc_start + j
            print(f'  Chunk {i}, chunk_line {j}, doc_line {doc_line}: "{line.strip()}"')
