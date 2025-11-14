"""
Run all tests in batches with real-time progress reporting.
Shows: current file, pass/fail counts, estimated completion time.
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime
import time

def run_batch(files, batch_num, total_batches):
    """Run a batch of test files and return results"""
    cmd = [
        sys.executable, "-m", "pytest",
        *files,
        "-p", "no:pytest_ethereum",
        "--tb=no",
        "--timeout=10",
        "-q",
        "--maxfail=999"
    ]
    
    print(f"\n{'='*60}")
    print(f"BATCH {batch_num}/{total_batches}: Testing {len(files)} files")
    print(f"{'='*60}")
    
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
    elapsed = time.time() - start
    
    # Parse results from output
    output = result.stdout + result.stderr
    
    # Look for "X passed" and "Y failed" in output
    import re
    passed_match = re.search(r'(\d+) passed', output)
    failed_match = re.search(r'(\d+) failed', output)
    error_match = re.search(r'(\d+) error', output)
    
    passed = int(passed_match.group(1)) if passed_match else 0
    failed = int(failed_match.group(1)) if failed_match else 0
    errors = int(error_match.group(1)) if error_match else 0
    
    print(f"Results: {passed} passed, {failed} failed, {errors} errors ({elapsed:.1f}s)")
    
    return {
        'passed': passed,
        'failed': failed,
        'errors': errors,
        'elapsed': elapsed,
        'files': files
    }


def main():
    print("\n" + "="*60)
    print("ALL TESTS RUNNER - WITH PROGRESS")
    print("="*60)
    
    test_dir = Path("backend/tests")
    all_files = sorted(test_dir.glob("test_*.py"))
    
    print(f"\nTotal test files: {len(all_files)}")
    print(f"Batch size: 10 files per batch")
    print(f"Starting at: {datetime.now().strftime('%H:%M:%S')}\n")
    
    # Split into batches of 10
    batch_size = 10
    batches = [all_files[i:i+batch_size] for i in range(0, len(all_files), batch_size)]
    
    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_time = 0
    
    batch_results = []
    
    for i, batch in enumerate(batches, 1):
        batch_files = [str(f) for f in batch]
        result = run_batch(batch_files, i, len(batches))
        
        total_passed += result['passed']
        total_failed += result['failed']
        total_errors += result['errors']
        total_time += result['elapsed']
        
        batch_results.append(result)
        
        # Show running totals
        total_tests = total_passed + total_failed + total_errors
        pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        
        print(f"\n📊 RUNNING TOTALS:")
        print(f"   Tests: {total_tests} ({total_passed} passed, {total_failed} failed, {total_errors} errors)")
        print(f"   Pass rate: {pass_rate:.1f}%")
        print(f"   Time: {total_time:.1f}s")
        
        # Estimate time remaining
        avg_batch_time = total_time / i
        batches_remaining = len(batches) - i
        est_remaining = avg_batch_time * batches_remaining
        
        if batches_remaining > 0:
            print(f"   Estimated time remaining: {est_remaining/60:.1f} minutes")
    
    # Final summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    print(f"Total tests: {total_passed + total_failed + total_errors}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    print(f"Errors: {total_errors}")
    print(f"Pass rate: {total_passed/(total_passed+total_failed+total_errors)*100:.1f}%")
    print(f"Total time: {total_time/60:.1f} minutes")
    print("="*60)
    
    # Show worst performing batches
    print("\nWorst performing batches:")
    sorted_batches = sorted(batch_results, key=lambda x: x['failed'] + x['errors'], reverse=True)
    for result in sorted_batches[:5]:
        fail_count = result['failed'] + result['errors']
        if fail_count > 0:
            print(f"  {fail_count} failures in: {', '.join([Path(f).name for f in result['files'][:3]])}")


if __name__ == "__main__":
    main()
