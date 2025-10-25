"""
Copy-Trading Module

Automated trade execution with risk controls and +30% pricing markup.
"""

from backend.app.copytrading.service import CopyTradeExecution
from backend.app.copytrading.service import (
    CopyTradeExecution as CopyTradeExecutionSchema,
)
from backend.app.copytrading.service import (
    CopyTradeSettings,
    CopyTradingEnable,
    CopyTradingService,
)
from backend.app.copytrading.service import (
    CopyTradingSettings as CopyTradingSettingsSchema,
)

__all__ = [
    "CopyTradeSettings",
    "CopyTradeExecution",
    "CopyTradingService",
    "CopyTradingEnable",
    "CopyTradingSettingsSchema",
    "CopyTradeExecutionSchema",
]
