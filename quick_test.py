#!/usr/bin/env python3
"""
Quick Test Runner - Run specific test files/patterns and commit with skip-ci marker.

Usage:
    python quick_test.py test_outbound_client_errors.py
    python quick_test.py test_outbound_client_errors.py test_data_pipeline.py
    python quick_test.py "test_pr_0*"
"""

import subprocess
import sys
from pathlib import Path


def run_tests(test_patterns: list[str]) -> tuple[int, str]:
    """Run pytest with the given test patterns.

    Args:
        test_patterns: List of test file patterns or paths

    Returns:
        Tuple of (exit_code, output)
    """
    # Convert patterns to full paths
    test_paths = []
    backend_tests = Path("backend/tests")

    for pattern in test_patterns:
        # If it's already a full path, use it
        if Path(pattern).exists():
            test_paths.append(pattern)
        # If it's just a filename, look in backend/tests
        elif (backend_tests / pattern).exists():
            test_paths.append(str(backend_tests / pattern))
        # If it's a pattern, use it as-is (pytest will expand)
        else:
            test_paths.append(str(backend_tests / pattern))

    # Build pytest command
    cmd = [
        ".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python",
        "-m",
        "pytest",
        *test_paths,
        "-v",
        "--tb=short",
        "--maxfail=10",  # Stop after 10 failures
    ]

    print(f"🧪 Running: {' '.join(cmd)}")
    print("=" * 80)

    result = subprocess.run(cmd, capture_output=False, text=True)
    return result.returncode


def git_commit_with_skip(test_files: list[str]):
    """Stage changed files and commit with [skip-ci] marker.

    Args:
        test_files: List of test files that were fixed
    """
    # Stage all changes
    subprocess.run(["git", "add", "-A"], check=True)

    # Check if there are changes to commit
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)

    if result.returncode == 0:
        print("⚠️  No changes to commit")
        return

    # Create commit message
    file_list = ", ".join(Path(f).stem for f in test_files)
    commit_msg = f"FIX: Test fixes for {file_list} [skip-ci]"

    print(f"\n📝 Committing: {commit_msg}")
    subprocess.run(["git", "commit", "-m", commit_msg], check=True)
    print("✅ Committed with [skip-ci] - CI will not run")
    print("💡 When ready for full CI, commit without [skip-ci]")


def main():
    if len(sys.argv) < 2:
        print("Usage: python quick_test.py <test_file_or_pattern> [more_files...]")
        print("\nExamples:")
        print("  python quick_test.py test_outbound_client_errors.py")
        print(
            "  python quick_test.py test_outbound_client_errors.py test_data_pipeline.py"
        )
        print('  python quick_test.py "test_pr_0*"')
        sys.exit(1)

    test_patterns = sys.argv[1:]

    print("🚀 Quick Test Runner")
    print(f"📂 Test patterns: {', '.join(test_patterns)}")
    print()

    # Run tests
    exit_code = run_tests(test_patterns)

    print("\n" + "=" * 80)

    if exit_code == 0:
        print("✅ All tests PASSED!")

        # Ask if user wants to commit
        response = input("\n📝 Commit changes with [skip-ci]? (y/n): ").strip().lower()
        if response == "y":
            git_commit_with_skip(test_patterns)
        else:
            print("⏭️  Skipping commit")
    else:
        print(f"❌ Tests FAILED (exit code: {exit_code})")
        print("Fix the failures and try again")
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
