"""
Check for regressions and exit with error code if found.
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Check for regressions")
    parser.add_argument(
        "--comparison",
        type=str,
        required=True,
        help="Path to comparison report JSON"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.05,
        help="Severity threshold (0.0-1.0)"
    )
    args = parser.parse_args()
    
    comparison_path = Path(args.comparison)
    
    if not comparison_path.exists():
        print(f"❌ Comparison report not found: {comparison_path}")
        return 1
    
    with open(comparison_path) as f:
        report = json.load(f)
    
    total_regressions = report["comparison_run"]["total_regression_count"]
    
    if total_regressions == 0:
        print("✅ No regressions detected - validation passed!")
        return 0
    
    print(f"\n🚨 REGRESSIONS DETECTED: {total_regressions} issue(s)\n")
    print("="*60)
    
    for comparison in report["comparisons"]:
        if not comparison.get("regression_detected"):
            continue
        
        print(f"\nReport: {comparison['report_name']}")
        print("-" * 60)
        
        for regression in comparison["regressions"]:
            severity_icon = "🔴" if regression["severity"] == "high" else "🟡"
            print(f"{severity_icon} [{regression['severity'].upper()}] {regression['message']}")
            print(f"   Current: {regression['current']}, Baseline: {regression['baseline']}")
            print(f"   Delta: {regression['delta']['absolute']} ({regression['delta']['percentage']:+.2f}%)")
    
    print("\n" + "="*60)
    print(f"❌ Validation FAILED - {total_regressions} regression(s) detected")
    print("="*60 + "\n")
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
