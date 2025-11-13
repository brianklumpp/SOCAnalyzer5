#!/usr/bin/env python3
"""
Check Available Dataiku LLM Models

This script connects to your Dataiku DSS instance and lists all available
LLM models in the catalog.
"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

# Load environment
from dotenv import load_dotenv
load_dotenv()

def check_dataiku_llms():
    """Check what LLM models are available in Dataiku"""
    
    try:
        import dataikuapi
        
        host = os.getenv("DATAIKU_DSS_HOST")
        api_key = os.getenv("DATAIKU_DSS_API_KEY")
        project_key = os.getenv("DATAIKU_DSS_PROJECT")
        
        print(f"Connecting to Dataiku DSS...")
        print(f"  Host: {host}")
        print(f"  Project: {project_key}")
        print()
        
        # Connect
        client = dataikuapi.DSSClient(host, api_key)
        
        # Handle SSL verification
        verify_ssl = os.getenv("DATAIKU_VERIFY_SSL", "true").lower() == "true"
        if not verify_ssl or os.getenv("DATAIKU_CA_BUNDLE"):
            ca_bundle = os.getenv("DATAIKU_CA_BUNDLE")
            if ca_bundle and os.path.exists(ca_bundle):
                client._session.verify = ca_bundle
            else:
                client._session.verify = False
        
        print("=" * 80)
        print("AVAILABLE LLM MODELS")
        print("=" * 80)
        
        # Try to get LLMs
        try:
            llms = client.list_llms()
            
            if not llms:
                print("No LLMs found (or permission denied)")
                print("\nTrying alternative method...")
            else:
                for i, llm in enumerate(llms, 1):
                    print(f"\n{i}. LLM ID: {llm.get('id', 'Unknown')}")
                    print(f"   Label: {llm.get('label', 'N/A')}")
                    print(f"   Type: {llm.get('type', 'N/A')}")
                    
                    # Check if this is Azure OpenAI
                    if 'azureopenai' in llm.get('id', '').lower():
                        parts = llm.get('id', '').split(':')
                        if len(parts) >= 3:
                            print(f"   Connection: {parts[1]}")
                            print(f"   Deployment: {parts[2]}")
                    
                    # Show description if available
                    if llm.get('description'):
                        print(f"   Description: {llm.get('description')}")
        
        except AttributeError:
            print("list_llms() not available, trying project-level access...")
            
        # Alternative: Try to get project and check LLMs there
        try:
            project = client.get_project(project_key)
            settings = project.get_settings()
            
            print("\nProject Settings LLM Configuration:")
            print("-" * 80)
            
            # This might not work depending on Dataiku version
            if hasattr(settings, 'get_llm_settings'):
                llm_settings = settings.get_llm_settings()
                print(llm_settings)
                
        except Exception as e:
            print(f"Could not get project LLM settings: {e}")
        
        # Show what's configured in your .env
        print("\n" + "=" * 80)
        print("YOUR CURRENT .ENV CONFIGURATION")
        print("=" * 80)
        
        env_models = {
            "GPT-4o": os.getenv("DATAIKU_LLM_GPT4O"),
            "GPT-3.5": os.getenv("DATAIKU_LLM_GPT35"),
            "GPT-5": os.getenv("DATAIKU_LLM_GPT5"),
            "GPT-4.1": os.getenv("DATAIKU_LLM_GPT41"),
            "GPT-4.1-mini": os.getenv("DATAIKU_LLM_GPT41_MINI"),
            "o4-mini": os.getenv("DATAIKU_LLM_O4_MINI"),
        }
        
        for name, llm_id in env_models.items():
            if llm_id:
                status = "✓" if llm_id else "✗"
                print(f"{status} {name:15} -> {llm_id}")
        
        print("\n" + "=" * 80)
        print("RECOMMENDATIONS")
        print("=" * 80)
        print()
        print("1. Check the Dataiku DSS web interface:")
        print(f"   {host}administration/connections/llms")
        print()
        print("2. Look for Azure-OpenAI-Prod connection and see available deployments")
        print()
        print("3. If GPT-5 is listed with a different deployment name, update .env:")
        print("   DATAIKU_LLM_GPT5=azureopenai:Azure-OpenAI-Prod:<actual-deployment-name>")
        print()
        print("4. Common GPT-5 deployment names to try:")
        print("   - gpt-5")
        print("   - gpt-5-turbo")
        print("   - gpt-5-preview")
        print("   - gpt5")
        print()
        
    except ImportError:
        print("ERROR: dataikuapi not installed")
        print("Install with: pip install dataiku-api-client")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_dataiku_llms()
