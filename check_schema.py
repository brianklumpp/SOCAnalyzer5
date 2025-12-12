"""
Schema Validation - Compare models.py with init migration
Finds missing columns that need migrations
"""

# Model columns from models.py
model_columns = {
    'scan': [
        'id', 'company_id', 'company', 'product', 'scan_date', 'report_date',
        'coverage_start', 'coverage_end', 'pdf_file', 'pdf_filename',
        'extracted_text', 'result_json', 'gpt_cost', 'gpt_model',
        'estimated_time_seconds', 'auditor', 'gpt_usage_details',
        'executive_summary', 'executive_summary_stale', 'is_sox_vendor',
        'report_type', 'as_of_date', 'progress_status', 'elapsed_seconds',
        'toc_page_offset', 'detected_standards', 'active_frameworks'
    ],
    'company': [
        'id', 'name', 'parent_company', 'confidence', 'scan_id',
        'company_domain', 'logo_url'
    ],
    'control': [
        'id', 'control_id', 'control_desc', 'control_test',
        'control_test_results', 'has_deviation', 'deviation_desc',
        'control_page_refs', 'control_line_ref', 'control_seq',
        'control_tsc_id', 'control_coso_id', 'control_tsc_similarity',
        'control_coso_similarity', 'control_tsc_confidence_pct',
        'control_coso_confidence_pct', 'control_closest_framework',
        'control_tsc_section', 'control_coso_section', 'control_soc_domain',
        'financial_assertions', 'framework_category', 'control_tsc_mappings',
        'control_coso_mappings', 'framework_mappings', 'primary_framework',
        'primary_criterion_id', 'primary_confidence', 'control_status',
        'merged_to_control_id', 'control_gpt_opinion', 'control_gpt_reasoning',
        'control_confidence', 'confidence_calc', 'scan_id', 'annotation',
        'analyst_notes', 'verification_status', 'verification_metadata',
        'pattern_confidence', 'final_confidence', 'deviation_summary',
        'merge_history', 'is_duplicate_instance', 'duplicate_group_id',
        'instance_differentiator'
    ],
    'cuec': [
        'id', 'cuec_seq', 'cuec_tsc_id', 'cuec_description', 'cuec_line_ref',
        'cuec_page_refs', 'cuec_confidence', 'cuec_gpt_opinion',
        'cuec_distance_from_cuec_keywords', 'cuec_gpt_reasoning',
        'cuec_framework_alignment', 'cuec_framework_alignment_id',
        'cuec_justification', 'cuec_coso_id', 'cuec_tsc_similarity',
        'cuec_coso_similarity', 'cuec_tsc_confidence_pct',
        'cuec_coso_confidence_pct', 'cuec_closest_framework',
        'cuec_confidence_justification', 'cuec_tsc_mappings',
        'cuec_coso_mappings', 'framework_mappings', 'primary_framework',
        'primary_criterion_id', 'primary_confidence', 'scan_id',
        'annotation', 'analyst_notes', 'control_strength'
    ],
    'subservice_org': [
        'id', 'name', 'confidence', 'scan_id', 'third_party_description',
        'third_party_page_ref', 'third_party_confidence',
        'distance_from_so_keywords', 'likely_so', 'common_so',
        'source_context', 'confidence_justification', 'third_party_controls',
        'annotation', 'analyst_notes'
    ]
}

# Init migration columns from 449ae1762a28_init_schema.py
init_migration_columns = {
    'scan': [
        'id', 'company_id', 'product', 'scan_date', 'report_date',
        'coverage_start', 'coverage_end', 'pdf_file', 'pdf_filename',
        'extracted_text', 'result_json', 'gpt_cost', 'gpt_model',
        'estimated_time_seconds', 'auditor', 'gpt_usage_details',
        'executive_summary', 'executive_summary_stale'
    ],
    'company': [
        'id', 'name', 'parent_company', 'confidence', 'scan_id'
    ],
    'control': [
        'id', 'control_id', 'control_desc', 'control_test',
        'control_test_results', 'control_page_ref', 'control_line_ref',
        'control_seq', 'control_tsc_id', 'control_coso_id',
        'control_tsc_similarity', 'control_coso_similarity',
        'control_tsc_confidence_pct', 'control_coso_confidence_pct',
        'control_closest_framework', 'control_tsc_section',
        'control_coso_section', 'control_soc_domain', 'control_status',
        'merged_to_control_id', 'control_gpt_opinion',
        'control_gpt_reasoning', 'control_confidence', 'confidence_calc',
        'scan_id', 'annotation'
    ],
    'cuec': [
        'id', 'cuec_seq', 'cuec_tsc_id', 'cuec_description',
        'cuec_line_ref', 'cuec_confidence', 'cuec_gpt_opinion',
        'cuec_distance_from_cuec_keywords', 'cuec_gpt_reasoning',
        'cuec_framework_alignment', 'cuec_framework_alignment_id',
        'cuec_justification', 'cuec_coso_id', 'cuec_tsc_similarity',
        'cuec_coso_similarity', 'cuec_tsc_confidence_pct',
        'cuec_coso_confidence_pct', 'cuec_closest_framework',
        'cuec_confidence_justification', 'scan_id', 'annotation',
        'control_strength'
    ],
    'subservice_org': [
        'id', 'name', 'confidence', 'scan_id',
        'third_party_description', 'third_party_page_ref',
        'third_party_confidence', 'distance_from_so_keywords',
        'likely_so', 'common_so', 'source_context',
        'confidence_justification', 'third_party_controls', 'annotation'
    ]
}

print("=" * 80)
print("SCHEMA VALIDATION REPORT")
print("=" * 80)
print()

all_missing = []

for table in model_columns.keys():
    model_cols = set(model_columns[table])
    init_cols = set(init_migration_columns[table])
    
    missing = model_cols - init_cols
    
    if missing:
        print(f"TABLE: {table}")
        print(f"  Missing columns ({len(missing)}):")
        for col in sorted(missing):
            print(f"    - {col}")
            all_missing.append((table, col))
        print()

print("=" * 80)
print(f"TOTAL MISSING COLUMNS: {len(all_missing)}")
print("=" * 80)

if all_missing:
    print("\nThese columns exist in models.py but are NOT in the init migration.")
    print("They should have been added via subsequent migrations.")
    print("\nYou need to verify that migrations exist for ALL of these columns.")
