#!/usr/bin/env python
"""Add @pytest.mark.asyncio decorators to async test methods."""

import re

# Read the test file
with open("backend/tests/test_pr_029_rates_quotes.py") as f:
    content = f.read()

# Find all async test methods and add @pytest.mark.asyncio if not present
# Pattern: "    async def test_" (at class level, 4 spaces indent)
pattern = r"(\n    )async def (test_\w+)\("
replacement = r"\1@pytest.mark.asyncio\n    async def \2("

# Replace all occurrences
updated_content = re.sub(pattern, replacement, content)

# Write back
with open("backend/tests/test_pr_029_rates_quotes.py", "w") as f:
    f.write(updated_content)

print("✓ Added @pytest.mark.asyncio decorators to all async test methods")
