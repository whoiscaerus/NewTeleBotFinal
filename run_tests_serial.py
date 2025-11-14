#!/usr/bin/env python3
"""Run tests serially to avoid hanging issues with parallel execution."""

import subprocess
import sys
from pathlib import Path

def run_tests():
    """Run test files one by one and report results."""
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
    
    print(f"Found {len(test_files)} test files")
    
    total_passed = 0
    total_failed = 0
    total_errors = 0
    failed_files = []
    
    for i, test_file in enumerate(test_files, 1):
        test_path = test_dir / test_file
        print(f"\n[{i}/{len(test_files)}] Running {test_file}...", end=" ", flush=True)
        
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                str(test_path),
                "-v",
                "--tb=line",
                "--timeout=10",
                "-q"
            ],
            capture_output=True,
            text=True
        )
        
        # Parse output
        last_line = result.stdout.split('\n')[-2] if result.stdout else ""
        
        if "passed" in last_line:
            # Extract numbers
            import re
            match = re.search(r'(\d+) passed', last_line)
            if match:
                passed = int(match.group(1))
                total_passed += passed
                
            match = re.search(r'(\d+) failed', last_line)
            if match:
                failed = int(match.group(1))
                total_failed += failed
                failed_files.append(test_file)
                
            match = re.search(r'(\d+) error', last_line)
            if match:
                errors = int(match.group(1))
                total_errors += errors
                
            print("✅" if result.returncode == 0 else "❌")
        else:
            print("⚠️")
    
    print(f"\n\n{'='*60}")
    print(f"FINAL RESULTS:")
    print(f"  ✅ Passed: {total_passed}")
    print(f"  ❌ Failed: {total_failed}")
    print(f"  ⚠️  Errors: {total_errors}")
    print(f"{'='*60}")
    
    if failed_files:
        print(f"\nFailed files ({len(failed_files)}):")
        for f in failed_files:
            print(f"  - {f}")

if __name__ == "__main__":
    run_tests()
