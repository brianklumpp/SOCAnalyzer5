
import sys
import os
from pathlib import Path
# Adjust path to import backend modules BEFORE importing analyze
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "app"))
import requests
from backend.app.analyze import analyze_pdf_file

# Set up API endpoint for DB insert (FastAPI test endpoint)
API_URL = "http://localhost:8000/test/insert_combined_result"

if __name__ == "__main__":
    # Path to your test PDF
    pdf_path = str(Path(__file__).resolve().parents[1] / "soc2_reports" / "Anaqua.pdf")
    print(f"Running full extraction pipeline on: {pdf_path}")
    results = analyze_pdf_file(pdf_path)
    print("Extraction and combine complete. Results keys:", list(results.keys()))
    print("combined_result.json written. Ready for DB insert.")

    # Trigger DB insert via FastAPI endpoint
    print("Triggering DB insert via /test/insert_combined_result ...")
    try:
        resp = requests.post(API_URL)
        print(f"Status code: {resp.status_code}")
        print(f"Response: {resp.text}")
    except Exception as e:
        print("Error during DB insert call:", e)
