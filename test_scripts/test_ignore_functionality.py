"""
Test script to verify the ignore functionality for controls.
"""
import requests
import json

BASE_URL = "http://localhost:8000"
SCAN_ID = 6

def test_ignore_control():
    """Test ignoring a control."""
    
    print(f"Testing IGNORE functionality for scan {SCAN_ID}...")
    
    # Get controls
    response = requests.get(f"{BASE_URL}/report/{SCAN_ID}")
    if response.status_code != 200:
        print(f"❌ Failed to fetch report: {response.status_code}")
        return False
    
    report = response.json()
    controls = report.get('controls', [])
    
    if not controls:
        print("❌ No controls found")
        return False
    
    # Find a control with confidence > 0
    test_control = None
    for ctrl in controls:
        conf = ctrl.get('control_confidence')
        if isinstance(conf, (int, float)) and conf > 0:
            test_control = ctrl
            break
        elif isinstance(conf, str):
            # Parse percentage string
            try:
                conf_val = float(conf.rstrip('%')) / 100
                if conf_val > 0:
                    test_control = ctrl
                    break
            except:
                pass
    
    if not test_control:
        print("❌ No control found with confidence > 0")
        return False
    
    control_id = test_control.get('control_id')
    db_id = test_control.get('id')
    current_conf = test_control.get('control_confidence')
    
    print(f"\n✓ Found test control:")
    print(f"  Control ID: {control_id}")
    print(f"  DB ID: {db_id}")
    print(f"  Current confidence: {current_conf}")
    
    # Test ignore by setting confidence to 0
    print(f"\n--- Testing IGNORE (set confidence to 0) ---")
    payload = {
        "control_confidence": 0,
        "confidence_calc": (test_control.get('confidence_calc', '') or '') + '; Test: Manually ignored - confidence set to 0'
    }
    
    response = requests.patch(
        f"{BASE_URL}/report/{SCAN_ID}/controls/id/{db_id}",
        json=payload
    )
    
    if response.status_code == 200:
        print(f"✓ PATCH successful - control ignored")
    else:
        print(f"❌ PATCH failed: {response.status_code}")
        print(f"  Response: {response.text}")
        return False
    
    # Verify the change
    print(f"\n--- Verifying change was saved ---")
    response = requests.get(f"{BASE_URL}/report/{SCAN_ID}")
    if response.status_code != 200:
        print(f"❌ Failed to fetch updated report: {response.status_code}")
        return False
    
    report = response.json()
    controls = report.get('controls', [])
    updated_control = next((c for c in controls if c.get('id') == db_id), None)
    
    if not updated_control:
        print(f"❌ Could not find updated control")
        return False
    
    new_conf = updated_control.get('control_confidence')
    print(f"✓ Updated control retrieved:")
    print(f"  New confidence: {new_conf}")
    
    # Check if confidence is 0
    if isinstance(new_conf, (int, float)):
        is_zero = new_conf == 0
    elif isinstance(new_conf, str):
        is_zero = new_conf in ['0', '0%', '0.0', '0.0%']
    else:
        is_zero = False
    
    if is_zero:
        print(f"✅ Control successfully ignored (confidence = 0)")
        
        # Now restore it
        print(f"\n--- Restoring control (undo ignore) ---")
        restore_payload = {
            "control_confidence": current_conf if isinstance(current_conf, (int, float)) else 0.8,
            "confidence_calc": (updated_control.get('confidence_calc', '') or '') + '; Test: Restored after ignore test'
        }
        
        response = requests.patch(
            f"{BASE_URL}/report/{SCAN_ID}/controls/id/{db_id}",
            json=restore_payload
        )
        
        if response.status_code == 200:
            print(f"✓ Control restored to original confidence")
        else:
            print(f"⚠️  Failed to restore: {response.status_code}")
        
        return True
    else:
        print(f"❌ Control confidence was not set to 0 (got: {new_conf})")
        return False

if __name__ == "__main__":
    try:
        success = test_ignore_control()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
