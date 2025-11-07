"""Fix message field references in test file."""

import re

# Read file
with open("backend/tests/test_messaging_bus.py", encoding="utf-8") as f:
    content = f.read()

# Replace message["id"] with message["message_id"]
content = re.sub(r'message\["id"\]', 'message["message_id"]', content)

# Write back
with open("backend/tests/test_messaging_bus.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed message field references")
