"""Check scan status"""
import requests
import sys

job_id = "8bc03cac-a755-4e29-a8fa-7a07470069cc"

# Login
resp = requests.post("http://localhost:8000/auth/login", 
                    data={'username': 'admin', 'password': 'admin'})
resp.raise_for_status()
token = resp.json()['access_token']

# Get status
headers = {'Authorization': f'Bearer {token}'}
resp = requests.get(f"http://localhost:8000/analyze/status/{job_id}", headers=headers)
resp.raise_for_status()
data = resp.json()

print(f"\nJob ID: {job_id}")
print(f"Status: {data.get('status')}")
print(f"Progress: {data.get('progress_percent', 0):.1f}%")
print(f"Done: {data.get('done', False)}")
if data.get('scan_id'):
    print(f"Scan ID: {data.get('scan_id')}")
print()
