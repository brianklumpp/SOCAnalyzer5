#!/usr/bin/env python3
"""
Analysis Completion Utility

Manually completes the analysis pipeline when extractors finish but 
the combining and database insertion steps don't execute properly.

This script:
1. Loads all extractor JSON files
2. Combines them into standardized format 
3. Writes combined_result.json
4. Inserts data into database
5. Updates scan status

Usage:
    python complete_analysis.py --scan-id SCAN_ID
    python complete_analysis.py --combined-only  # Just create combined_result.json
    python complete_analysis.py --db-only        # Just do database insert
"""

import argparse
import json
import sys
import os
import requests
from pathlib import Path
from datetime import datetime
import traceback

# Add the backend directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

def load_extractor_results():
    """Load all extractor results from JSON files"""
    print("🔍 Loading extractor results...")
    
    extractor_files = {
        'company': 'data/json/company_result.json',
        'auditor': 'data/json/auditor_result.json', 
        'controls': 'data/json/control_result.json',
        'cuecs': 'data/json/cuec_result.json',
        'subservice_orgs': 'data/json/subservice_orgs_result.json',
        'product': 'data/json/product_result.json',
        'report_date': 'data/json/report_date_result.json',
        'coverage_period': 'data/json/coverage_period_result.json',
        'sections': 'data/json/section_results.json'
    }
    
    results = {}
    for key, file_path in extractor_files.items():
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                
                # Handle malformed JSON from append-mode writing (like controls)
                if key == 'controls' and content.startswith('[]'):
                    # Remove the initial empty array and parse individual objects
                    content = content[2:].strip()
                    if content.startswith(','):
                        content = content[1:].strip()
                    
                    if content:
                        # Add array brackets to make it valid JSON
                        content = '[' + content + ']'
                        data = json.loads(content)
                    else:
                        data = []
                else:
                    # Standard JSON format
                    data = json.loads(content)
                
                results[key] = data
                if isinstance(data, list):
                    print(f"   ✅ {key}: {len(data)} items")
                elif isinstance(data, dict):
                    print(f"   ✅ {key}: {list(data.keys())}")
                else:
                    print(f"   ✅ {key}: {type(data)}")
                    
            except Exception as e:
                print(f"   ❌ {key}: Error loading - {e}")
                results[key] = None
        else:
            print(f"   ⚠️  {key}: File not found")
            results[key] = None
    
    return results

def create_combined_result(extractor_results, pdf_filename=None):
    """Create standardized combined result matching analyze.py format"""
    print("🔄 Creating combined result...")
    
    # Use the same flattening logic as analyze.py
    standardized_results = {}
    
    # Map extractor results to standardized format
    if extractor_results.get('controls'):
        controls = extractor_results['controls']
        if isinstance(controls, dict) and 'controls' in controls:
            controls = controls['controls']
        standardized_results['controls'] = controls
        print(f"   📊 Controls: {len(controls)} items")
    
    if extractor_results.get('cuecs'):
        cuecs = extractor_results['cuecs'] 
        if isinstance(cuecs, dict) and 'cuecs' in cuecs:
            cuecs = cuecs['cuecs']
        standardized_results['cuecs'] = cuecs
        print(f"   📊 CUECs: {len(cuecs) if cuecs else 0} items")
    
    if extractor_results.get('subservice_orgs'):
        suborgs = extractor_results['subservice_orgs']
        if isinstance(suborgs, dict) and 'third_parties' in suborgs:
            suborgs = suborgs['third_parties']
        elif isinstance(suborgs, dict) and 'subservice_orgs' in suborgs:
            suborgs = suborgs['subservice_orgs']
        standardized_results['subservice_orgs'] = suborgs
        print(f"   📊 Subservice Orgs: {len(suborgs) if suborgs else 0} items")
    
    # Handle company extraction (can be missing)
    if extractor_results.get('company'):
        standardized_results['company'] = extractor_results['company']
        print(f"   📊 Company: included")
    
    # Simple mappings for other extractors
    simple_mappings = ['auditor', 'product', 'report_date', 'coverage_period', 'sections']
    for key in simple_mappings:
        if extractor_results.get(key):
            data = extractor_results[key]
            if isinstance(data, dict) and key in data:
                standardized_results[key] = data[key]
            else:
                standardized_results[key] = data
            print(f"   📊 {key}: included")
    
    # Add extracted text if available
    try:
        with open('data/output/output.txt', 'r', encoding='utf-8') as f:
            extracted_text = f.read()
        standardized_results["extracted_text"] = extracted_text
        print(f"   📊 Extracted text: {len(extracted_text)} characters")
    except Exception as e:
        print(f"   ⚠️  Extracted text: Not available - {e}")
        standardized_results["extracted_text"] = None
    
    # Add metadata
    if pdf_filename:
        standardized_results["pdf_filename"] = pdf_filename
        print(f"   📊 PDF filename: {pdf_filename}")
    
    # Add dummy GPT tracking (since we're post-processing)
    standardized_results.update({
        "gpt_cost": 0.0,
        "gpt_model": "post-processing",
        "gpt_usage_details": [],
        "total_calls": 0,
        "total_tokens": 0
    })
    
    return standardized_results

def write_combined_result(combined_result):
    """Write combined result to JSON file"""
    print("💾 Writing combined_result.json...")
    
    try:
        output_path = 'data/json/combined_result.json'
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(combined_result, f, indent=2, ensure_ascii=False)
        
        print(f"   ✅ Written to {output_path}")
        return True
    except Exception as e:
        print(f"   ❌ Error writing combined result: {e}")
        return False

def insert_to_database(combined_result_path=None):
    """Insert combined result into database"""
    if not combined_result_path:
        combined_result_path = 'data/json/combined_result.json'
    
    print("🗄️  Inserting into database...")
    
    try:
        # Import the insertion function
        from backend.app.explicit_sql_insert import insert_extracted_data
        
        summary = insert_extracted_data(combined_result_path)
        
        print("   ✅ Database insertion complete!")
        print("   📊 Summary:")
        for key, value in summary.items():
            if key != "errors":
                print(f"      {key}: {value}")
        
        if summary.get("errors"):
            print("   ⚠️  Errors:")
            for error in summary["errors"]:
                print(f"      {error}")
        
        return True, summary
    except Exception as e:
        print(f"   ❌ Database insertion failed: {e}")
        print(f"   📋 Traceback: {traceback.format_exc()}")
        return False, None

def update_scan_status(scan_id, mark_complete=True):
    """Update scan status to mark control extraction as complete"""
    print(f"🔄 Updating scan status for {scan_id}...")
    
    try:
        # Get current status
        response = requests.get(f"http://127.0.0.1:8000/analyze/status/{scan_id}", timeout=10)
        if response.status_code != 200:
            print(f"   ❌ Could not get current status: {response.status_code}")
            return False
        
        status = response.json()
        checklist = status.get('checklist', [])
        
        # Update control extraction status
        for item in checklist:
            if item['name'] == 'control_extraction':
                if mark_complete:
                    item['status'] = 'done'
                    print("   ✅ Marked control_extraction as done")
                break
        
        # Note: In a full implementation, you would update Redis here
        # For now, we just provide guidance
        print("   💡 Manual status update required:")
        print("      - Control extraction should be marked as 'done'")
        print("      - Pipeline should continue to completion")
        
        return True
    except Exception as e:
        print(f"   ❌ Error updating status: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Complete SOC Analyzer analysis pipeline")
    parser.add_argument('--scan-id', type=str, help='Scan ID to update status for')
    parser.add_argument('--combined-only', action='store_true', help='Only create combined_result.json')
    parser.add_argument('--db-only', action='store_true', help='Only insert to database')
    parser.add_argument('--pdf-filename', type=str, help='PDF filename to include in results')
    
    args = parser.parse_args()
    
    if args.db_only:
        # Just do database insertion
        success, summary = insert_to_database()
        if success:
            print("\n🎉 Database insertion completed successfully!")
        else:
            print("\n❌ Database insertion failed!")
            sys.exit(1)
        return
    
    # Load all extractor results
    extractor_results = load_extractor_results()
    
    # Create combined result
    combined_result = create_combined_result(extractor_results, args.pdf_filename)
    
    # Write combined result
    if not write_combined_result(combined_result):
        print("\n❌ Failed to write combined result!")
        sys.exit(1)
    
    if args.combined_only:
        print("\n✅ Combined result created successfully!")
        return
    
    # Insert to database
    success, summary = insert_to_database()
    if not success:
        print("\n❌ Database insertion failed!")
        sys.exit(1)
    
    # Update scan status if provided
    if args.scan_id:
        update_scan_status(args.scan_id, mark_complete=True)
    
    print("\n🎉 Analysis completion successful!")
    print(f"📊 Total controls: {len(combined_result.get('controls', []))}")
    print(f"📊 Total CUECs: {len(combined_result.get('cuecs', []))}")
    print(f"📊 Total subservice orgs: {len(combined_result.get('subservice_orgs', []))}")

if __name__ == "__main__":
    main() 