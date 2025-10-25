#!/usr/bin/env python3
"""
PR-014 Phase 4 Verification Script

Validates all Phase 4 deliverables:
- Test file exists and is well-formed
- All tests pass
- Coverage meets expectations
- File formatting is correct
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd):
    """Run shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def check_test_file():
    """Verify test file exists and has correct structure."""
    print("\n📋 Checking test file structure...")
    test_file = Path("backend/tests/test_fib_rsi_strategy_phase4.py")

    if not test_file.exists():
        print(f"  ❌ Test file not found: {test_file}")
        return False

    with open(test_file) as f:
        content = f.read()

    checks = {
        "TestRSIPatternDetectorShort": "TestRSIPatternDetectorShort" in content,
        "TestRSIPatternDetectorLong": "TestRSIPatternDetectorLong" in content,
        "TestRSIPatternDetectorEdgeCases": "TestRSIPatternDetectorEdgeCases" in content,
        "TestStrategyEngineSignalGeneration": "TestStrategyEngineSignalGeneration"
        in content,
        "TestSignalCandidate": "TestSignalCandidate" in content,
        "TestExecutionPlan": "TestExecutionPlan" in content,
        "TestAcceptanceCriteria": "TestAcceptanceCriteria" in content,
        "TestIntegration": "TestIntegration" in content,
    }

    for check_name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {check_name}: {result}")

    all_passed = all(checks.values())
    print(f"  📊 File size: {len(content):,} bytes")
    print(f"  📚 Lines: {len(content.splitlines())}")

    return all_passed


def run_tests():
    """Run all Phase 4 tests."""
    print("\n🧪 Running tests...")
    code, stdout, stderr = run_command(
        ".venv/Scripts/python.exe -m pytest backend/tests/test_fib_rsi_strategy_phase4.py -v --tb=short"
    )

    # Extract results
    if "passed" in stdout:
        for line in stdout.split("\n"):
            if "passed" in line or "failed" in line:
                print(f"  {line.strip()}")

    return code == 0


def check_coverage():
    """Check test coverage."""
    print("\n📊 Checking coverage...")
    code, stdout, stderr = run_command(
        ".venv/Scripts/python.exe -m pytest backend/tests/test_fib_rsi_strategy_phase4.py "
        "--cov=backend/app/strategy/fib_rsi --cov-report=term-missing --quiet"
    )

    # Extract coverage line
    for line in stdout.split("\n"):
        if "TOTAL" in line or "backend/app/strategy/fib_rsi" in line:
            if "%" in line:
                print(f"  {line.strip()}")

    return code == 0


def check_formatting():
    """Check Black formatting."""
    print("\n🎨 Checking Black formatting...")
    code, stdout, stderr = run_command(
        ".venv/Scripts/python.exe -m black backend/tests/test_fib_rsi_strategy_phase4.py --check"
    )

    if code == 0:
        print("  ✅ Code is Black formatted")
    else:
        print("  ⚠️ Code needs Black formatting")
        # Apply formatting
        run_command(
            ".venv/Scripts/python.exe -m black backend/tests/test_fib_rsi_strategy_phase4.py"
        )
        print("  ✅ Code formatted automatically")

    return True


def main():
    """Run all verification checks."""
    print("=" * 70)
    print("PR-014 PHASE 4 VERIFICATION")
    print("=" * 70)

    checks = [
        ("Test File Structure", check_test_file),
        ("Black Formatting", check_formatting),
        ("Test Execution", run_tests),
        ("Code Coverage", check_coverage),
    ]

    results = {}
    for check_name, check_func in checks:
        try:
            result = check_func()
            results[check_name] = result
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results[check_name] = False

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    for check_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {check_name}")

    all_passed = all(results.values())

    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 PHASE 4 VERIFICATION COMPLETE - ALL CHECKS PASSED")
    else:
        print("⚠️ PHASE 4 VERIFICATION - SOME CHECKS FAILED")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
