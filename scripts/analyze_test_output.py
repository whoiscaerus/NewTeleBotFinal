#!/usr/bin/env python3
"""
Comprehensive Test Output Analysis Script

Parses pytest JSON output and generates detailed failure reports
with per-test, per-file debugging information.

Usage:
    python scripts/analyze_test_output.py --json output.json --output report.md
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


class TestAnalyzer:
    """Analyze pytest test results and generate detailed reports."""

    def __init__(self, json_file: str):
        """Initialize analyzer with test results."""
        self.json_file = Path(json_file)
        self.results = self._load_results()
        self.failures_by_file: dict[str, list[dict]] = defaultdict(list)
        self.errors_by_file: dict[str, list[dict]] = defaultdict(list)
        self.skipped_by_file: dict[str, list[dict]] = defaultdict(list)
        self._organize_results()

    def _load_results(self) -> dict[str, Any]:
        """Load JSON test results."""
        try:
            with open(self.json_file) as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Error: File not found: {self.json_file}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ Error: Invalid JSON: {e}")
            sys.exit(1)

    def _organize_results(self):
        """Organize test results by file and status."""
        for test in self.results.get("tests", []):
            file_path = test.get("file", "unknown")
            outcome = test.get("outcome", "unknown")

            if outcome == "failed":
                self.failures_by_file[file_path].append(test)
            elif outcome == "error":
                self.errors_by_file[file_path].append(test)
            elif outcome == "skipped":
                self.skipped_by_file[file_path].append(test)

    def generate_markdown_report(self, output_file: str):
        """Generate comprehensive markdown report."""
        lines = []

        # Header
        lines.append("# Comprehensive Test Failure Analysis\n")
        lines.append(
            f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        )

        # Summary
        summary = self.results.get("summary", {})
        lines.append("## Executive Summary\n")
        lines.append(f"- **Total Tests**: {summary.get('total', 0)}")
        lines.append(f"- **Passed**: {summary.get('passed', 0)} ✅")
        lines.append(f"- **Failed**: {summary.get('failed', 0)} ❌")
        lines.append(f"- **Errors**: {summary.get('errors', 0)} 🔥")
        lines.append(f"- **Skipped**: {summary.get('skipped', 0)} ⏭️")
        lines.append(f"- **Duration**: {summary.get('duration', 0):.2f}s\n")

        # Pass rate
        total = summary.get("total", 1)
        passed = summary.get("passed", 0)
        pass_rate = (passed / total * 100) if total > 0 else 0
        lines.append(f"**Pass Rate**: {pass_rate:.1f}% ({passed}/{total})\n")

        # Failures section
        if self.failures_by_file:
            lines.append("## Failures by File\n")
            for file_path in sorted(self.failures_by_file.keys()):
                tests = self.failures_by_file[file_path]
                lines.append(f"### {file_path}\n")
                lines.append(f"**Count**: {len(tests)} failed\n")

                for test in tests:
                    lines.append(f"#### {test.get('name', 'unknown')}\n")
                    lines.append("**Status**: ❌ FAILED\n")

                    if "error" in test:
                        error_msg = test["error"]
                        lines.append("**Error Message**:\n")
                        lines.append(f"```\n{error_msg}\n```\n")

                    if "assertion" in test:
                        lines.append("**Assertion Failed**:\n")
                        lines.append(f"```\n{test['assertion']}\n```\n")

                    if "traceback" in test:
                        lines.append("**Stack Trace**:\n")
                        lines.append(f"```\n{test['traceback']}\n```\n")

                    lines.append("---\n")

        # Errors section
        if self.errors_by_file:
            lines.append("## Errors by File\n")
            for file_path in sorted(self.errors_by_file.keys()):
                tests = self.errors_by_file[file_path]
                lines.append(f"### {file_path}\n")
                lines.append(f"**Count**: {len(tests)} errors\n")

                for test in tests:
                    lines.append(f"#### {test.get('name', 'unknown')}\n")
                    lines.append("**Status**: 🔥 ERROR\n")

                    if "error" in test:
                        lines.append("**Error Message**:\n")
                        lines.append(f"```\n{test['error']}\n```\n")

                    if "traceback" in test:
                        lines.append("**Stack Trace**:\n")
                        lines.append(f"```\n{test['traceback']}\n```\n")

                    lines.append("---\n")

        # Skipped section
        if self.skipped_by_file:
            lines.append("## Skipped Tests by File\n")
            for file_path in sorted(self.skipped_by_file.keys()):
                tests = self.skipped_by_file[file_path]
                lines.append(f"### {file_path}\n")
                lines.append(f"**Count**: {len(tests)} skipped\n")

                for test in tests:
                    reason = test.get("reason", "No reason provided")
                    lines.append(f"- `{test.get('name', 'unknown')}`: {reason}\n")

                lines.append("\n")

        # Statistics section
        lines.append("## Statistics\n")
        lines.append(f"**Files with Failures**: {len(self.failures_by_file)}\n")
        lines.append(f"**Files with Errors**: {len(self.errors_by_file)}\n")
        lines.append(f"**Files with Skipped**: {len(self.skipped_by_file)}\n\n")

        # Error patterns section
        lines.append("## Common Error Patterns\n")
        error_patterns = self._analyze_error_patterns()
        for pattern, count in sorted(error_patterns.items(), key=lambda x: -x[1]):
            lines.append(f"- `{pattern}`: {count} occurrences\n")

        lines.append("\n---\n")
        lines.append(f"*Report generated on {datetime.now().isoformat()}*\n")

        # Write report
        with open(output_file, "w") as f:
            f.writelines(lines)

        print(f"✅ Report generated: {output_file}")

    def generate_csv_report(self, output_file: str):
        """Generate CSV report with per-test details."""
        import csv

        rows = []
        rows.append(
            ["file", "test_name", "status", "error_type", "error_message", "duration"]
        )

        for test in self.results.get("tests", []):
            if test.get("outcome") != "passed":
                rows.append(
                    [
                        test.get("file", ""),
                        test.get("name", ""),
                        test.get("outcome", ""),
                        test.get("error_type", ""),
                        test.get("error", "").split("\n")[0][
                            :100
                        ],  # First line, truncated
                        test.get("duration", ""),
                    ]
                )

        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)

        print(f"✅ CSV report generated: {output_file}")

    def _analyze_error_patterns(self) -> dict[str, int]:
        """Analyze common error patterns."""
        patterns = defaultdict(int)

        for tests in [*self.failures_by_file.values(), *self.errors_by_file.values()]:
            for test in tests:
                error = test.get("error", "")
                if "AssertionError" in error:
                    patterns["AssertionError"] += 1
                if "TypeError" in error:
                    patterns["TypeError"] += 1
                if "ValueError" in error:
                    patterns["ValueError"] += 1
                if "KeyError" in error:
                    patterns["KeyError"] += 1
                if "AttributeError" in error:
                    patterns["AttributeError"] += 1
                if "ConnectionError" in error:
                    patterns["ConnectionError"] += 1
                if "TimeoutError" in error:
                    patterns["TimeoutError"] += 1
                if "ImportError" in error or "ModuleNotFoundError" in error:
                    patterns["ImportError"] += 1

        return patterns

    def print_summary(self):
        """Print summary to console."""
        summary = self.results.get("summary", {})
        print("\n" + "=" * 60)
        print("TEST RESULTS SUMMARY")
        print("=" * 60)
        print(f"Total Tests:    {summary.get('total', 0)}")
        print(f"Passed:         {summary.get('passed', 0)} ✅")
        print(f"Failed:         {summary.get('failed', 0)} ❌")
        print(f"Errors:         {summary.get('errors', 0)} 🔥")
        print(f"Skipped:        {summary.get('skipped', 0)} ⏭️")
        print(f"Duration:       {summary.get('duration', 0):.2f}s")
        print("=" * 60 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze pytest JSON output and generate detailed reports"
    )
    parser.add_argument("--json", required=True, help="Path to pytest JSON output")
    parser.add_argument("--output", default="test_report.md", help="Output report file")
    parser.add_argument("--csv", help="Generate CSV report at specified path")

    args = parser.parse_args()

    analyzer = TestAnalyzer(args.json)
    analyzer.print_summary()
    analyzer.generate_markdown_report(args.output)

    if args.csv:
        analyzer.generate_csv_report(args.csv)


if __name__ == "__main__":
    main()
