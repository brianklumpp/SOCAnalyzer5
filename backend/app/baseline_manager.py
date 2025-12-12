"""
Baseline Management Service
============================

Manages validation baselines for SOC report extraction accuracy testing.
Handles creation, storage, comparison, and FIFO retention of baselines.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Baseline storage directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
BASELINES_DIR = PROJECT_ROOT / "soc1_reports" / "baselines"
BASELINES_DIR.mkdir(parents=True, exist_ok=True)

MAX_BASELINES_PER_REPORT = 20


class BaselineManager:
    """Manages creation, storage, and comparison of validation baselines."""
    
    @staticmethod
    def create_baseline(
        scan_data: Dict[str, Any],
        report_name: str,
        extractor_version: str,
        reviewer_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new baseline from approved scan data.
        
        Args:
            scan_data: Complete scan results (controls, cuecs, metadata)
            report_name: Name of the report (without extension)
            extractor_version: Version tag (e.g., "v4_soc1", "combined")
            reviewer_notes: Optional notes from manual review
            
        Returns:
            Baseline metadata dict with file path
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{report_name}_{extractor_version}_{timestamp}.json"
        filepath = BASELINES_DIR / filename
        
        # Calculate metrics
        controls = scan_data.get("controls", [])
        metrics = BaselineManager._calculate_metrics(controls)
        
        baseline = {
            "baseline_id": filename,
            "report_name": report_name,
            "extractor_version": extractor_version,
            "created_at": datetime.now().isoformat(),
            "report_type": scan_data.get("report_type", "SOC1"),
            "scan_id": scan_data.get("scan_id"),
            "reviewer_notes": reviewer_notes,
            "metrics": metrics,
            "scan_data": scan_data
        }
        
        # Save to file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(baseline, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Created baseline: {filename}")
        
        # Cleanup old baselines (FIFO)
        BaselineManager._cleanup_old_baselines(report_name, extractor_version)
        
        return {
            "baseline_id": filename,
            "filepath": str(filepath),
            "metrics": metrics,
            "created_at": baseline["created_at"]
        }
    
    @staticmethod
    def _calculate_metrics(controls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate accuracy metrics from controls."""
        total_controls = len(controls)
        if total_controls == 0:
            return {"total_controls": 0}
        
        # Framework breakdown
        framework_counts = {}
        for ctrl in controls:
            fw = ctrl.get("framework_category", "UNKNOWN")
            framework_counts[fw] = framework_counts.get(fw, 0) + 1
        
        # Assertion statistics
        total_assertions = 0
        controls_with_assertions = 0
        for ctrl in controls:
            assertions = ctrl.get("financial_assertions", [])
            if assertions:
                controls_with_assertions += 1
                total_assertions += len(assertions)
        
        return {
            "total_controls": total_controls,
            "framework_breakdown": framework_counts,
            "controls_with_assertions": controls_with_assertions,
            "total_assertions": total_assertions,
            "avg_assertions_per_control": round(total_assertions / total_controls, 2) if total_controls > 0 else 0,
            "ambiguous_count": framework_counts.get("AMBIGUOUS", 0),
            "partial_extraction_count": framework_counts.get("PARTIAL_EXTRACTION", 0)
        }
    
    @staticmethod
    def _cleanup_old_baselines(report_name: str, extractor_version: str):
        """Remove oldest baselines if exceeding MAX_BASELINES_PER_REPORT."""
        pattern = f"{report_name}_{extractor_version}_*.json"
        baselines = list(BASELINES_DIR.glob(pattern))
        
        if len(baselines) > MAX_BASELINES_PER_REPORT:
            # Sort by creation time (oldest first)
            baselines.sort(key=lambda p: p.stat().st_ctime)
            
            # Delete oldest
            to_delete = baselines[:len(baselines) - MAX_BASELINES_PER_REPORT]
            for baseline_file in to_delete:
                baseline_file.unlink()
                logger.info(f"Deleted old baseline: {baseline_file.name}")
    
    @staticmethod
    def list_baselines(report_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all baselines, optionally filtered by report name.
        
        Args:
            report_name: Optional filter by report name
            
        Returns:
            List of baseline metadata dicts
        """
        pattern = f"{report_name}_*.json" if report_name else "*.json"
        baseline_files = list(BASELINES_DIR.glob(pattern))
        
        baselines = []
        for filepath in baseline_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    baselines.append({
                        "baseline_id": data.get("baseline_id", filepath.name),
                        "report_name": data.get("report_name"),
                        "extractor_version": data.get("extractor_version"),
                        "created_at": data.get("created_at"),
                        "metrics": data.get("metrics"),
                        "filepath": str(filepath)
                    })
            except Exception as e:
                logger.error(f"Failed to load baseline {filepath.name}: {e}")
        
        # Sort by creation time (newest first)
        baselines.sort(key=lambda b: b.get("created_at", ""), reverse=True)
        return baselines
    
    @staticmethod
    def get_baseline(baseline_id: str) -> Optional[Dict[str, Any]]:
        """Load a specific baseline by ID."""
        filepath = BASELINES_DIR / baseline_id
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load baseline {baseline_id}: {e}")
            return None
    
    @staticmethod
    def compare_to_baseline(
        current_scan: Dict[str, Any],
        baseline_id: str
    ) -> Dict[str, Any]:
        """
        Compare current scan results to a baseline.
        
        Args:
            current_scan: Current extraction results
            baseline_id: Baseline ID to compare against
            
        Returns:
            Comparison report with deltas and regression flags
        """
        baseline = BaselineManager.get_baseline(baseline_id)
        if not baseline:
            return {"error": f"Baseline {baseline_id} not found"}
        
        baseline_data = baseline.get("scan_data", {})
        baseline_metrics = baseline.get("metrics", {})
        
        # Calculate current metrics
        current_controls = current_scan.get("controls", [])
        current_metrics = BaselineManager._calculate_metrics(current_controls)
        
        # Calculate deltas
        deltas = {}
        for key in ["total_controls", "controls_with_assertions", "total_assertions"]:
            baseline_val = baseline_metrics.get(key, 0)
            current_val = current_metrics.get(key, 0)
            delta = current_val - baseline_val
            pct_change = (delta / baseline_val * 100) if baseline_val > 0 else 0
            deltas[key] = {
                "baseline": baseline_val,
                "current": current_val,
                "delta": delta,
                "percent_change": round(pct_change, 2)
            }
        
        # Framework breakdown comparison
        baseline_fw = baseline_metrics.get("framework_breakdown", {})
        current_fw = current_metrics.get("framework_breakdown", {})
        
        # Detect regressions
        regressions = []
        
        # Control count regression (>5% drop)
        if deltas["total_controls"]["percent_change"] < -5:
            regressions.append({
                "type": "control_count_drop",
                "severity": "high",
                "message": f"Control count dropped by {abs(deltas['total_controls']['percent_change']):.1f}%"
            })
        
        # AMBIGUOUS increase
        baseline_ambig = baseline_fw.get("AMBIGUOUS", 0)
        current_ambig = current_fw.get("AMBIGUOUS", 0)
        if current_ambig > baseline_ambig * 1.5:  # 50% increase
            regressions.append({
                "type": "ambiguous_increase",
                "severity": "medium",
                "message": f"AMBIGUOUS controls increased from {baseline_ambig} to {current_ambig}"
            })
        
        # PARTIAL_EXTRACTION appearance
        if current_fw.get("PARTIAL_EXTRACTION", 0) > 0:
            regressions.append({
                "type": "partial_extraction_detected",
                "severity": "high",
                "message": f"{current_fw['PARTIAL_EXTRACTION']} controls flagged as PARTIAL_EXTRACTION"
            })
        
        return {
            "baseline_id": baseline_id,
            "baseline_created_at": baseline.get("created_at"),
            "comparison_timestamp": datetime.now().isoformat(),
            "baseline_metrics": baseline_metrics,
            "current_metrics": current_metrics,
            "deltas": deltas,
            "framework_comparison": {
                "baseline": baseline_fw,
                "current": current_fw
            },
            "regressions": regressions,
            "regression_detected": len(regressions) > 0
        }
    
    @staticmethod
    def delete_baseline(baseline_id: str) -> bool:
        """Delete a baseline by ID."""
        filepath = BASELINES_DIR / baseline_id
        if filepath.exists():
            filepath.unlink()
            logger.info(f"Deleted baseline: {baseline_id}")
            return True
        return False
