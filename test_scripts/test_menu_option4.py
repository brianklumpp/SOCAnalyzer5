"""
Quick test for open_report_in_browser function
"""
import sys
sys.path.insert(0, '.')

# Import the function
from interactive_scan import open_report_in_browser

# Test it (will show menu)
print("Testing open_report_in_browser() - should show menu of last 9 reports")
print("=" * 80)
open_report_in_browser()
