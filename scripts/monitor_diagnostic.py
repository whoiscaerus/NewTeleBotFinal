#!/usr/bin/env python3
"""
Monitor GitHub Actions workflow and download diagnostic results.
Run this after pushing to check on the diagnostic run status.
"""

import json
import subprocess
import sys
from pathlib import Path
from time import sleep


def get_latest_run():
    """Get latest workflow run for this repo."""
    try:
        result = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--repo",
                "whoiscaerus/NewTeleBotFinal",
                "--workflow",
                "full-diagnostic.yml",
                "--limit",
                "1",
                "--json",
                "status,conclusion,databaseId,number,updatedAt",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        runs = json.loads(result.stdout)
        return runs[0] if runs else None
    except Exception as e:
        print(f"❌ Error fetching runs: {e}")
        return None


def download_artifacts(run_id):
    """Download artifacts from workflow run."""
    try:
        print(f"\n📥 Downloading artifacts from run {run_id}...")
        subprocess.run(
            [
                "gh",
                "run",
                "download",
                str(run_id),
                "--repo",
                "whoiscaerus/NewTeleBotFinal",
                "--dir",
                "diagnostic_results",
            ],
            check=True,
        )
        print("✅ Artifacts downloaded to ./diagnostic_results/")
        return True
    except Exception as e:
        print(f"❌ Error downloading artifacts: {e}")
        return False


def monitor_run():
    """Monitor workflow run until completion."""
    print("🔍 Monitoring Full Diagnostic Test Run...")
    print("   Repo: whoiscaerus/NewTeleBotFinal")
    print("   Workflow: full-diagnostic.yml")
    print("")

    last_status = None
    while True:
        run = get_latest_run()

        if not run:
            print("⏳ Waiting for workflow to start...")
            sleep(10)
            continue

        status = run.get("status")
        conclusion = run.get("conclusion")
        run_id = run.get("databaseId")
        run_num = run.get("number")

        if status != last_status:
            last_status = status
            print(f"[{run_num}] Status: {status}")

        if status == "completed":
            print("\n✅ Workflow completed!")
            print(f"   Conclusion: {conclusion}")
            print(f"   Run ID: {run_id}")
            print(f"   Run #: {run_num}")

            if conclusion == "success":
                print("\n✅ Tests completed successfully!")
                if download_artifacts(run_id):
                    # Read and display summary
                    results_dir = Path("diagnostic_results/full-diagnostic-results")
                    detailed_file = results_dir / "DETAILED_TEST_RESULTS.txt"
                    if detailed_file.exists():
                        print("\n" + "=" * 80)
                        print("TEST RESULTS SUMMARY")
                        print("=" * 80)
                        with open(detailed_file) as f:
                            lines = f.readlines()
                            print("".join(lines[:100]))
                        print(f"\n(Full results saved to: {detailed_file})")
            else:
                print(f"\n⚠️  Workflow completed with conclusion: {conclusion}")
                if download_artifacts(run_id):
                    print("   Check diagnostic_results/ for details")

            break

        print(".", end="", flush=True)
        sleep(30)


if __name__ == "__main__":
    # Check if gh CLI is available
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ GitHub CLI (gh) not found. Install it:")
        print("   https://cli.github.com")
        sys.exit(1)

    monitor_run()
