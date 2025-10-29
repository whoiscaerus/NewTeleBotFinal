#!/usr/bin/env python3
"""Fix test_user_id fixture issues by removing test_user_id: UUID parameters."""

import re

# Read the file
with open("backend/tests/test_pr_023_phase6_integration.py") as f:
    content = f.read()

# Replace pattern: remove "test_user_id: UUID," from function signatures
pattern = r"(\n\s+async def test_[a-zA-Z0-9_]+\(\s*self,\s*db_session: AsyncSession,\s*)test_user_id: UUID,(\s*\):)"
content = re.sub(pattern, r"\1\2", content)

# Write back
with open("backend/tests/test_pr_023_phase6_integration.py", "w") as f:
    f.write(content)

print("✓ Removed test_user_id: UUID parameters from test method signatures")
