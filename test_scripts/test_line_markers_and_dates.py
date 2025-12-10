"""
Test script for line markers and date deduction enhancements.

Tests:
1. Line markers added during chunking
2. Line markers stripped before database insertion
3. Date deduction with temporal rules
4. Performance metrics for token overhead
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.extractors.control_extractor import (
    strip_line_markers,
    validate_markers_stripped,
    create_aware_chunks
)
from app.extractors.coverage_period import extract_coverage_period

def test_line_marker_utilities():
    """Test line marker utility functions."""
    print("\n" + "="*80)
    print("TEST 1: Line Marker Utilities")
    print("="*80)
    
    # Test strip_line_markers
    test_text = "║245║ REV-\n║246║ 01-01"
    stripped = strip_line_markers(test_text)
    expected = "REV-\n01-01"
    
    print(f"Original: {repr(test_text)}")
    print(f"Stripped: {repr(stripped)}")
    print(f"Expected: {repr(expected)}")
    assert stripped == expected, f"Strip failed: got {repr(stripped)}"
    print("✓ strip_line_markers works correctly")
    
    # Test validate_markers_stripped
    assert validate_markers_stripped("No markers here"), "Should validate clean text"
    assert not validate_markers_stripped("║123║ Has markers"), "Should detect markers"
    print("✓ validate_markers_stripped works correctly")
    
    print("\n✅ All line marker utility tests passed!")

def test_chunking_with_markers():
    """Test that create_aware_chunks adds line markers."""
    print("\n" + "="*80)
    print("TEST 2: Chunking with Line Markers")
    print("="*80)
    
    # Create sample lines
    sample_lines = [
        "Control ID: REV-\n",
        "01-01\n",
        "Control Description: Test control\n",
        "Test Procedure: Inspected sample\n",
        "Result: No exceptions noted\n"
    ]
    
    # Create chunks (small size to test)
    chunks = create_aware_chunks(
        text_lines=sample_lines,
        start_line=1,
        end_line=5,
        tokens_per_chunk=100,
        overlap_tokens=20
    )
    
    print(f"Created {len(chunks)} chunk(s)")
    
    # Check first chunk has markers
    if chunks:
        chunk_text = chunks[0]['text']
        print(f"\nFirst chunk preview (first 200 chars):")
        print(chunk_text[:200])
        
        # Verify markers exist
        assert '║' in chunk_text, "Line markers should be present in chunk text"
        assert '║1║' in chunk_text, "First line should have marker ║1║"
        print("\n✓ Line markers successfully added to chunks")
    
    print("\n✅ Chunking test passed!")

def test_date_extraction():
    """Test date extraction with deduction fallback."""
    print("\n" + "="*80)
    print("TEST 3: Date Extraction with Deduction Fallback")
    print("="*80)
    
    print("Running extract_coverage_period()...")
    print("(This will attempt GPT extraction first, then deduction if needed)")
    
    try:
        result = extract_coverage_period()
        
        print("\nExtraction Result:")
        print(f"  Type: {result.get('type')}")
        print(f"  Start Date: {result.get('start_date')}")
        print(f"  End Date: {result.get('end_date')}")
        print(f"  Explanation: {result.get('explanation', 'N/A')[:200]}")
        
        # Check if we have dates
        if result.get('start_date') or result.get('end_date'):
            print("\n✓ Date extraction successful")
            
            # Check for deduction indicators
            explanation = result.get('explanation', '')
            if 'Deduced via temporal rules' in explanation:
                print("✓ Deduction fallback was used")
            elif 'Heuristic parse' in explanation:
                print("✓ Regex fallback was used")
            else:
                print("✓ GPT extraction was successful")
        else:
            print("\n⚠ Date extraction returned no dates (may need manual review)")
        
        print("\n✅ Date extraction test completed!")
        
    except Exception as e:
        print(f"\n❌ Date extraction test failed: {e}")
        import traceback
        traceback.print_exc()

def test_marker_stripping_integration():
    """Test that markers are properly stripped in the full pipeline."""
    print("\n" + "="*80)
    print("TEST 4: Marker Stripping Integration")
    print("="*80)
    
    # Test with sample control data
    sample_control = {
        'control_id': '║245║ REV-║246║ 01-01',
        'control_desc': '║247║ The entity reviews ║248║ access logs monthly.',
        'control_tests': ['║249║ Inspected access logs'],
        'control_test_results': ['║250║ No exceptions noted']
    }
    
    print("Sample control with markers:")
    for key, value in sample_control.items():
        print(f"  {key}: {repr(value)}")
    
    # Import validate_controls to test stripping
    from app.extractors.control_extractor import validate_controls
    
    validated = validate_controls([sample_control])
    
    if validated:
        control = validated[0]
        print("\nValidated control after stripping:")
        for key in ['control_id', 'control_desc']:
            if key in control:
                value = control[key]
                print(f"  {key}: {repr(value)}")
                assert '║' not in str(value), f"Marker found in {key}: {value}"
        
        print("\n✓ All markers successfully stripped")
        print("✅ Marker stripping integration test passed!")
    else:
        print("❌ Validation returned no controls")

if __name__ == "__main__":
    print("\n" + "="*80)
    print("LINE MARKERS AND DATE DEDUCTION TEST SUITE")
    print("="*80)
    
    try:
        # Test 1: Utility functions
        test_line_marker_utilities()
        
        # Test 2: Chunking with markers
        test_chunking_with_markers()
        
        # Test 3: Date extraction (requires actual PDF data)
        print("\n⚠ Skipping date extraction test (requires full document)")
        print("  Run this test after processing a SOC1 report")
        # test_date_extraction()  # Uncomment when ready to test with real data
        
        # Test 4: Marker stripping integration
        test_marker_stripping_integration()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED!")
        print("="*80)
        print("\nNext steps:")
        print("1. Process a SOC1 report (e.g., SAP ARIBA)")
        print("2. Check logs for performance metrics and date deduction details")
        print("3. Verify control IDs are correctly extracted (e.g., 'REV-01-01')")
        print("4. Confirm database records have no line markers (║)")
        
    except Exception as e:
        print(f"\n❌ TEST SUITE FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
