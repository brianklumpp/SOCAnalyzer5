# test_control_extraction.py

"""
Interactive test script for control extraction using control_extractor_v2.py.
Allows selection of a SOC report PDF and focuses on control extraction.
"""

import os
import logging
import argparse
from backend.app.extractors.control_extractor_v2 import extract_controls_v2
from backend.app.pdf_handler import extract_text_from_pdf

# Set up argument parser
parser = argparse.ArgumentParser(description='Test control extraction from a specified SOC report file.')
parser.add_argument('file_path', type=str, help='Path to the SOC report file to be tested')

# Parse the command-line arguments
args = parser.parse_args()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Path to SOC reports
SOC2_REPORTS_PATH = 'soc2_reports'

# Function to list available SOC reports

def list_soc_reports():
    reports = [f for f in os.listdir(SOC2_REPORTS_PATH) if f.endswith('.pdf')]
    for idx, report in enumerate(reports):
        print(f"{idx + 1}: {report}")
    return reports

# Main function for interactive testing

def main():
    print("Select a SOC report to analyze:")
    reports = list_soc_reports()
    choice = int(input("Enter the number of the report to analyze: ")) - 1
    if choice < 0 or choice >= len(reports):
        print("Invalid choice. Exiting.")
        return

    selected_report = reports[choice]
    report_path = os.path.join(SOC2_REPORTS_PATH, selected_report)
    print(f"Selected report: {selected_report}")

    # Extract text from the selected PDF
    text_output_path = 'data/output/output.txt'
    extract_text_from_pdf(report_path, text_output_path)
    print(f"Text extracted to {text_output_path}")

    # Run control extraction
    extract_controls_v2(text_output_path)
    print("Control extraction completed.")

# Run the control extraction test
logging.info(f'Starting control extraction test for file: {args.file_path}')
try:
    extract_controls_v2(args.file_path)
    logging.info('Control extraction test completed successfully.')
except Exception as e:
    logging.error(f'Error during control extraction test: {e}')

if __name__ == "__main__":
    main() 