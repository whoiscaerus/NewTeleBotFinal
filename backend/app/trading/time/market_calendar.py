"""Market calendar and trading hours definitions.

Provides market hours lookup, timezone handling, and market session detection.
Enables gating of trading signals based on market operating hours.

Example:
    >>> from datetime import datetime
    >>> import pytz
    >>> from backend.app.trading.time.market_calendar import MarketCalendar
    >>>
    >>> dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
    >>> is_open = MarketCalendar.is_market_open("GOLD", dt)
    >>> print(f"Market open: {is_open}")
    Market open: True
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

import pytz


@dataclass
class MarketSession:
    """Market trading session definition.

    Attributes:
        name: Session identifier (London, NewYork, Asia, Crypto)
        open_time: Market open time in MARKET LOCAL timezone
        close_time: Market close time in MARKET LOCAL timezone
        trading_days: Set of weekday integers (0=Monday, 6=Sunday)
        timezone: IANA timezone string for market
    """

    name: str
    open_time: time
    close_time: time
    trading_days: set[int]
    timezone: str


class MarketCalendar:
    """Market hours and trading session management.

    Provides lookups for market open/close times, timezone conversions,
    and market session information for trading symbols.
    """

    # Define market sessions
    SESSIONS: dict[str, MarketSession] = {
        "london": MarketSession(
            name="London",
            open_time=time(8, 0),  # 08:00 GMT/BST (market-local time)
            close_time=time(16, 30),  # 16:30 GMT/BST
            trading_days={0, 1, 2, 3, 4},  # Mon-Fri
            timezone="Europe/London",
        ),
        "newyork": MarketSession(
            name="New York",
            open_time=time(9, 30),  # 09:30 EST/EDT (market-local time)
            close_time=time(16, 0),  # 16:00 EST/EDT
            trading_days={0, 1, 2, 3, 4},  # Mon-Fri
            timezone="America/New_York",
        ),
        "asia": MarketSession(
            name="Asia",
            open_time=time(8, 15),  # 08:15 IST (market-local time)
            close_time=time(14, 45),  # 14:45 IST
            trading_days={0, 1, 2, 3, 4},  # Mon-Fri
            timezone="Asia/Kolkata",
        ),
        "crypto": MarketSession(
            name="Crypto",
            open_time=time(0, 0),  # 00:00 UTC
            close_time=time(23, 59),  # 23:59 UTC
            trading_days={0, 1, 2, 3, 4},  # Mon-Fri (not 24/7, closed weekends)
            timezone="UTC",
        ),
    }

    # Map symbols to their trading sessions
    SYMBOL_TO_SESSION: dict[str, str] = {
        # Commodities (London)
        "GOLD": "london",
        "SILVER": "london",
        "OIL": "london",
        "NATGAS": "london",
        # Forex (24-hour, but gated by primary session)
        "EURUSD": "london",  # Start in London session
        "GBPUSD": "london",
        "USDJPY": "newyork",
        "AUDUSD": "asia",
        "NZDUSD": "asia",
        # Stocks (New York)
        "S&P500": "newyork",
        "NASDAQ": "newyork",
        "DOWJONES": "newyork",
        "TESLA": "newyork",
        "APPLE": "newyork",
        # Indices
        "DAX": "london",
        "FTSE": "london",
        "NIFTY": "asia",
        "HANGSENG": "asia",
        # Crypto (24/5)
        "BTCUSD": "crypto",
        "ETHUSD": "crypto",
    }

    @staticmethod
    def is_market_open(symbol: str, dt: datetime) -> bool:
        """Check if market is open for symbol at given datetime.

        Args:
            symbol: Trading symbol (e.g., "GOLD", "EURUSD", "S&P500")
            dt: Datetime to check (should be in UTC)

        Returns:
            True if market is open for symbol at given time, False otherwise

        Raises:
            ValueError: If symbol is not recognized

        Example:
            >>> from datetime import datetime
            >>> import pytz
            >>>
            >>> # Monday 10:00 UTC (London session open)
            >>> dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
            >>> MarketCalendar.is_market_open("GOLD", dt)
            True

            >>> # Friday 17:00 UTC (after London close)
            >>> dt = datetime(2025, 10, 24, 17, 0, tzinfo=pytz.UTC)
            >>> MarketCalendar.is_market_open("GOLD", dt)
            False

            >>> # Saturday (weekend)
            >>> dt = datetime(2025, 10, 25, 10, 0, tzinfo=pytz.UTC)
            >>> MarketCalendar.is_market_open("GOLD", dt)
            False
        """
        if symbol not in MarketCalendar.SYMBOL_TO_SESSION:
            raise ValueError(f"Unknown symbol: {symbol}")

        # Ensure dt has UTC timezone
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        elif dt.tzinfo != pytz.UTC:
            dt = dt.astimezone(pytz.UTC)

        # Get session for symbol
        session_key = MarketCalendar.SYMBOL_TO_SESSION[symbol]
        session = MarketCalendar.SESSIONS[session_key]

        # Check if weekday is trading day
        if dt.weekday() not in session.trading_days:
            return False

        # Convert to market timezone
        market_tz = pytz.timezone(session.timezone)
        market_dt = dt.astimezone(market_tz)

        # Handle sessions that cross midnight (e.g., Asia session)
        market_time = market_dt.time()

        # Simple case: open < close (e.g., London 08:00-16:30)
        if session.open_time < session.close_time:
            return session.open_time <= market_time < session.close_time

        # Session crosses midnight (e.g., Asia 23:15-09:45)
        # In this case: open < time OR time < close
        return market_time >= session.open_time or market_time < session.close_time

    @staticmethod
    def get_session(symbol: str) -> MarketSession:
        """Get trading session for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            MarketSession object for the symbol

        Raises:
            ValueError: If symbol is not recognized

        Example:
            >>> session = MarketCalendar.get_session("GOLD")
            >>> print(session.name)
            London
        """
        if symbol not in MarketCalendar.SYMBOL_TO_SESSION:
            raise ValueError(f"Unknown symbol: {symbol}")

        session_key = MarketCalendar.SYMBOL_TO_SESSION[symbol]
        return MarketCalendar.SESSIONS[session_key]

    @staticmethod
    def get_next_open(symbol: str, from_dt: datetime | None = None) -> datetime:
        """Get next market open time for symbol.

        Args:
            symbol: Trading symbol
            from_dt: Start datetime (default: now in UTC)

        Returns:
            Next datetime when market opens for symbol (in UTC)

        Raises:
            ValueError: If symbol is not recognized

        Example:
            >>> from datetime import datetime
            >>> import pytz
            >>>
            >>> # Friday 17:00 UTC (after market close)
            >>> dt = datetime(2025, 10, 24, 17, 0, tzinfo=pytz.UTC)
            >>> next_open = MarketCalendar.get_next_open("GOLD", dt)
            >>> print(f"Next open: {next_open}")
            Next open: 2025-10-27 08:00:00+00:00  # Monday 08:00 UTC
        """
        if symbol not in MarketCalendar.SYMBOL_TO_SESSION:
            raise ValueError(f"Unknown symbol: {symbol}")

        if from_dt is None:
            from_dt = datetime.now(pytz.UTC)

        if from_dt.tzinfo is None:
            from_dt = pytz.UTC.localize(from_dt)
        elif from_dt.tzinfo != pytz.UTC:
            from_dt = from_dt.astimezone(pytz.UTC)

        session = MarketCalendar.get_session(symbol)
        market_tz = pytz.timezone(session.timezone)

        # Start from next day if market is closed now
        check_dt = from_dt + timedelta(days=1)

        # Find next trading day
        while check_dt.weekday() not in session.trading_days:
            check_dt += timedelta(days=1)

        # Create datetime at market open in market timezone
        market_dt = market_tz.localize(
            datetime(
                check_dt.year,
                check_dt.month,
                check_dt.day,
                session.open_time.hour,
                session.open_time.minute,
            )
        )

        # Convert to UTC
        return market_dt.astimezone(pytz.UTC)

    @staticmethod
    def get_market_status(symbol: str, dt: datetime | None = None) -> dict:
        """Get market status for symbol.

        Args:
            symbol: Trading symbol
            dt: Datetime to check (default: now)

        Returns:
            Dictionary with market status information

        Example:
            >>> status = MarketCalendar.get_market_status("GOLD")
            >>> print(status)
            {
                'symbol': 'GOLD',
                'is_open': True,
                'session': 'London',
                'open_time': datetime(...),
                'close_time': datetime(...),
                'next_open': datetime(...)
            }
        """
        if dt is None:
            dt = datetime.now(pytz.UTC)

        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        elif dt.tzinfo != pytz.UTC:
            dt = dt.astimezone(pytz.UTC)

        session = MarketCalendar.get_session(symbol)
        is_open = MarketCalendar.is_market_open(symbol, dt)

        market_tz = pytz.timezone(session.timezone)
        market_dt = dt.astimezone(market_tz)

        # Get today's market hours
        open_dt = market_tz.localize(
            datetime(
                market_dt.year,
                market_dt.month,
                market_dt.day,
                session.open_time.hour,
                session.open_time.minute,
            )
        ).astimezone(pytz.UTC)

        close_dt = market_tz.localize(
            datetime(
                market_dt.year,
                market_dt.month,
                market_dt.day,
                session.close_time.hour,
                session.close_time.minute,
            )
        ).astimezone(pytz.UTC)

        return {
            "symbol": symbol,
            "is_open": is_open,
            "session": session.name,
            "timezone": session.timezone,
            "open_time_utc": open_dt,
            "close_time_utc": close_dt,
            "next_open": MarketCalendar.get_next_open(symbol, dt),
        }
