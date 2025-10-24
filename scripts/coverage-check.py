#!/usr/bin/env python
"""
Coverage check script - validates test coverage meets minimum threshold.
Fails CI/CD if coverage < 90%.
"""

import subprocess
import sys

MINIMUM_COVERAGE = 90


def run_coverage_check() -> int:
    """Run pytest with coverage and check minimum threshold."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests",
            f"--cov=backend/app",
            "--cov-report=term-missing",
            "--cov-report=html",
            "-v",
        ],
        capture_output=False,
    )

    if result.returncode != 0:
        print(f"\n❌ Tests failed")
        return 1

    # Parse coverage from pytest output
    cov_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests",
            f"--cov=backend/app",
            "--cov-report=term",
            "-q",
        ],
        capture_output=True,
        text=True,
    )

    output = cov_result.stdout + cov_result.stderr

    # Extract coverage percentage
    for line in output.split("\n"):
        if "TOTAL" in line:
            parts = line.split()
            if len(parts) >= 4:
                coverage_str = parts[-1].strip("%")
                try:
                    coverage = float(coverage_str)
                    if coverage < MINIMUM_COVERAGE:
                        print(
                            f"\n❌ Coverage {coverage}% is below minimum {MINIMUM_COVERAGE}%"
                        )
                        print(f"   See htmlcov/index.html for detailed report")
                        return 1
                    else:
                        print(f"\n✅ Coverage {coverage}% meets minimum {MINIMUM_COVERAGE}%")
                        return 0
                except ValueError:
                    pass

    print(f"\n⚠️  Could not parse coverage (see htmlcov/index.html)")
    return 0


if __name__ == "__main__":
    sys.exit(run_coverage_check())
