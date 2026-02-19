"""
Test AI-Enhanced Merge Strategy

This script tests the tiered merge logic without requiring a database.
Tests all 3 tiers: exact match, bullet merging, and AI consolidation.
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from app.utils.text_analysis import (
    extract_bullets,
    is_substring_match,
    calculate_text_difference,
    has_bullet_structure,
    merge_bullet_lists
)


def test_tier1_exact_match():
    """Test Tier 1: Exact match detection"""
    print("\n=== TEST TIER 1: Exact Match ===")
    
    text1 = "The organization maintains a password policy."
    text2 = "The organization maintains a password policy."
    
    diff = calculate_text_difference(text1, text2)
    print(f"Text 1: {text1}")
    print(f"Text 2: {text2}")
    print(f"Difference: {diff:.2%} ({'EXACT MATCH' if diff == 0 else 'DIFFERENT'})")
    assert diff == 0.0, "Expected exact match"
    print("✓ PASSED")


def test_tier1_substring():
    """Test Tier 1: Substring/superset detection"""
    print("\n=== TEST TIER 1: Substring Detection ===")
    
    text1 = "The organization maintains a password policy."
    text2 = "The organization maintains a password policy that requires complexity."
    
    is_subset, longer = is_substring_match(text1, text2)
    print(f"Text 1: {text1}")
    print(f"Text 2: {text2}")
    print(f"Is Subset: {is_subset}")
    print(f"Longer Text: {longer}")
    assert is_subset, "Expected substring match"
    assert longer == text2, "Expected text2 to be the superset"
    print("✓ PASSED")


def test_tier2_bullet_detection():
    """Test Tier 2: Bullet structure detection"""
    print("\n=== TEST TIER 2: Bullet Detection ===")
    
    text_with_bullets = """The following controls are in place:
• Password complexity requirements
• Multi-factor authentication
• Regular password rotation"""
    
    text_without_bullets = "The organization maintains security controls including passwords and MFA."
    
    has_bullets_1 = has_bullet_structure(text_with_bullets)
    has_bullets_2 = has_bullet_structure(text_without_bullets)
    
    print(f"Text with bullets: {text_with_bullets[:50]}...")
    print(f"Has bullet structure: {has_bullets_1}")
    print(f"\nText without bullets: {text_without_bullets}")
    print(f"Has bullet structure: {has_bullets_2}")
    
    assert has_bullets_1, "Expected bullet structure detection"
    assert not has_bullets_2, "Expected no bullet structure"
    print("✓ PASSED")


def test_tier2_bullet_extraction():
    """Test Tier 2: Bullet extraction"""
    print("\n=== TEST TIER 2: Bullet Extraction ===")
    
    text = """The control includes:
1. Password complexity requirements
2. Multi-factor authentication
3. Regular password rotation"""
    
    bullets = extract_bullets(text)
    print(f"Original text:\n{text}")
    print(f"\nExtracted bullets:")
    for i, bullet in enumerate(bullets, 1):
        print(f"  {i}. {bullet}")
    
    assert len(bullets) == 3, f"Expected 3 bullets, got {len(bullets)}"
    assert "Password complexity requirements" in bullets[0]
    print("✓ PASSED")


def test_tier2_bullet_merge():
    """Test Tier 2: Intelligent bullet merging"""
    print("\n=== TEST TIER 2: Bullet Merging ===")
    
    list1 = [
        "Password complexity requirements (minimum 12 characters)",
        "Multi-factor authentication for all users",
        "Regular password rotation every 90 days"
    ]
    
    list2 = [
        "Password complexity requirements (min 12 chars)",  # Similar to list1[0]
        "Multi-factor authentication for all users",  # Exact duplicate
        "Account lockout after 5 failed attempts",  # New item
        "Session timeout after 15 minutes of inactivity"  # New item
    ]
    
    merged = merge_bullet_lists(list1, list2)
    
    print(f"List 1 ({len(list1)} items):")
    for item in list1:
        print(f"  • {item}")
    
    print(f"\nList 2 ({len(list2)} items):")
    for item in list2:
        print(f"  • {item}")
    
    print(f"\nMerged ({len(merged)} items):")
    for item in merged:
        print(f"  • {item}")
    
    # Should preserve unique items and choose longer version of similar items
    assert len(merged) >= 4, f"Expected at least 4 unique items, got {len(merged)}"
    assert any("12 characters" in item for item in merged), "Expected longer password requirement"
    assert any("lockout" in item for item in merged), "Expected account lockout item"
    print("✓ PASSED")


def test_tier3_difference_threshold():
    """Test when AI consolidation should trigger"""
    print("\n=== TEST TIER 3: Difference Threshold ===")
    
    # Small difference - should NOT trigger AI
    text1 = "The organization maintains password policies and MFA."
    text2 = "The organization maintains password policies and multi-factor authentication."
    
    diff1 = calculate_text_difference(text1, text2)
    print(f"Small difference test:")
    print(f"  Text 1: {text1}")
    print(f"  Text 2: {text2}")
    print(f"  Difference: {diff1:.2%}")
    
    # Large difference - should trigger AI
    text3 = "The organization uses password policies."
    text4 = "Controls include authentication mechanisms, session management, and periodic reviews."
    
    diff2 = calculate_text_difference(text3, text4)
    print(f"\nLarge difference test:")
    print(f"  Text 3: {text3}")
    print(f"  Text 4: {text4}")
    print(f"  Difference: {diff2:.2%}")
    
    # Check against config threshold (15%)
    from app import config
    threshold = config.MERGE_AI_MIN_DIFF_THRESHOLD
    
    print(f"\nAI Trigger Threshold: {threshold:.2%}")
    print(f"Small diff would trigger AI: {diff1 > threshold}")
    print(f"Large diff would trigger AI: {diff2 > threshold}")
    
    assert diff2 > diff1, "Expected larger semantic difference"
    print("✓ PASSED")


def test_config_values():
    """Test that configuration is loaded correctly"""
    print("\n=== TEST: Configuration Values ===")
    
    from app import config
    
    print(f"MERGE_STRATEGY: {config.MERGE_STRATEGY}")
    print(f"MERGE_AI_MIN_DIFF_THRESHOLD: {config.MERGE_AI_MIN_DIFF_THRESHOLD}")
    print(f"MERGE_PRESERVE_ALL_BULLETS: {config.MERGE_PRESERVE_ALL_BULLETS}")
    print(f"MERGE_AI_INCLUDE_TEST_PROCEDURES: {config.MERGE_AI_INCLUDE_TEST_PROCEDURES}")
    print(f"MERGE_AI_AUTO_APPLY_THRESHOLD: {config.MERGE_AI_AUTO_APPLY_THRESHOLD}")
    print(f"MERGE_CONSOLIDATION_PROMPT length: {len(config.MERGE_CONSOLIDATION_PROMPT)} chars")
    
    assert config.MERGE_STRATEGY == "ai_enhanced", "Expected ai_enhanced strategy"
    assert 0 < config.MERGE_AI_MIN_DIFF_THRESHOLD < 1, "Threshold should be between 0 and 1"
    assert "{control_id}" in config.MERGE_CONSOLIDATION_PROMPT, "Prompt should have placeholders"
    print("✓ PASSED")


def main():
    """Run all tests"""
    print("=" * 60)
    print("AI-ENHANCED MERGE STRATEGY TEST SUITE")
    print("=" * 60)
    
    tests = [
        test_config_values,
        test_tier1_exact_match,
        test_tier1_substring,
        test_tier2_bullet_detection,
        test_tier2_bullet_extraction,
        test_tier2_bullet_merge,
        test_tier3_difference_threshold
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 All tests passed! AI merge implementation is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
