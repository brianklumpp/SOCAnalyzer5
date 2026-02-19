"""Quick scan starter and status checker"""
import requests
import sys
import time
import os

API_BASE = "http://localhost:8000"  # Direct to backend, skip nginx

def get_auth_token():
    """Get authentication token"""
    # Try environment variables first
    username = os.getenv('SOC_USERNAME', 'admin')
    password = os.getenv('SOC_PASSWORD', 'admin')
    
    resp = requests.post(f"{API_BASE}/auth/login", 
                        data={'username': username, 'password': password},
                        timeout=10)
    resp.raise_for_status()
    return resp.json()['access_token']

def start_scan(pdf_path, token):
    """Upload PDF and start scan"""
    print(f"Uploading {pdf_path}...")
    with open(pdf_path, 'rb') as f:
        files = {'files': f}
        data = {
            'report_types': '',  # Auto-detect
            'priorities': '1',  # Normal priority
            'passwords': ''
        }
        headers = {'Authorization': f'Bearer {token}'}
        resp = requests.post(f"{API_BASE}/analyze/batch", 
                            files=files, data=data, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        # Batch endpoint returns job_ids array
        job_ids = data.get('job_ids', [])
        if not job_ids:
            raise ValueError(f"No job IDs returned: {data}")
        job_id = job_ids[0]
        print(f"✓ Started scan - Job ID: {job_id}")
        return job_id

def check_status(job_id, token):
    """Check job status"""
    headers = {'Authorization': f'Bearer {token}'}
    resp = requests.get(f"{API_BASE}/analyze/status/{job_id}", headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python quick_scan.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    # Get auth token
    print("Authenticating...")
    try:
        token = get_auth_token()
    except requests.exceptions.HTTPError as e:
        print(f"❌ Authentication failed: {e}")
        print("Set SOC_USERNAME and SOC_PASSWORD environment variables or use defaults (admin/admin123)")
        sys.exit(1)
    
    job_id = start_scan(pdf_path, token)
    
    print("\nWaiting 5 seconds for scan to start...")
    time.sleep(5)
    
    status = check_status(job_id, token)
    print(f"\nStatus: {status.get('status')}")
    print(f"Progress: {status.get('progress_percent', 0):.1f}%")
    print(f"Done: {status.get('done', False)}")
    print(f"\nCheck status: curl http://localhost:8000/analyze/status/{job_id}")
