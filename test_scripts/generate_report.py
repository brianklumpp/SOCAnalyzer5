"""
Generate markdown test report for GitHub PR comments.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime


def format_delta(delta: dict) -> str:
    """Format delta with emoji indicator."""
    pct = delta["percentage"]
    absolute = delta["absolute"]
    
    if pct > 5:
        icon = "📈"
        color = "🟢"
    elif pct < -5:
        icon = "📉"
        color = "🔴"
    else:
        icon = "➡️"
        color = "⚪"
    
    sign = "+" if absolute >= 0 else ""
    return f"{icon} {sign}{absolute} ({pct:+.1f}%)"


def generate_report(comparison_path: Path) -> str:
    """Generate markdown report from comparison JSON."""
    if not comparison_path.exists():
        return "❌ Comparison report not found"
    
    with open(comparison_path) as f:
        report = json.load(f)
    
    run_info = report["comparison_run"]
    comparisons = report["comparisons"]
    
    # Header
    lines = []
    lines.append(f"**Test Run:** {datetime.fromisoformat(run_info['timestamp']).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"**Reports Tested:** {run_info['total_reports']}")
    lines.append(f"**Baselines Found:** {run_info['reports_with_baselines']}")
    lines.append("")
    
    # Overall status
    if run_info["regressions_detected"] > 0:
        lines.append(f"## 🚨 Status: FAILED")
        lines.append(f"**{run_info['regressions_detected']} report(s) with regressions** ({run_info['total_regression_count']} total issues)")
    else:
        lines.append(f"## ✅ Status: PASSED")
        lines.append("No regressions detected")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Per-report details
    for comparison in comparisons:
        report_name = comparison["report_name"]
        
        if comparison.get("error"):
            lines.append(f"### ❌ {report_name}")
            lines.append(f"**Error:** {comparison['error']}")
            lines.append("")
            continue
        
        if not comparison.get("baseline_found"):
            lines.append(f"### ℹ️  {report_name}")
            lines.append("**Status:** No baseline found (first run)")
            lines.append("")
            lines.append("**Current Metrics:**")
            metrics = comparison["current_metrics"]
            lines.append(f"- Total Controls: {metrics['total_controls']}")
            lines.append(f"- With Assertions: {metrics['controls_with_assertions']}")
            lines.append(f"- Framework: SOC1={metrics['framework_breakdown']['SOC1']}, SOC2={metrics['framework_breakdown']['SOC2']}, COMBINED={metrics['framework_breakdown']['COMBINED']}")
            lines.append("")
            continue
        
        # Report with baseline
        if comparison.get("regression_detected"):
            icon = "🚨"
            status = f"FAILED ({len(comparison['regressions'])} regressions)"
        else:
            icon = "✅"
            status = "PASSED"
        
        lines.append(f"### {icon} {report_name}")
        lines.append(f"**Status:** {status}")
        lines.append(f"**Baseline:** {comparison['baseline_id']}")
        lines.append("")
        
        # Regressions
        if comparison.get("regressions"):
            lines.append("**Regressions:**")
            for reg in comparison["regressions"]:
                severity_icon = "🔴" if reg["severity"] == "high" else "🟡"
                lines.append(f"- {severity_icon} **[{reg['severity'].upper()}]** {reg['message']}")
            lines.append("")
        
        # Metrics table
        lines.append("**Metrics Comparison:**")
        lines.append("")
        lines.append("| Metric | Current | Baseline | Delta |")
        lines.append("|--------|---------|----------|-------|")
        
        curr = comparison["current_metrics"]
        base = comparison["baseline_metrics"]
        deltas = comparison["deltas"]
        
        lines.append(f"| Total Controls | {curr['total_controls']} | {base['total_controls']} | {format_delta(deltas['total_controls'])} |")
        lines.append(f"| With Assertions | {curr['controls_with_assertions']} | {base['controls_with_assertions']} | {format_delta(deltas['controls_with_assertions'])} |")
        lines.append(f"| Ambiguous | {curr['ambiguous_count']} | {base['ambiguous_count']} | {format_delta(deltas['ambiguous_count'])} |")
        lines.append(f"| Partial Extraction | {curr['partial_extraction_count']} | {base['partial_extraction_count']} | - |")
        lines.append("")
        
        # Framework breakdown
        lines.append("**Framework Breakdown:**")
        for framework, count in curr["framework_breakdown"].items():
            baseline_count = base["framework_breakdown"].get(framework, 0)
            delta_str = f" ({count - baseline_count:+d})" if count != baseline_count else ""
            lines.append(f"- {framework}: {count}{delta_str}")
        lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate test report")
    parser.add_argument(
        "--comparison",
        type=str,
        required=True,
        help="Path to comparison report JSON"
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output markdown file"
    )
    args = parser.parse_args()
    
    comparison_path = Path(args.comparison)
    output_path = Path(args.output)
    
    report_md = generate_report(comparison_path)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(report_md)
    
    print(f"📄 Test report generated: {output_path}")
    print("\n" + "="*60)
    print(report_md)
    print("="*60)


if __name__ == "__main__":
    main()
