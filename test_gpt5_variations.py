#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Different GPT-5 LLM Catalog Variations

This script tries various possible GPT-5 deployment names in Dataiku
to find the one that actually works.
"""

import os
import sys
from pathlib import Path

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

# Load environment
from dotenv import load_dotenv
load_dotenv()

def test_llm_variations():
    """Test different possible GPT-5 catalog IDs"""
    
    try:
        import dataikuapi
        from dataikuapi.dss.llm import DSSLLM
        
        host = os.getenv("DATAIKU_DSS_HOST")
        api_key = os.getenv("DATAIKU_DSS_API_KEY")
        project_key = os.getenv("DATAIKU_DSS_PROJECT")
        
        print("=" * 80)
        print("TESTING GPT-5 LLM VARIATIONS")
        print("=" * 80)
        print(f"Host: {host}")
        print(f"Project: {project_key}")
        print()
        
        # Connect
        client = dataikuapi.DSSClient(host, api_key)
        
        # Handle SSL
        verify_ssl = os.getenv("DATAIKU_VERIFY_SSL", "true").lower() == "true"
        ca_bundle = os.getenv("DATAIKU_CA_BUNDLE")
        if ca_bundle and os.path.exists(ca_bundle):
            client._session.verify = ca_bundle
        elif not verify_ssl:
            client._session.verify = False
        
        project = client.get_project(project_key)
        
        # List of variations to try
        variations = [
            # Original
            "azureopenai:Azure-OpenAI-Prod:gpt-5",
            
            # Different deployment names
            "azureopenai:Azure-OpenAI-Prod:gpt5",
            "azureopenai:Azure-OpenAI-Prod:gpt-5-turbo",
            "azureopenai:Azure-OpenAI-Prod:gpt5-turbo",
            "azureopenai:Azure-OpenAI-Prod:gpt-5-preview",
            "azureopenai:Azure-OpenAI-Prod:gpt5-preview",
            
            # Different connection names
            "azureopenai:Azure-OpenAI-Prod-4-1:gpt-5",
            "azureopenai:Azure-OpenAI-Prod-5:gpt-5",
            "azureopenai:Azure-OpenAI-GPT5:gpt-5",
            
            # Try with gpt-4o variants (in case GPT-5 maps to 4o)
            "azureopenai:Azure-OpenAI-Prod:gpt-4o",
            
            # O-series models (new reasoning models)
            "azureopenai:Azure-OpenAI-Prod:o1",
            "azureopenai:Azure-OpenAI-Prod:o1-preview",
            "azureopenai:Azure-OpenAI-Prod:o1-mini",
            "azureopenai:Azure-OpenAI-Prod-4-1:o1",
        ]
        
        print("Testing each variation with a simple prompt...")
        print("-" * 80)
        
        test_prompt = "Say 'OK' if you can read this."
        
        for i, llm_id in enumerate(variations, 1):
            print(f"\n{i:2d}. Testing: {llm_id}")
            
            try:
                # Try to get the LLM from the project
                llm = project.get_llm(llm_id)
                
                # Try a simple completion
                completion = llm.new_completion()
                completion = completion.with_message("Say OK", role="user")
                
                resp = completion.execute()
                
                # Success!
                response_text = getattr(resp, 'text', str(resp))
                print(f"    ✓ SUCCESS! Model responded: {response_text[:50]}...")
                print(f"    >> USE THIS: {llm_id}")
                
            except Exception as e:
                error_msg = str(e)
                
                # Categorize the error
                if "not available" in error_msg.lower():
                    print(f"    [X] Not available in catalog")
                elif "not found" in error_msg.lower():
                    print(f"    [X] Model not found")
                elif "unauthorized" in error_msg.lower():
                    print(f"    [!] Permission denied")
                elif "forbidden" in error_msg.lower():
                    print(f"    [!] Forbidden")
                else:
                    print(f"    [X] Error: {error_msg[:60]}")
        
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print("Check the results above for any ✓ SUCCESS entries.")
        print("Update your .env file with the working LLM ID:")
        print()
        print("  DATAIKU_LLM_GPT5=<the-working-llm-id>")
        print()
        
    except ImportError:
        print("ERROR: dataikuapi not installed")
        print("Install with: pip install dataiku-api-client")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_llm_variations()
