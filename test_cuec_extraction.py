"""
Test CUEC extraction on sample text
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from backend.app import config
from backend.app.gpt_client import gpt_extract
import json

# Sample text from user
SAMPLE_TEXT = """Control Objective 2
1. User entities are responsible for notifying Boomi of changes made to technical or administrative
contact information.
2. User entities are responsible for maintaining their own system(s) of record.
3. User entities are responsible for ensuring the supervision, management, and control of the use of
Boomi services by their personnel.
4. User entities are responsible for understanding and complying with their contractual obligations to
Boomi.
5. User entities are responsible for maintaining appropriate password settings within their Flow and
Boomi Enterprise Platform.
Control Objective 3
6. User entities are responsible for immediately notifying Boomi of any actual or suspected information
security breaches, including compromised user accounts, including those used for integrations and
secure file transfers.
Control Objective 5
7. User entities are responsible for developing their own disaster recovery and business continuity
plans that address the inability to access or utilize Boomi services.
8. User entities are responsible for provisioning access to their Boomi Enterprise Platform and Flow
Services System environment, including access for Boomi personnel for troubleshooting and
configuration support purposes.
9. User entities are responsible for monitoring Flow and Atoms within their Boomi Enterprise Platform
and Flow Services System environment for failures and resolving failures as needed.
10. User entities are responsible for monitoring the Boomi Performance and Availability Website for
planned platform downtime and for incidents and issues related to the Boomi Enterprise Platform,
Integration, API Gateway, API Control Plane, Cloud API Management, Business-to-Business
(B2B)/electronic data interchange (EDI), Managed Cloud Service (MCS), Boomi Insights, Boomi
AI, Event Streams, and Master Data Hub (MDH).
Control Objective 6
11. User entities are responsible for appropriately configuring Flow and Atoms within the Boomi
Enterprise Platform, Integration, API Gateway, API Control Plane, Cloud API Management,
Business-to-Business (B2B)/electronic data interchange (EDI), Managed Cloud Service (MCS),
Boomi Insights, Boomi AI, Event Streams, and Master Data Hub (MDH)."""

def test_cuec_extraction():
    print("Testing CUEC extraction with improved prompt...")
    print("=" * 80)
    
    # Format the prompt
    prompt = config.CUEC_EXTRACTION_PROMPT.format(
        text=SAMPLE_TEXT,
        company_names="Boomi, the Company, the service organization",
        parent_company_names="the parent company"
    )
    
    print("\nSample text length:", len(SAMPLE_TEXT), "characters")
    print("\nCalling GPT extraction...")
    
    try:
        response = gpt_extract(prompt, 'cuec_extractor_test')
        print("\n" + "=" * 80)
        print("GPT Response:")
        print("=" * 80)
        print(response)
        print("=" * 80)
        
        # Try to parse as JSON
        clean_response = response.strip()
        if clean_response.startswith('```json'):
            clean_response = clean_response[7:]
        if clean_response.startswith('```'):
            clean_response = clean_response[3:]
        if clean_response.endswith('```'):
            clean_response = clean_response[:-3]
        clean_response = clean_response.strip()
        
        data = json.loads(clean_response)
        
        # Extract CUECs
        if isinstance(data, dict) and 'cuecs' in data:
            cuecs = data['cuecs']
        elif isinstance(data, list):
            cuecs = data
        else:
            cuecs = []
        
        print(f"\n✓ Extracted {len(cuecs)} CUECs")
        print("\nCUEC Summaries:")
        print("-" * 80)
        for i, cuec in enumerate(cuecs, 1):
            desc = cuec.get('cuec_description', '')
            opinion = cuec.get('cuec_gpt_opinion', 'Unknown')
            reasoning = cuec.get('cuec_gpt_reasoning', 'No reasoning')
            # Truncate description for display
            desc_short = desc[:80] + "..." if len(desc) > 80 else desc
            print(f"{i}. {desc_short}")
            print(f"   Opinion: {opinion} | Reasoning: {reasoning[:60]}...")
            print()
        
        # Show excluded items if any
        if isinstance(data, dict) and 'excluded' in data:
            excluded = data['excluded']
            if excluded:
                print(f"\n⚠ Excluded {len(excluded)} items")
                for ex in excluded:
                    print(f"  - {ex.get('excluded_description', '')[:60]}...")
                    print(f"    Reason: {ex.get('excluded_reason', 'No reason')}")
        
        # Summary
        expected = 11
        actual = len(cuecs)
        print("\n" + "=" * 80)
        print(f"RESULT: Extracted {actual} out of {expected} expected CUECs")
        if actual == expected:
            print("✓ SUCCESS - All CUECs extracted!")
        else:
            print(f"⚠ PARTIAL - Missing {expected - actual} CUECs")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n✗ Error during extraction: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_cuec_extraction()
