#!/usr/bin/env python3
"""
Analyze CI test results and generate fix recommendations.

Usage:
  python analyze_ci_results.py

Expected artifacts in current directory:
  - ci_collected_tests.txt
  - test_output.log
  - TEST_FAILURES_DETAILED.md
  - test_results.json (optional)
"""

import re
from collections import defaultdict


def analyze_collection(filepath: str) -> tuple[int, list[str]]:
    """Extract test count and any collection errors."""
    try:
        with open(filepath) as f:
            content = f.read()

        # Find total count (usually last line like "6424 tests in 0.50s")
        lines = content.strip().split("\n")
        test_count = 0
        errors = []

        for line in lines:
            if "tests" in line and ("passed" in line or "error" in line):
                # Extract number like "6424 tests"
                match = re.search(r"(\d+)\s+tests?", line)
                if match:
                    test_count = int(match.group(1))

            if "ERROR" in line or "error" in line:
                errors.append(line)

        return test_count, errors
    except FileNotFoundError:
        print(f"⚠️  File not found: {filepath}")
        return 0, []


def analyze_test_output(filepath: str) -> dict:
    """Extract summary stats from test output."""
    try:
        with open(filepath) as f:
            content = f.read()

        # Look for summary line like "6424 passed, 70 failed, 929 errors in 3600.50s"
        summary_match = re.search(
            r"(\d+)\s+passed(?:,\s+(\d+)\s+failed)?(?:,\s+(\d+)\s+error)?",
            content,
            re.IGNORECASE,
        )

        result = {
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "total": 0,
        }

        if summary_match:
            result["passed"] = int(summary_match.group(1))
            result["failed"] = int(summary_match.group(2) or 0)
            result["errors"] = int(summary_match.group(3) or 0)
            result["total"] = result["passed"] + result["failed"] + result["errors"]

        # Extract test execution time
        time_match = re.search(r"in\s+([\d.]+)s", content)
        if time_match:
            result["duration_seconds"] = float(time_match.group(1))

        return result
    except FileNotFoundError:
        print(f"⚠️  File not found: {filepath}")
        return {}


def analyze_failures(filepath: str) -> dict[str, list[str]]:
    """Categorize failures by module."""
    try:
        with open(filepath) as f:
            content = f.read()

        # Extract failure blocks
        failures_by_module = defaultdict(list)

        # Find sections like "### tests/test_pr_016_trade_store.py"
        module_sections = re.split(r"###\s+(.+?)\n", content)

        for i in range(1, len(module_sections), 2):
            if i + 1 < len(module_sections):
                module_name = module_sections[i]
                section_content = module_sections[i + 1]

                # Extract test names and errors
                test_matches = re.findall(r"####\s+(\d+)\.\s+(.+?)\n", section_content)
                for _, test_name in test_matches:
                    failures_by_module[module_name].append(test_name)

        return dict(failures_by_module)
    except FileNotFoundError:
        print(f"⚠️  File not found: {filepath}")
        return {}


def generate_report() -> None:
    """Generate comprehensive analysis report."""
    print("\n" + "=" * 70)
    print("🔍 CI TEST RESULTS ANALYSIS")
    print("=" * 70)

    # Analyze collection
    print("\n📊 TEST COLLECTION:")
    print("-" * 70)
    test_count, collection_errors = analyze_collection("ci_collected_tests.txt")
    print(f"  Total tests collected: {test_count}")
    if collection_errors:
        print(f"  ⚠️  Collection errors: {len(collection_errors)}")
        for error in collection_errors[:5]:
            print(f"      - {error[:80]}")
    else:
        print("  ✅ No collection errors")

    # Analyze test output
    print("\n🧪 TEST EXECUTION RESULTS:")
    print("-" * 70)
    stats = analyze_test_output("test_output.log")
    if stats:
        total = stats.get("total", 0)
        passed = stats.get("passed", 0)
        failed = stats.get("failed", 0)
        errors = stats.get("errors", 0)
        duration = stats.get("duration_seconds", 0)

        print(f"  Total: {total}")
        print(f"  ✅ Passed: {passed}")
        print(f"  ❌ Failed: {failed}")
        print(f"  💥 Errors: {errors}")
        print(f"  ⏱️  Duration: {duration / 60:.1f} minutes")

        if total > 0:
            pass_rate = (passed / total) * 100
            print(f"  📈 Pass Rate: {pass_rate:.1f}%")

        # Highlight critical issues
        if errors > 100:
            print(f"\n  🚨 CRITICAL: {errors} schema/import errors detected!")
            print("     Likely cause: Missing model imports in conftest.py")
            print("     Status: Should be FIXED in latest commit e543d78")
    else:
        print("  ⚠️  Could not parse test output")

    # Analyze failures
    print("\n📋 FAILURES BY MODULE:")
    print("-" * 70)
    failures = analyze_failures("TEST_FAILURES_DETAILED.md")

    if failures:
        # Sort by failure count
        sorted_modules = sorted(failures.items(), key=lambda x: len(x[1]), reverse=True)

        for module, test_list in sorted_modules:
            print(f"\n  📁 {module}")
            print(f"     {len(test_list)} failures:")
            for test in test_list[:5]:
                print(f"       - {test}")
            if len(test_list) > 5:
                print(f"       ... and {len(test_list) - 5} more")

        print(f"\n  Total modules with failures: {len(failures)}")
        print(f"  Total failing tests: {sum(len(v) for v in failures.values())}")
    else:
        print("  ✅ No failures found!")

    # Generate recommendations
    print("\n💡 RECOMMENDATIONS:")
    print("-" * 70)

    if stats.get("errors", 0) > 100:
        print("  1. Schema/Import Errors Detected (929+)")
        print("     → Check conftest.py model imports")
        print("     → Latest fix: commit e543d78 adds 50+ missing models")
        print("     → If errors still present, review model registration")

    if stats.get("failed", 0) > 0:
        print(f"\n  2. Logic Test Failures ({stats.get('failed', 0)})")
        print("     → Analyze by module:")
        for module, test_list in sorted_modules[:3]:
            print(f"        a) {module}: {len(test_list)} failures")
        print("     → Start with highest-impact category")
        print("     → Run: python test_quick.py schema")

    if stats.get("passed", 0) > 0:
        pass_rate = (stats["passed"] / stats.get("total", 1)) * 100
        if pass_rate < 90:
            print(f"\n  3. Pass Rate Low ({pass_rate:.1f}%)")
            print("     → Multiple categories failing")
            print("     → Prioritize schema fixes first")
        else:
            print(f"\n  3. Pass Rate Good ({pass_rate:.1f}%)")
            print("     → Most tests working")
            print("     → Focus on remaining failures")

    print("\n" + "=" * 70)
    print("📝 NEXT STEPS:")
    print("=" * 70)
    print(
        """
  1. Review the specific failures by module above
  2. For each module, identify root cause (schema, logic, fixture)
  3. Apply targeted fixes locally
  4. Test with: python test_quick.py schema
  5. Once passing locally, push to GitHub
  6. GitHub Actions will verify all 6400+ tests passing
  7. If still issues, repeat analysis cycle
    """
    )

    print("=" * 70 + "\n")


if __name__ == "__main__":
    generate_report()
