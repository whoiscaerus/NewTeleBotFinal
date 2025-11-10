#!/usr/bin/env python3
"""Fix User instantiations to include required email field."""

import re
from pathlib import Path

# Read test file
test_file = Path("backend/tests/test_trust_index.py")
content = test_file.read_text(encoding="utf-8")

# Pattern: User(id="userId", ...) -> User(id="userId", email="userId@test.com", ...)
# Match User(...) where it contains id="something" but doesn't already have email=
def add_email(match):
    user_content = match.group(1)
    # Extract user ID
    id_match = re.search(r'id="([^"]+)"', user_content)
    if not id_match:
        return match.group(0)  # No id found, keep as is
    
    user_id = id_match.group(1)
    
    # Check if email already exists
    if "email=" in user_content:
        return match.group(0)  # Already has email
    
    # Add email after id
    new_content = user_content.replace(
        f'id="{user_id}"',
        f'id="{user_id}", email="{user_id}@test.com"'
    )
    return f"User({new_content})"

# Replace all User(...) instantiations
pattern = r'User\(([^)]+)\)'
fixed_content = re.sub(pattern, add_email, content)

# Write back
test_file.write_text(fixed_content, encoding="utf-8")
print(f"✅ Fixed User instantiations in {test_file}")
print("Added email field to all User() calls")
