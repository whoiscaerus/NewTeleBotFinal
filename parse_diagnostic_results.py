#!/usr/bin/env python3
"""Parse full diagnostic test run results and generate comprehensive summary."""

import re
from collections import defaultdict
from pathlib import Path


def parse_test_output(log_file: Path) -> dict:
    """Parse pytest output log and extract test statistics."""
    with open(log_file) as f:
        content = f.read()

    # Extract test results using regex
    passed = len(re.findall(r"PASSED", content))
    failed = len(re.findall(r"FAILED", content))
    error = len(re.findall(r"ERROR", content))
    timeout = len(re.findall(r"Timeout", content))

    # Extract test names and their outcomes
    results = {"passed": [], "failed": [], "error": [], "timeout": []}

    for line in content.split("\n"):
        if "PASSED" in line:
            # Extract test name
            match = re.search(r"backend/tests/.*?(?=\s+PASSED)", line)
            if match:
                results["passed"].append(match.group(0))
        elif "FAILED" in line:
            match = re.search(r"backend/tests/.*?(?=\s+FAILED)", line)
            if match:
                results["failed"].append(match.group(0))
        elif "ERROR" in line and "::" in line:
            match = re.search(r"backend/tests/.*?(?=\s+ERROR)", line)
            if match:
                results["error"].append(match.group(0))
        elif "Timeout" in line:
            match = re.search(r"backend/tests/.*?(?=\s+\+)", line)
            if match:
                results["timeout"].append(match.group(0))

    return {
        "total_passed": passed,
        "total_failed": failed,
        "total_error": error,
        "total_timeout": timeout,
        "test_results": results,
    }


def generate_summary_report():
    """Generate comprehensive test results summary."""
    log_file = Path(
        "C:\\Users\\FCumm\\Downloads\\full-diagnostic-results (1)\\full_test_run_output.log"
    )

    if not log_file.exists():
        print(f"❌ Log file not found: {log_file}")
        return

    with open(log_file) as f:
        content = f.read()

    # Look for pytest summary line
    summary_match = re.search(
        r"(\d+) passed(?:, (\d+) failed)?(?:, (\d+) error)?(?:, (\d+) skipped)?",
        content,
    )

    report = []
    report.append("\n" + "=" * 80)
    report.append("COMPREHENSIVE TEST EXECUTION REPORT")
    report.append("=" * 80 + "\n")

    if summary_match:
        passed = int(summary_match.group(1)) if summary_match.group(1) else 0
        failed = int(summary_match.group(2)) if summary_match.group(2) else 0
        error = int(summary_match.group(3)) if summary_match.group(3) else 0
        skipped = int(summary_match.group(4)) if summary_match.group(4) else 0
        total = passed + failed + error + skipped

        report.append(f"Total Tests:      {total}")
        report.append(f"✅ Passed:        {passed:,}")
        report.append(f"❌ Failed:        {failed:,}")
        report.append(f"⚠️  Errors:        {error:,}")
        report.append(f"⏭️  Skipped:       {skipped:,}\n")
        report.append(f"Pass Rate:        {(passed/total*100):.1f}%")
    else:
        report.append("⚠️ Could not parse summary from log file")

    report.append("\n" + "=" * 80)
    report.append("FAILURE DETAILS")
    report.append("=" * 80 + "\n")

    # Extract failed tests
    failed_tests = re.findall(r"(backend/tests/[^\s]+)\s+FAILED\s+\[.*?\]", content)

    if failed_tests:
        report.append(f"FAILED TESTS ({len(set(failed_tests))} unique):\n")
        for test in sorted(set(failed_tests)):
            report.append(f"  ❌ {test}")
    else:
        report.append("✅ No failed tests found!\n")

    # Extract error tests
    report.append("\n" + "-" * 80)
    error_tests = re.findall(r"(backend/tests/[^\s]+)\s+ERROR\s+\[.*?\]", content)

    if error_tests:
        report.append(f"\nERROR TESTS ({len(set(error_tests))} unique):\n")
        for test in sorted(set(error_tests)):
            report.append(f"  ⚠️  {test}")
    else:
        report.append("\n✅ No error tests found!\n")

    # Extract timeout tests
    report.append("\n" + "-" * 80)
    timeout_matches = re.findall(r"(backend/tests/[^\s]+)\s+.*?(?:Timeout)", content)

    if timeout_matches:
        report.append(f"\nTIMEOUT TESTS ({len(set(timeout_matches))} unique):\n")
        for test in sorted(set(timeout_matches)):
            report.append(f"  ⏱️  {test}")
    else:
        report.append("\n✅ No timeout tests found!\n")

    # Test file statistics
    report.append("\n" + "=" * 80)
    report.append("TEST FILE BREAKDOWN")
    report.append("=" * 80 + "\n")

    file_stats = defaultdict(lambda: {"passed": 0, "failed": 0, "error": 0})

    for line in content.split("\n"):
        if "PASSED" in line or "FAILED" in line or "ERROR" in line:
            match = re.search(r"backend/tests/([^/]+)/([^:]+)::", line)
            if match:
                category = match.group(1)
                file_name = match.group(2)
                key = f"{category}/{file_name}.py"

                if "PASSED" in line:
                    file_stats[key]["passed"] += 1
                elif "FAILED" in line:
                    file_stats[key]["failed"] += 1
                elif "ERROR" in line:
                    file_stats[key]["error"] += 1

    for file_path in sorted(file_stats.keys()):
        stats = file_stats[file_path]
        total_file = stats["passed"] + stats["failed"] + stats["error"]
        report.append(
            f"{file_path:40} | ✅ {stats['passed']:3} | ❌ {stats['failed']:2} | ⚠️  {stats['error']:2} | Total: {total_file:3}"
        )

    # Print and save report
    report_text = "\n".join(report)
    print(report_text)

    # Save to file
    with open(
        "C:\\Users\\FCumm\\NewTeleBotFinal\\TEST_DIAGNOSTIC_SUMMARY.txt", "w"
    ) as f:
        f.write(report_text)

    print(
        "\n✅ Report saved to: C:\\Users\\FCumm\\NewTeleBotFinal\\TEST_DIAGNOSTIC_SUMMARY.txt"
    )


if __name__ == "__main__":
    generate_summary_report()
