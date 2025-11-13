"""
Script to update control confidence to 100% for a list of control IDs.
"""
import requests
import json

BASE_URL = "http://localhost:8000"
SCAN_ID = 6

# List of control IDs to update
CONTROL_IDS = [
    "PR-03-03",
    "SDD-01-01",
    "SG-01-01",
    "SG-02-01",
    "RM-01-01",
    "VM-01-01",
    "RM-02-02",
    "VM-02-01",
    "EM-05-01",
    "IAM-01-04",
    "IAM-02-03",
    "SO-01-01",
    "SO-02-01",
    "SO-02-05",
    "IAM-02-10",
    "CFM-01-01",
    "CFM-01-02",
    "SM-02-01",
    "SM-02-02",
    "IR-01-01",
    "BC-01-02",
    "CHM-01-01",
    "CHM-01-02",
    "TPM-01-01",
    "TPM-02-02",
    "SM-03-01",
    "AM-03-01",
    "BM-01-01",
    "BM-01-02",
    "DM-06-02",
    "TPM-04-01",
]

def main():
    print(f"Fetching controls for scan {SCAN_ID}...")
    
    # Get all controls for the scan
    response = requests.get(f"{BASE_URL}/report/{SCAN_ID}")
    if response.status_code != 200:
        print(f"❌ Failed to fetch report: {response.status_code}")
        return
    
    report = response.json()
    controls = report.get('controls', [])
    
    if not controls:
        print("❌ No controls found in report")
        return
    
    print(f"✓ Found {len(controls)} controls in scan")
    
    # Build a mapping of control_id -> list of db IDs
    control_map = {}
    for ctrl in controls:
        ctrl_id = ctrl.get('control_id')
        db_id = ctrl.get('id')
        if ctrl_id:
            if ctrl_id not in control_map:
                control_map[ctrl_id] = []
            control_map[ctrl_id].append({
                'db_id': db_id,
                'current_confidence': ctrl.get('control_confidence')
            })
    
    print(f"\n{'='*70}")
    print(f"Updating {len(CONTROL_IDS)} control IDs to 100% confidence")
    print(f"{'='*70}\n")
    
    updated = []
    not_found = []
    failed = []
    duplicates = []
    
    for control_id in CONTROL_IDS:
        if control_id not in control_map:
            not_found.append(control_id)
            print(f"⚠️  {control_id}: NOT FOUND in scan")
            continue
        
        instances = control_map[control_id]
        
        if len(instances) > 1:
            duplicates.append(control_id)
            print(f"⚠️  {control_id}: MULTIPLE INSTANCES ({len(instances)} found) - updating all:")
            for idx, inst in enumerate(instances, 1):
                db_id = inst['db_id']
                current = inst['current_confidence']
                payload = {"control_confidence": 1.0}
                
                response = requests.patch(
                    f"{BASE_URL}/report/{SCAN_ID}/controls/id/{db_id}",
                    json=payload
                )
                
                if response.status_code == 200:
                    print(f"     ✓ Instance {idx} (DB ID {db_id}): {current:.1%} → 100%")
                    updated.append(f"{control_id} [ID:{db_id}]")
                else:
                    print(f"     ❌ Instance {idx} (DB ID {db_id}): FAILED - {response.status_code}")
                    failed.append(f"{control_id} [ID:{db_id}]")
        else:
            # Single instance
            inst = instances[0]
            db_id = inst['db_id']
            current = inst['current_confidence']
            payload = {"control_confidence": 1.0}
            
            response = requests.patch(
                f"{BASE_URL}/report/{SCAN_ID}/controls/id/{db_id}",
                json=payload
            )
            
            if response.status_code == 200:
                print(f"✓ {control_id}: {current:.1%} → 100%")
                updated.append(control_id)
            else:
                print(f"❌ {control_id}: FAILED - {response.status_code}")
                print(f"   Response: {response.text}")
                failed.append(control_id)
    
    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"✓ Successfully updated: {len(updated)} controls")
    print(f"⚠️  Not found in scan: {len(not_found)} controls")
    print(f"⚠️  Multiple instances: {len(duplicates)} controls (all updated)")
    print(f"❌ Failed to update: {len(failed)} controls")
    
    if not_found:
        print(f"\n{'='*70}")
        print("Controls NOT FOUND in scan 6:")
        print(f"{'='*70}")
        for control_id in not_found:
            print(f"  - {control_id}")
    
    if failed:
        print(f"\n{'='*70}")
        print("Controls that FAILED to update:")
        print(f"{'='*70}")
        for control_id in failed:
            print(f"  - {control_id}")
    
    if duplicates:
        print(f"\n{'='*70}")
        print("Controls with MULTIPLE instances (all updated):")
        print(f"{'='*70}")
        for control_id in duplicates:
            instances = control_map[control_id]
            print(f"  - {control_id} ({len(instances)} instances)")
    
    print(f"\n{'='*70}")
    if not_found or failed:
        print("⚠️  Some controls could not be updated (see above)")
    else:
        print("✅ All controls successfully updated!")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Script failed with exception: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
