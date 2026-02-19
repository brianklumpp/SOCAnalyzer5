"""
Test script to validate objective extraction boundary enforcement and control filtering.

This script tests:
1. Section boundary enforcement (Control_Descriptions only)
2. Control vs Objective classification filter
3. Post-extraction validation
"""
import sys
import json
sys.path.insert(0, 'backend')

from sqlalchemy import create_engine, text as sql_text
from sqlalchemy.orm import sessionmaker

# Database connection
engine = create_engine('postgresql+psycopg2://soc2_analyzer:puntitforthewin@localhost:5432/soc2analyzer')
Session = sessionmaker(bind=engine)
db = Session()

print("=" * 80)
print("OBJECTIVE EXTRACTION VALIDATION TESTS")
print("=" * 80)

# Test 1: Check for objectives outside Control_Descriptions section
print("\n\u2705 TEST 1: Boundary Violations Check")
print("-" * 80)

# For Adobe scan (ID 2), Control_Descriptions section is typically at different lines
# We'll check if any objectives exist outside expected boundaries
query = """
SELECT 
    scan_id,
    COUNT(*) as total_objectives,
    MIN(line_ref) as min_line,
    MAX(line_ref) as max_line,
    COUNT(CASE WHEN line_ref IS NULL THEN 1 END) as no_line_ref
FROM control_objectives
WHERE scan_id = 2
GROUP BY scan_id
"""

result = db.execute(sql_text(query)).fetchone()
if result:
    print(f"Scan ID: {result[0]}")
    print(f"Total objectives: {result[1]}")
    print(f"Line range: {result[2]} to {result[3]}")
    print(f"Objectives without line_ref: {result[4]}")
    
    # Expected Control_Descriptions boundaries vary by scan
    # This will show if we have objectives outside typical ranges
    if result[2] and result[2] < 1000:
        print(f"\u26a0  WARNING: Minimum line {result[2]} seems too early (may be outside Control_Descriptions)")
else:
    print("No objectives found for scan_id=2")

# Test 2: Check for control-like text patterns in extracted objectives
print("\n\u2705 TEST 2: Control Misclassification Detection")
print("-" * 80)

# Look for objectives with control-specific keywords
control_patterns = [
    ("action verbs", "'review%' OR objective_text ILIKE '%verify%' OR objective_text ILIKE '%test%'"),
    ("frequencies", "'quarterly%' OR objective_text ILIKE '%annually%' OR objective_text ILIKE '%daily%'"),
    ("procedures", "'process includes%' OR objective_text ILIKE '%procedure for%' OR objective_text ILIKE '%steps to%'")
]

for pattern_name, sql_pattern in control_patterns:
    query = f"""
    SELECT COUNT(*) as count
    FROM control_objectives
    WHERE scan_id = 2
      AND (objective_text ILIKE {sql_pattern})
    """
    
    result = db.execute(sql_text(query)).fetchone()
    count = result[0] if result else 0
    
    if count > 0:
        print(f"\u26a0  Found {count} objectives with {pattern_name} (potential controls)")
        
        # Show samples
        sample_query = f"""
        SELECT objective_id, LEFT(objective_text, 100) as text_preview
        FROM control_objectives
        WHERE scan_id = 2
          AND (objective_text ILIKE {sql_pattern})
        LIMIT 3
        """
        samples = db.execute(sql_text(sample_query)).fetchall()
        for sample in samples:
            print(f"    - [{sample[0]}] {sample[1]}...")
    else:
        print(f"\u2713 No objectives with {pattern_name} found (good!)")

# Test 3: Check for objective IDs matching control IDs
print("\n\u2705 TEST 3: Objective ID vs Control ID Overlap")
print("-" * 80)

query = """
SELECT 
    co.objective_id,
    c.control_id,
    LEFT(co.objective_text, 80) as obj_text,
    LEFT(c.control_description, 80) as ctrl_desc
FROM control_objectives co
INNER JOIN control c ON co.scan_id = c.scan_id
WHERE co.scan_id = 2
  AND UPPER(TRIM(co.objective_id)) = UPPER(TRIM(c.control_id))
LIMIT 10
"""

overlaps = db.execute(sql_text(query)).fetchall()
if overlaps:
    print(f"\u26a0  Found {len(overlaps)} objectives with IDs matching control IDs:")
    for overlap in overlaps:
        print(f"    - ID: {overlap[0]} / {overlap[1]}")
        print(f"      Objective: {overlap[2]}...")
        print(f"      Control:   {overlap[3]}...")
else:
    print("\u2713 No objective/control ID overlaps found (good!)")

# Test 4: Distribution check
print("\n\u2705 TEST 4: Objective Distribution Analysis")
print("-" * 80)

query = """
SELECT 
    extraction_method,
    COUNT(*) as count,
    AVG(final_confidence) as avg_confidence,
    COUNT(CASE WHEN objective_id IS NOT NULL THEN 1 END) as with_id,
    COUNT(CASE WHEN objective_id IS NULL THEN 1 END) as without_id
FROM control_objectives
WHERE scan_id = 2
GROUP BY extraction_method
ORDER BY count DESC
"""

results = db.execute(sql_text(query)).fetchall()
print(f"{'Method':<20} {'Count':>8} {'Avg Conf':>10} {'With ID':>10} {'No ID':>10}")
print("-" * 80)
for row in results:
    print(f"{row[0]:<20} {row[1]:>8} {row[2]:>10.3f} {row[3]:>10} {row[4]:>10}")

# Test 5: Sample high-confidence objectives
print("\n\u2705 TEST 5: Sample High-Confidence Objectives")
print("-" * 80)

query = """
SELECT 
    objective_id,
    LEFT(objective_text, 120) as text_preview,
    final_confidence,
    line_ref
FROM control_objectives
WHERE scan_id = 2
  AND final_confidence > 0.7
ORDER BY final_confidence DESC
LIMIT 5
"""

samples = db.execute(sql_text(query)).fetchall()
print(f"Top {len(samples)} highest confidence objectives:\n")
for i, sample in enumerate(samples, 1):
    print(f"{i}. [{sample[0] or 'No ID'}] (conf={sample[2]:.3f}, line={sample[3] or 'N/A'})")
    print(f"   {sample[1]}...\n")

# Summary
print("=" * 80)
print("VALIDATION COMPLETE")
print("=" * 80)
print("\nRecommendations:")
print("1. If boundary violations found: Check section_results.json boundaries")
print("2. If control patterns found: Review and enhance control filter logic")
print("3. If ID overlaps found: Ensure controls and objectives are properly distinguished")
print("\nNext step: Run fresh extraction with new validation logic to test enforcement")

db.close()
