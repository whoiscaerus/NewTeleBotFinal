#!/usr/bin/env python3
"""Parse test results and generate detailed report."""

import json
import sys
from collections import defaultdict
from pathlib import Path


def parse_test_results():
    """Parse test_results.json and generate comprehensive report."""

    result_file = Path("test_results.json")
    if not result_file.exists():
        print("Waiting for test_results.json to be created...")
        return False

    try:
        with open(result_file) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print("test_results.json is being written, please wait...")
        return False

    # Extract summary
    summary = data.get("summary", {})
    tests = data.get("tests", [])

    print("\n" + "=" * 80)
    print("COMPREHENSIVE TEST RESULTS REPORT")
    print("=" * 80)

    # Overall stats
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    errors = summary.get("error", 0)
    skipped = summary.get("skipped", 0)

    print("\nOVERALL RESULTS:")
    print(f"  Total Tests:    {total}")
    print(f"  PASSED:         {passed} ({passed*100/total if total else 0:.1f}%)")
    print(f"  FAILED:         {failed} ({failed*100/total if total else 0:.1f}%)")
    print(f"  ERROR:          {errors} ({errors*100/total if total else 0:.1f}%)")
    print(f"  SKIPPED:        {skipped} ({skipped*100/total if total else 0:.1f}%)")

    # Group by test file
    by_file = defaultdict(lambda: {"passed": 0, "failed": 0, "error": 0, "skipped": 0})
    failed_tests = []
    error_tests = []

    for test in tests:
        outcome = test.get("outcome", "unknown")
        nodeid = test.get("nodeid", "")
        file_path = nodeid.split("::")[0] if "::" in nodeid else nodeid

        by_file[file_path][outcome] += 1

        if outcome == "failed":
            failed_tests.append(
                {
                    "name": test.get("nodeid", ""),
                    "error": test.get("call", {}).get("longrepr", "No error details"),
                }
            )
        elif outcome == "error":
            error_tests.append(
                {
                    "name": test.get("nodeid", ""),
                    "error": test.get("setup", {}).get(
                        "longrepr",
                        test.get("call", {}).get("longrepr", "No error details"),
                    ),
                }
            )

    # Print by file
    print("\n" + "=" * 80)
    print("RESULTS BY TEST FILE:")
    print("=" * 80)

    for file_path in sorted(by_file.keys()):
        stats = by_file[file_path]
        file_total = sum(stats.values())
        file_passed = stats["passed"]
        file_failed = stats["failed"]
        file_error = stats["error"]

        status = "✅" if file_failed + file_error == 0 else "❌"
        print(f"\n{status} {Path(file_path).name}")
        print(
            f"   PASSED: {file_passed:4d} | FAILED: {file_failed:4d} | ERROR: {file_error:4d} | Total: {file_total:4d}"
        )

    # Print failed tests with details
    if failed_tests:
        print("\n" + "=" * 80)
        print(f"FAILED TESTS ({len(failed_tests)} total):")
        print("=" * 80)
        for i, test in enumerate(failed_tests[:20], 1):  # Show first 20
            print(f"\n{i}. {test['name']}")
            error_lines = test["error"].split("\n")[:5]  # First 5 lines
            for line in error_lines:
                print(f"   {line}")
            if len(test["error"].split("\n")) > 5:
                line_count = len(test["error"].split("\n")) - 5
                print(f"   ... ({line_count} more lines)")

    # Print error tests with details
    if error_tests:
        print("\n" + "=" * 80)
        print(f"ERROR TESTS ({len(error_tests)} total):")
        print("=" * 80)
        for i, test in enumerate(error_tests[:20], 1):  # Show first 20
            print(f"\n{i}. {test['name']}")
            error_lines = test["error"].split("\n")[:5]  # First 5 lines
            for line in error_lines:
                print(f"   {line}")
            if len(test["error"].split("\n")) > 5:
                line_count = len(test["error"].split("\n")) - 5
                print(f"   ... ({line_count} more lines)")

    print("\n" + "=" * 80)
    return True


if __name__ == "__main__":
    if parse_test_results():
        print("\nReport generated successfully!")
    else:
        print("Could not parse results yet. Wait for tests to complete.")
        sys.exit(1)
