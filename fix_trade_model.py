#!/usr/bin/env python3
"""Fix all Trade instantiations to match actual Trade model."""

import re
from pathlib import Path

# Read test file
test_file = Path("backend/tests/test_trust_index.py")
content = test_file.read_text(encoding="utf-8")

# Replace Trade(...) with correct fields
# Old: id=, instrument=, side=, entry_price=, exit_price=, quantity=, profit=, risk_reward_ratio=, status=, signal_id=, entry_time=, exit_time=
# New: trade_id=, user_id=, symbol=, strategy=, timeframe=, trade_type=, direction=, entry_price=, entry_time=, stop_loss=, take_profit=, volume=, exit_price=, exit_time=, profit=, risk_reward_ratio=, status=, signal_id=

# Pattern to find Trade instantiations
pattern = r'Trade\(\s*id=f"([^"]+)",\s*user_id="([^"]+)",\s*instrument="([^"]+)",\s*side=(\d+),\s*entry_price=([\d.]+),\s*exit_price=([\d.]+) if profit > 0 else ([\d.]+),\s*quantity=([\d.]+),\s*profit=profit,\s*risk_reward_ratio=([\d.]+) if profit > 0 else ([\d.]+),\s*status="([^"]+)",\s*signal_id=f"([^"]+)" if i < \d+ else None,\s*entry_time=([^,]+),\s*exit_time=([^)]+)\s*\)'

# Replacement pattern
replacement = r'''Trade(
            trade_id=f"\1",
            user_id="\2",
            symbol="\3",  # was instrument
            strategy="fib_rsi",  # required
            timeframe="H1",  # required
            trade_type="BUY" if \4 == 0 else "SELL",
            direction=\4,
            entry_price=\5,
            entry_time=\13,
            stop_loss=\5 * 0.98 if \4 == 0 else \5 * 1.02,  # 2% below/above entry
            take_profit=\5 * 1.04 if \4 == 0 else \5 * 0.96,  # 4% above/below entry
            volume=\8,  # was quantity
            exit_price=\6 if profit > 0 else \7,
            exit_time=\14,
            profit=profit,
            risk_reward_ratio=\9 if profit > 0 else \10,
            status="\11",
            signal_id=f"\12" if i < 5 else None,
        )'''

fixed_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

# Write back
test_file.write_text(fixed_content, encoding="utf-8")
print(f"✅ Fixed Trade instantiations in {test_file}")
print("Mapped Trade fields:")
print("  id → trade_id")
print("  instrument → symbol") 
print("  side → direction (kept same)")
print("  quantity → volume")
print("  Added: strategy, timeframe, trade_type, stop_loss, take_profit")
