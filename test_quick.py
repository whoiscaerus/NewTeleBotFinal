#!/usr/bin/env python3
"""
Quick targeted test runner - runs only tests for recently fixed code.
Usage: python test_quick.py [module_name]

Available modules:
  data_pipeline    - SymbolPrice, OHLCCandle, DataPullLog (66 tests, 1-2 min)
  position         - OpenPosition model (9 tests, 15 sec)
  trade_store      - Trade, Position, EquityPoint, ValidationLog (34 tests, 1-2 min)
  decision_logs    - DecisionLog model (20 tests, 30 sec)
  rate_limit       - Rate limiting logic (11 tests, 2 min)
  poll             - Poll functionality (7 tests, 1 min)
  integration      - Integration workflows (7 tests, 30 sec)
  schema           - ALL schema tests combined (129 tests, 2-3 min)
  all              - ALL critical tests (188 tests, 5-10 min)
  full             - FULL suite (6400+ tests, 1+ hour)

Examples:
  python test_quick.py data_pipeline   # Test data pipeline only
  python test_quick.py schema          # Test all schema-related fixes
  python test_quick.py all             # Test all critical fixes
  python test_quick.py full            # Run full test suite before commit
"""

import subprocess
import sys

# Define test targets - grouped by feature area
TEST_MODULES = {
    "data_pipeline": [
        "backend/tests/test_data_pipeline.py",
    ],
    "position": [
        "backend/tests/integration/test_position_monitor.py",
    ],
    "trade_store": [
        "backend/tests/test_pr_016_trade_store.py",
    ],
    "decision_logs": [
        "backend/tests/test_decision_logs.py",
    ],
    "rate_limit": [
        "backend/tests/test_pr_005_ratelimit.py",
    ],
    "poll": [
        "backend/tests/test_poll_v2.py",
    ],
    "integration": [
        "backend/tests/test_pr_017_018_integration.py",
    ],
    "schema": [
        "backend/tests/test_data_pipeline.py",
        "backend/tests/integration/test_position_monitor.py",
        "backend/tests/test_pr_016_trade_store.py",
        "backend/tests/test_decision_logs.py",
    ],
    "all": [
        "backend/tests/test_data_pipeline.py",
        "backend/tests/integration/test_position_monitor.py",
        "backend/tests/test_pr_016_trade_store.py",
        "backend/tests/test_decision_logs.py",
        "backend/tests/test_pr_005_ratelimit.py",
        "backend/tests/test_poll_v2.py",
        "backend/tests/test_pr_017_018_integration.py",
    ],
    "full": [
        "backend/tests",
    ],
}


def print_available():
    """Print available test modules."""
    print("\n" + "=" * 80)
    print("⚡ Available Test Suites")
    print("=" * 80)
    for name in sorted(TEST_MODULES.keys()):
        print(f"  python test_quick.py {name}")
    print("=" * 80 + "\n")


def run_tests(module_name):
    """Run pytest on specified test module."""
    if module_name not in TEST_MODULES:
        print(f"\n❌ Unknown module: {module_name}\n")
        print_available()
        return 1

    test_paths = TEST_MODULES[module_name]

    cmd = [
        ".venv/Scripts/python.exe" if sys.platform == "win32" else "python",
        "-m",
        "pytest",
        *test_paths,
        "-v",
        "--tb=short",
        "--maxfail=5",
    ]

    print("\n" + "=" * 80)
    print(f"🧪 Testing: {module_name.upper()}")
    print("=" * 80)
    print(f"Running: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED!")
        print("=" * 80 + "\n")
    else:
        print("\n" + "=" * 80)
        print("❌ SOME TESTS FAILED - See output above")
        print("=" * 80 + "\n")

    return result.returncode


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print_available()
        return 1

    module = sys.argv[1].lower()
    return run_tests(module)


if __name__ == "__main__":
    sys.exit(main())
