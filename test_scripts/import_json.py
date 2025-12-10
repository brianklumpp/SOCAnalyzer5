#!/usr/bin/env python3
"""
Import combined_result.json into the database
"""
import sys
sys.path.insert(0, '/app')

from backend.app.explicit_sql_insert import insert_extracted_data

if __name__ == "__main__":
    json_path = "/app/data/json/combined_result.json"
    print(f"Importing data from {json_path}...")
    summary = insert_extracted_data(json_path)
    print(f"\nImport Summary:")
    print(summary)
