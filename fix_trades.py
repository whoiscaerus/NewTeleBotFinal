#!/usr/bin/env python3
"""Fix all Trade() instantiations in test_pr_024_fraud.py"""

import re

file_path = "backend/tests/test_pr_024_fraud.py"

# Read the file
with open(file_path, encoding="utf-8") as f:
    content = f.read()

# Pattern 1: Replace id= with trade_id=
content = re.sub(r'(\s+)id="', r'\1trade_id="', content)

# Pattern 2: Remove standalone side= lines (already embedded in trade_type/direction)
content = re.sub(r"\s+side=\d+,?\s*\n", "", content)


# Pattern 3: Find all `trade = Trade(` blocks and replace with helper function calls
# This pattern finds Trade( followed by any content until the closing )
def replace_trade_with_helper(match):
    """Replace Trade instantiation with create_test_trade helper."""
    indent = match.group(1)
    # Extract parameters
    params_text = match.group(2)

    # Parse key parameters
    params = {}
    for line in params_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key_val = line.split("=", 1)
            key = key_val[0].strip()
            val = key_val[1].strip().rstrip(",")
            params[key] = val

    # Check if we have the minimum required params
    required = [
        "trade_id",
        "user_id",
        "symbol",
        "entry_price",
        "exit_price",
        "volume",
        "status",
        "entry_time",
        "exit_time",
    ]
    if not all(k in params for k in required):
        return match.group(0)  # Return unchanged if required params missing

    # Build helper function call
    result = f"{indent}trade = create_test_trade(\n"
    result += f"{indent}    trade_id={params['trade_id']},\n"
    result += f"{indent}    user_id={params['user_id']},\n"
    result += f"{indent}    symbol={params['symbol']},\n"
    result += f"{indent}    entry_price={params['entry_price']},\n"
    result += f"{indent}    exit_price={params['exit_price']},\n"
    result += f"{indent}    volume={params['volume']},\n"
    result += f"{indent}    profit={params.get('profit', 'None')},\n"
    result += f"{indent}    status={params['status']},\n"
    result += f"{indent}    entry_time={params['entry_time']},\n"
    result += f"{indent}    exit_time={params['exit_time']},\n"
    result += f"{indent})"

    return result


# Apply replacement (skip this complex replacement for now - too risky)
# Just fix the simple patterns above

# Write back
with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed Trade instantiations in test file")
