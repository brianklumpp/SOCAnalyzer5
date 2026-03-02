"""
Verify the _find_line_and_page_refs fix by simulating its logic against scan 10 data.
Tests that gap-search objectives now resolve to controls-section headings, not TOC.
"""
import re
import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "dbname": "soc2analyzer",
    "user": "soc2_analyzer",
    "password": "puntitforthewin"
}

def get_page_at_position(full_text: str, char_idx: int):
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

def find_line_and_page_refs(text: str, objective_id: str, controls_section_start: int):
    doc_lines = text.split('\n')
    text_lower = text.lower()
    result = {"line_ref": None, "page_refs": None, "all_line_refs": [], "all_page_refs": []}
    
    if not objective_id:
        return result
    
    pattern = r'\b' + re.escape(objective_id.lower()) + r'\b'
    matches = list(re.finditer(pattern, text_lower))
    
    if not matches:
        return result
    
    all_occurrences = []
    for m in matches:
        idx = m.start()
        line_number = text[:idx].count('\n') + 1
        page = get_page_at_position(text, idx)
        line_content = doc_lines[line_number - 1] if line_number <= len(doc_lines) else ""
        is_heading = is_heading_line(line_content, objective_id)
        is_in_controls = line_number >= controls_section_start
        all_occurrences.append({
            "idx": idx, "line_number": line_number, "page": page,
            "is_heading": is_heading, "is_in_controls": is_in_controls,
            "line_content": line_content.strip()[:80]
        })
    
    all_lines = sorted(set(o["line_number"] for o in all_occurrences))
    all_pages = sorted(set(o["page"] for o in all_occurrences if o["page"] is not None))
    result["all_line_refs"] = all_lines
    result["all_page_refs"] = all_pages
    
    best = None
    for priority_filter in [
        lambda o: o["is_heading"] and o["is_in_controls"],
        lambda o: o["is_in_controls"],
        lambda o: o["is_heading"],
        lambda o: True,
    ]:
        candidates = [o for o in all_occurrences if priority_filter(o)]
        if candidates:
            best = candidates[0]
            break
    
    if best:
        result["line_ref"] = best["line_number"]
        result["page_refs"] = [best["page"]] if best["page"] else None
    
    return result, all_occurrences

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # Get extracted text
    cur.execute("SELECT extracted_text FROM scan WHERE id=10")
    text = cur.fetchone()[0]
    
    # Get controls section start from structural objectives
    cur.execute("""
        SELECT MIN(line_ref) FROM control_objectives 
        WHERE scan_id=10 AND extraction_method != 'gap_search' AND extraction_method != 'manual'
          AND line_ref IS NOT NULL
    """)
    controls_section_start = cur.fetchone()[0] or 1500
    
    # Get gap-search objectives
    cur.execute("""
        SELECT objective_id, line_ref, page_refs::text, all_line_refs::text, all_page_refs::text
        FROM control_objectives 
        WHERE scan_id=10 AND extraction_method='gap_search'
        ORDER BY objective_id
    """)
    gap_objectives = cur.fetchall()
    
    print(f"Controls section starts at line: {controls_section_start}")
    print(f"{'='*80}")
    
    expected_fixes = {
        "CC6.2": 3526,
        "CC6.3": 3598,
        "CC7.1": 4237,
    }
    
    all_passed = True
    for obj_id, current_line_ref, current_page_refs, current_all_lines, current_all_pages in gap_objectives:
        result, occurrences = find_line_and_page_refs(text, obj_id, controls_section_start)
        new_line_ref = result["line_ref"]
        
        status = "OK"
        if obj_id in expected_fixes:
            if new_line_ref == expected_fixes[obj_id]:
                status = "FIXED ✓"
            else:
                status = f"WRONG (expected {expected_fixes[obj_id]})"
                all_passed = False
        elif new_line_ref != current_line_ref:
            status = "CHANGED"
        
        print(f"\n{obj_id}:")
        print(f"  Current line_ref: {current_line_ref}")
        print(f"  New line_ref:     {new_line_ref} [{status}]")
        print(f"  New page_refs:    {result['page_refs']}")
        print(f"  All line refs:    {result['all_line_refs']}")
        print(f"  All page refs:    {result['all_page_refs']}")
        
        if occurrences:
            print(f"  Occurrences ({len(occurrences)}):")
            for occ in occurrences:
                print(f"    Line {occ['line_number']:5d} | page={occ['page']:3d} | heading={occ['is_heading']!s:5s} | controls={occ['is_in_controls']!s:5s} | {occ['line_content']}")
    
    print(f"\n{'='*80}")
    if all_passed:
        print("ALL CRITICAL FIXES VERIFIED ✓")
    else:
        print("SOME FIXES FAILED ✗")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
