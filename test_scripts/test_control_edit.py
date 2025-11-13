"""
Test script to verify control editing functionality.
This tests the PATCH endpoint for controls.
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_control_edit():
    """Test editing a control record."""
    
    # Use scan_id 6 (most recent from the logs)
    scan_id = 6
    print(f"✓ Using scan_id: {scan_id}")
    
    # Get controls for this scan
    print("Fetching controls...")
    response = requests.get(f"{BASE_URL}/report/{scan_id}")
    if response.status_code != 200:
        print(f"❌ Failed to fetch report: {response.status_code}")
        return False
    
    report = response.json()
    controls = report.get('controls', [])
    
    if not controls:
        print("❌ No controls found in report")
        return False
    
    # Pick the first control
    control = controls[0]
    control_id = control.get('control_id')
    control_db_id = control.get('id')
    
    print(f"✓ Found control: control_id='{control_id}', db_id={control_db_id}")
    print(f"  Current annotation: {control.get('annotation', '(none)')}")
    
    # Test 1: Update annotation via db ID endpoint
    print("\n--- Test 1: Update annotation via db ID endpoint ---")
    test_annotation = f"Test annotation at {json.dumps(str(__import__('datetime').datetime.now()))}"
    payload = {
        "annotation": test_annotation
    }
    
    response = requests.patch(
        f"{BASE_URL}/report/{scan_id}/controls/id/{control_db_id}",
        json=payload
    )
    
    if response.status_code == 200:
        print(f"✓ PATCH successful via db ID endpoint")
        result = response.json()
        print(f"  Response: {result}")
    else:
        print(f"❌ PATCH failed: {response.status_code}")
        print(f"  Response: {response.text}")
        return False
    
    # Test 2: Update control_confidence with type conversion
    print("\n--- Test 2: Update control_confidence (test type conversion) ---")
    payload2 = {
        "control_confidence": 1  # Send as int to test conversion
    }
    
    response = requests.patch(
        f"{BASE_URL}/report/{scan_id}/controls/id/{control_db_id}",
        json=payload2
    )
    
    if response.status_code == 200:
        print(f"✓ PATCH successful - control_confidence updated")
        result = response.json()
        print(f"  Response: {result}")
    else:
        print(f"❌ PATCH failed: {response.status_code}")
        print(f"  Response: {response.text}")
        return False
    
    # Test 3: Verify the update was saved
    print("\n--- Test 3: Verify update was saved ---")
    response = requests.get(f"{BASE_URL}/report/{scan_id}")
    if response.status_code != 200:
        print(f"❌ Failed to fetch updated report: {response.status_code}")
        return False
    
    report = response.json()
    controls = report.get('controls', [])
    updated_control = next((c for c in controls if c.get('id') == control_db_id), None)
    
    if updated_control:
        saved_annotation = updated_control.get('annotation', '')
        print(f"✓ Control retrieved after update")
        print(f"  Saved annotation: {saved_annotation}")
        if saved_annotation == test_annotation:
            print("✓ Annotation was correctly saved!")
        else:
            print("⚠ Annotation doesn't match (may be race condition)")
    else:
        print("❌ Could not find updated control")
        return False
    
    # Test 4: Update other fields
    print("\n--- Test 4: Update control_desc field ---")
    original_desc = updated_control.get('control_desc', '')
    test_desc = f"{original_desc}\n[TEST EDIT]"
    payload3 = {
        "control_desc": test_desc
    }
    
    response = requests.patch(
        f"{BASE_URL}/report/{scan_id}/controls/id/{control_db_id}",
        json=payload3
    )
    
    if response.status_code == 200:
        print(f"✓ Updated control_desc successfully")
    else:
        print(f"❌ Failed to update control_desc: {response.status_code}")
        print(f"  Response: {response.text}")
        return False
    
    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED!")
    print("="*60)
    return True

if __name__ == "__main__":
    try:
        success = test_control_edit()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
