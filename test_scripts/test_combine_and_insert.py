import os
import json
import requests
from pathlib import Path

# Directory containing the result JSONs
json_dir = Path(__file__).resolve().parents[1] / "data" / "json"

# List of result files to combine
result_files = [
    "auditor_result.json",
    "scan_result.json",
    "company_result.json",
    "control_result.json",
    "coverage_period_result.json",
    "cuec_result.json",
    "subservice_orgs_result.json",
    "product_result.json",
    "report_date_result.json",
    "section_result.json"
]

combined = {}

# Read and merge each result file if it exists
for fname in result_files:
    fpath = json_dir / fname
    if fpath.exists():
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Special handling for control_result.json, cuec_result.json, and subservice_orgs_result.json to support both formats
            if fname == "control_result.json":
                # If the file is a list, wrap in {"controls": ...}
                if isinstance(data, list):
                    combined["controls"] = data
                elif isinstance(data, dict):
                    # If it has "controls" or "control_extraction", merge as-is
                    if "controls" in data or "control_extraction" in data:
                        combined.update(data)
                    else:
                        combined["controls"] = data
            elif fname == "cuec_result.json":
                # If the file is a list, wrap in {"cuecs": ...}
                if isinstance(data, list):
                    combined["cuecs"] = data
                elif isinstance(data, dict):
                    if "cuecs" in data or "cuec_extraction" in data:
                        combined.update(data)
                    else:
                        combined["cuecs"] = data
            elif fname == "subservice_orgs_result.json":
                # If the file is a list, wrap in {"subservice_orgs": ...}
                if isinstance(data, list):
                    combined["subservice_orgs"] = data
                elif isinstance(data, dict):
                    # If it has "third_parties" (the common format), flatten to subservice_orgs
                    if "third_parties" in data and isinstance(data["third_parties"], list):
                        combined["subservice_orgs"] = data["third_parties"]
                    elif "subservice_orgs" in data or "subservice_orgs_extraction" in data:
                        combined.update(data)
                    else:
                        combined["subservice_orgs"] = data
            else:
                # Merge keys (assumes each file is a dict with unique top-level keys)
                combined.update(data)


# Debug printout of keys and counts for controls, cuecs, subservice_orgs
print("Combined JSON keys:", list(combined.keys()))
print("controls count:", len(combined.get("controls", [])))
print("cuecs count:", len(combined.get("cuecs", [])))
print("subservice_orgs count:", len(combined.get("subservice_orgs", [])))



# --- PATCH: Normalize all relevant entities for backend compatibility ---
# Company normalization
if "company" in combined:
    if isinstance(combined["company"], str):
        combined["company"] = {"name": combined["company"]}
    for key in ["parent_company", "confidence"]:
        if key in combined:
            combined["company"][key] = combined[key]
            del combined[key]

# Product normalization
if "product" in combined:
    if isinstance(combined["product"], str):
        combined["product"] = {"name": combined["product"]}
    for key in ["confidence"]:
        if key in combined:
            if isinstance(combined["product"], dict):
                combined["product"][key] = combined[key]
                del combined[key]

# Auditor normalization
if "auditor" in combined:
    if isinstance(combined["auditor"], str):
        combined["auditor"] = {"name": combined["auditor"]}
    for key in ["confidence"]:
        if key in combined:
            if isinstance(combined["auditor"], dict):
                combined["auditor"][key] = combined[key]
                del combined[key]

# Subservice orgs/third_parties normalization
if "subservice_orgs" in combined and isinstance(combined["subservice_orgs"], list):
    for idx, org in enumerate(combined["subservice_orgs"]):
        if isinstance(org, str):
            combined["subservice_orgs"][idx] = {"name": org}
        # Move any top-level fields that should be in each org dict
        for key in ["confidence"]:
            if key in combined and isinstance(combined["subservice_orgs"][idx], dict):
                combined["subservice_orgs"][idx][key] = combined[key]
    # Optionally remove the top-level field if it was meant for all
    for key in ["confidence"]:
        if key in combined:
            del combined[key]

# Write combined_result.json
combined_path = json_dir / "combined_result.json"
with open(combined_path, "w", encoding="utf-8") as f:
    json.dump(combined, f, indent=2)
print(f"Combined result written to {combined_path}")

# Trigger DB insert via FastAPI endpoint
API_URL = "http://localhost:8000/test/insert_combined_result"
try:
    resp = requests.post(API_URL)
    print(f"Status code: {resp.status_code}")
    print(f"Response: {resp.text}")
except Exception as e:
    print("Error during DB insert call:", e)
