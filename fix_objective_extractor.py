#!/usr/bin/env python3
"""
Script to remove duplicate control loop code from objective_extractor.py
"""

file_path = r'c:\Users\bklumpp\OneDrive - NANDPS\Documents\Python Scripts\SOCAnalyzer5\backend\app\extractors\objective_extractor.py'

# Read the file
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find key markers
old_code_removed_idx = None
commit_mappings_indices = []

for i, line in enumerate(lines):
    if '# OLD CODE REMOVED' in line:
        old_code_removed_idx = i
        print(f"Found '# OLD CODE REMOVED' at line {i+1}")
    if '# Commit mappings' in line and line.strip() == '# Commit mappings':
        commit_mappings_indices.append(i)
        print(f"Found '# Commit mappings' at line {i+1}")

# We want to keep everything up to and including "# OLD CODE REMOVED"
# Then skip to the LAST "# Commit mappings" (the real one)
if old_code_removed_idx is not None and len(commit_mappings_indices) >= 2:
    # Remove from after OLD CODE REMOVED to before the last Commit mappings
    last_commit_idx = commit_mappings_indices[-1]
    
    print(f"\nRemoving lines {old_code_removed_idx+2} to {last_commit_idx}")
    print(f"That's {last_commit_idx - old_code_removed_idx - 1} lines")
    
    # Construct new file: everything before OLD CODE REMOVED, then everything from last Commit mappings onward
    new_lines = lines[:old_code_removed_idx+1] + ['\n'] + lines[last_commit_idx:]
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print(f"✓ File fixed! Removed {last_commit_idx - old_code_removed_idx - 1} duplicate lines")
else:
    print("ERROR: Could not find expected markers")
    print(f"old_code_removed_idx: {old_code_removed_idx}")
    print(f"commit_mappings_indices: {commit_mappings_indices}")
