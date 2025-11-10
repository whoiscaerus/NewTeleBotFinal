"""Comprehensively fix all User instantiations in test_social.py"""
import re

# Read file
with open('tests/test_social.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern 1: User( with just id and telegram_user_id (missing email/password_hash)
# Find: User(\n        id="userX",\n        telegram_user_id=NNNNN,
# Replace: User(\n        id="userX",\n        email="userX@test.com",\n        password_hash="hashed",\n        telegram_user_id=NNNNN,

pattern1 = r'User\(\s+id="(user\d+)",\s+telegram_user_id='
replacement1 = r'User(\n        id="\1",\n        email="\1@test.com",\n        password_hash="hashed",\n        telegram_user_id='
content = re.sub(pattern1, replacement1, content)

# Pattern 2: User( with just id and username (need to remove username, add email/password_hash/telegram_user_id)
# Find: User(\n        id="X",\n        email="X@test.com",\n        password_hash="hashed",\n        telegram_user_id=NNNNN,\n        username="X",
# Replace: User(\n        id="X",\n        email="X@test.com",\n        password_hash="hashed",\n        telegram_user_id=NNNNN,

pattern2 = r'(\s+telegram_user_id=\d+,)\s+username="[^"]+",\s+'
replacement2 = r'\1\n        '
content = re.sub(pattern2, replacement2, content)

# Pattern 3: Handle new_user and target_user variations
# Find: User(\n        id="new_user" or "target" etc
pattern3 = r'User\(\s+id="(new_user|target|newuser)",\s+telegram_user_id='
replacement3 = r'User(\n        id="\1",\n        email="\1@test.com",\n        password_hash="hashed",\n        telegram_user_id='
content = re.sub(pattern3, replacement3, content)

# Write back
with open('tests/test_social.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed all User instantiations")
print("- Added email/password_hash where missing")
print("- Removed username parameters")
