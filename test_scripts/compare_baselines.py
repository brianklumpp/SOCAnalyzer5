"""
Compare extraction results against baselines for regression detection.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime


def load_latest_baseline(baselines_dir: Path, report_name: str) -> dict | None:
    """Find and load the most recent baseline for a report."""
    pattern = f"{report_name}_*.json"
    matching = sorted(baselines_dir.glob(pattern), reverse=True)
    
    if not matching:
        return None
    
    with open(matching[0]) as f:
        return json.load(f)


def calculate_delta(current: float | int, baseline: float | int) -> dict:
    """Calculate absolute and percentage delta."""
    if baseline == 0:
        return {
            "absolute": current - baseline,
            "percentage": 0.0 if current == 0 else 100.0
        }
    
    absolute = current - baseline
    percentage = (absolute / baseline) * 100
    
    return {
        "absolute": absolute,
        "percentage": round(percentage, 2)
    }


def detect_regressions(current_metrics: dict, baseline_metrics: dict) -> list[dict]:
    """Detect regressions based on metric changes."""
    regressions = []
    
    # Check total control count (>5% drop)
    control_delta = calculate_delta(
        current_metrics["total_controls"],
        baseline_metrics["total_controls"]
    )
    
    if control_delta["percentage"] < -5:
        regressions.append({
            "severity": "high",
            "metric": "total_controls",
            "message": f"Control count dropped by {abs(control_delta['percentage'])}% "
                      f"({control_delta['absolute']} controls)",
            "current": current_metrics["total_controls"],
            "baseline": baseline_metrics["total_controls"],
            "delta": control_delta
        })
    
    # Check AMBIGUOUS increase (>50% relative increase)
    ambiguous_delta = calculate_delta(
        current_metrics["ambiguous_count"],
        baseline_metrics["ambiguous_count"]
    )
    
    if ambiguous_delta["percentage"] > 50 and current_metrics["ambiguous_count"] > 2:
        regressions.append({
            "severity": "medium",
            "metric": "ambiguous_count",
            "message": f"AMBIGUOUS controls increased by {ambiguous_delta['percentage']}% "
                      f"({ambiguous_delta['absolute']} controls)",
            "current": current_metrics["ambiguous_count"],
            "baseline": baseline_metrics["ambiguous_count"],
            "delta": ambiguous_delta
        })
    
    # Check PARTIAL_EXTRACTION presence (any is a regression)
    if current_metrics["partial_extraction_count"] > baseline_metrics["partial_extraction_count"]:
        regressions.append({
            "severity": "high",
            "metric": "partial_extraction_count",
            "message": f"PARTIAL_EXTRACTION controls detected: "
                      f"{current_metrics['partial_extraction_count']} (baseline: {baseline_metrics['partial_extraction_count']})",
            "current": current_metrics["partial_extraction_count"],
            "baseline": baseline_metrics["partial_extraction_count"],
            "delta": calculate_delta(
                current_metrics["partial_extraction_count"],
                baseline_metrics["partial_extraction_count"]
            )
        })
    
    # Check assertion accuracy (>10% drop in controls with assertions)
    assertion_delta = calculate_delta(
        current_metrics["controls_with_assertions"],
        baseline_metrics["controls_with_assertions"]
    )
    
    if assertion_delta["percentage"] < -10:
        regressions.append({
            "severity": "medium",
            "metric": "controls_with_assertions",
            "message": f"Controls with financial assertions dropped by {abs(assertion_delta['percentage'])}% "
                      f"({assertion_delta['absolute']} controls)",
            "current": current_metrics["controls_with_assertions"],
            "baseline": baseline_metrics["controls_with_assertions"],
            "delta": assertion_delta
        })
    
    return regressions


def compare_result(result: dict, baselines_dir: Path) -> dict:
    """Compare a single result against its baseline."""
    if not result.get("success"):
        return {
            "report_name": result.get("pdf_name", "unknown"),
            "baseline_found": False,
            "error": result.get("error", "Extraction failed")
        }
    
    report_name = result["report_name"]
    baseline = load_latest_baseline(baselines_dir, report_name)
    
    if not baseline:
        return {
            "report_name": report_name,
            "baseline_found": False,
            "message": "No baseline found - this is the first run",
            "current_metrics": result["metrics"]
        }
    
    regressions = detect_regressions(result["metrics"], baseline["metrics"])
    
    return {
        "report_name": report_name,
        "baseline_found": True,
        "baseline_id": baseline["baseline_id"],
        "baseline_created_at": baseline["created_at"],
        "regression_detected": len(regressions) > 0,
        "regressions": regressions,
        "current_metrics": result["metrics"],
        "baseline_metrics": baseline["metrics"],
        "deltas": {
            "total_controls": calculate_delta(
                result["metrics"]["total_controls"],
                baseline["metrics"]["total_controls"]
            ),
            "controls_with_assertions": calculate_delta(
                result["metrics"]["controls_with_assertions"],
                baseline["metrics"]["controls_with_assertions"]
            ),
            "ambiguous_count": calculate_delta(
                result["metrics"]["ambiguous_count"],
                baseline["metrics"]["ambiguous_count"]
            )
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Compare results against baselines")
    parser.add_argument(
        "--results",
        type=str,
        required=True,
        help="Path to validation results JSON"
    )
    parser.add_argument(
        "--baseline-dir",
        type=str,
        required=True,
        help="Directory containing baseline files"
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output comparison report JSON"
    )
    args = parser.parse_args()
    
    results_path = Path(args.results)
    baselines_dir = Path(args.baseline_dir)
    output_path = Path(args.output)
    
    if not results_path.exists():
        print(f"❌ Results file not found: {results_path}")
        return 1
    
    if not baselines_dir.exists():
        print(f"⚠️  Baseline directory not found: {baselines_dir}")
        baselines_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_path) as f:
        data = json.load(f)
    
    comparisons = []
    for result in data["results"]:
        comparison = compare_result(result, baselines_dir)
        comparisons.append(comparison)
        
        if comparison.get("regression_detected"):
            print(f"🚨 {comparison['report_name']}: {len(comparison['regressions'])} regression(s)")
        elif comparison.get("baseline_found"):
            print(f"✅ {comparison['report_name']}: No regressions")
        else:
            print(f"ℹ️  {comparison['report_name']}: No baseline (first run)")
    
    total_regressions = sum(
        len(c.get("regressions", [])) for c in comparisons
    )
    
    report = {
        "comparison_run": {
            "timestamp": datetime.utcnow().isoformat(),
            "total_reports": len(comparisons),
            "reports_with_baselines": sum(1 for c in comparisons if c.get("baseline_found")),
            "regressions_detected": sum(1 for c in comparisons if c.get("regression_detected")),
            "total_regression_count": total_regressions
        },
        "comparisons": comparisons
    }
    
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Comparison report saved to {output_path}")
    print(f"Total regressions: {total_regressions}")
    
    return 0


if __name__ == "__main__":
    exit(main())
