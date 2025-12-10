#!/usr/bin/env python3
"""
SOC Analyzer Scan Status Management Utility

This script helps manage hanging scans by:
1. Checking current scan status
2. Forcing completion of stuck extractors with current results
3. Viewing extraction progress and statistics

Usage:
    python manage_scan_status.py --status SCAN_ID
    python manage_scan_status.py --complete-controls SCAN_ID
    python manage_scan_status.py --view-controls
"""

import argparse
import json
import sys
import os
import requests
from pathlib import Path

# Add the backend directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

def get_scan_status(scan_id):
    """Get current status of a scan"""
    try:
        response = requests.get(f"http://127.0.0.1:8000/analyze/status/{scan_id}", timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Error getting status: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error connecting to backend: {e}")
        return None

def view_control_stats():
    """View statistics about extracted controls"""
    control_file = Path("data/json/control_result.json")
    if not control_file.exists():
        print("❌ No control results found")
        return
    
    try:
        with open(control_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        # Handle malformed JSON from append-mode writing
        if content.startswith('[]'):
            # Remove the initial empty array and parse individual objects
            content = content[2:].strip()
            if content.startswith(','):
                content = content[1:].strip()
            
            # Split into individual JSON objects and parse
            controls = []
            if content:
                # Add array brackets to make it valid JSON
                content = '[' + content + ']'
                try:
                    controls = json.loads(content)
                except json.JSONDecodeError:
                    # Fallback: try to parse line by line
                    controls = []
                    for line in content.split('\n'):
                        line = line.strip().rstrip(',')
                        if line and line.startswith('{'):
                            try:
                                controls.append(json.loads(line))
                            except:
                                continue
        else:
            # Standard JSON format
            controls = json.loads(content)
            if isinstance(controls, dict) and 'controls' in controls:
                controls = controls['controls']
        
        if not isinstance(controls, list):
            print("❌ Invalid control result format")
            return
        
        print(f"📊 Control Extraction Statistics:")
        print(f"   Total Controls: {len(controls)}")
        
        if controls:
            # Get line range
            line_refs = [c.get('control_line_ref') for c in controls if c.get('control_line_ref')]
            end_lines = [c.get('end_line') for c in controls if c.get('end_line')]
            
            if line_refs and end_lines:
                print(f"   Line Range: {min(line_refs)} → {max(end_lines)}")
            
            # Framework distribution
            frameworks = {}
            for control in controls:
                fw = control.get('control_closest_framework', 'Unknown')
                frameworks[fw] = frameworks.get(fw, 0) + 1
            
            print(f"   Framework Distribution:")
            for fw, count in frameworks.items():
                print(f"     {fw}: {count}")
            
            # Confidence stats
            confidences = [c.get('control_confidence') for c in controls if c.get('control_confidence') is not None]
            if confidences:
                avg_conf = sum(confidences) / len(confidences)
                print(f"   Average Confidence: {avg_conf:.2f}")
    
    except Exception as e:
        print(f"❌ Error reading control results: {e}")

def complete_control_extraction(scan_id):
    """Force completion of control extraction with current results"""
    print(f"🔧 Attempting to complete control extraction for scan {scan_id}")
    
    # First check current status
    status = get_scan_status(scan_id)
    if not status:
        return False
    
    print(f"   Current Status: {status.get('status', 'Unknown')}")
    print(f"   Progress: {status.get('progress', 0)}%")
    
    # Check checklist
    checklist = status.get('checklist', [])
    control_item = next((item for item in checklist if item['name'] == 'control_extraction'), None)
    
    if not control_item:
        print("❌ Control extraction not found in checklist")
        return False
    
    print(f"   Control Extraction Status: {control_item['status']}")
    
    if control_item['status'] in ['done', 'partial']:
        print("✅ Control extraction already completed")
        return True
    
    # Check if we have control results
    view_control_stats()
    
    # Note: In a real implementation, you would update the Redis status here
    # For now, we just provide guidance
    print("\n💡 To force completion:")
    print("1. Stop the backend server")
    print("2. Restart with: python backend/app/main.py")
    print("3. The system will detect existing control results and continue")
    
    return True

def main():
    parser = argparse.ArgumentParser(description="SOC Analyzer Scan Status Management")
    parser.add_argument('--status', type=str, help='Check status of scan ID')
    parser.add_argument('--complete-controls', type=str, help='Force complete control extraction for scan ID')
    parser.add_argument('--view-controls', action='store_true', help='View control extraction statistics')
    
    args = parser.parse_args()
    
    if args.status:
        status = get_scan_status(args.status)
        if status:
            print(f"📋 Scan Status for {args.status}:")
            print(f"   Status: {status.get('status', 'Unknown')}")
            print(f"   Progress: {status.get('progress', 0)}%")
            print(f"   Done: {status.get('done', False)}")
            
            checklist = status.get('checklist', [])
            print(f"   Checklist:")
            for item in checklist:
                status_icon = {"done": "✅", "pending": "⏳", "partial": "⚠️"}.get(item['status'], "❓")
                print(f"     {status_icon} {item['name']}: {item['status']}")
    
    elif args.complete_controls:
        complete_control_extraction(args.complete_controls)
    
    elif args.view_controls:
        view_control_stats()
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 