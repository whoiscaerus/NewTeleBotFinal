#!/usr/bin/env python3
"""Fix test_user_id fixture parameters in test file."""

import re

# Read the file
with open("backend/tests/test_pr_023_phase6_integration.py") as f:
    content = f.read()

# Pattern 1: Remove "test_user_id: UUID," from method signatures
# This handles both cases: ",\n" and ", "
pattern = r",\s*test_user_id:\s*UUID\s*(?=\))"
content = re.sub(pattern, "", content)

# Pattern 2: Also handle if it's the only parameter
pattern = r"\(\s*self,\s*db_session:\s*AsyncSession,\s*test_user_id:\s*UUID\s*\)"
content = re.sub(
    pattern, r"(\n        self,\n        db_session: AsyncSession,\n    )", content
)

# Write back
with open("backend/tests/test_pr_023_phase6_integration.py", "w") as f:
    f.write(content)

print("Fixed test_user_id fixture parameters")
