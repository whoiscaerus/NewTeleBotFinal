#!/usr/bin/env python
"""Fix test file by removing orphaned code."""

with open("backend/tests/test_pr_046_risk_compliance.py") as f:
    lines = f.readlines()

# Find the line with 'if __name__'
for i, line in enumerate(lines):
    if 'if __name__ == "__main__"' in line:
        keep_until = i + 3  # Keep main block
        break

# Write only valid lines
with open("backend/tests/test_pr_046_risk_compliance.py", "w") as f:
    f.writelines(lines[:keep_until])

print(f"Truncated to {keep_until} lines")
