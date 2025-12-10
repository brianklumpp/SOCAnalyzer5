"""
Direct extraction test - bypasses API to test max_controls parameter
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.app.extractors.control_extractor import extract_controls
from backend.app.pdf_handler import extract_text_from_pdf, find_section_candidates
from backend.app import config
import json

def test_direct_extraction(pdf_path: str, report_type: str = "SOC2"):
    """Test control extraction with max_controls=10"""
    
    print("=" * 80)
    print(f"Direct Extraction Test: {os.path.basename(pdf_path)}")
    print("=" * 80)
    print(f"Report Type: {report_type}")
    print(f"Max Controls: 10")
    print()
    
    # Extract text
    print("Step 1: Extracting text from PDF...")
    output_path = "data/tmp/test_extraction.txt"
    extract_text_from_pdf(pdf_path, output_path)
    
    with open(output_path, 'r', encoding='utf-8') as f:
        full_text = f.read()
    
    lines = full_text.count('\n')
    print(f"✓ Extracted {lines} lines")
    
    # Find sections
    print("\nStep 2: Finding control section...")
    sections = find_section_candidates(full_text)
    
    control_section = None
    for section in sections:
        if 'control' in section.get('name', '').lower():
            control_section = section
            break
    
    if not control_section:
        print("✗ No control section found")
        return
    
    print(f"✓ Found control section: {control_section['name']}")
    print(f"  Pages: {control_section.get('toc_page', 'N/A')} - {control_section.get('doc_page', 'N/A')}")
    
    # Extract controls with limit
    print(f"\nStep 3: Extracting first 10 controls...")
    print(f"Using report_type={report_type}, max_controls=10")
    
    controls = extract_controls(
        [control_section],
        report_type=report_type,
        enable_assertion_mapping=False,
        start_at_line=None,
        max_controls=10  # LIMIT TO 10
    )
    
    print(f"\n✓ Extracted {len(controls)} controls")
    
    # Display results
    print("\n" + "=" * 80)
    print("Framework Mapping Results")
    print("=" * 80)
    
    for i, ctrl in enumerate(controls, 1):
        print(f"\n[{i}] Control: {ctrl.get('control_id', 'N/A')}")
        print(f"    Description: {ctrl.get('control_desc', '')[:80]}...")
        
        # Framework mappings
        primary_framework = ctrl.get('primary_framework')
        primary_criterion = ctrl.get('primary_criterion_id')
        primary_confidence = ctrl.get('primary_confidence', 0)
        
        if primary_framework:
            print(f"    Primary Framework: {primary_framework}")
            print(f"    Primary Criterion: {primary_criterion}")
            print(f"    Confidence: {primary_confidence:.2f}")
        else:
            print(f"    ⚠ No framework mapping")
        
        # Show all framework mappings
        framework_mappings = ctrl.get('framework_mappings', [])
        if framework_mappings:
            print(f"    All Mappings: {len(framework_mappings)}")
            for mapping in framework_mappings[:3]:  # Show top 3
                print(f"      • {mapping.get('framework')}: {mapping.get('criterion_id')} (conf: {mapping.get('confidence', 0):.2f})")
    
    # Summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Total Controls: {len(controls)}")
    mapped = sum(1 for c in controls if c.get('primary_framework'))
    print(f"With Framework Mapping: {mapped}/{len(controls)} ({mapped/len(controls)*100:.1f}%)")
    
    # Save to JSON for inspection
    output_file = "data/json/test_direct_extraction.json"
    with open(output_file, 'w') as f:
        json.dump(controls, f, indent=2)
    print(f"\n✓ Results saved to: {output_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test direct control extraction with max_controls")
    parser.add_argument('--soc1', type=str, help='Path to SOC1 PDF')
    parser.add_argument('--soc2', type=str, help='Path to SOC2 PDF')
    
    args = parser.parse_args()
    
    if args.soc1:
        test_direct_extraction(args.soc1, "SOC1")
    elif args.soc2:
        test_direct_extraction(args.soc2, "SOC2")
    else:
        print("Error: Provide --soc1 or --soc2 with PDF path")
        sys.exit(1)
