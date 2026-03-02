#!/usr/bin/env python3
"""
SOCAnalyzer5 — Post-Scan Quality Analysis

Run after a scan is reviewed to evaluate:
  1. Control extraction quality (FP, FN, confidence)
  2. Objective extraction quality (gap vs structural)
  3. Control→Objective mapping effectiveness (precision by source)
  4. Simulated "nearest-objective-by-line" mapping approach
  5. Recommendations for config tuning

Usage:
    python test_scripts/analyze_scan_quality.py [--scan-id N]

If --scan-id is omitted, uses the most recent scan.
"""
from __future__ import annotations

import argparse
import json
import sys
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# ── DB connection ──────────────────────────────────────────────────
import psycopg2

DB_HOST = os.getenv("ANALYZE_DB_HOST", "localhost")
DB_PORT = int(os.getenv("ANALYZE_DB_PORT", "5433"))
DB_NAME = os.getenv("ANALYZE_DB_NAME", "soc2analyzer")
DB_USER = os.getenv("ANALYZE_DB_USER", "soc2_analyzer")
DB_PASS = os.getenv("ANALYZE_DB_PASS", "puntitforthewin")


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        dbname=DB_NAME, user=DB_USER, password=DB_PASS,
    )


# ── Data classes ───────────────────────────────────────────────────
@dataclass
class ControlRow:
    id: int
    control_id: str
    control_desc: str
    control_confidence: float
    control_line_ref: Optional[int]
    control_page_refs: Optional[str]  # JSON array string
    pages: List[int] = field(default_factory=list)

    def __post_init__(self):
        self.pages = parse_pages(self.control_page_refs)


@dataclass
class ObjectiveRow:
    id: int
    objective_id: str
    objective_text: str
    line_ref: Optional[int]
    page_refs: Optional[str]
    all_page_refs: Optional[str]
    status: str
    source: Optional[str]
    pages: List[int] = field(default_factory=list)

    def __post_init__(self):
        self.pages = parse_pages(self.all_page_refs) or parse_pages(self.page_refs)


@dataclass
class MappingRow:
    id: int
    control_id: int  # FK
    objective_id: int  # FK
    mapping_confidence: float
    mapping_method: str
    mapping_justification: str


@dataclass
class FeedbackRow:
    id: int
    control_id: int
    objective_id: int
    action: str
    original_confidence: Optional[float]
    original_method: Optional[str]
    control_id_text: str
    objective_id_text: str


def parse_pages(raw) -> List[int]:
    """Parse JSON page array from string/list/None."""
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    if isinstance(raw, list):
        return sorted(set(int(p) for p in raw if p is not None))
    return []


# ── Queries ────────────────────────────────────────────────────────
def load_scan_id(cur) -> int:
    cur.execute("SELECT id FROM scan ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("ERROR: No scans found")
        sys.exit(1)
    return row[0]


def load_controls(cur, scan_id: int) -> List[ControlRow]:
    cur.execute("""
        SELECT id, control_id, control_desc, control_confidence,
               control_line_ref, control_page_refs::text
        FROM control WHERE scan_id = %s
        ORDER BY control_line_ref NULLS LAST
    """, (scan_id,))
    return [ControlRow(*r) for r in cur.fetchall()]


def load_objectives(cur, scan_id: int) -> List[ObjectiveRow]:
    cur.execute("""
        SELECT id, objective_id, objective_text, line_ref,
               page_refs::text, all_page_refs::text, status,
               extraction_method
        FROM control_objectives WHERE scan_id = %s
        ORDER BY line_ref NULLS LAST
    """, (scan_id,))
    return [ObjectiveRow(*r) for r in cur.fetchall()]


def load_mappings(cur, scan_id: int) -> List[MappingRow]:
    cur.execute("""
        SELECT m.id, m.control_id, m.objective_id,
               m.mapping_confidence, m.mapping_method,
               COALESCE(m.mapping_justification, '')
        FROM control_objective_mappings m
        JOIN control c ON m.control_id = c.id
        WHERE c.scan_id = %s
    """, (scan_id,))
    return [MappingRow(*r) for r in cur.fetchall()]


def load_feedback(cur, scan_id: int) -> List[FeedbackRow]:
    cur.execute("""
        SELECT id, control_id, objective_id, action,
               original_confidence, original_method,
               COALESCE(control_id_text, ''), COALESCE(objective_id_text, '')
        FROM mapping_feedback WHERE scan_id = %s
        ORDER BY created_at
    """, (scan_id,))
    return [FeedbackRow(*r) for r in cur.fetchall()]


def load_control_feedback(cur, scan_id: int) -> List[dict]:
    cur.execute("""
        SELECT action, control_db_id, COALESCE(control_id_text, ''),
               COALESCE(rejection_reason, '')
        FROM control_feedback WHERE scan_id = %s
    """, (scan_id,))
    return [{"action": r[0], "control_db_id": r[1],
             "control_id_text": r[2], "reason": r[3]} for r in cur.fetchall()]


def load_scan_info(cur, scan_id: int) -> dict:
    cur.execute("""
        SELECT company, product, report_type, scan_date
        FROM scan WHERE id = %s
    """, (scan_id,))
    row = cur.fetchone()
    return {"company": row[0], "product": row[1],
            "report_type": row[2], "scan_date": str(row[3])} if row else {}


def load_section_bounds(cur, scan_id: int) -> Optional[tuple]:
    """Get Control_Descriptions section start/end lines from scan.result_json."""
    cur.execute("SELECT result_json FROM scan WHERE id = %s", (scan_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    rj = row[0]
    if isinstance(rj, str):
        try:
            rj = json.loads(rj)
        except Exception:
            return None
    if not isinstance(rj, dict):
        return None
    sections = rj.get('sections', [])
    cd = next((s for s in sections if s.get('topic') == 'Control_Descriptions'), None)
    if cd and isinstance(cd.get('start_line'), int) and isinstance(cd.get('end_line'), int):
        return (cd['start_line'], cd['end_line'])
    return None


# ── Analysis helpers ───────────────────────────────────────────────
def classify_mapping_source(conf: Optional[float], just: str) -> str:
    """Classify a mapping source from its confidence / justification."""
    if not conf:
        return "unknown"
    just_lower = (just or "").lower()
    if "section assignment" in just_lower:
        return "Section Assignment"
    if "gpt classification" in just_lower:
        return "GPT Classification"
    if "tier 0" in just_lower:
        return "Tier 0 (Structure)"
    if "tier 1" in just_lower:
        return "Tier 1 (ID)"
    if "tier 2" in just_lower:
        return "Tier 2 (Line)"
    if "tier 3" in just_lower:
        return "Tier 3 (Page)"
    # Fallback: use confidence heuristic
    if conf >= 0.95:
        return "Section Assignment (inferred)"
    return "GPT Classification (inferred)"


def bucket(conf: float) -> str:
    if conf >= 0.95:
        return "0.95+"
    if conf >= 0.85:
        return "0.85-0.94"
    if conf >= 0.75:
        return "0.75-0.84"
    if conf >= 0.65:
        return "0.65-0.74"
    if conf >= 0.50:
        return "0.50-0.64"
    return "<0.50"


# ── Nearest-Objective-By-Line simulation ───────────────────────────
def simulate_line_based_mapping(
    controls: List[ControlRow],
    objectives: List[ObjectiveRow],
) -> Dict[int, str]:
    """
    For each control with a line_ref, walk backward through objectives
    sorted by line_ref descending to find the nearest preceding objective.

    Returns: Dict[control_db_id → objective_id_str]
    """
    # Only approved objectives with line_refs
    obj_with_lines = sorted(
        [o for o in objectives if o.status == 'approved' and o.line_ref],
        key=lambda o: o.line_ref,
    )
    result: Dict[int, str] = {}
    for ctrl in controls:
        if not ctrl.control_line_ref or not ctrl.control_id:
            continue
        if ctrl.control_confidence < 0.50:
            continue
        # Walk backward: find last objective whose line_ref <= control's line_ref
        best_obj = None
        for obj in obj_with_lines:
            if obj.line_ref <= ctrl.control_line_ref:
                best_obj = obj
            else:
                break
        if best_obj:
            result[ctrl.id] = best_obj.objective_id
    return result


def simulate_page_based_mapping(
    controls: List[ControlRow],
    objectives: List[ObjectiveRow],
) -> Dict[int, Set[str]]:
    """
    For each control, for each page it appears on, find all objectives
    that also appear on that page. If multiple objectives share a page,
    pick the one with the highest line_ref that is still <= control's line.

    Returns: Dict[control_db_id → set of objective_id_str]
    """
    # Build page → objectives index
    page_to_objs: Dict[int, List[ObjectiveRow]] = defaultdict(list)
    for obj in objectives:
        if obj.status != 'approved':
            continue
        for pg in obj.pages:
            page_to_objs[pg].append(obj)

    result: Dict[int, Set[str]] = {}
    for ctrl in controls:
        if not ctrl.control_id or ctrl.control_confidence < 0.50:
            continue
        matches: Set[str] = set()
        for pg in ctrl.pages:
            if pg in page_to_objs:
                # Objectives on same page — prefer those with line_ref before control
                candidates = page_to_objs[pg]
                if ctrl.control_line_ref:
                    # Nearest preceding by line
                    preceding = [
                        o for o in candidates if o.line_ref and o.line_ref <= ctrl.control_line_ref
                    ]
                    if preceding:
                        best = max(preceding, key=lambda o: o.line_ref)
                        matches.add(best.objective_id)
                    else:
                        # No preceding objective — take nearest by line distance
                        with_lines = [o for o in candidates if o.line_ref]
                        if with_lines:
                            nearest = min(with_lines, key=lambda o: abs(o.line_ref - ctrl.control_line_ref))
                            matches.add(nearest.objective_id)
                else:
                    # No line_ref — take all objectives on same page
                    for o in candidates:
                        matches.add(o.objective_id)
        if matches:
            result[ctrl.id] = matches
    return result


# ── Report printing ────────────────────────────────────────────────
SEP = "=" * 78
THIN = "-" * 78


def section(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def print_scan_overview(info: dict, scan_id: int, controls, objectives, mappings, feedback):
    section(f"SCAN {scan_id} QUALITY ANALYSIS")
    print(f"  Company:  {info.get('company', '?')}")
    print(f"  Product:  {info.get('product', '?')}")
    print(f"  Type:     {info.get('report_type', '?')}")
    print(f"  Date:     {info.get('scan_date', '?')}")
    print(f"\n  Controls:   {len(controls)}")
    print(f"  Objectives: {len(objectives)}")
    print(f"  Mappings:   {len(mappings)} (current)")
    print(f"  Feedback:   {len(feedback)} actions")


def print_control_analysis(controls, ctrl_feedback):
    section("1. CONTROL EXTRACTION QUALITY")

    eligible = [c for c in controls if c.control_id and c.control_confidence >= 0.50]
    low_conf = [c for c in controls if c.control_confidence < 0.50]
    no_id = [c for c in controls if not c.control_id or c.control_id.strip() == '']
    no_line = [c for c in eligible if not c.control_line_ref]

    print(f"\n  Total extracted:       {len(controls)}")
    print(f"  Eligible (conf≥0.50):  {len(eligible)}")
    print(f"  Low confidence (<0.50):{len(low_conf):>4}")
    print(f"  Missing control_id:    {len(no_id):>4}")
    print(f"  Missing line_ref:      {len(no_line):>4}")

    # Confidence distribution
    print(f"\n  Confidence Distribution:")
    buckets = defaultdict(int)
    for c in controls:
        buckets[bucket(c.control_confidence)] += 1
    for b in ["0.95+", "0.85-0.94", "0.75-0.84", "0.65-0.74", "0.50-0.64", "<0.50"]:
        if buckets[b]:
            print(f"    {b:>10}: {buckets[b]:>4}")

    # User feedback on controls
    if ctrl_feedback:
        print(f"\n  Analyst Control Actions:")
        actions = defaultdict(int)
        for f in ctrl_feedback:
            actions[f['action']] += 1
        for act, cnt in sorted(actions.items(), key=lambda x: -x[1]):
            print(f"    {act:>10}: {cnt}")

        # Detail rejected controls
        rejected = [f for f in ctrl_feedback if f['action'] == 'rejected']
        if rejected:
            print(f"\n  Rejected Controls (FP extractions):")
            for f in rejected:
                print(f"    ✗ {f['control_id_text'] or f['control_db_id']}: {f['reason'][:80]}")

    if no_line:
        print(f"\n  Controls Missing line_ref (cannot be section-assigned):")
        for c in no_line:
            pages_str = ",".join(str(p) for p in c.pages[:5])
            print(f"    ? {c.control_id} (pages=[{pages_str}], conf={c.control_confidence:.2f})")


def print_objective_analysis(objectives):
    section("2. OBJECTIVE EXTRACTION QUALITY")

    approved = [o for o in objectives if o.status == 'approved']
    pending = [o for o in objectives if o.status != 'approved']
    with_line = [o for o in approved if o.line_ref]
    gap_search = [o for o in approved if o.source and 'gap' in o.source.lower()]
    structural = [o for o in approved if not o.source or 'gap' not in (o.source or '').lower()]

    print(f"\n  Total:    {len(objectives)}")
    print(f"  Approved: {len(approved)}")
    print(f"  Pending:  {len(pending)}")
    print(f"  With line_ref: {len(with_line)}")
    print(f"  From gap search: {len(gap_search)}")
    print(f"  From structural extraction: {len(structural)}")

    if gap_search:
        print(f"\n  Gap-Search Objectives (line_ref may be from TOC/assertions):")
        for o in sorted(gap_search, key=lambda x: x.line_ref or 99999):
            lr = o.line_ref or "?"
            pgs = ",".join(str(p) for p in o.pages[:3])
            print(f"    ▸ {o.objective_id:>8} line={lr} pages=[{pgs}]")


def print_mapping_analysis(mappings, feedback, controls, objectives):
    section("3. MAPPING EFFECTIVENESS")

    # Build lookups
    ctrl_by_id = {c.id: c for c in controls}
    obj_by_id = {o.id: o for o in objectives}
    obj_by_str = {o.objective_id: o for o in objectives}

    # Feedback analysis
    removed = [f for f in feedback if f.action == 'removed']
    confirmed = [f for f in feedback if f.action == 'confirmed']
    added = [f for f in feedback if f.action == 'added']

    auto_total = len(removed) + len(confirmed)
    precision = len(confirmed) / auto_total * 100 if auto_total else 0

    print(f"\n  Auto-generated mappings: {auto_total}")
    print(f"  Confirmed by analyst:    {len(confirmed)} ({precision:.1f}% precision)")
    print(f"  Removed by analyst:      {len(removed)} ({100-precision:.1f}% FP rate)")
    print(f"  Manually added:          {len(added)}")
    print(f"  Final mappings:          {len(mappings)}")

    # Break down by confidence bucket
    print(f"\n  {THIN}")
    print(f"  FP Rate by Confidence Bucket:")
    print(f"  {'Bucket':<22} {'Confirmed':>9} {'Removed':>9} {'Total':>7} {'FP%':>7}")
    print(f"  {THIN}")

    auto_feedback = [f for f in feedback if f.action in ('confirmed', 'removed')]
    conf_buckets = defaultdict(lambda: {"confirmed": 0, "removed": 0})
    for f in auto_feedback:
        b = bucket(f.original_confidence or 0)
        conf_buckets[b][f.action] += 1
    for b in ["0.95+", "0.85-0.94", "0.75-0.84", "0.65-0.74", "0.50-0.64", "<0.50"]:
        if b in conf_buckets:
            d = conf_buckets[b]
            t = d["confirmed"] + d["removed"]
            fp = d["removed"] / t * 100 if t else 0
            print(f"  {b:<22} {d['confirmed']:>9} {d['removed']:>9} {t:>7} {fp:>6.1f}%")

    # Classify by mapping source (from justification in current mappings + feedback)
    print(f"\n  {THIN}")
    print(f"  FP Rate by Source (inferred from confidence):")
    print(f"  {'Source':<30} {'Confirmed':>9} {'Removed':>9} {'Total':>7} {'FP%':>7}")
    print(f"  {THIN}")

    source_stats = defaultdict(lambda: {"confirmed": 0, "removed": 0})
    for f in auto_feedback:
        src = classify_mapping_source(f.original_confidence, "")
        source_stats[src][f.action] += 1
    for src in sorted(source_stats):
        d = source_stats[src]
        t = d["confirmed"] + d["removed"]
        fp = d["removed"] / t * 100 if t else 0
        print(f"  {src:<30} {d['confirmed']:>9} {d['removed']:>9} {t:>7} {fp:>6.1f}%")

    # Detail: what was removed (wrong mappings)?
    print(f"\n  Removed Mappings (false positives):")
    removed_by_ctrl = defaultdict(list)
    for f in removed:
        removed_by_ctrl[f.control_id_text].append(f.objective_id_text)
    for ctrl_text in sorted(removed_by_ctrl):
        objs = ", ".join(sorted(removed_by_ctrl[ctrl_text]))
        print(f"    ✗ {ctrl_text:>12} → {objs}")

    # Detail: what was added (system missed)?
    print(f"\n  Added Mappings (false negatives — system missed):")
    added_by_ctrl = defaultdict(list)
    for f in added:
        added_by_ctrl[f.control_id_text].append(f.objective_id_text)
    for ctrl_text in sorted(added_by_ctrl):
        objs = ", ".join(sorted(added_by_ctrl[ctrl_text]))
        print(f"    + {ctrl_text:>12} → {objs}")


def print_simulation_results(
    controls, objectives, feedback,
    line_map, page_map,
):
    section("4. SIMULATED MAPPING APPROACHES")

    ctrl_by_id = {c.id: c for c in controls}
    obj_by_str = {o.objective_id: o for o in objectives}

    # Build ground truth from feedback:
    #   confirmed = auto mapping that was correct
    #   added = manual mapping that was correct
    #   removed = auto mapping that was wrong
    ground_truth: Dict[int, Set[str]] = defaultdict(set)  # ctrl_db_id → set of correct obj_id_str
    wrong_auto: Dict[int, Set[str]] = defaultdict(set)

    for f in feedback:
        if f.action in ('confirmed', 'added'):
            ground_truth[f.control_id].add(f.objective_id_text)
        elif f.action == 'removed':
            wrong_auto[f.control_id].add(f.objective_id_text)

    # ── Approach A: Nearest objective by line (single primary) ──
    print(f"\n  A) NEAREST OBJECTIVE BY LINE (single primary per control)")
    print(f"  {THIN}")
    a_correct = 0
    a_wrong = 0
    a_missed = 0
    a_details_wrong = []
    a_details_missed = []

    for ctrl in controls:
        if not ctrl.control_id or ctrl.control_confidence < 0.50:
            continue
        predicted_obj = line_map.get(ctrl.id)
        correct_objs = ground_truth.get(ctrl.id, set())

        if not correct_objs:
            continue  # No ground truth — untouched

        if predicted_obj:
            if predicted_obj in correct_objs:
                a_correct += 1
            else:
                a_wrong += 1
                expected = ", ".join(sorted(correct_objs))
                a_details_wrong.append(
                    f"    ✗ {ctrl.control_id:>12} → predicted {predicted_obj}, "
                    f"correct: {expected}"
                )
        else:
            a_missed += 1

        # Check for FNs — additional correct objectives beyond primary
        extras = correct_objs - {predicted_obj} if predicted_obj else correct_objs
        if extras:
            a_missed += len(extras)

    a_total = a_correct + a_wrong
    a_precision = a_correct / a_total * 100 if a_total else 0
    a_recall_denom = a_correct + a_missed
    a_recall = a_correct / a_recall_denom * 100 if a_recall_denom else 0

    print(f"  Correct primary:     {a_correct}")
    print(f"  Wrong primary:       {a_wrong}")
    print(f"  Missed (FN):         {a_missed}")
    print(f"  Precision:           {a_precision:.1f}%")
    print(f"  Recall:              {a_recall:.1f}%")

    if a_details_wrong:
        print(f"\n  Wrong primaries:")
        for d in a_details_wrong[:20]:
            print(d)

    # ── Approach B: Page-based multi-mapping ──
    print(f"\n  B) PAGE-BASED MAPPING (all objectives sharing a page)")
    print(f"  {THIN}")
    b_correct = 0
    b_wrong = 0
    b_missed = 0
    b_details_wrong = []

    for ctrl in controls:
        if not ctrl.control_id or ctrl.control_confidence < 0.50:
            continue
        predicted_objs = page_map.get(ctrl.id, set())
        correct_objs = ground_truth.get(ctrl.id, set())

        if not correct_objs:
            continue

        true_pos = predicted_objs & correct_objs
        false_pos = predicted_objs - correct_objs
        false_neg = correct_objs - predicted_objs

        b_correct += len(true_pos)
        b_wrong += len(false_pos)
        b_missed += len(false_neg)

        if false_pos:
            b_details_wrong.append(
                f"    ✗ {ctrl.control_id:>12} → FP: {', '.join(sorted(false_pos))}"
            )

    b_total = b_correct + b_wrong
    b_precision = b_correct / b_total * 100 if b_total else 0
    b_recall_denom = b_correct + b_missed
    b_recall = b_correct / b_recall_denom * 100 if b_recall_denom else 0

    print(f"  True positives:      {b_correct}")
    print(f"  False positives:     {b_wrong}")
    print(f"  Missed (FN):         {b_missed}")
    print(f"  Precision:           {b_precision:.1f}%")
    print(f"  Recall:              {b_recall:.1f}%")

    if b_details_wrong:
        print(f"\n  False positives:")
        for d in b_details_wrong[:20]:
            print(d)

    # ── Approach C: Nearest-by-line primary + page-based secondaries ──
    print(f"\n  C) COMBINED: Line-primary + Page-secondaries")
    print(f"  {THIN}")
    c_correct = 0
    c_wrong = 0
    c_missed = 0

    for ctrl in controls:
        if not ctrl.control_id or ctrl.control_confidence < 0.50:
            continue
        predicted = set()
        primary = line_map.get(ctrl.id)
        if primary:
            predicted.add(primary)
        page_objs = page_map.get(ctrl.id, set())
        predicted.update(page_objs)

        correct_objs = ground_truth.get(ctrl.id, set())
        if not correct_objs:
            continue

        true_pos = predicted & correct_objs
        false_pos = predicted - correct_objs
        false_neg = correct_objs - predicted

        c_correct += len(true_pos)
        c_wrong += len(false_pos)
        c_missed += len(false_neg)

    c_total = c_correct + c_wrong
    c_precision = c_correct / c_total * 100 if c_total else 0
    c_recall_denom = c_correct + c_missed
    c_recall = c_correct / c_recall_denom * 100 if c_recall_denom else 0

    print(f"  True positives:      {c_correct}")
    print(f"  False positives:     {c_wrong}")
    print(f"  Missed (FN):         {c_missed}")
    print(f"  Precision:           {c_precision:.1f}%")
    print(f"  Recall:              {c_recall:.1f}%")

    # ── Comparison summary ──
    section("5. APPROACH COMPARISON SUMMARY")
    print(f"  {'Approach':<40} {'Prec%':>7} {'Recall%':>8} {'FP':>5} {'FN':>5}")
    print(f"  {THIN}")
    print(f"  {'A) Line-nearest (single primary)':<40} {a_precision:>6.1f}% {a_recall:>7.1f}% {a_wrong:>5} {a_missed:>5}")
    print(f"  {'B) Page-based (multi-map)':<40} {b_precision:>6.1f}% {b_recall:>7.1f}% {b_wrong:>5} {b_missed:>5}")
    print(f"  {'C) Line primary + Page secondary':<40} {c_precision:>6.1f}% {c_recall:>7.1f}% {c_wrong:>5} {c_missed:>5}")

    # Current system stats
    confirmed_ct = sum(1 for f in feedback if f.action == 'confirmed')
    removed_ct = sum(1 for f in feedback if f.action == 'removed')
    added_ct = sum(1 for f in feedback if f.action == 'added')
    sys_total = confirmed_ct + removed_ct
    sys_prec = confirmed_ct / sys_total * 100 if sys_total else 0
    sys_recall = confirmed_ct / (confirmed_ct + added_ct) * 100 if (confirmed_ct + added_ct) else 0
    print(f"  {'Current system (auto_classified)':<40} {sys_prec:>6.1f}% {sys_recall:>7.1f}% {removed_ct:>5} {added_ct:>5}")


def print_line_based_detail(controls, objectives, feedback, line_map):
    """Show exactly what the simplest approach (nearest-obj-by-line) produces."""
    section("6. LINE-BASED MAPPING DETAIL (Approach A)")

    ctrl_by_id = {c.id: c for c in controls}
    obj_by_str = {o.objective_id: o for o in objectives}

    # Build ground truth
    gt: Dict[int, Set[str]] = defaultdict(set)
    for f in feedback:
        if f.action in ('confirmed', 'added'):
            gt[f.control_id].add(f.objective_id_text)

    print(f"\n  {'Control':<14} {'Line':>6} {'Predicted':>10} {'Ground Truth':<30} {'Match':>5}")
    print(f"  {THIN}")

    eligible = [
        c for c in controls
        if c.control_id and c.control_confidence >= 0.50
    ]
    for ctrl in sorted(eligible, key=lambda c: c.control_line_ref or 99999):
        predicted = line_map.get(ctrl.id, "—")
        correct = gt.get(ctrl.id, set())
        if not correct:
            match = "?"
        elif predicted in correct:
            match = "✓"
        else:
            match = "✗"
        correct_str = ", ".join(sorted(correct)) if correct else "—"
        lr = ctrl.control_line_ref or "—"
        print(f"  {ctrl.control_id:<14} {str(lr):>6} {predicted:>10} {correct_str:<30} {match:>5}")


def print_ref_consistency(
    controls: List[ControlRow],
    objectives: List[ObjectiveRow],
    section_bounds: Optional[tuple],
):
    """Validate that all line/page refs fall within Control_Descriptions section."""
    print("\n" + "=" * 72)
    print("SECTION 8: LINE/PAGE REF CONSISTENCY")
    print("=" * 72)

    if not section_bounds:
        print("  ⚠ Control_Descriptions section bounds not found in result_json")
        print("    Cannot validate ref consistency.")
        return

    sec_start, sec_end = section_bounds
    print(f"  Control_Descriptions: lines {sec_start}–{sec_end}")

    # Check controls
    oob_controls = []
    for c in controls:
        if c.control_line_ref and (c.control_line_ref < sec_start or c.control_line_ref > sec_end):
            oob_controls.append(c)
    # Check objectives
    oob_objectives = []
    for o in objectives:
        if o.line_ref and (o.line_ref < sec_start or o.line_ref > sec_end):
            oob_objectives.append(o)

    total_controls = sum(1 for c in controls if c.control_line_ref)
    total_objectives = sum(1 for o in objectives if o.line_ref)

    if not oob_controls and not oob_objectives:
        print(f"  ✓ All {total_controls} control line_refs within section")
        print(f"  ✓ All {total_objectives} objective line_refs within section")
    else:
        if oob_controls:
            print(f"  ✗ {len(oob_controls)}/{total_controls} controls have line_ref OUTSIDE section:")
            for c in oob_controls[:10]:
                print(f"    {c.control_id}: line_ref={c.control_line_ref}")
        else:
            print(f"  ✓ All {total_controls} control line_refs within section")

        if oob_objectives:
            print(f"  ✗ {len(oob_objectives)}/{total_objectives} objectives have line_ref OUTSIDE section:")
            for o in oob_objectives[:10]:
                print(f"    {o.objective_id}: line_ref={o.line_ref} (method={o.extraction_method})")
        else:
            print(f"  ✓ All {total_objectives} objective line_refs within section")


def print_recommendations(feedback, controls, objectives, line_map, page_map):
    section("7. RECOMMENDATIONS")

    confirmed = sum(1 for f in feedback if f.action == 'confirmed')
    removed = sum(1 for f in feedback if f.action == 'removed')
    added = sum(1 for f in feedback if f.action == 'added')
    auto_total = confirmed + removed

    # GPT classification FP rate
    gpt_class = [f for f in feedback if f.action in ('confirmed', 'removed')
                 and (f.original_confidence or 0) < 0.95]
    gpt_removed = sum(1 for f in gpt_class if f.action == 'removed')
    gpt_fp = gpt_removed / len(gpt_class) * 100 if gpt_class else 0

    # Section assignment FP rate
    sect = [f for f in feedback if f.action in ('confirmed', 'removed')
            and (f.original_confidence or 0) >= 0.95]
    sect_removed = sum(1 for f in sect if f.action == 'removed')
    sect_fp = sect_removed / len(sect) * 100 if sect else 0

    # Controls without line_ref
    no_line = [c for c in controls if c.control_id and c.control_confidence >= 0.50 and not c.control_line_ref]

    print(f"\n  Overall: {removed}/{auto_total} auto-mappings removed ({removed/auto_total*100:.1f}% FP)")
    print(f"  Section Assignment: {sect_removed}/{len(sect)} removed ({sect_fp:.1f}% FP)")
    print(f"  GPT Classification: {gpt_removed}/{len(gpt_class)} removed ({gpt_fp:.1f}% FP)")
    print(f"  Manual additions:   {added} needed")
    print(f"  Controls without line_ref: {len(no_line)}")

    print(f"\n  Issues Identified:")
    if gpt_fp > 60:
        print(f"  ⚠ GPT Classification has {gpt_fp:.0f}% FP rate — contributing most false positives.")
        print(f"    → Consider disabling GPT secondary classification entirely.")
        print(f"    → Or raise minimum confidence threshold above 0.85.")
    if sect_fp > 20:
        print(f"  ⚠ Section Assignment has {sect_fp:.0f}% FP rate (expected <10%).")
        gap_objs = [o for o in objectives if o.source and 'gap' in (o.source or '').lower()]
        if gap_objs:
            print(f"    → {len(gap_objs)} gap-search objectives may have misleading line_refs.")
            print(f"    → Gap-search objectives placed before the controls section create wrong sections.")
    if added > 20:
        print(f"  ⚠ {added} manual additions — system has low recall for secondary mappings.")
        print(f"    → Many controls map to objectives in distant sections (different page regions).")
    if no_line:
        print(f"  ⚠ {len(no_line)} controls lack line_ref — cannot be section-assigned.")

    print(f"\n  Potential Simplification:")
    print(f"    The nearest-objective-by-line approach is the simplest possible mapping.")
    print(f"    It produces one primary per control with no GPT calls at all.")
    print(f"    Compare 'Approach A' precision/recall with the current system above.")


# ── Main ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="SOCAnalyzer5 Post-Scan Quality Analysis")
    parser.add_argument("--scan-id", type=int, default=None, help="Scan ID (default: latest)")
    parser.add_argument("--detail", action="store_true", help="Show per-control line mapping detail")
    args = parser.parse_args()

    conn = get_conn()
    cur = conn.cursor()

    scan_id = args.scan_id or load_scan_id(cur)
    info = load_scan_info(cur, scan_id)
    controls = load_controls(cur, scan_id)
    objectives = load_objectives(cur, scan_id)
    mappings = load_mappings(cur, scan_id)
    feedback = load_feedback(cur, scan_id)
    ctrl_feedback = load_control_feedback(cur, scan_id)

    section_bounds = load_section_bounds(cur, scan_id)

    # Simulations
    line_map = simulate_line_based_mapping(controls, objectives)
    page_map = simulate_page_based_mapping(controls, objectives)

    # Reports
    print_scan_overview(info, scan_id, controls, objectives, mappings, feedback)
    print_control_analysis(controls, ctrl_feedback)
    print_objective_analysis(objectives)
    print_mapping_analysis(mappings, feedback, controls, objectives)
    print_simulation_results(controls, objectives, feedback, line_map, page_map)
    print_ref_consistency(controls, objectives, section_bounds)

    if args.detail:
        print_line_based_detail(controls, objectives, feedback, line_map)

    print_recommendations(feedback, controls, objectives, line_map, page_map)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
