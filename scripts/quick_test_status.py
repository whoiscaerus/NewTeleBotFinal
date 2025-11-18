#!/usr/bin/env python3
"""
Quick test status analyzer - runs a subset and reports pass/fail
"""
import subprocess
import sys
from pathlib import Path


def run_test_file(test_file):
    """Run a single test file and return pass/fail counts"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "-v", "--tb=no", "-q"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        output = result.stdout + result.stderr
        passed = output.count(" PASSED")
        failed = output.count(" FAILED")
        error = output.count(" ERROR")

        return passed, failed, error
    except subprocess.TimeoutExpired:
        return 0, 0, 999  # 999 = timeout
    except Exception:
        return 0, 0, -1  # -1 = error


def main():
    # Test files to check
    test_files = [
        "backend/tests/test_auth.py",
        "backend/tests/test_cache.py",
        "backend/tests/test_cache_standalone.py",
        "backend/tests/test_copy.py",
        "backend/tests/test_dashboard_ws.py",
    ]

    print("=" * 80)
    print("QUICK TEST STATUS CHECK")
    print("=" * 80)
    print()

    total_passed = 0
    total_failed = 0
    total_error = 0

    for test_file in test_files:
        if not Path(test_file).exists():
            print(f"SKIP  {test_file:40s} (not found)")
            continue

        print(f"Running {test_file}...", end=" ", flush=True)
        passed, failed, error = run_test_file(test_file)

        if error == 999:
            print("TIMEOUT")
        elif error == -1:
            print("ERROR")
        else:
            status = "OK" if failed == 0 and error == 0 else "FAIL"
            print(f"{status:4s}  P:{passed:3d}  F:{failed:3d}  E:{error:3d}")
            total_passed += passed
            total_failed += failed
            total_error += error

    print()
    print("=" * 80)
    print(
        f"TOTALS: {total_passed:3d} PASSED | {total_failed:3d} FAILED | {total_error:3d} ERROR"
    )
    print("=" * 80)


if __name__ == "__main__":
    main()
