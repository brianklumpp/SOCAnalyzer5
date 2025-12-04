"""
Test script for report type auto-detection
"""
import requests
import time
import json

API_URL = "http://localhost:8000"

def upload_report(pdf_path):
    """Upload a PDF report for analysis."""
    print(f"\n{'='*60}")
    print(f"Uploading: {pdf_path}")
    print(f"{'='*60}")
    
    with open(pdf_path, 'rb') as f:
        files = {'file': f}
        # Note: NOT sending report_type - it will be auto-detected
        response = requests.post(f"{API_URL}/analyze/", files=files)
    
    if response.status_code == 200:
        job_id = response.json()['job_id']
        print(f"✓ Upload successful! Job ID: {job_id}")
        return job_id
    else:
        print(f"✗ Upload failed: {response.text}")
        return None

def check_status(job_id):
    """Check job status."""
    response = requests.get(f"{API_URL}/analyze/status/{job_id}")
    return response.json()

def monitor_job(job_id, max_wait=120):
    """Monitor job progress and handle confirmation if needed."""
    print(f"\nMonitoring job {job_id}...")
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < max_wait:
        try:
            status = check_status(job_id)
            
            # Only print if status changed
            current_status = status.get('status', 'Unknown')
            if current_status != last_status:
                print(f"\n[{time.strftime('%H:%M:%S')}] Status: {current_status}")
                last_status = current_status
            
            # Check for AWAITING_CONFIRMATION
            if status.get('awaiting_confirmation'):
                detection = status.get('detection_result', {})
                print(f"\n{'='*60}")
                print("🔍 REPORT TYPE DETECTION - CONFIRMATION REQUIRED")
                print(f"{'='*60}")
                print(f"Detected Type: {detection.get('detected_type')} {detection.get('detected_subtype')}")
                print(f"Confidence: {detection.get('confidence', 0)*100:.1f}%")
                print(f"Analysis Stage: {detection.get('analysis_stage', 'unknown')}")
                
                if detection.get('evidence'):
                    print(f"\nEvidence Found:")
                    for i, evidence in enumerate(detection['evidence'][:5], 1):
                        print(f"  {i}. {evidence}")
                
                print(f"\n{'='*60}")
                print("Please confirm via the web UI at http://localhost:3000")
                print(f"{'='*60}")
                
                # Keep monitoring to see if user confirms
                while True:
                    time.sleep(3)
                    status = check_status(job_id)
                    if not status.get('awaiting_confirmation'):
                        print("\n✓ Confirmation received! Resuming analysis...")
                        break
                    if status.get('done') or status.get('error'):
                        break
            
            # Check if done
            if status.get('done'):
                print(f"\n{'='*60}")
                print("✓ ANALYSIS COMPLETE")
                print(f"{'='*60}")
                
                # Get result summary
                try:
                    result_resp = requests.get(f"{API_URL}/analyze/result/{job_id}?format=summary")
                    result = result_resp.json()
                    
                    if not result.get('error'):
                        print(f"Controls: {result.get('control_count', 0)}")
                        print(f"CUECs: {result.get('cuec_count', 0)}")
                        print(f"Company: {result.get('company_name', 'N/A')}")
                        print(f"Auditor: {result.get('auditor_name', 'N/A')}")
                except Exception as e:
                    print(f"Could not fetch results: {e}")
                
                return status
            
            # Check for errors
            if status.get('error'):
                print(f"\n✗ Error: {status['error']}")
                return status
            
            # Show progress
            progress = status.get('progress', 0)
            print(f"  Progress: {progress}%", end='\r')
            
            time.sleep(3)
            
        except Exception as e:
            print(f"\n✗ Monitoring error: {e}")
            time.sleep(3)
    
    print(f"\n⚠ Monitoring timed out after {max_wait} seconds")
    return None

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python test_auto_detection.py <path_to_pdf>")
        print("\nExample:")
        print("  python test_auto_detection.py 'soc2_reports/Okta.pdf'")
        print("  python test_auto_detection.py 'SAP ARIBA 2024.09.30 SOC 1 Type 2 Report EV Final SECURED.pdf'")
        return
    
    pdf_path = sys.argv[1]
    
    # Upload
    job_id = upload_report(pdf_path)
    if not job_id:
        return
    
    # Monitor
    monitor_job(job_id, max_wait=300)

if __name__ == "__main__":
    main()
