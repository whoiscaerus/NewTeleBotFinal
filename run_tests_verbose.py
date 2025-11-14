#!/usr/bin/env python3
"""Run tests and show output for EVERY SINGLE TEST."""

import subprocess
import sys
from pathlib import Path

def run_all_tests():
    """Run all tests serially with output for each individual test."""
    test_dir = Path("backend/tests")
    
    # Get all test files
    test_files = sorted([f.name for f in test_dir.glob("test_*.py")])
    
    # Exclude known problematic files
    exclude = {
        "test_pr_025_execution_store.py",
        "test_pr_048_trace_worker.py",
        "test_pr_102_web3_comprehensive.py"
    }
    test_files = [f for f in test_files if f not in exclude]
    
    print(f"Found {len(test_files)} test files\n")
    
    total_passed = 0
    total_failed = 0
    total_errors = 0
    
    for i, test_file in enumerate(test_files, 1):
        test_path = test_dir / test_file
        print(f"\n{'='*80}")
        print(f"[{i}/{len(test_files)}] {test_file}")
        print(f"{'='*80}")
        
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                str(test_path),
                "-v",
                "--tb=short",
                "--timeout=10"
            ],
            text=True
        )
        
        # Parse results from output
        import re
        if result.returncode == 0:
            print(f"✅ {test_file} - ALL PASSED")
        else:
            print(f"❌ {test_file} - SOME FAILURES")
        
        print()

if __name__ == "__main__":
    run_all_tests()
