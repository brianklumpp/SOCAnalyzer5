"""
Test script for enhanced subservice orgs deduplication and confidence adjustment.

This script loads existing subservice orgs from the database for scan 6,
applies the enhancements, and shows before/after comparison.

Run this inside the backend container:
docker exec -it socanalyzer-backend python /app/test_subservice_enhancement.py
"""

import sys
import os
import json
import asyncio

# This script should run inside the container
sys.path.insert(0, '/app')

from backend.app.database import get_db
from backend.app.models import SubserviceOrg
from sqlalchemy import select
from backend.app.extractors.subservice_orgs_dedup import enhance_subservice_orgs


async def test_enhancement():
    """Test the enhancement on scan 6 data"""
    print("="*80)
    print("SUBSERVICE ORGS ENHANCEMENT TEST")
    print("="*80)
    
    # Get database session
    db = await anext(get_db())
    
    try:
        # Load scan 6 subservice orgs
        print("\n[1] Loading subservice orgs from scan 6...")
        result = await db.execute(
            select(SubserviceOrg).where(SubserviceOrg.scan_id == 6)
        )
        orgs = result.scalars().all()
        
        print(f"[1] Loaded {len(orgs)} organizations")
        
        # Convert to dict format
        orgs_dict = []
        for org in orgs:
            org_dict = {
                "id": org.id,
                "third_party_name": org.name,
                "third_party_description": org.third_party_description,
                "third_party_confidence": org.third_party_confidence or org.confidence,
                "third_party_page_ref": org.third_party_page_ref,
                "confidence_justification": org.confidence_justification or [],
                "third_party_controls": org.third_party_controls,
                "likely_so": org.likely_so,
                "common_so": org.common_so,
            }
            orgs_dict.append(org_dict)
        
        # Show before state
        print("\n[2] BEFORE Enhancement:")
        print("-" * 80)
        
        # Group by confidence
        high_conf = [o for o in orgs_dict if o["third_party_confidence"] >= 0.9]
        med_conf = [o for o in orgs_dict if 0.7 <= o["third_party_confidence"] < 0.9]
        
        print(f"High confidence (>=0.9): {len(high_conf)}")
        for org in high_conf[:10]:  # Show first 10
            print(f"  • {org['third_party_name']}: {org['third_party_confidence']}")
        if len(high_conf) > 10:
            print(f"  ... and {len(high_conf) - 10} more")
        
        print(f"\nMedium confidence (0.7-0.9): {len(med_conf)}")
        
        # Look for potential duplicates
        print("\n[3] Potential duplicates detected:")
        print("-" * 80)
        names = [o["third_party_name"].lower() for o in orgs_dict]
        
        # Check for AWS variations
        aws_variations = [o["third_party_name"] for o in orgs_dict if "amazon" in o["third_party_name"].lower() or "aws" in o["third_party_name"].lower()]
        if aws_variations:
            print(f"AWS variations ({len(aws_variations)}):")
            for name in aws_variations:
                print(f"  • {name}")
        
        # Check for Azure variations
        azure_variations = [o["third_party_name"] for o in orgs_dict if "azure" in o["third_party_name"].lower() or ("microsoft" in o["third_party_name"].lower() and "azure" not in o["third_party_name"].lower())]
        if azure_variations:
            print(f"\nAzure/Microsoft variations ({len(azure_variations)}):")
            for name in azure_variations:
                print(f"  • {name}")
        
        # Check for GCP variations
        gcp_variations = [o["third_party_name"] for o in orgs_dict if "google" in o["third_party_name"].lower() or "gcp" in o["third_party_name"].lower()]
        if gcp_variations:
            print(f"\nGCP/Google variations ({len(gcp_variations)}):")
            for name in gcp_variations:
                print(f"  • {name}")
        
        # Identify SaaS tools
        saas_tools = ["splunk", "workday", "pagerduty", "servicenow", "sailpoint", "datadog", "new relic", "nagios"]
        found_saas = [o for o in orgs_dict if any(tool in o["third_party_name"].lower() for tool in saas_tools)]
        if found_saas:
            print(f"\n[4] SaaS tools with high confidence:")
            print("-" * 80)
            for org in found_saas:
                print(f"  • {org['third_party_name']}: {org['third_party_confidence']}")
        
        # Run enhancement
        print("\n[5] Running enhancement...")
        print("=" * 80)
        enhanced = enhance_subservice_orgs(orgs_dict.copy())
        
        # Show after state
        print("\n[6] AFTER Enhancement:")
        print("-" * 80)
        
        high_conf_after = [o for o in enhanced if o["third_party_confidence"] >= 0.9]
        med_conf_after = [o for o in enhanced if 0.7 <= o["third_party_confidence"] < 0.9]
        low_conf_after = [o for o in enhanced if o["third_party_confidence"] < 0.7]
        
        print(f"High confidence (>=0.9): {len(high_conf_after)} (was {len(high_conf)})")
        print(f"Medium confidence (0.7-0.9): {len(med_conf_after)} (was {len(med_conf)})")
        print(f"Low confidence (<0.7): {len(low_conf_after)}")
        print(f"Total: {len(enhanced)} (was {len(orgs_dict)})")
        
        # Show changes
        print("\n[7] Changes made:")
        print("-" * 80)
        
        # Find entries that were merged (no longer exist)
        before_names = {o["third_party_name"].lower() for o in orgs_dict}
        after_names = {o["third_party_name"].lower() for o in enhanced}
        merged = before_names - after_names
        
        if merged:
            print(f"\nMerged/removed ({len(merged)} entries):")
            for name in list(merged)[:10]:
                # Find the original entry
                orig = next((o for o in orgs_dict if o["third_party_name"].lower() == name), None)
                if orig:
                    print(f"  • {orig['third_party_name']} ({orig['third_party_confidence']})")
        
        # Find entries with changed confidence
        print("\nConfidence adjustments:")
        for after_org in enhanced:
            before_org = next((o for o in orgs_dict if o["third_party_name"].lower() == after_org["third_party_name"].lower()), None)
            if before_org and abs(before_org["third_party_confidence"] - after_org["third_party_confidence"]) > 0.05:
                print(f"  • {after_org['third_party_name']}: {before_org['third_party_confidence']} → {after_org['third_party_confidence']}")
                # Show justification
                just = after_org.get("confidence_justification", [])
                if just:
                    latest = just[-1] if isinstance(just, list) else just
                    print(f"    Reason: {latest}")
        
        # Save enhanced results to a test file
        output_path = "data/json/subservice_orgs_enhanced_test.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({"subservice_orgs": enhanced}, f, indent=2, ensure_ascii=False)
        
        print(f"\n[8] Enhanced results saved to: {output_path}")
        print("="*80)
        print("TEST COMPLETE")
        print("="*80)
        
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(test_enhancement())
