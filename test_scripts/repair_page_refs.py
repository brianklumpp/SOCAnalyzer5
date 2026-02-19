#!/usr/bin/env python3
"""
Repair page_refs for existing scans by recomputing from stored line_refs.

Usage:
    docker exec socanalyzer-backend python -m test_scripts.repair_page_refs [--scan-id N] [--dry-run]

Or run directly (connects to Docker Postgres via localhost:5433):
    python test_scripts/repair_page_refs.py [--scan-id N] [--dry-run]
"""
import argparse
import json
import os
import sys
import glob

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_page_for_line(lines, line_num):
    """Replicate pdf_handler.get_page_for_line() locally."""
    page = 1
    target_index = line_num - 1
    for i in range(min(target_index, len(lines))):
        line = lines[i].strip() if isinstance(lines[i], str) else ''
        if line.startswith('=== PAGE '):
            try:
                page = int(line.split()[2])
            except Exception:
                continue
    return page


def find_output_txt(scan_id):
    """Find the output.txt file for a given scan."""
    # Check job directories
    jobs_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'jobs')
    for root, dirs, files in os.walk(jobs_root):
        if 'output.txt' in files:
            path = os.path.join(root, 'output.txt')
            return path
    # Check Docker paths
    docker_paths = [
        f'/app/data/jobs/{scan_id}',
        '/app/data/jobs/1',
    ]
    for base in docker_paths:
        if os.path.isdir(base):
            for root, dirs, files in os.walk(base):
                if 'output.txt' in files:
                    return os.path.join(root, 'output.txt')
    return None


def repair_scan(conn, scan_id, text_lines, dry_run=False):
    """Repair page refs for a single scan.
    
    Conservative approach: only ADD pages (from line_ref/all_line_refs), never remove
    existing pages that may have come from control merges during extraction.
    """
    cur = conn.cursor()
    changes = {'controls': 0, 'objectives': 0, 'cuecs': 0, 'toc_offset': False}

    # Fix toc_page_offset
    cur.execute("SELECT toc_page_offset FROM scan WHERE id = %s", (scan_id,))
    row = cur.fetchone()
    if row and row[0] is None:
        print(f"  [SCAN] toc_page_offset is NULL, setting to 0")
        if not dry_run:
            cur.execute("UPDATE scan SET toc_page_offset = 0 WHERE id = %s", (scan_id,))
        changes['toc_offset'] = True

    # Repair control page_refs (additive only — preserve existing pages from merges)
    cur.execute("""
        SELECT id, control_id, control_page_refs, control_line_ref, all_line_refs
        FROM control WHERE scan_id = %s
    """, (scan_id,))
    controls = cur.fetchall()
    
    for ctrl_id, ctrl_name, old_page_refs, line_ref, all_line_refs_json in controls:
        existing_pages = set(old_page_refs) if isinstance(old_page_refs, list) else set()
        computed_pages = set()
        
        # Get page from primary line_ref
        if line_ref and isinstance(line_ref, int) and line_ref > 0:
            p = get_page_for_line(text_lines, line_ref)
            if p:
                computed_pages.add(p)
        
        # Get pages from all_line_refs
        all_lr = all_line_refs_json if isinstance(all_line_refs_json, list) else []
        for lr in all_lr:
            if isinstance(lr, int) and lr > 0:
                p = get_page_for_line(text_lines, lr)
                if p:
                    computed_pages.add(p)
        
        # Union: keep existing + add any newly computed
        merged_pages = sorted(existing_pages | computed_pages)
        old_sorted = sorted(existing_pages)
        
        if merged_pages != old_sorted and merged_pages:
            added = sorted(computed_pages - existing_pages)
            print(f"  [CTRL] {ctrl_name}: page_refs {json.dumps(old_sorted)} -> {json.dumps(merged_pages)} (+{added})")
            if not dry_run:
                cur.execute(
                    "UPDATE control SET control_page_refs = %s WHERE id = %s",
                    (json.dumps(merged_pages), ctrl_id)
                )
            changes['controls'] += 1

    # Repair objective page_refs and all_page_refs (additive only)
    cur.execute("""
        SELECT id, objective_id, page_refs, all_page_refs, line_ref, all_line_refs
        FROM control_objectives WHERE scan_id = %s
    """, (scan_id,))
    objectives = cur.fetchall()
    
    for obj_id, obj_name, old_page_refs, old_all_page_refs, line_ref, all_line_refs_json in objectives:
        existing_pages = set(old_page_refs) if isinstance(old_page_refs, list) else set()
        existing_all = set(old_all_page_refs) if isinstance(old_all_page_refs, list) else set()
        computed_pages = set()
        
        if line_ref and isinstance(line_ref, int) and line_ref > 0:
            p = get_page_for_line(text_lines, line_ref)
            if p:
                computed_pages.add(p)
        
        all_lr = all_line_refs_json if isinstance(all_line_refs_json, list) else []
        for lr in all_lr:
            if isinstance(lr, int) and lr > 0:
                p = get_page_for_line(text_lines, lr)
                if p:
                    computed_pages.add(p)
        
        merged_pages = sorted(existing_pages | computed_pages)
        merged_all = sorted(existing_all | computed_pages)
        old_sorted = sorted(existing_pages)
        
        if merged_pages != old_sorted and merged_pages:
            added = sorted(computed_pages - existing_pages)
            print(f"  [OBJ]  {obj_name}: page_refs {json.dumps(old_sorted)} -> {json.dumps(merged_pages)} (+{added})")
            if not dry_run:
                cur.execute(
                    "UPDATE control_objectives SET page_refs = %s, all_page_refs = %s WHERE id = %s",
                    (json.dumps(merged_pages), json.dumps(merged_all), obj_id)
                )
            changes['objectives'] += 1

    # Repair CUEC page_refs (additive only)
    cur.execute("""
        SELECT id, cuec_seq, cuec_page_refs, cuec_line_ref
        FROM cuec WHERE scan_id = %s
    """, (scan_id,))
    cuecs = cur.fetchall()
    
    for cuec_db_id, cuec_seq, old_page_refs, line_ref in cuecs:
        existing_pages = set(old_page_refs) if isinstance(old_page_refs, list) else set()
        
        if line_ref and isinstance(line_ref, int) and line_ref > 0:
            p = get_page_for_line(text_lines, line_ref)
            if p:
                merged = sorted(existing_pages | {p})
                old_sorted = sorted(existing_pages)
                if merged != old_sorted:
                    print(f"  [CUEC] seq={cuec_seq}: page_refs {json.dumps(old_sorted)} -> {json.dumps(merged)}")
                    if not dry_run:
                        cur.execute(
                            "UPDATE cuec SET cuec_page_refs = %s WHERE id = %s",
                            (json.dumps(merged), cuec_db_id)
                        )
                    changes['cuecs'] += 1

    if not dry_run:
        conn.commit()
    
    return changes


def main():
    parser = argparse.ArgumentParser(description='Repair page refs for existing scans')
    parser.add_argument('--scan-id', type=int, help='Specific scan ID to repair (default: all)')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without applying')
    args = parser.parse_args()

    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not available. Run inside Docker or install psycopg2-binary.")
        sys.exit(1)

    # Try Docker-internal connection first, then localhost
    db_params = [
        {'host': 'postgres', 'port': 5432, 'dbname': 'soc2analyzer', 'user': 'soc2_analyzer', 'password': 'puntitforthewin'},
        {'host': 'localhost', 'port': 5433, 'dbname': 'soc2analyzer', 'user': 'soc2_analyzer', 'password': 'puntitforthewin'},
    ]
    
    conn = None
    for params in db_params:
        try:
            conn = psycopg2.connect(**params)
            print(f"Connected to {params['host']}:{params['port']}")
            break
        except Exception:
            continue
    
    if not conn:
        print("ERROR: Could not connect to database")
        sys.exit(1)

    cur = conn.cursor()
    
    if args.scan_id:
        cur.execute("SELECT id, company, pdf_filename FROM scan WHERE id = %s", (args.scan_id,))
    else:
        cur.execute("SELECT id, company, pdf_filename FROM scan ORDER BY id")
    
    scans = cur.fetchall()
    
    if not scans:
        print("No scans found.")
        return

    mode = "DRY RUN" if args.dry_run else "REPAIR"
    print(f"\n=== Page Reference {mode} ===\n")

    for scan_id, company, pdf_filename in scans:
        print(f"Scan {scan_id}: {company} ({pdf_filename})")
        
        # Find output.txt
        output_path = find_output_txt(scan_id)
        if not output_path:
            print(f"  WARNING: output.txt not found, skipping")
            continue
        
        print(f"  Using: {output_path}")
        with open(output_path, 'r', encoding='utf-8') as f:
            text_lines = f.readlines()
        print(f"  Text lines: {len(text_lines)}")
        
        changes = repair_scan(conn, scan_id, text_lines, dry_run=args.dry_run)
        
        total = changes['controls'] + changes['objectives'] + changes['cuecs'] + (1 if changes['toc_offset'] else 0)
        if total == 0:
            print(f"  No changes needed")
        else:
            print(f"  Summary: {changes['controls']} controls, {changes['objectives']} objectives, "
                  f"{changes['cuecs']} CUECs, toc_offset={'fixed' if changes['toc_offset'] else 'ok'}")
    
    conn.close()
    print(f"\n{'(dry run - no changes applied)' if args.dry_run else 'Done!'}")


if __name__ == '__main__':
    main()
