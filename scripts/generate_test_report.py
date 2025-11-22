#!/usr/bin/env python3
"""
Generate comprehensive test report from pytest JSON output.
Saves to TEST_RESULTS_REPORT.md and TEST_FAILURES.csv.

Usage:
    python generate_test_report.py --json test-results/test_results.json \
                                   --output test-results/TEST_RESULTS_REPORT.md \
                                   --csv test-results/TEST_FAILURES.csv
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime


def group_failures_by_module(tests: list) -> dict:
    """Group failed tests by module."""
    failures = defaultdict(list)
    for test in tests:
        outcome = test.get("outcome", "unknown")
        if outcome in ["failed", "error"]:
            nodeid = test.get("nodeid", "unknown")
            module = nodeid.split("::")[0]
            failures[module].append(test)
    return failures


def parse_pytest_json(json_file: str) -> dict:
    """Parse pytest JSON report."""
    try:
        with open(json_file) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️ {json_file} not found")
        return None
    except json.JSONDecodeError as e:
        print(f"⚠️ Invalid JSON in {json_file}: {e}")
        return None


def generate_markdown_report(data: dict, output_md: str) -> None:
    """Generate comprehensive Markdown report."""

    # Get summary
    summary = data.get("summary", {})
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    skipped = summary.get("skipped", 0)
    errors = summary.get("error", 0)
    duration = data.get("duration", 0.0)

    # Calculate pass rate
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    # Get tests and group failures
    tests = data.get("tests", [])
    failures_by_module = group_failures_by_module(tests)

    # Build report
    report = []
    report.append("# 🧪 Comprehensive Test Results Report\n")
    report.append(
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
    )

    # Summary section
    report.append("## 📊 Executive Summary\n")
    report.append("| Metric | Value |\n")
    report.append("|--------|-------|\n")
    report.append(f"| **Total Tests** | {total} |\n")
    report.append(f"| ✅ **Passed** | {passed} |\n")
    report.append(f"| ❌ **Failed** | {failed} |\n")
    report.append(f"| ⏭️ **Skipped** | {skipped} |\n")
    report.append(f"| 💥 **Errors** | {errors} |\n")
    report.append(f"| **Duration** | {duration:.2f}s |\n")
    report.append(f"| **Pass Rate** | {pass_rate:.1f}% |\n\n")

    # Status indicator
    if failed == 0 and errors == 0:
        report.append("### ✅ **Status: ALL TESTS PASSED**\n\n")
        report.append(f"🎉 Congratulations! All {total} tests passed successfully!\n\n")
    else:
        total_issues = failed + errors
        report.append(f"### ⚠️ **Status: {total_issues} Test(s) Failing**\n\n")
        report.append("Please review the failures below and fix before merging.\n\n")

    # Failures by module section
    if failures_by_module:
        report.append("## 🚨 Failures by Module\n\n")
        report.append("| Module | Failed | Error | Total Issues |\n")
        report.append("|--------|--------|-------|---------------|\n")

        for module in sorted(failures_by_module.keys()):
            module_failures = failures_by_module[module]
            fail_count = sum(1 for t in module_failures if t.get("outcome") == "failed")
            err_count = sum(1 for t in module_failures if t.get("outcome") == "error")
            total_count = len(module_failures)
            report.append(
                f"| `{module}` | {fail_count} | {err_count} | **{total_count}** |\n"
            )

        report.append("\n")

    # Test details table
    report.append("## 📋 All Test Results\n\n")
    report.append("| Test Case | Status | Duration | Error Summary |\n")
    report.append("|-----------|--------|----------|----------------|\n")

    for test in tests:
        nodeid = test.get("nodeid", "unknown")
        outcome = test.get("outcome", "unknown")
        test_duration = test.get("call", {}).get("duration", 0.0)

        # Status emoji
        if outcome == "passed":
            status = "✅ PASS"
        elif outcome == "failed":
            status = "❌ FAIL"
        elif outcome == "error":
            status = "💥 ERROR"
        elif outcome == "skipped":
            status = "⏭️ SKIP"
        else:
            status = f"❓ {outcome.upper()}"

        # Get error message
        error_msg = ""
        if "call" in test and "longrepr" in test["call"]:
            longrepr = test["call"]["longrepr"]
            if isinstance(longrepr, str):
                # Get last line of error
                lines = longrepr.strip().split("\n")
                error_msg = lines[-1] if lines else "Unknown error"
            else:
                error_msg = str(longrepr)[:100]
        elif "setup" in test and "longrepr" in test["setup"]:
            error_msg = "Setup failed"
        elif "teardown" in test and "longrepr" in test["teardown"]:
            error_msg = "Teardown failed"

        # Truncate and escape
        error_msg = error_msg.replace("|", "\\|").replace("\n", " ")
        if len(error_msg) > 80:
            error_msg = error_msg[:77] + "..."

        report.append(
            f"| `{nodeid}` | {status} | {test_duration:.4f}s | {error_msg} |\n"
        )

    report.append("\n")

    # Detailed failure section
    if failures_by_module:
        report.append("## 🔍 Detailed Failure Analysis\n\n")

        failure_index = 1
        for module in sorted(failures_by_module.keys()):
            module_failures = failures_by_module[module]
            report.append(f"### {module} ({len(module_failures)} issue(s))\n\n")

            for test in module_failures:
                nodeid = test.get("nodeid", "unknown")
                outcome = test.get("outcome", "unknown")
                test_duration = test.get("call", {}).get("duration", 0.0)

                report.append(f"#### {failure_index}. {nodeid}\n")
                report.append(f"**Status**: {outcome.upper()}\n")
                report.append(f"**Duration**: {test_duration:.4f}s\n\n")

                # Get full traceback
                longrepr = None
                if "call" in test and "longrepr" in test["call"]:
                    longrepr = test["call"]["longrepr"]
                elif "setup" in test and "longrepr" in test["setup"]:
                    longrepr = test["setup"]["longrepr"]
                    report.append("**Phase**: Setup\n\n")
                elif "teardown" in test and "longrepr" in test["teardown"]:
                    longrepr = test["teardown"]["longrepr"]
                    report.append("**Phase**: Teardown\n\n")

                if longrepr:
                    report.append("**Error Details**:\n```\n")
                    if isinstance(longrepr, str):
                        # Truncate very long tracebacks
                        lines = longrepr.split("\n")
                        if len(lines) > 50:
                            report.append("\n".join(lines[:25]))
                            report.append(
                                f"\n... ({len(lines) - 50} lines omitted) ...\n"
                            )
                            report.append("\n".join(lines[-25:]))
                        else:
                            report.append(longrepr)
                    else:
                        report.append(json.dumps(longrepr, indent=2)[:2000])
                    report.append("\n```\n\n")

                # Add captured output if available
                if "call" in test:
                    call = test["call"]

                    if call.get("stdout"):
                        report.append("**Captured Stdout**:\n```\n")
                        stdout = call["stdout"][:500]
                        report.append(stdout)
                        if len(call["stdout"]) > 500:
                            report.append("\n... (truncated)")
                        report.append("\n```\n\n")

                    if call.get("stderr"):
                        report.append("**Captured Stderr**:\n```\n")
                        stderr = call["stderr"][:500]
                        report.append(stderr)
                        if len(call["stderr"]) > 500:
                            report.append("\n... (truncated)")
                        report.append("\n```\n\n")

                    if call.get("log"):
                        report.append("**Captured Logs**:\n```\n")
                        logs = json.dumps(call["log"], indent=2)[:1000]
                        report.append(logs)
                        if len(json.dumps(call["log"], indent=2)) > 1000:
                            report.append("\n... (truncated)")
                        report.append("\n```\n\n")

                report.append("---\n\n")
                failure_index += 1

    # How to fix section
    report.append("## 🔧 How to Fix Failing Tests\n\n")
    report.append("### Quick Steps\n")
    report.append("1. **Read the error** in the detailed failure section above\n")
    report.append(
        "2. **Identify the root cause** (assertion failure, missing data, timeout, etc.)\n"
    )
    report.append("3. **Run locally** to reproduce:\n")
    report.append("   ```powershell\n")
    report.append("   .venv/Scripts/python.exe -m pytest <test_path> -xvs\n")
    report.append("   ```\n")
    report.append("4. **Fix the issue** in your code\n")
    report.append("5. **Verify locally** that the test passes\n")
    report.append(
        "6. **Commit & push** to GitHub → CI/CD will re-run automatically\n\n"
    )

    # Common issues
    report.append("### Common Issues & Solutions\n")
    report.append("| Issue | Cause | Solution |\n")
    report.append("|-------|-------|----------|\n")
    report.append(
        "| `AssertionError` | Expected value doesn't match actual | Check assertion logic and expected values |\n"
    )
    report.append(
        "| `TimeoutError` | Test took too long (>60s) | Optimize test or increase timeout |\n"
    )
    report.append(
        "| `ConnectionError` | Can't connect to service | Verify PostgreSQL/Redis are running |\n"
    )
    report.append(
        "| `KeyError` | Missing required data | Check fixture or test setup |\n"
    )
    report.append(
        "| `ImportError` | Can't import module | Check file location and PYTHONPATH |\n\n"
    )

    # Resources
    report.append("## 📚 Resources\n\n")
    report.append(
        "- **Test Command**: `.venv/Scripts/python.exe -m pytest backend/tests -v`\n"
    )
    report.append(
        "- **Coverage Report**: `coverage/backend/htmlcov/index.html` (in CI artifacts)\n"
    )
    report.append("- **Full Test Log**: `test_output.log` (in CI artifacts)\n")
    report.append(
        "- **GitHub Actions Run**: [View in Actions tab](https://github.com/who-is-caerus/NewTeleBotFinal/actions)\n\n"
    )

    # Footer
    report.append("---\n")
    report.append("*Report automatically generated by GitHub Actions CI/CD pipeline*\n")
    report.append(f"*Generated at: {datetime.now().isoformat()}*\n")

    # Write report
    with open(output_md, "w", encoding="utf-8") as f:
        f.write("".join(report))

    print(f"✅ Markdown report generated: {output_md}")


def generate_csv_report(data: dict, output_csv: str) -> None:
    """Generate CSV report for easy analysis."""

    tests = data.get("tests", [])
    csv_rows = [["Test Case", "Status", "Duration (s)", "Outcome", "Error Summary"]]

    for test in tests:
        nodeid = test.get("nodeid", "unknown")
        outcome = test.get("outcome", "unknown")
        test_duration = test.get("call", {}).get("duration", 0.0)

        # Get error message
        error_msg = ""
        if outcome in ["failed", "error"]:
            if "call" in test and "longrepr" in test["call"]:
                longrepr = test["call"]["longrepr"]
                if isinstance(longrepr, str):
                    lines = longrepr.strip().split("\n")
                    error_msg = lines[-1] if lines else "Unknown error"
                else:
                    error_msg = str(longrepr)[:200]
            elif "setup" in test and "longrepr" in test["setup"]:
                error_msg = "Setup failed"
            elif "teardown" in test and "longrepr" in test["teardown"]:
                error_msg = "Teardown failed"

        csv_rows.append(
            [
                nodeid,
                outcome.upper(),
                f"{test_duration:.4f}",
                outcome.upper(),
                error_msg[:500],  # Truncate for CSV
            ]
        )

    # Write CSV
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(csv_rows)

    print(f"✅ CSV report generated: {output_csv}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate comprehensive test report from pytest JSON output"
    )
    parser.add_argument("--json", required=True, help="Input pytest JSON report file")
    parser.add_argument("--output", required=True, help="Output Markdown report file")
    parser.add_argument("--csv", required=True, help="Output CSV file")

    args = parser.parse_args()

    # Parse JSON
    data = parse_pytest_json(args.json)

    if data is None:
        print(f"❌ Failed to parse pytest JSON from: {args.json}")
        sys.exit(1)

    # Generate reports
    generate_markdown_report(data, args.output)
    generate_csv_report(data, args.csv)

    print("\n✅ All reports generated successfully!")
