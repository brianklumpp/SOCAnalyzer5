"""
Test objective extraction with caching - extract once, test deduplication many times
Usage: 
  docker exec socanalyzer-backend python /app/test_objective_extraction_cached.py <scan_id>
  docker exec socanalyzer-backend python /app/test_objective_extraction_cached.py <scan_id> --skip-cache
"""
import sys
import os
sys.path.insert(0, '/app/backend')
os.chdir('/app/backend')

import json
import logging
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy import text as sql_text
from backend.app.models import Scan
from backend.app.extractors.objective_extractor import (
    chunk_text_by_tokens,
    extract_objectives_from_chunk,
    deduplicate_objectives,
    _score_objectives_for_selection,
    _select_high_conf_objectives,
    _select_high_conf_controls,
    _get_control_confidence,
    _learn_objective_patterns,
    _can_rescan_with_patterns,
    _rescan_objectives_with_patterns
)
from backend.app.models import Control
import backend.app.config as config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)

SYNC_DATABASE_URL = "postgresql+psycopg2://soc2_analyzer:puntitforthewin@postgres:5432/soc2analyzer"
CACHE_DIR = Path("/app/data/tmp/extraction_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def extract_raw_objectives(extracted_text, scan_id):
    """Extract objectives from all chunks WITHOUT deduplication"""
    chunks = chunk_text_by_tokens(extracted_text, tokens_per_chunk=4000, overlap_tokens=200)
    print(f"Processing {len(chunks)} chunks...")
    
    all_objectives = []
    for i, (chunk_text, start_pos, end_pos) in enumerate(chunks):
        objectives = extract_objectives_from_chunk(chunk_text, i, scan_id)
        if objectives:
            print(f"  Chunk {i}: extracted {len(objectives)} objectives")
            all_objectives.extend(objectives)
    
    return all_objectives

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_objective_extraction_cached.py <scan_id> [--skip-cache]")
        sys.exit(1)
    
    scan_id = int(sys.argv[1])
    skip_cache = '--skip-cache' in sys.argv
    
    print(f"\n{'='*80}")
    print(f"OBJECTIVE EXTRACTION TEST (CACHED) - Scan ID: {scan_id}")
    print(f"{'='*80}\n")
    
    engine = create_engine(SYNC_DATABASE_URL)
    
    # Load scan
    with engine.connect() as conn:
        result = conn.execute(
            sql_text("""
                SELECT s.id, c.name as company_name, s.product, s.extracted_text 
                FROM scan s 
                LEFT JOIN company c ON s.company_id = c.id 
                WHERE s.id = :scan_id
            """),
            {"scan_id": scan_id}
        )
        row = result.fetchone()
        if not row:
            print(f"ERROR: Scan {scan_id} not found")
            sys.exit(1)
        
        scan_data = {
            'id': row[0],
            'company_name': row[1],
            'product': row[2],
            'extracted_text': row[3]
        }
    
    print(f"✓ Found scan: {scan_data['company_name']} - {scan_data['product']}")
    print(f"  Extracted text length: {len(scan_data['extracted_text'])} characters")
    
    # Check cache
    cache_file = CACHE_DIR / f"scan_{scan_id}_raw_objectives.json"
    
    if cache_file.exists() and not skip_cache:
        print(f"\n{'='*80}")
        print("LOADING CACHED RAW EXTRACTION")
        print(f"{'='*80}")
        print(f"✓ Using cache: {cache_file}")
        print("  (Use --skip-cache to re-extract)")
        
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)
        raw_objectives = cache_data['raw_objectives']
        print(f"✓ Loaded {len(raw_objectives)} raw objectives from cache")
    else:
        print(f"\n{'='*80}")
        print("EXTRACTING OBJECTIVES FROM CHUNKS")
        print(f"{'='*80}")
        
        raw_objectives = extract_raw_objectives(scan_data['extracted_text'], scan_id)
        
        print(f"\n✓ Extracted {len(raw_objectives)} total objectives (before deduplication)")
        
        # Save to cache
        print(f"✓ Saving to cache: {cache_file}")
        cache_data = {
            'scan_id': scan_id,
            'raw_objectives': raw_objectives,
            'count': len(raw_objectives)
        }
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
    
    # Now test deduplication
    print(f"\n{'='*80}")
    print("TESTING DEDUPLICATION")
    print(f"{'='*80}")
    print(f"Input: {len(raw_objectives)} raw objectives")
    
    if len(raw_objectives) == 0:
        print("⚠ No objectives to deduplicate!")
        return
    
    # Run deduplication
    deduplicated = deduplicate_objectives(raw_objectives)
    
    if deduplicated:
        reduction_pct = (1 - len(deduplicated) / len(raw_objectives)) * 100
        print(f"\n✓ Deduplication complete:")
        print(f"  Input:  {len(raw_objectives)} objectives")
        print(f"  Output: {len(deduplicated)} objectives")
        print(f"  Preserved: {len(deduplicated)/len(raw_objectives)*100:.1f}%")
        print(f"  Reduced: {reduction_pct:.1f}%")
        
        # Show samples
        print(f"\nFirst 10 deduplicated objectives:")
        for i, obj in enumerate(deduplicated[:10], 1):
            obj_id = obj.get('objective_id') or "(no ID)"
            text = obj.get('objective_text', '')
            text_preview = text[:80] + "..." if len(text) > 80 else text
            print(f"  {i}. [{obj_id}] {text_preview}")
        
        if len(deduplicated) > 10:
            print(f"  ... and {len(deduplicated) - 10} more")
    else:
        print("⚠ Deduplication returned None/empty - using raw objectives")
        deduplicated = raw_objectives
    
    print(f"\n{'='*80}")
    print("TEST COMPLETE")
    print(f"{'='*80}")
    
    if len(raw_objectives) > 0:
        target_min = int(len(raw_objectives) * 0.95)
        target_max = int(len(raw_objectives) * 0.99)
        if len(deduplicated) >= target_min:
            print(f"✓ SUCCESS: Preserved {len(deduplicated)}/{len(raw_objectives)} objectives")
            print(f"  (Target: {target_min}-{target_max} for 95-99% preservation)")
        else:
            print(f"⚠ WARNING: Only preserved {len(deduplicated)}/{len(raw_objectives)} objectives")
            print(f"  (Target: {target_min}-{target_max} for 95-99% preservation)")
            print(f"  Deduplication is too aggressive!")
    
    # Step 4: Pattern Learning & Gap Extraction (if we have objectives)
    if scan_id and deduplicated and len(deduplicated) >= config.OBJECTIVE_PATTERN_MIN_OBJECTIVES:
        print(f"\n{'='*80}")
        print("PATTERN LEARNING & GAP EXTRACTION")
        print(f"{'='*80}")
        
        # Load controls from database
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=engine)
        db = Session()
        
        try:
            controls = db.query(Control).filter_by(scan_id=scan_id).all()
            print(f"Loaded {len(controls)} controls from database")
            
            # Score and select high-confidence objectives and controls
            scored_objectives = _score_objectives_for_selection(deduplicated, scan_data['extracted_text'])
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
            
            print(f"High-confidence objectives: {len(high_conf_objectives)}/{len(deduplicated)}")
            print(f"High-confidence controls: {len(high_conf_controls)}/{len(controls)}")
            
            if len(high_conf_objectives) >= config.OBJECTIVE_PATTERN_MIN_OBJECTIVES and \
               len(high_conf_controls) >= config.OBJECTIVE_PATTERN_MIN_CONTROLS:
                
                # Learn patterns
                objective_samples = [
                    {
                        "objective_id": obj.get("objective_id"),
                        "objective_text": obj.get("objective_text"),
                        "final_confidence": obj.get("_final_confidence", 0.8)
                    }
                    for obj in high_conf_objectives
                ]
                control_samples = [
                    {
                        "control_id": ctrl.control_id,
                        "control_desc": ctrl.control_desc,
                        "final_confidence": _get_control_confidence(ctrl)
                    }
                    for ctrl in high_conf_controls
                ]
                
                print("Learning objective patterns from high-confidence samples...")
                patterns = _learn_objective_patterns(objective_samples, control_samples)
                
                if patterns:
                    print(f"✓ Learned patterns:")
                    print(f"  ID pattern present: {patterns.get('id_pattern', {}).get('present', False)}")
                    print(f"  Text cues: {len(patterns.get('text_cues', []))} cues")
                    
                    if _can_rescan_with_patterns(patterns):
                        print("\nRescanning chunks with learned patterns...")
                        
                        # Get chunks (need to recreate them)
                        chunks = chunk_text_by_tokens(
                            scan_data['extracted_text'],
                            tokens_per_chunk=4000,
                            overlap_tokens=200
                        )
                        
                        existing_objectives_payload = [
                            {
                                "objective_id": obj.get("objective_id"),
                                "objective_text": obj.get("objective_text")
                            }
                            for obj in deduplicated
                        ]
                        
                        rescanned_objectives = _rescan_objectives_with_patterns(
                            chunks,
                            patterns,
                            existing_objectives_payload
                        )
                        
                        if rescanned_objectives:
                            print(f"✓ Found {len(rescanned_objectives)} additional objectives via pattern rescan")
                            
                            # Combine and re-deduplicate
                            combined_objectives = deduplicated + rescanned_objectives
                            final_objectives = deduplicate_objectives(combined_objectives)
                            
                            print(f"\nFinal count after gap extraction:")
                            print(f"  Before: {len(deduplicated)} objectives")
                            print(f"  Added: {len(rescanned_objectives)} from pattern rescan")
                            print(f"  After dedup: {len(final_objectives)} objectives")
                            print(f"  Net gain: +{len(final_objectives) - len(deduplicated)} objectives")
                        else:
                            print("No additional objectives found via pattern rescan")
                    else:
                        print("⚠ Learned patterns insufficient for rescanning")
                else:
                    print("⚠ Pattern learning failed")
            else:
                print(f"⚠ Insufficient high-confidence samples for pattern learning")
                print(f"  Need {config.OBJECTIVE_PATTERN_MIN_OBJECTIVES} objectives, {config.OBJECTIVE_PATTERN_MIN_CONTROLS} controls")
        finally:
            db.close()
    else:
        if not deduplicated:
            print("\n⚠ Skipping pattern learning: No objectives to learn from")
        else:
            print(f"\n⚠ Skipping pattern learning: Need at least {config.OBJECTIVE_PATTERN_MIN_OBJECTIVES} objectives (have {len(deduplicated)})")

if __name__ == "__main__":
    main()
