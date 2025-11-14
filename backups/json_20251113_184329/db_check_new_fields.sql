-- Check new fields in Control table
SELECT id, control_id, control_test, control_test_results, control_page_ref, control_line_ref, control_gpt_opinion, control_gpt_reasoning FROM control ORDER BY id DESC LIMIT 5;

-- Check new fields in CUEC table
SELECT id, cuec_id, cuec_distance_from_cuec_keywords FROM cuec ORDER BY id DESC LIMIT 5;

-- Check new fields in SubserviceOrg table
SELECT id, name, confidence FROM subservice_org ORDER BY id DESC LIMIT 5;

-- Check new fields in Company table
SELECT id, name, parent_company, confidence FROM company ORDER BY id DESC LIMIT 5;

-- Check new fields in Scan table
SELECT id, product, gpt_cost, gpt_model, estimated_time_seconds FROM scan ORDER BY id DESC LIMIT 5;
