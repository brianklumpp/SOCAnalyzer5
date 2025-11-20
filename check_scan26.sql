-- Check scan 26 details
SELECT 
  id,
  pdf_filename,
  product,
  company_id,
  scan_date,
  (SELECT COUNT(*) FROM control WHERE scan_id = 26) as control_count,
  (SELECT COUNT(*) FROM control WHERE scan_id = 26 AND control_confidence IS NOT NULL) as controls_with_confidence,
  (SELECT COUNT(*) FROM control WHERE scan_id = 26 AND control_page_refs IS NOT NULL) as controls_with_page_refs,
  (SELECT COUNT(*) FROM control WHERE scan_id = 26 AND merged_to_control_id IS NOT NULL) as merged_controls
FROM scan 
WHERE id = 26;

\echo '\n--- Control confidence values ---'
SELECT 
  control_id,
  control_confidence,
  control_page_refs,
  merged_to_control_id,
  CASE 
    WHEN verification_metadata IS NOT NULL THEN 'Yes'
    ELSE 'No'
  END as has_metadata
FROM control 
WHERE scan_id = 26 
LIMIT 10;

\echo '\n--- Find duplicate control IDs ---'
SELECT 
  control_id, 
  COUNT(*) as count,
  STRING_AGG(id::text, ', ') as db_ids
FROM control 
WHERE scan_id = 26 
  AND control_id IS NOT NULL
GROUP BY control_id 
HAVING COUNT(*) > 1 
ORDER BY count DESC;

\echo '\n--- Check merged status of duplicates ---'
SELECT 
  c.control_id,
  c.id as db_id,
  c.merged_to_control_id,
  c.control_confidence,
  SUBSTRING(c.control_desc, 1, 50) as desc_preview
FROM control c
WHERE c.scan_id = 26
  AND c.control_id IN (
    SELECT control_id FROM control WHERE scan_id = 26 GROUP BY control_id HAVING COUNT(*) > 1
  )
ORDER BY c.control_id, c.id;
