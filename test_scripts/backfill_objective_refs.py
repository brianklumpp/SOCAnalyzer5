"""
Backfill script: Fix line_ref/page_refs/all_line_refs/all_page_refs for ALL objectives
in a given scan. Searches ONLY the Control_Descriptions section for each objective's
heading position and updates the database.

CRITICAL: Only includes occurrences from within Control_Descriptions section.
TOC, assertions, test results, etc. are excluded.

Usage: python test_scripts/backfill_objective_refs.py [--scan-id N] [--dry-run]
"""
import re
import sys
import argparse
import psycopg2
from typing import Optional, List, Dict, Any

DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "dbname": "soc2analyzer",
    "user": "soc2_analyzer",
    "password": "puntitforthewin"
}


def get_page_at_position(full_text: str, char_idx: int) -> Optional[int]:
    try:
        text_before = full_text[:char_idx]
        page_markers = list(re.finditer(r'====?\s*(?:Page|PAGE)\s+(\d+)\s*====?', text_before))
        if page_markers:
            return int(page_markers[-1].group(1))
    except Exception:
        pass
    return None


def is_heading_line(line_content: str, objective_id: str) -> bool:
    stripped = line_content.strip()
    if ',' in stripped:
        id_pattern = r'\b[A-Z]{1,4}\d+(?:\.\d+)*\b'
        ids_on_line = re.findall(id_pattern, stripped)
        if len(ids_on_line) >= 3:
            return False
    if stripped.lower().startswith(objective_id.lower()):
        return True
    id_match = re.search(r'\b' + re.escape(objective_id) + r'\b', stripped, re.IGNORECASE)
    if id_match and len(stripped) < 200:
        return True
    return False


def resolve_refs(text: str, objective_id: str, section_start: int, section_end: int) -> Dict[str, Any]:
    """
    Find all occurrences WITHIN Control_Descriptions section only.
    Select the heading as primary line_ref.
    
    Args:
        text: Full document text (not sliced)
        objective_id: The ID to search for
        section_start: First line of Control_Descriptions (1-indexed, inclusive)
        section_end: Last line of Control_Descriptions (1-indexed, inclusive)
    """
    doc_lines = text.split('\n')
    text_lower = text.lower()
    result = {"line_ref": None, "page_refs": None, "all_line_refs": [], "all_page_refs": []}
    
    if not objective_id:
        return result
    
    pattern = r'\b' + re.escape(objective_id.lower()) + r'\b'
    matches = list(re.finditer(pattern, text_lower))
    
    if not matches:
        return result
    
    # Filter to Control_Descriptions section ONLY
    section_occurrences = []
    for m in matches:
        idx = m.start()
        line_number = text[:idx].count('\n') + 1
        if line_number < section_start or line_number > section_end:
            continue  # Outside Control_Descriptions — skip
        page = get_page_at_position(text, idx)
        line_content = doc_lines[line_number - 1] if line_number <= len(doc_lines) else ""
        is_heading = is_heading_line(line_content, objective_id)
        section_occurrences.append({
            "line_number": line_number, "page": page,
            "is_heading": is_heading,
        })
    
    if not section_occurrences:
        return result
    
    all_lines = sorted(set(o["line_number"] for o in section_occurrences))
    all_pages = sorted(set(o["page"] for o in section_occurrences if o["page"] is not None))
    result["all_line_refs"] = all_lines
    result["all_page_refs"] = all_pages
    
    # Select primary: prefer heading, then first in section
    headings = [o for o in section_occurrences if o["is_heading"]]
    best = headings[0] if headings else section_occurrences[0]
    
    result["line_ref"] = best["line_number"]
    result["page_refs"] = [best["page"]] if best["page"] else None
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Backfill objective line/page refs")
    parser.add_argument("--scan-id", type=int, default=10, help="Scan ID to backfill")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB, just show changes")
    parser.add_argument("--gap-only", action="store_true", help="Only fix gap_search objectives")
    args = parser.parse_args()
    
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # Get extracted text and result_json
    cur.execute("SELECT extracted_text, result_json FROM scan WHERE id=%s", (args.scan_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        print(f"No extracted text found for scan {args.scan_id}")
        return
    text = row[0]
    result_json = row[1]
    
    # Get Control_Descriptions section bounds from result_json
    import json as json_mod
    section_start = None
    section_end = None
    if result_json:
        if isinstance(result_json, str):
            try:
                result_json = json_mod.loads(result_json)
            except Exception:
                result_json = {}
        sections = result_json.get('sections', []) if isinstance(result_json, dict) else []
        cd = next((s for s in sections if s.get('topic') == 'Control_Descriptions'), None)
        if cd and isinstance(cd.get('start_line'), int) and isinstance(cd.get('end_line'), int):
            section_start = cd['start_line']
            section_end = cd['end_line']
    
    if not section_start or not section_end:
        print(f"ERROR: Control_Descriptions section bounds not found in result_json for scan {args.scan_id}")
        print("Cannot proceed without section boundaries — would include TOC/assertion/test refs")
        return
    
    # Get objectives to fix
    where_clause = "scan_id=%s"
    params = [args.scan_id]
    if args.gap_only:
        where_clause += " AND extraction_method='gap_search'"
    
    cur.execute(f"""
        SELECT id, objective_id, line_ref, page_refs::text, 
               all_line_refs::text, all_page_refs::text, extraction_method
        FROM control_objectives 
        WHERE {where_clause}
        ORDER BY objective_id
    """, params)
    objectives = cur.fetchall()
    
    print(f"Scan {args.scan_id}: {len(objectives)} objectives to process")
    print(f"Control_Descriptions section: lines {section_start}-{section_end}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}")
    print(f"{'='*80}")
    
    updated = 0
    skipped = 0
    
    import json
    
    for obj_id_db, objective_id, current_line_ref, current_page_refs, current_all_lines, current_all_pages, method in objectives:
        if not objective_id:
            skipped += 1
            continue
        
        refs = resolve_refs(text, objective_id, section_start, section_end)
        new_line_ref = refs["line_ref"]
        new_page_refs = refs["page_refs"]
        new_all_lines = refs["all_line_refs"]
        new_all_pages = refs["all_page_refs"]
        
        if new_line_ref is None:
            skipped += 1
            continue
        
        # For gap_search objectives: update everything (line_ref was wrong)
        # For structural objectives: only update all_line_refs/all_page_refs (keep original line_ref)
        is_gap = method == "gap_search"
        
        final_line_ref = new_line_ref if is_gap else current_line_ref
        final_page_refs = new_page_refs if is_gap else current_page_refs
        
        # Parse current all_line/all_page for comparison
        try:
            cur_all_lines_list = json.loads(current_all_lines) if current_all_lines else []
        except Exception:
            cur_all_lines_list = []
        try:
            cur_all_pages_list = json.loads(current_all_pages) if current_all_pages else []
        except Exception:
            cur_all_pages_list = []
        
        changed = False
        if is_gap and new_line_ref != current_line_ref:
            changed = True
        if new_all_lines != cur_all_lines_list:
            changed = True
        if new_all_pages != cur_all_pages_list:
            changed = True
        
        if not changed:
            skipped += 1
            continue
        
        label = "→ WOULD UPDATE" if args.dry_run else "→ UPDATED"
        print(f"\n{objective_id} (db_id={obj_id_db}, method={method}):")
        if is_gap:
            print(f"  line_ref:      {current_line_ref} → {final_line_ref}")
            if str(current_page_refs) != str(final_page_refs):
                print(f"  page_refs:     {current_page_refs} → {final_page_refs}")
        else:
            print(f"  line_ref:      {current_line_ref} (kept)")
        print(f"  all_line_refs: {current_all_lines} → {new_all_lines}")
        print(f"  all_page_refs: {current_all_pages} → {new_all_pages}")
        print(f"  {label}")
        
        if not args.dry_run:
            if is_gap:
                # Update primary line_ref + page_refs + all refs
                cur.execute("""
                    UPDATE control_objectives 
                    SET line_ref=%s, page_refs=%s::jsonb, 
                        all_line_refs=%s::jsonb, all_page_refs=%s::jsonb,
                        updated_at=NOW()
                    WHERE id=%s
                """, (
                    final_line_ref,
                    json.dumps(new_page_refs) if new_page_refs else None,
                    json.dumps(new_all_lines),
                    json.dumps(new_all_pages),
                    obj_id_db
                ))
            else:
                # Only update all_line_refs/all_page_refs, keep primary line_ref intact
                cur.execute("""
                    UPDATE control_objectives 
                    SET all_line_refs=%s::jsonb, all_page_refs=%s::jsonb,
                        updated_at=NOW()
                    WHERE id=%s
                """, (
                    json.dumps(new_all_lines),
                    json.dumps(new_all_pages),
                    obj_id_db
                ))
            updated += 1
    
    if not args.dry_run:
        conn.commit()
    
    print(f"\n{'='*80}")
    print(f"Results: {updated} updated, {skipped} skipped (unchanged or no ID)")
    
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
