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
            # Special handling for control_result.json, cuec_result.json, and subservice_orgs_result.json to support both formats and nested keys
            if fname == "control_result.json":
                # If the file is a list, wrap in {"controls": ...}
                if isinstance(data, list):
                    combined["controls"] = data
                elif isinstance(data, dict):
                    # Support nested key: control_extraction.controls
                    if "control_extraction" in data and "controls" in data["control_extraction"]:
                        combined["control_extraction"] = {"controls": data["control_extraction"]["controls"]}
                    elif "controls" in data:
                        combined["controls"] = data["controls"]
                    else:
                        combined.update(data)
            elif fname == "cuec_result.json":
                if isinstance(data, list):
                    combined["cuecs"] = data
                elif isinstance(data, dict):
                    # Support nested key: cuec_extraction.cuecs
                    if "cuec_extraction" in data and "cuecs" in data["cuec_extraction"]:
                        combined["cuec_extraction"] = {"cuecs": data["cuec_extraction"]["cuecs"]}
                    elif "cuecs" in data:
                        combined["cuecs"] = data["cuecs"]
                    else:
                        combined.update(data)
            elif fname == "subservice_orgs_result.json":
                if isinstance(data, list):
                    combined["subservice_orgs"] = data
                elif isinstance(data, dict):
                    # Support nested key: subservice_orgs_extraction.subservice_orgs
                    if "subservice_orgs_extraction" in data and "subservice_orgs" in data["subservice_orgs_extraction"]:
                        combined["subservice_orgs_extraction"] = {"subservice_orgs": data["subservice_orgs_extraction"]["subservice_orgs"]}
                    elif "third_parties" in data and isinstance(data["third_parties"], list):
                        combined["subservice_orgs"] = data["third_parties"]
                    elif "subservice_orgs" in data:
                        combined["subservice_orgs"] = data["subservice_orgs"]
                    else:
                        combined.update(data)
            else:
                # Merge keys (assumes each file is a dict with unique top-level keys)
                combined.update(data)



# --- PATCH: Mirror backend logic for nested and top-level keys ---
# Controls normalization: support both 'controls' and 'control_extraction'
if "control_extraction" in combined and not combined.get("controls"):
    # If control_extraction is a dict with 'controls' key, extract the list
    if isinstance(combined["control_extraction"], dict) and "controls" in combined["control_extraction"]:
        combined["controls"] = combined["control_extraction"]["controls"]
    else:
        combined["controls"] = combined["control_extraction"]
    del combined["control_extraction"]
elif "controls" in combined and not combined.get("control_extraction"):
    pass  # already in correct place
elif "controls" in combined and "control_extraction" in combined:
    # If both exist, merge if both are lists, or extract from dict if needed
    if isinstance(combined["control_extraction"], dict) and "controls" in combined["control_extraction"]:
        new_controls = combined["control_extraction"]["controls"]
    else:
        new_controls = combined["control_extraction"]
    if isinstance(combined["controls"], list) and isinstance(new_controls, list):
        combined["controls"] += [c for c in new_controls if c not in combined["controls"]]
    del combined["control_extraction"]

# CUECs normalization: support both 'cuecs' and 'cuec_extraction'
if "cuec_extraction" in combined and not combined.get("cuecs"):
    combined["cuecs"] = combined["cuec_extraction"]
    del combined["cuec_extraction"]
elif "cuecs" in combined and not combined.get("cuec_extraction"):
    pass
elif "cuecs" in combined and "cuec_extraction" in combined:
    if isinstance(combined["cuecs"], list) and isinstance(combined["cuec_extraction"], list):
        combined["cuecs"] += [c for c in combined["cuec_extraction"] if c not in combined["cuecs"]]
    del combined["cuec_extraction"]

# Subservice orgs normalization: support both 'subservice_orgs' and 'subservice_orgs_extraction'
if "subservice_orgs_extraction" in combined and not combined.get("subservice_orgs"):
    combined["subservice_orgs"] = combined["subservice_orgs_extraction"]
    del combined["subservice_orgs_extraction"]
elif "subservice_orgs" in combined and not combined.get("subservice_orgs_extraction"):
    pass
elif "subservice_orgs" in combined and "subservice_orgs_extraction" in combined:
    if isinstance(combined["subservice_orgs"], list) and isinstance(combined["subservice_orgs_extraction"], list):
        combined["subservice_orgs"] += [c for c in combined["subservice_orgs_extraction"] if c not in combined["subservice_orgs"]]
    del combined["subservice_orgs_extraction"]


# Filter out controls that do not have a control_seq (only keep those with a non-null control_seq)
if "controls" in combined and isinstance(combined["controls"], list):
    combined["controls"] = [
        c for c in combined["controls"]
        if isinstance(c, dict) and c.get("control_seq") is not None
    ]

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
    try:
        resp_json = resp.json()
        scan_id = resp_json.get("scan_id")
        scan_table_id = resp_json.get("scan_table_id")
        if scan_id != scan_table_id:
            print(f"Warning: scan_id (ScanHistory.id={scan_id}) != scan_table_id (Scan.id={scan_table_id})")
        else:
            print(f"Scan ID: {scan_id} (IDs are aligned)")
        print(json.dumps(resp_json, indent=2))
    except Exception as parse_exc:
        print(f"Could not parse JSON response: {parse_exc}")
        print(f"Raw response: {resp.text}")
except Exception as e:
    print("Error during DB insert call:", e)
