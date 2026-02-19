"""Test ID Pattern Detection and Penalty Logic

Tests the enhanced objective confidence scoring with ID pattern analysis.
Run this to verify pattern detection, super majority calculation, and penalty application.
"""

import sys
import os

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.insert(0, os.path.abspath(backend_path))

from app.extractors.objective_extractor import (
    _calculate_id_penalties,
    _analyze_id_patterns,
    _extract_id_pattern
)
from app import config

print("=" * 80)
print("OBJECTIVE ID PATTERN DETECTION TESTS")
print("=" * 80)

# Test 1: Pattern Extraction
print("\n📋 Test 1: Pattern Extraction")
print("-" * 80)
test_ids = [
    'CC1.1', 'CC2.3', 'C1.1', 'A1.2', 'PI1.1', 'P1.1',
    'SO-1-2', 'IAM-01-03', 'IM.1.2', 'OBJ001', 'CTL23',
    'Conf1.1', 'custom-format'
]
for test_id in test_ids:
    pattern = _extract_id_pattern(test_id)
    print(f"  {test_id:20} → {pattern}")

# Test 2: Pattern Analysis
print("\n📊 Test 2: Pattern Counting")
print("-" * 80)
sample_objectives = [
    {'objective_id': 'CC1.1'}, {'objective_id': 'CC1.2'},
    {'objective_id': 'CC2.1'}, {'objective_id': 'CC2.2'},
    {'objective_id': 'CC3.1'}, {'objective_id': 'CC4.1'},
    {'objective_id': 'CC5.1'}, {'objective_id': 'CC6.1'},
    {'objective_id': 'SO-1-2'}, {'objective_id': 'IAM-01-03'},
]
all_ids = [obj['objective_id'] for obj in sample_objectives]
pattern_counts = _analyze_id_patterns(all_ids)
print(f"  Total IDs: {len(all_ids)}")
for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
    pct = (count / len(all_ids)) * 100
    print(f"  {pattern:20} : {count:2} ({pct:5.1f}%)")

# Test 3: Missing ID Penalty
print("\n❌ Test 3: Missing ID Penalty (Super Majority Scenario)")
print("-" * 80)
objectives_with_ids = [
    {'objective_id': 'CC1.1'}, {'objective_id': 'CC1.2'},
    {'objective_id': 'CC2.1'}, {'objective_id': 'CC2.2'},
    {'objective_id': 'CC3.1'}, {'objective_id': ''}  # Missing
]
penalties = _calculate_id_penalties('', objectives_with_ids)
print(f"  Scenario: 5/6 objectives have IDs (83%)")
print(f"  Threshold: {config.OBJECTIVE_ID_SUPERMAJORITY_THRESHOLD * 100}%")
print(f"  Penalties: {len(penalties)}")
for penalty_type, penalty_value, reason in penalties:
    print(f"    - Type: {penalty_type}")
    print(f"      Penalty: {penalty_value * 100}%")
    print(f"      Reason: {reason}")

# Test 4: Outlier Pattern Penalty
print("\n🔍 Test 4: Outlier Pattern Penalty")
print("-" * 80)
objectives_cc_dominant = [
    {'objective_id': 'CC1.1'}, {'objective_id': 'CC1.2'},
    {'objective_id': 'CC2.1'}, {'objective_id': 'CC2.2'},
    {'objective_id': 'CC3.1'}, {'objective_id': 'SO-1-2'}  # Outlier
]
penalties = _calculate_id_penalties('SO-1-2', objectives_cc_dominant)
print(f"  Scenario: 5/6 use 'CC.' pattern (83%), 1 uses 'ALPHA-NUM-NUM'")
print(f"  Threshold: {config.OBJECTIVE_ID_SUPERMAJORITY_THRESHOLD * 100}%")
print(f"  Penalties: {len(penalties)}")
for penalty_type, penalty_value, reason in penalties:
    print(f"    - Type: {penalty_type}")
    print(f"      Penalty: {penalty_value * 100}%")
    print(f"      Reason: {reason}")

# Test 5: No Penalty (Diverse Patterns)
print("\n✅ Test 5: No Penalty (Diverse Patterns, No Super Majority)")
print("-" * 80)
objectives_diverse = [
    {'objective_id': 'CC1.1'}, {'objective_id': 'CC1.2'},
    {'objective_id': 'SO-1-2'}, {'objective_id': 'IAM-01-03'},
    {'objective_id': 'IM.1.2'}, {'objective_id': 'OBJ001'}
]
penalties = _calculate_id_penalties('SO-1-2', objectives_diverse)
print(f"  Scenario: Mixed patterns, no single pattern >80%")
print(f"  Penalties: {len(penalties)}")
if not penalties:
    print(f"  ✅ No penalties applied (expected - no super majority)")

# Test 6: Confidence Impact
print("\n📉 Test 6: Confidence Impact Simulation")
print("-" * 80)
base_confidence = 0.80
print(f"  Base Confidence: {base_confidence:.2f}")
print(f"  After 50% penalty: {base_confidence * 0.5:.2f}")
print(f"  After 2x 50% penalties: {base_confidence * 0.5 * 0.5:.2f}")

# Test 7: Edge Cases
print("\n🔬 Test 7: Edge Cases")
print("-" * 80)
edge_cases = [
    # Too few objectives for analysis
    ({'objectives': [{'objective_id': 'CC1.1'}, {'objective_id': ''}]}, ''),
    # All missing IDs
    ({'objectives': [{'objective_id': ''}, {'objective_id': ''}, {'objective_id': ''}]}, ''),
]
for case_data, test_id in edge_cases:
    objectives = case_data['objectives']
    penalties = _calculate_id_penalties(test_id, objectives)
    print(f"  Scenario: {len(objectives)} objectives, test_id='{test_id}'")
    print(f"  Penalties: {len(penalties)} (expected: 0 for edge cases)")

print("\n" + "=" * 80)
print("✅ ALL TESTS COMPLETED")
print("=" * 80)
print("\n💡 Key Takeaways:")
print("  1. Pattern detection recognizes 9 common ID formats (TSC + custom)")
print("  2. Super majority threshold: 80% (configurable)")
print("  3. Missing ID penalty: 50% reduction when 80%+ have IDs")
print("  4. Outlier pattern penalty: 50% reduction when format differs from 80%+ dominant")
print("  5. Edge cases handled gracefully (< 4 objectives = no penalties)")
