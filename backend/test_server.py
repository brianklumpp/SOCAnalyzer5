#!/usr/bin/env python3
"""
Test script to check if backend imports work correctly
"""
try:
    print("Testing imports...")
    from app.main import app
    print("✅ Backend imports successful!")
    
    # Test if the app can start
    import uvicorn
    print("Starting test server on port 8001...")
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="debug")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc() 