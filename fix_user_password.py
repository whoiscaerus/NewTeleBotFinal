#!/usr/bin/env python3
"""Add password_hash to all User instantiations."""

import re
from pathlib import Path

# Read test file
test_file = Path("backend/tests/test_trust_index.py")
content = test_file.read_text(encoding="utf-8")

# Pattern: Add password_hash after email if not already present
def add_password(match):
    user_content = match.group(1)
    
    # Check if password_hash already exists
    if "password_hash=" in user_content:
        return match.group(0)  # Already has password_hash
    
    # Add password_hash after email
    if "email=" in user_content:
        new_content = user_content.replace(
            'email=',
            'email='
        ).replace(
            '@test.com"',
            '@test.com", password_hash="hashed_pwd"'
        )
        return f"User({new_content})"
    
    return match.group(0)  # No email, keep as is

# Replace all User(...) instantiations
pattern = r'User\(([^)]+)\)'
fixed_content = re.sub(pattern, add_password, content)

# Write back
test_file.write_text(fixed_content, encoding="utf-8")
print(f"✅ Fixed User instantiations in {test_file}")
print("Added password_hash field to all User() calls")
