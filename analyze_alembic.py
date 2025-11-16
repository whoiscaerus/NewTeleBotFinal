#!/usr/bin/env python3
"""
Analyze and report alembic migration chain issues.
"""

import re
from pathlib import Path

migrations_dir = Path("backend/alembic/versions")

# Parse all migrations
migrations = {}
for file_path in sorted(migrations_dir.glob("*.py")):
    if file_path.name.startswith("__"):
        continue

    content = file_path.read_text()

    # Extract revision ID
    rev_match = re.search(r'revision\s*=\s*["\']([^"\']+)["\']', content)
    if not rev_match:
        continue

    revision_id = rev_match.group(1)

    # Extract down_revision
    down_match = re.search(r'down_revision\s*=\s*["\']?([^"\'\n]+)["\']?', content)
    down_revision = down_match.group(1) if down_match else None

    migrations[revision_id] = {"file": file_path.name, "down_revision": down_revision}

print("=" * 80)
print("ALEMBIC MIGRATION CHAIN ANALYSIS")
print("=" * 80)

# Check for broken references
issues = []
for rev_id, data in sorted(migrations.items()):
    down_rev = data["down_revision"]

    if down_rev is None:
        print(f"OK {rev_id:40s} (HEAD - no parent)")
    elif down_rev not in migrations and down_rev != "None":
        # This is broken
        issues.append((rev_id, data["file"], down_rev))
        print(f"XX {rev_id:40s} -> {down_rev} (BROKEN - not found)")
    else:
        print(f"OK {rev_id:40s} -> {down_rev}")

print("\n" + "=" * 80)
if issues:
    print(f"FOUND {len(issues)} BROKEN REFERENCES:\n")
    for rev_id, file, broken_ref in issues:
        print(f"File: {file}")
        print(f"  Revision: {rev_id}")
        print(f"  References (broken): {broken_ref}")
        # Try to find what this might be
        similar = [r for r in migrations.keys() if broken_ref.lower() in r.lower()]
        if similar:
            print(f"  Similar revisions: {similar}")
        print()
else:
    print("OK - No broken references found!")

print("=" * 80)
print(f"Total migrations: {len(migrations)}")
print("=" * 80)
