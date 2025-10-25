"""Timezone conversion utilities for market hours.

Provides functions for converting between UTC and market-local timezones,
with automatic DST (Daylight Saving Time) handling via pytz.

Example:
    >>> from datetime import datetime
    >>> import pytz
    >>> from backend.app.trading.time.tz import to_market_tz, to_utc
    >>>
    >>> # Convert UTC to GOLD market timezone (London)
    >>> utc_dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
    >>> market_dt = to_market_tz(utc_dt, "GOLD")
    >>> print(f"Market time: {market_dt}")
    Market time: 2025-10-27 10:00:00+00:00
"""

from datetime import datetime

import pytz

# Map symbols to their market timezones
SYMBOL_TO_TIMEZONE: dict[str, str] = {
    # Commodities (London)
    "GOLD": "Europe/London",
    "SILVER": "Europe/London",
    "OIL": "Europe/London",
    "NATGAS": "Europe/London",
    # Forex (various primary sessions)
    "EURUSD": "Europe/London",
    "GBPUSD": "Europe/London",
    "USDJPY": "America/New_York",
    "AUDUSD": "Asia/Kolkata",
    "NZDUSD": "Asia/Kolkata",
    # Stocks (New York)
    "S&P500": "America/New_York",
    "NASDAQ": "America/New_York",
    "DOWJONES": "America/New_York",
    "TESLA": "America/New_York",
    "APPLE": "America/New_York",
    # Indices
    "DAX": "Europe/London",
    "FTSE": "Europe/London",
    "NIFTY": "Asia/Kolkata",
    "HANGSENG": "Asia/Hong_Kong",
    # Crypto (UTC-based)
    "BTCUSD": "UTC",
    "ETHUSD": "UTC",
}


def to_market_tz(dt: datetime, symbol: str) -> datetime:
    """Convert datetime from UTC to market timezone.

    Args:
        dt: UTC datetime (should have tzinfo=pytz.UTC)
        symbol: Trading symbol

    Returns:
        Datetime in market's local timezone

    Raises:
        ValueError: If symbol is unknown or timezone is invalid
        TypeError: If dt is not a datetime object

    Example:
        >>> from datetime import datetime
        >>> import pytz
        >>>
        >>> # UTC 10:00
        >>> utc_dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        >>>
        >>> # Convert to London time (same in winter, +1 hour in DST)
        >>> london_dt = to_market_tz(utc_dt, "GOLD")
        >>> print(london_dt)
        2025-10-27 10:00:00+00:00  # October: no DST in London

        >>> # Convert to New York time
        >>> ny_dt = to_market_tz(utc_dt, "S&P500")
        >>> print(ny_dt)
        2025-10-27 06:00:00-04:00  # EDT (UTC-4)
    """
    if not isinstance(dt, datetime):
        raise TypeError(f"Expected datetime, got {type(dt)}")

    if symbol not in SYMBOL_TO_TIMEZONE:
        raise ValueError(f"Unknown symbol: {symbol}")

    tz_name = SYMBOL_TO_TIMEZONE[symbol]
    market_tz = pytz.timezone(tz_name)

    # Ensure input has UTC timezone
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    elif dt.tzinfo != pytz.UTC:
        dt = dt.astimezone(pytz.UTC)

    # Convert to market timezone
    return dt.astimezone(market_tz)


def to_utc(dt: datetime, symbol: str) -> datetime:
    """Convert datetime from market timezone to UTC.

    Args:
        dt: Market datetime (should have tzinfo set to market timezone)
        symbol: Trading symbol

    Returns:
        Datetime in UTC timezone

    Raises:
        ValueError: If symbol is unknown or timezone is invalid
        TypeError: If dt is not a datetime object

    Example:
        >>> from datetime import datetime
        >>> import pytz
        >>>
        >>> # Create London time during winter (GMT)
        >>> london_tz = pytz.timezone("Europe/London")
        >>> london_dt = london_tz.localize(datetime(2025, 1, 15, 10, 0))
        >>>
        >>> # Convert to UTC
        >>> utc_dt = to_utc(london_dt, "GOLD")
        >>> print(utc_dt)
        2025-01-15 10:00:00+00:00

        >>> # Create New York time during EDT
        >>> ny_tz = pytz.timezone("America/New_York")
        >>> ny_dt = ny_tz.localize(datetime(2025, 10, 27, 6, 0))
        >>>
        >>> # Convert to UTC
        >>> utc_dt = to_utc(ny_dt, "S&P500")
        >>> print(utc_dt)
        2025-10-27 10:00:00+00:00
    """
    if not isinstance(dt, datetime):
        raise TypeError(f"Expected datetime, got {type(dt)}")

    if symbol not in SYMBOL_TO_TIMEZONE:
        raise ValueError(f"Unknown symbol: {symbol}")

    # Ensure dt has timezone info
    if dt.tzinfo is None:
        raise ValueError("Datetime must have timezone info")

    # Convert to UTC
    return dt.astimezone(pytz.UTC)


def is_dst_transition(dt: datetime, tz_name: str) -> bool:
    """Check if datetime is during DST transition period.

    DST transitions occur:
    - Spring forward: 2:00 AM → 3:00 AM (UTC+2 to UTC+1 or similar)
    - Fall back: 2:00 AM → 1:00 AM (UTC+1 to UTC+2 or similar)

    During transition, a wall clock time might be ambiguous or non-existent.

    Args:
        dt: Datetime to check
        tz_name: IANA timezone name (e.g., "America/New_York")

    Returns:
        True if dt is in DST transition window (typically 1-2 AM), False otherwise

    Raises:
        ValueError: If timezone is invalid
        TypeError: If dt is not a datetime object

    Example:
        >>> from datetime import datetime
        >>> import pytz
        >>>
        >>> # Spring forward: 2:00 AM on 2025-03-09 (US)
        >>> dt = datetime(2025, 3, 9, 2, 30)
        >>> is_dst_transition(dt, "America/New_York")
        True

        >>> # Normal time (not transition)
        >>> dt = datetime(2025, 10, 15, 10, 0)
        >>> is_dst_transition(dt, "America/New_York")
        False

        >>> # Fall back: 1:00 AM on 2025-11-02 (US)
        >>> dt = datetime(2025, 11, 2, 1, 30)
        >>> is_dst_transition(dt, "America/New_York")
        True
    """
    if not isinstance(dt, datetime):
        raise TypeError(f"Expected datetime, got {type(dt)}")

    try:
        tz = pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError as e:
        raise ValueError(f"Unknown timezone: {tz_name}") from e

    # Create naive datetime for this timezone
    naive_dt = dt.replace(tzinfo=None)

    # Try to localize - if it raises AmbiguousTimeError or NonExistentTimeError, we're in transition
    try:
        tz.localize(naive_dt, is_dst=None)
        # Successfully localized without ambiguity - not in transition
        return False
    except pytz.exceptions.AmbiguousTimeError:
        # Time exists twice (fall back) - in transition
        return True
    except pytz.exceptions.NonExistentTimeError:
        # Time doesn't exist (spring forward) - in transition
        return True


def get_offset_utc(dt: datetime, tz_name: str) -> str:
    """Get UTC offset string for timezone at given datetime.

    Args:
        dt: Datetime to check (naive datetime in the given timezone)
        tz_name: IANA timezone name

    Returns:
        Offset string like "+00:00", "-05:00", "+05:30"

    Raises:
        ValueError: If timezone is invalid
        TypeError: If dt is not a datetime object

    Example:
        >>> from datetime import datetime
        >>>
        >>> # London in winter (GMT, UTC+0)
        >>> dt = datetime(2025, 1, 15, 10, 0)
        >>> offset = get_offset_utc(dt, "Europe/London")
        >>> print(f"Offset: {offset}")
        Offset: +00:00

        >>> # New York in summer (EDT, UTC-4)
        >>> dt = datetime(2025, 7, 15, 10, 0)
        >>> offset = get_offset_utc(dt, "America/New_York")
        >>> print(f"Offset: {offset}")
        Offset: -04:00
    """
    if not isinstance(dt, datetime):
        raise TypeError(f"Expected datetime, got {type(dt)}")

    try:
        tz = pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError as e:
        raise ValueError(f"Unknown timezone: {tz_name}") from e

    # Localize naive datetime
    naive_dt = dt.replace(tzinfo=None)

    try:
        localized = tz.localize(naive_dt, is_dst=None)
    except (pytz.exceptions.AmbiguousTimeError, pytz.exceptions.NonExistentTimeError):
        # During DST transitions, use is_dst=True to get post-transition offset
        localized = tz.localize(naive_dt, is_dst=True)

    # Get offset
    offset = localized.utcoffset()
    if offset is None:
        raise ValueError(f"Unable to determine offset for {naive_dt} in {tz_name}")

    hours, remainder = divmod(int(offset.total_seconds()), 3600)
    minutes = remainder // 60

    return f"{hours:+03d}:{minutes:02d}"


def is_same_day_in_tz(
    dt_utc: datetime, tz_name: str, year: int, month: int, day: int
) -> bool:
    """Check if UTC datetime corresponds to given date in specified timezone.

    Args:
        dt_utc: UTC datetime
        tz_name: Target timezone
        year, month, day: Date components to check

    Returns:
        True if dt_utc converts to the given date in tz_name timezone

    Example:
        >>> from datetime import datetime
        >>> import pytz
        >>>
        >>> # UTC midnight (Jan 1)
        >>> dt_utc = datetime(2025, 1, 1, 0, 0, tzinfo=pytz.UTC)
        >>>
        >>> # In New York (UTC-5), this is Dec 31, 19:00
        >>> is_same_day_in_tz(dt_utc, "America/New_York", 2024, 12, 31)
        True

        >>> # Not Jan 1 in New York yet
        >>> is_same_day_in_tz(dt_utc, "America/New_York", 2025, 1, 1)
        False
    """
    if not isinstance(dt_utc, datetime):
        raise TypeError(f"Expected datetime, got {type(dt_utc)}")

    # Convert to target timezone
    tz = pytz.timezone(tz_name)
    dt_local = dt_utc.astimezone(tz)

    # Check if date matches
    return dt_local.year == year and dt_local.month == month and dt_local.day == day
