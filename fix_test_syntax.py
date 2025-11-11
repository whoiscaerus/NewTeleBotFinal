#!/usr/bin/env python3
"""Fix syntax errors in test file."""
import pathlib

test_file = pathlib.Path(
    "backend/tests/test_pr_048_049_mt5_fixed_risk_comprehensive.py"
)
content = test_file.read_text(encoding="utf-8")

# Fix double closing brackets
search_str = 'global_risk_percent"]]'
replace_str = 'global_risk_percent"]'
count = content.count(search_str)
fixed = content.replace(search_str, replace_str)

test_file.write_text(fixed, encoding="utf-8")
print(f"Fixed {count} occurrences")
