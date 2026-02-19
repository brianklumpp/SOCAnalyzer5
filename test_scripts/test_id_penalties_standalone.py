"""Standalone Test for ID Pattern Detection Logic

Tests pattern extraction and penalty calculation without requiring full backend imports.
This validates the core algorithm logic independently.
"""

import re
from typing import List, Dict, Any, Tuple, Optional

# Mock config values
class MockConfig:
    OBJECTIVE_ID_MISSING_PENALTY = 0.50
    OBJECTIVE_ID_OUTLIER_PENALTY = 0.50
    OBJECTIVE_ID_SUPERMAJORITY_THRESHOLD = 0.80

config = MockConfig()

# Copy of the functions from objective_extractor.py
def _extract_id_pattern(objective_id: str) -> str:
    """Extract the structural pattern from an objective ID."""
    if not objective_id:
        return "none"
    
    # Normalize: uppercase, strip spaces
    normalized = objective_id.upper().replace(" ", "")
    
    # Check for known TSC patterns
    if re.match(r'^CC\d+\.\d+', normalized):
        return "CC."
    if re.match(r'^C\d+\.\d+', normalized):
        return "C."
    if re.match(r'^A\d+\.\d+', normalized):
        return "A."
    if re.match(r'^P\d+\.\d+', normalized):
        return "P."
    if re.match(r'^PI\d+\.\d+', normalized):
        return "PI."
    if re.match(r'^CONF\d+\.\d+', normalized):
        return "Conf."
    
    # Check for common custom patterns
    if re.match(r'^[A-Z]+-\d+-\d+', normalized):
        return "ALPHA-NUM-NUM"  # SO-1-2, IAM-01-03
    if re.match(r'^[A-Z]+\.\d+\.\d+', normalized):
        return "ALPHA.NUM.NUM"  # IM.1.2
    if re.match(r'^[A-Z]+\d+$', normalized):
        return "ALPHANUM"  # OBJ001, CTL23
    
    # Unknown pattern
    return "custom"


def _analyze_id_patterns(objective_ids: List[str]) -> Dict[str, int]:
    """Analyze objective ID patterns and return counts."""
    pattern_counts = {}
    
    for obj_id in objective_ids:
        pattern = _extract_id_pattern(obj_id)
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
    
    return pattern_counts


def _calculate_id_penalties(
    objective_id: str,
    all_objectives: Optional[List[Dict[str, Any]]]
) -> List[Tuple[str, float, str]]:
    """Calculate ID-related penalties for confidence scoring."""
    penalties = []
    
    if not all_objectives or len(all_objectives) < 4:
        # Need at least 4 objectives for pattern analysis
        return penalties
    
    # Collect all objective IDs
    all_ids = [obj.get('objective_id', '').strip() for obj in all_objectives if obj.get('objective_id', '').strip()]
    total_count = len(all_objectives)
    with_id_count = len(all_ids)
    
    # Rule 1: Missing ID when super majority have IDs
    if not objective_id:
        if with_id_count >= total_count * config.OBJECTIVE_ID_SUPERMAJORITY_THRESHOLD:
            penalties.append((
                "missing_id_supermajority",
                config.OBJECTIVE_ID_MISSING_PENALTY,
                f"Missing ID when {with_id_count}/{total_count} ({with_id_count/total_count:.0%}) have IDs"
            ))
        return penalties  # No need for pattern check if ID is missing
    
    # Rule 2: ID format outlier detection
    if with_id_count >= 4:  # Need enough IDs for pattern analysis
        pattern_counts = _analyze_id_patterns(all_ids)
        
        if pattern_counts:
            # Find dominant pattern (super majority)
            total_patterns = sum(pattern_counts.values())
            dominant_pattern = max(pattern_counts.keys(), key=lambda k: pattern_counts[k])
            dominant_count = pattern_counts[dominant_pattern]
            
            if dominant_count >= total_patterns * config.OBJECTIVE_ID_SUPERMAJORITY_THRESHOLD:
                # Check if current ID matches dominant pattern
                current_pattern = _extract_id_pattern(objective_id)
                if current_pattern != dominant_pattern:
                    penalties.append((
                        "id_pattern_outlier",
                        config.OBJECTIVE_ID_OUTLIER_PENALTY,
                        f"ID format '{current_pattern}' differs from dominant '{dominant_pattern}' ({dominant_count}/{total_patterns} = {dominant_count/total_patterns:.0%})"
                    ))
    
    return penalties


# Run tests
print("=" * 80)
print("OBJECTIVE ID PATTERN DETECTION TESTS (Standalone)")
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
sample_ids = ['CC1.1', 'CC1.2', 'CC2.1', 'CC2.2', 'CC3.1', 'CC4.1', 'CC5.1', 'CC6.1', 'SO-1-2', 'IAM-01-03']
pattern_counts = _analyze_id_patterns(sample_ids)
print(f"  Total IDs: {len(sample_ids)}")
for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
    pct = (count / len(sample_ids)) * 100
    print(f"  {pattern:20} : {count:2} ({pct:5.1f}%)")

# Test 3: Missing ID Penalty
print("\n❌ Test 3: Missing ID Penalty (Super Majority Scenario)")
print("-" * 80)
objectives_with_ids = [
    {'objective_id': 'CC1.1'}, {'objective_id': 'CC1.2'},
    {'objective_id': 'CC2.1'}, {'objective_id': 'CC2.2'},
    {'objective_id': 'CC3.1'}, {'objective_id': ''}
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
    {'objective_id': 'CC3.1'}, {'objective_id': 'SO-1-2'}
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
# Too few objectives
penalties1 = _calculate_id_penalties('', [{'objective_id': 'CC1.1'}, {'objective_id': ''}])
print(f"  Scenario: Only 2 objectives → Penalties: {len(penalties1)} (expected 0)")

# All missing IDs
all_missing = [{'objective_id': ''}, {'objective_id': ''}, {'objective_id': ''}, {'objective_id': ''}]
penalties2 = _calculate_id_penalties('', all_missing)
print(f"  Scenario: All missing IDs → Penalties: {len(penalties2)} (expected 0)")

print("\n" + "=" * 80)
print("✅ ALL TESTS COMPLETED")
print("=" * 80)
print("\n💡 Key Takeaways:")
print("  1. Pattern detection recognizes 9 common ID formats (TSC + custom)")
print("  2. Super majority threshold: 80% (configurable)")
print("  3. Missing ID penalty: 50% reduction when 80%+ have IDs")
print("  4. Outlier pattern penalty: 50% reduction when format differs from 80%+ dominant")
print("  5. Edge cases handled gracefully (< 4 objectives = no penalties)")
