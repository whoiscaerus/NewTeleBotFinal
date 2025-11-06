"""Fix Trade() instances to include required stop_loss and take_profit fields."""

import re

with open("backend/tests/test_pr_051_etl_comprehensive.py", encoding="utf-8") as f:
    content = f.read()

# Pattern: Find Trade( ... volume=..., profit=... ) and insert SL/TP before profit
pattern = r"(Trade\([^)]*?volume=Decimal\([^)]+\),)\s*(\n\s*profit=)"
replacement = r'\1\n            stop_loss=Decimal("1.0000"),\n            take_profit=Decimal("2.0000"),\2'

content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open("backend/tests/test_pr_051_etl_comprehensive.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed Trade() instances")
