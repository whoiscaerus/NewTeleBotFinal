"""Trading time utilities - market hours and timezone management.

Provides market hours gating to prevent trading outside of market open hours,
with automatic DST handling for all supported timezones.

Modules:
    market_calendar: Market session definitions and hours lookup
    tz: Timezone conversion utilities with DST support

Example:
    >>> from datetime import datetime
    >>> import pytz
    >>> from backend.app.trading.time import MarketCalendar, to_market_tz, to_utc
    >>>
    >>> # Check if market is open
    >>> dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
    >>> is_open = MarketCalendar.is_market_open("GOLD", dt)
    >>> print(f"GOLD market open: {is_open}")
    GOLD market open: True
    >>>
    >>> # Convert to market timezone
    >>> market_dt = to_market_tz(dt, "GOLD")
    >>> print(f"Local time: {market_dt}")
    Local time: 2025-10-27 10:00:00+00:00
    >>>
    >>> # Get next market open
    >>> next_open = MarketCalendar.get_next_open("GOLD")
    >>> print(f"Next open: {next_open}")
    Next open: 2025-10-28 08:00:00+00:00
"""

from backend.app.trading.time.market_calendar import MarketCalendar, MarketSession
from backend.app.trading.time.tz import (
    SYMBOL_TO_TIMEZONE,
    get_offset_utc,
    is_dst_transition,
    is_same_day_in_tz,
    to_market_tz,
    to_utc,
)

__all__ = [
    "MarketCalendar",
    "MarketSession",
    "to_market_tz",
    "to_utc",
    "is_dst_transition",
    "get_offset_utc",
    "is_same_day_in_tz",
    "SYMBOL_TO_TIMEZONE",
]

__version__ = "1.0.0"
