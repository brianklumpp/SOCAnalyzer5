#!/usr/bin/env python3
"""
Display all objectives from cached extraction for deduplication analysis
"""
import sys
sys.path.insert(0, '/app/backend')

import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy import text as sql_text
from sqlalchemy.orm import sessionmaker
from backend.app.extractors.objective_extractor import (
    chunk_text_by_tokens,
    deduplicate_objectives,
    _score_objectives_for_selection,
    _select_high_conf_objectives,
    _select_high_conf_controls,
    _get_control_confidence,
    _learn_objective_patterns,
    _rescan_objectives_with_patterns
)
from backend.app.models import Control
import backend.app.config as config

SYNC_DATABASE_URL = 'postgresql+psycopg2://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer'
CACHE_DIR = Path('/app/data/tmp/extraction_cache')

def main():
    scan_id = 2
    
    # Load cached raw objectives
    cache_file = CACHE_DIR / f'scan_{scan_id}_raw_objectives.json'
    if not cache_file.exists():
        print(f"❌ Cache file not found: {cache_file}")
        return
    
    with open(cache_file) as f:
        cache_data = json.load(f)
    
    raw_objectives = cache_data['raw_objectives']
    
    # Get extracted text from database
    engine = create_engine(SYNC_DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(
            sql_text('SELECT extracted_text FROM scan s WHERE s.id = :scan_id'),
            {'scan_id': scan_id}
        )
        row = result.fetchone()
        extracted_text = row[0]
    
    print(f"\n{'='*100}")
    print(f"OBJECTIVE DEDUPLICATION ANALYSIS - Scan {scan_id}")
    print(f"{'='*100}\n")
    
    # Phase 1: Show raw extraction
    print(f"📄 PHASE 1: RAW EXTRACTION")
    print(f"   Total extracted: {len(raw_objectives)} objectives\n")
    
    # Phase 2: Deduplication
    deduplicated = deduplicate_objectives(raw_objectives)
    print(f"🔄 PHASE 2: DEDUPLICATION")
    print(f"   After dedup: {len(deduplicated)} objectives")
    print(f"   Preserved: {len(deduplicated)/len(raw_objectives)*100:.1f}%\n")
    
    # Phase 3: Pattern learning + gap extraction
    Session = sessionmaker(bind=engine)
    db = Session()
    
    controls = db.query(Control).filter_by(scan_id=scan_id).all()
    scored_objectives = _score_objectives_for_selection(deduplicated, extracted_text)
    high_conf_objectives = _select_high_conf_objectives(
        scored_objectives, 
        config.HIGH_CONFIDENCE_THRESHOLD, 
        config.OBJECTIVE_PATTERN_MIN_OBJECTIVES
    )
    high_conf_controls = _select_high_conf_controls(
        controls, 
        config.HIGH_CONFIDENCE_THRESHOLD, 
        config.OBJECTIVE_PATTERN_MIN_CONTROLS
    )
    
    objective_samples = [
        {
            'objective_id': obj.get('objective_id'), 
            'objective_text': obj.get('objective_text'), 
            'final_confidence': obj.get('_final_confidence', 0.8)
        } 
        for obj in high_conf_objectives
    ]
    control_samples = [
        {
            'control_id': ctrl.control_id, 
            'control_desc': ctrl.control_desc, 
            'final_confidence': _get_control_confidence(ctrl)
        } 
        for ctrl in high_conf_controls
    ]
    
    patterns = _learn_objective_patterns(objective_samples, control_samples)
    chunks = chunk_text_by_tokens(extracted_text, tokens_per_chunk=4000, overlap_tokens=200)
    existing_objectives_payload = [
        {'objective_id': obj.get('objective_id'), 'objective_text': obj.get('objective_text')} 
        for obj in deduplicated
    ]
    rescanned_objectives = _rescan_objectives_with_patterns(chunks, patterns, existing_objectives_payload)
    
    print(f"🔍 PHASE 3: PATTERN LEARNING + GAP EXTRACTION")
    print(f"   Gap extraction found: {len(rescanned_objectives)} additional objectives\n")
    
    # Combine all
    combined_objectives = deduplicated + rescanned_objectives
    
    print(f"\n{'='*100}")
    print(f"COMPLETE OBJECTIVE LIST ({len(combined_objectives)} total)")
    print(f"{'='*100}\n")
    
    # Display all objectives with source tags
    for i, obj in enumerate(combined_objectives, 1):
        obj_id = obj.get('objective_id', '(no ID)')
        text = obj.get('objective_text', '')
        source = 'INITIAL' if i <= len(deduplicated) else 'GAP-EXTRACT'
        
        # Truncate text if too long
        display_text = text if len(text) <= 100 else f"{text[:100]}..."
        
        print(f"{i:3d}. [{source:12s}] ID: {obj_id:10s} | {display_text}")
    
    print(f"\n{'='*100}")
    print(f"SUMMARY:")
    print(f"  Initial extraction: {len(deduplicated)} objectives")
    print(f"  Gap extraction: +{len(rescanned_objectives)} objectives")
    print(f"  Total: {len(combined_objectives)} objectives")
    print(f"  Gain: +{(len(rescanned_objectives)/len(deduplicated)*100):.0f}%")
    print(f"{'='*100}\n")
    
    db.close()

if __name__ == '__main__':
    main()
