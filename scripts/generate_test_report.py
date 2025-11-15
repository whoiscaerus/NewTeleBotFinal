#!/usr/bin/env python3
"""
Generate detailed test failure report from pytest JSON output.
Saves to TEST_FAILURES_DETAILED.md in repo root for easy review.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def parse_pytest_json(json_file: str) -> dict:
    """Parse pytest JSON report."""
    try:
        with open(json_file) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️ {json_file} not found")
        return None


def group_failures_by_module(tests: list) -> dict:
    """Group test failures by module."""
    failures = defaultdict(list)
    for test in tests:
        if test["outcome"] == "failed":
            # Extract module name from test nodeid
            module = test["nodeid"].split("::")[0].replace("backend/tests/", "")
            failures[module].append(test)
    return failures


def generate_report(json_file: str, output_file: str):
    """Generate detailed failure report."""

    # Parse JSON
    data = parse_pytest_json(json_file)

    # Handle missing JSON file
    if data is None:
        print("⚠️ Cannot generate report without pytest JSON output")
        print(f"   Tried: {json_file}")
        print("   Make sure pytest runs with --json-report flag")
        return

    # Get summary
    summary = data.get("summary", {})
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    skipped = summary.get("skipped", 0)
    errors = summary.get("error", 0)

    # Get tests
    tests = data.get("tests", [])

    # Group failures
    failures_by_module = group_failures_by_module(tests)

    # Generate markdown report
    report = []
    report.append("# 🧪 Test Failure Report\n")
    report.append(f"**Generated**: {datetime.now().isoformat()}\n")
    report.append(
        f"**GitHub Actions Run**: {Path('GITHUB_ACTIONS_RUN_URL').read_text().strip() if Path('GITHUB_ACTIONS_RUN_URL').exists() else 'Unknown'}\n\n"
    )

    # Summary section
    report.append("## 📊 Summary\n")
    report.append(f"- **Total Tests**: {total}\n")
    report.append(f"- ✅ **Passed**: {passed}\n")
    report.append(f"- ❌ **Failed**: {failed}\n")
    report.append(f"- ⏭️ **Skipped**: {skipped}\n")
    report.append(f"- 💥 **Errors**: {errors}\n")
    # Fix division by zero
    if total > 0:
        report.append(f"- **Pass Rate**: {(passed/total*100):.1f}%\n\n")
    else:
        report.append("- **Pass Rate**: N/A (no tests collected)\n\n")

    # Quick summary table
    if failures_by_module:
        report.append("## 🚨 Failures by Module\n\n")
        report.append("| Module | Count | Tests |\n")
        report.append("|--------|-------|-------|\n")

        for module in sorted(failures_by_module.keys()):
            failures = failures_by_module[module]
            test_names = ", ".join([t["nodeid"].split("::")[-1] for t in failures[:3]])
            if len(failures) > 3:
                test_names += f", ... +{len(failures)-3} more"
            report.append(f"| `{module}` | {len(failures)} | {test_names} |\n")

        report.append("\n")

    # Detailed failures
    if failures_by_module:
        report.append("## 📋 Detailed Failures\n\n")

        for module in sorted(failures_by_module.keys()):
            failures = failures_by_module[module]
            report.append(f"### {module}\n\n")

            for i, test in enumerate(failures, 1):
                test_name = test["nodeid"].split("::")[-1]
                report.append(f"#### {i}. {test_name}\n\n")
                report.append(f"**Test Path**: `{test['nodeid']}`\n\n")

                # Get failure info
                if "call" in test and test["call"].get("longrepr"):
                    report.append("**Error**:\n```\n")
                    report.append(test["call"]["longrepr"][:500])  # First 500 chars
                    if len(test["call"]["longrepr"]) > 500:
                        report.append("\n... (truncated)")
                    report.append("\n```\n\n")

                # Get assertion details
                if "call" in test:
                    call = test["call"]
                    if call.get("outcome") == "failed":
                        if "longreprtext" in call:
                            report.append("**Details**:\n```\n")
                            report.append(call["longreprtext"][:300])
                            report.append("\n```\n\n")

    # No failures section
    if failed == 0 and errors == 0:
        report.append("## ✅ All Tests Passed!\n\n")
        report.append(f"🎉 **{passed} tests passed** with 0 failures!\n\n")

    # How to fix section
    report.append("## 🔧 How to Fix\n\n")
    report.append("1. **Read the error message** in each failure above\n")
    report.append(
        "2. **Identify the root cause** (wrong assertion, missing data, etc.)\n"
    )
    report.append("3. **Run locally** to reproduce:\n")
    report.append("   ```bash\n")
    report.append("   .venv/Scripts/python.exe -m pytest <test-path> -xvs\n")
    report.append("   ```\n")
    report.append("4. **Fix the code** based on error\n")
    report.append("5. **Commit & push** to GitHub → CI/CD re-runs automatically\n\n")

    # Footer
    report.append("---\n")
    report.append("*Report generated by GitHub Actions CI/CD pipeline*\n")

    # Write report
    with open(output_file, "w") as f:
        f.writelines(report)

    print(f"✅ Report saved: {output_file}")
    print(f"📊 Summary: {passed} passed, {failed} failed, {skipped} skipped")


if __name__ == "__main__":
    # Default paths - pytest-json-report outputs to repo root by default
    json_report = "test_results.json"
    output_report = "TEST_FAILURES_DETAILED.md"

    # Check if pytest JSON exists
    if not Path(json_report).exists():
        print(f"⚠️ {json_report} not found, trying alternate paths...")
        # Try alternate locations
        for alt_path in [
            "backend/tests/.pytest_cache/test_results.json",
            "backend/test_results.json",
            ".pytest_cache/test_results.json",
            ".pytest_results.json",
        ]:
            if Path(alt_path).exists():
                json_report = alt_path
                print(f"   ✅ Found: {json_report}")
                break
        else:
            print("   ⚠️ No JSON report found in any location")
            print("   This can happen if pytest didn't complete or JSON plugin failed")
            # Create a minimal report anyway
            with open(output_report, "w") as f:
                f.write("# 🧪 Test Failure Report\n\n")
                f.write("⚠️ **Report Generation Issue**\n\n")
                f.write("The pytest JSON report was not found. This can happen if:\n")
                f.write("- pytest-json-report plugin failed to install\n")
                f.write("- pytest didn't complete successfully\n")
                f.write("- Tests were skipped or collection failed\n\n")
                f.write("Check the GitHub Actions logs for details.\n")
            print(f"Created minimal report: {output_report}")
            sys.exit(0)

    generate_report(json_report, output_report)
