#!/usr/bin/env python
"""PR-012 Verification Script - Market Hours & Timezone Gating

Quick verification that all PR-012 deliverables are in place and working.
Run from project root: python scripts/verify/verify-pr-012.sh
"""

import subprocess
import sys
from pathlib import Path


def verify_files_exist():
    """Verify all required files exist."""
    print("\n" + "=" * 60)
    print("VERIFYING PR-012 FILES")
    print("=" * 60)

    files = [
        "backend/app/trading/time/__init__.py",
        "backend/app/trading/time/market_calendar.py",
        "backend/app/trading/time/tz.py",
        "backend/tests/test_market_calendar.py",
        "docs/prs/PR-012-IMPLEMENTATION-PLAN.md",
        "docs/prs/PR-012-IMPLEMENTATION-COMPLETE.md",
    ]

    all_exist = True
    for file in files:
        path = Path(file)
        if path.exists():
            size = path.stat().st_size
            print(f"✅ {file:<50} ({size:,} bytes)")
        else:
            print(f"❌ {file:<50} MISSING")
            all_exist = False

    return all_exist


def run_tests():
    """Run test suite."""
    print("\n" + "=" * 60)
    print("RUNNING PR-012 TESTS")
    print("=" * 60 + "\n")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests/test_market_calendar.py",
            "-v",
            "--tb=short",
            "--cov=backend/app/trading/time",
            "--cov-report=term",
        ],
        capture_output=False,
        text=True,
    )

    return result.returncode == 0


def verify_imports():
    """Verify all imports work."""
    print("\n" + "=" * 60)
    print("VERIFYING PR-012 IMPORTS")
    print("=" * 60)

    try:
        from backend.app.trading.time import MarketCalendar

        print("✅ All imports successful")

        # Quick sanity check
        from datetime import datetime

        import pytz

        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        is_open = MarketCalendar.is_market_open("GOLD", dt)
        print(f"✅ is_market_open('GOLD', 2025-10-27 10:00 UTC) = {is_open}")

        session = MarketCalendar.get_session("NASDAQ")
        print(f"✅ get_session('NASDAQ') = {session.name}")

        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all verifications."""
    print("\n" + "█" * 60)
    print("█ PR-012: Market Hours & Timezone Gating - VERIFICATION")
    print("█" * 60)

    checks = [
        ("Files Exist", verify_files_exist),
        ("Imports Work", verify_imports),
        ("All Tests Pass", run_tests),
    ]

    results = {}
    for name, check in checks:
        try:
            results[name] = check()
        except Exception as e:
            print(f"\n❌ {name} failed: {e}")
            import traceback

            traceback.print_exc()
            results[name] = False

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(results.values())

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 PR-012 VERIFICATION COMPLETE - ALL CHECKS PASSED")
        print("=" * 60)
        return 0
    else:
        print("❌ PR-012 VERIFICATION FAILED - SEE ABOVE FOR DETAILS")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
