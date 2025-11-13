"""
Test Control Extractor V4
==========================

Quick test script to run the AWARE-CHUNK + CoT extractor and display results.

Usage:
    python test_control_v4.py [--version v4] [--start-line LINE]
"""

import sys
import os
import json
import argparse
from pathlib import Path

# Add parent directory to path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Change to parent directory for proper imports
os.chdir(str(parent_dir))

from backend.app.extractors.control_integration import extract_controls, compare_versions, get_available_versions

def print_diagnostics(diagnostics):
    """Print diagnostic information in a formatted way."""
    print("\n" + "=" * 80)
    print("EXTRACTION DIAGNOSTICS")
    print("=" * 80)
    
    for key, value in diagnostics.items():
        label = key.replace('_', ' ').title()
        print(f"{label:.<50} {value}")
    
    print("=" * 80)

def print_control_summary(controls, max_display=5):
    """Print summary of extracted controls."""
    print("\n" + "=" * 80)
    print(f"EXTRACTED CONTROLS (showing {min(max_display, len(controls))} of {len(controls)})")
    print("=" * 80)
    
    for i, control in enumerate(controls[:max_display], 1):
        print(f"\n[Control {i}]")
        print(f"  ID: {control.get('control_id', 'N/A')}")
        print(f"  Description: {control.get('control_desc', 'N/A')[:100]}...")
        print(f"  Tests: {len(control.get('control_tests', []))}")
        print(f"  Results: {len(control.get('control_test_results', []))}")
        print(f"  Deviation: {control.get('has_deviation', False)}")
        print(f"  Confidence: {control.get('control_confidence', 0):.2f}")
        print(f"  Continuation: {control.get('continuation', False)}")
        print(f"  Lines: {control.get('source_start_line', '?')}-{control.get('end_line', '?')}")
    
    if len(controls) > max_display:
        print(f"\n... and {len(controls) - max_display} more controls")
    
    print("=" * 80)

def print_rejected_summary(rejected):
    """Print summary of rejected controls."""
    if not rejected:
        print("\nNo controls were rejected (all passed confidence threshold)")
        return
    
    print("\n" + "=" * 80)
    print(f"REJECTED CONTROLS (low confidence: {len(rejected)})")
    print("=" * 80)
    
    for i, control in enumerate(rejected, 1):
        print(f"\n[Rejected {i}]")
        print(f"  ID: {control.get('control_id', 'N/A')}")
        print(f"  Confidence: {control.get('control_confidence', 0):.2f}")
        print(f"  Reason: {control.get('control_gpt_conf_justification', 'N/A')}")
    
    print("=" * 80)

def main():
    parser = argparse.ArgumentParser(description="Test control extractor")
    parser.add_argument("--version", default="v4", choices=["v2", "v4"], 
                        help="Extractor version to use (default: v4)")
    parser.add_argument("--start-line", type=int, 
                        help="Resume from specific line number")
    parser.add_argument("--start-control", type=int, 
                        help="Resume from specific control sequence")
    parser.add_argument("--compare", action="store_true",
                        help="Show version comparison")
    parser.add_argument("--max-display", type=int, default=5,
                        help="Maximum controls to display (default: 5)")
    
    args = parser.parse_args()
    
    if args.compare:
        compare_versions()
        return
    
    print("=" * 80)
    print(f"TESTING CONTROL EXTRACTOR {args.version.upper()}")
    print("=" * 80)
    print(f"Available versions: {', '.join(get_available_versions())}")
    
    if args.start_line:
        print(f"Resuming from line: {args.start_line}")
    if args.start_control:
        print(f"Resuming from control: {args.start_control}")
    
    print("\nStarting extraction...")
    print("-" * 80)
    
    try:
        # Run extraction (writes to config.CONTROL_JSON_PATH)
        extract_controls(
            version=args.version,
            start_at_line=args.start_line,
            start_at_control=args.start_control
        )
        
        # Read results from file
        from backend.app import config
        with open(config.CONTROL_JSON_PATH, 'r', encoding='utf-8') as f:
            result = json.load(f)
        
        # Display results
        controls = result.get("controls", [])
        diagnostics = result.get("diagnostics", {})
        rejected = result.get("rejected_controls", [])
        
        # Print diagnostics
        print_diagnostics(diagnostics)
        
        # Print control summary
        print_control_summary(controls, max_display=args.max_display)
        
        # Print rejected controls
        if args.version == "v4":
            print_rejected_summary(rejected)
        
        # Summary statistics
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total Controls: {len(controls)}")
        
        if args.version == "v4":
            avg_conf = sum(c.get('control_confidence', 0) for c in controls) / len(controls) if controls else 0
            deviations = sum(1 for c in controls if c.get('has_deviation', False))
            continuations = sum(1 for c in controls if c.get('continuation', False))
            
            print(f"Average Confidence: {avg_conf:.2f}")
            print(f"Controls with Deviations: {deviations}")
            print(f"Continuations Detected: {diagnostics.get('continuations_detected', 0)}")
            print(f"Controls Merged: {diagnostics.get('controls_merged', 0)}")
            print(f"Rejected (low confidence): {len(rejected)}")
        
        print("=" * 80)
        
        # Save detailed output
        output_file = Path(__file__).parent.parent / "data" / "json" / f"control_test_{args.version}_output.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\nDetailed output saved to: {output_file}")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n✅ Extraction completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
