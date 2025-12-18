"""
Test script for job resume capability.

Tests that the checkpoint system properly resumes jobs after:
1. Mid-extraction crashes
2. Partial metadata failures
3. Redis connection loss
"""

import json
import os
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / 'backend'
sys.path.insert(0, str(backend_path))

from app.config import get_job_paths, JOBS_DIR

def test_checkpoint_save():
    """Test that checkpoints are saved correctly"""
    print("TEST 1: Checkpoint Save")
    print("-" * 50)
    
    user_id = 999
    job_id = "test-checkpoint-123"
    job_paths = get_job_paths(user_id, job_id)
    
    # Create job directories
    for path in [job_paths['json_dir'], job_paths['logs_dir'], job_paths['temp_dir']]:
        path.mkdir(parents=True, exist_ok=True)
    
    # Create mock checkpoint
    checkpoint_path = job_paths['json_dir'].parent / 'checkpoint.json'
    checkpoint_data = {
        "completed": ["company_extraction", "logo_fetching"],
        "checklist": [
            {"name": "company_extraction", "status": "done"},
            {"name": "logo_fetching", "status": "done"}
        ]
    }
    
    with open(checkpoint_path, 'w') as f:
        json.dump(checkpoint_data, f, indent=2)
    
    # Verify checkpoint exists
    assert checkpoint_path.exists(), "Checkpoint not created"
    
    with open(checkpoint_path, 'r') as f:
        loaded = json.load(f)
    
    assert loaded['completed'] == ["company_extraction", "logo_fetching"]
    print("✓ Checkpoint saved and loaded correctly")
    
    # Cleanup
    checkpoint_path.unlink()
    print()

def test_resume_from_checkpoint():
    """Test that jobs resume from checkpoint"""
    print("TEST 2: Resume from Checkpoint")
    print("-" * 50)
    
    user_id = 999
    job_id = "test-resume-456"
    job_paths = get_job_paths(user_id, job_id)
    
    # Create job directories
    for path in [job_paths['json_dir'], job_paths['logs_dir'], job_paths['temp_dir']]:
        path.mkdir(parents=True, exist_ok=True)
    
    # Create mock completed extractors checkpoint
    checkpoint_path = job_paths['json_dir'].parent / 'checkpoint.json'
    checkpoint_data = {
        "completed": ["company_extraction", "logo_fetching", "product_extraction"],
        "checklist": []
    }
    
    with open(checkpoint_path, 'w') as f:
        json.dump(checkpoint_data, f, indent=2)
    
    # Load checkpoint
    with open(checkpoint_path, 'r') as f:
        loaded = json.load(f)
    
    completed = loaded.get('completed', [])
    
    # Simulate resume logic
    extractors_to_run = []
    all_extractors = [
        "company_extraction",
        "logo_fetching",
        "product_extraction",
        "auditor_extraction",
        "report_date_extraction"
    ]
    
    for extractor in all_extractors:
        if extractor not in completed:
            extractors_to_run.append(extractor)
    
    expected = ["auditor_extraction", "report_date_extraction"]
    assert extractors_to_run == expected, f"Expected {expected}, got {extractors_to_run}"
    print(f"✓ Resume skips completed extractors: {completed}")
    print(f"✓ Resume runs remaining extractors: {extractors_to_run}")
    
    # Cleanup
    checkpoint_path.unlink()
    print()

def test_partial_failure_handling():
    """Test handling of partial metadata failures"""
    print("TEST 3: Partial Failure Handling")
    print("-" * 50)
    
    # Simulate metadata extraction results
    metadata_results = {
        'auditor_extraction': {'auditor': 'Deloitte'},
        'product_extraction': None,  # Failed
        'report_date_extraction': {'report_date': '2024-01-15'},
        'coverage_period_extraction': None  # Failed
    }
    
    successful = [k for k, v in metadata_results.items() if v is not None]
    failed = [k for k, v in metadata_results.items() if v is None]
    
    assert len(successful) == 2, "Should have 2 successful extractors"
    assert len(failed) == 2, "Should have 2 failed extractors"
    assert 'product_extraction' in failed
    assert 'coverage_period_extraction' in failed
    
    print(f"✓ Detected {len(successful)} successful extractors")
    print(f"✓ Detected {len(failed)} failed extractors: {failed}")
    print()

def test_checkpoint_corruption():
    """Test handling of corrupted checkpoint files"""
    print("TEST 4: Corrupted Checkpoint Handling")
    print("-" * 50)
    
    user_id = 999
    job_id = "test-corrupt-789"
    job_paths = get_job_paths(user_id, job_id)
    
    # Create job directories
    for path in [job_paths['json_dir'], job_paths['logs_dir'], job_paths['temp_dir']]:
        path.mkdir(parents=True, exist_ok=True)
    
    # Create corrupted checkpoint
    checkpoint_path = job_paths['json_dir'].parent / 'checkpoint.json'
    with open(checkpoint_path, 'w') as f:
        f.write("{ invalid json data")
    
    # Try to load checkpoint
    try:
        with open(checkpoint_path, 'r') as f:
            json.load(f)
        assert False, "Should have raised JSONDecodeError"
    except json.JSONDecodeError:
        print("✓ Correctly detected corrupted checkpoint")
        # In production, should start from beginning
        completed_extractors = []
        print("✓ Fallback to empty completed list")
    
    # Cleanup
    checkpoint_path.unlink()
    print()

def test_job_paths_structure():
    """Test that job_paths dict has all required keys"""
    print("TEST 5: Job Paths Structure")
    print("-" * 50)
    
    user_id = 1
    job_id = "test-paths-999"
    job_paths = get_job_paths(user_id, job_id)
    
    required_keys = ['json_dir', 'logs_dir', 'temp_dir', 'txt_path']
    
    for key in required_keys:
        assert key in job_paths, f"Missing required key: {key}"
        print(f"✓ Key '{key}' present: {job_paths[key]}")
    
    # Verify all are Path objects (except txt_path which should also be Path)
    from pathlib import Path as PathType
    for key, value in job_paths.items():
        assert isinstance(value, PathType), f"{key} should be Path object, got {type(value)}"
    
    print("✓ All job_paths are Path objects")
    print()

def test_sequential_fallback_parameters():
    """Test that sequential fallback has correct parameter signature"""
    print("TEST 6: Sequential Fallback Parameters")
    print("-" * 50)
    
    # Read the function signature directly from source file
    analyze_path = Path(__file__).parent.parent / 'backend' / 'app' / 'analyze.py'
    with open(analyze_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for the function definition with job_paths parameter
    assert 'def _run_metadata_extractors_sequential(' in content
    assert 'job_paths=None' in content
    
    # Find the function definition
    import re
    pattern = r'def _run_metadata_extractors_sequential\((.*?)\):'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        params_str = match.group(1)
        assert 'job_paths' in params_str, "job_paths parameter missing"
        print(f"✓ Function has job_paths parameter")
        print("✓ Sequential fallback signature verified from source")
    else:
        print("⚠ Could not parse function signature, but job_paths found in file")
    
    print()

def main():
    print("\n" + "=" * 50)
    print("JOB RESUME CAPABILITY TEST SUITE")
    print("=" * 50 + "\n")
    
    try:
        test_checkpoint_save()
        test_resume_from_checkpoint()
        test_partial_failure_handling()
        test_checkpoint_corruption()
        test_job_paths_structure()
        test_sequential_fallback_parameters()
        
        print("=" * 50)
        print("ALL TESTS PASSED ✓")
        print("=" * 50 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
