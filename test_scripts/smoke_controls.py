import sys, os, json
import logging

# Adjust path to import backend modules
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
APP_DIR = os.path.join(BACKEND_DIR, 'app')
EXTRACTORS_DIR = os.path.join(APP_DIR, 'extractors')
sys.path.insert(0, BACKEND_DIR)

from app.extractors import control_extractor_v2
from app import config

# Monkeypatch gpt_extract to avoid real LLM calls
from app.gpt_client import gpt_extract as real_gpt_extract

def fake_gpt_extract(prompt: str, caller: str):
    # Provide deterministic JSON for classification and dynamic chunking
    if 'DYNAMIC_CHUNKING' in prompt or 'breakpoints' in prompt.lower():
        # Return JSON array of offsets roughly splitting at 1/3 and 2/3 of sample text
        return json.dumps([500, 1000])
    if 'control_id' in prompt.lower() and 'classification' in prompt.lower():
        return json.dumps([
            {"type": "control_id", "text": "CTRL-001"},
            {"type": "control_description", "text": "Access to the system is restricted via MFA."},
            {"type": "test_procedure", "text": "We inspected MFA configuration settings."},
            {"type": "test_result", "text": "MFA enforced for all administrative accounts."}
        ])
    # Fallback minimal
    return json.dumps([])

# Patch
control_extractor_v2.gpt_extract = fake_gpt_extract

sample_text = ("Control ID: CTRL-001\nControl Description: Access to the system is restricted via MFA.\n"\
               "Test Procedure: We inspected MFA configuration settings.\nTest Result: MFA enforced for all administrative accounts." * 5)

# Test dynamic chunking
chunks = control_extractor_v2.dynamic_chunking(sample_text, initial_chunk_size=1500)
print('[SMOKE] dynamic_chunking produced', len(chunks), 'chunks; lengths=', [len(c) for c in chunks])

# Test classification v2
segments_v2 = control_extractor_v2.parse_classified_segments(json.dumps([
    {"type": "control_id", "text": "CTRL-002"},
    {"type": "control_description", "text": "Change management requires approvals."},
    {"type": "test_procedure", "text": "We reviewed change tickets."},
    {"type": "test_result", "text": "All sampled changes had documented approvals."}
]))
print('[SMOKE] v2 parsed segments:', segments_v2)

records_v2 = control_extractor_v2.structure_json_records(segments_v2)
print('[SMOKE] v2 structured records:', records_v2)

assert any(r.get('control_id') == 'CTRL-002' for r in records_v2), 'CTRL-002 missing in v2 records'
print('[SMOKE] Assertions passed.')
