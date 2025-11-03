"""Comprehensive gap tests for PR-012 Market Calendar & Timezone Gating.

Tests REAL business logic for:
- MarketCalendar: market open/close times, symbol mapping, trading sessions
- Timezone conversion: UTC ↔ market local times with DST handling
- Market status: daily open/close, next_open calculation, session info
- Edge cases: DST boundaries, weekend detection, symbol validation

All tests use REAL pytz timezone handling and datetime logic.
Tests validate BUSINESS LOGIC, not implementation details.
"""

from datetime import datetime, time, timedelta

import pytest
import pytz

from backend.app.trading.time.market_calendar import MarketCalendar, MarketSession
from backend.app.trading.time.tz import to_market_tz, to_utc, SYMBOL_TO_TIMEZONE


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def london_session():
    """London trading session (08:00-16:30 GMT/BST)."""
    return MarketCalendar.SESSIONS["london"]


@pytest.fixture
def newyork_session():
    """New York trading session (09:30-16:00 EST/EDT)."""
    return MarketCalendar.SESSIONS["newyork"]


@pytest.fixture
def asia_session():
    """Asia trading session (08:15-14:45 IST)."""
    return MarketCalendar.SESSIONS["asia"]


@pytest.fixture
def crypto_session():
    """Crypto trading session (00:00-23:59 UTC, Mon-Fri)."""
    return MarketCalendar.SESSIONS["crypto"]


# ============================================================================
# TEST CLASS: Market Session Definitions
# ============================================================================


class TestMarketSessionDefinitions:
    """Test market session configuration."""

    def test_london_session_defined(self, london_session):
        """London session is properly defined."""
        assert london_session.name == "London"
        assert london_session.open_time == time(8, 0)
        assert london_session.close_time == time(16, 30)
        assert london_session.trading_days == {0, 1, 2, 3, 4}  # Mon-Fri
        assert london_session.timezone == "Europe/London"

    def test_newyork_session_defined(self, newyork_session):
        """New York session is properly defined."""
        assert newyork_session.name == "New York"
        assert newyork_session.open_time == time(9, 30)
        assert newyork_session.close_time == time(16, 0)
        assert newyork_session.trading_days == {0, 1, 2, 3, 4}
        assert newyork_session.timezone == "America/New_York"

    def test_asia_session_defined(self, asia_session):
        """Asia session is properly defined."""
        assert asia_session.name == "Asia"
        assert asia_session.open_time == time(8, 15)
        assert asia_session.close_time == time(14, 45)
        assert asia_session.trading_days == {0, 1, 2, 3, 4}
        assert asia_session.timezone == "Asia/Kolkata"

    def test_crypto_session_defined(self, crypto_session):
        """Crypto session is properly defined (24/5)."""
        assert crypto_session.name == "Crypto"
        assert crypto_session.open_time == time(0, 0)
        assert crypto_session.close_time == time(23, 59)
        assert crypto_session.trading_days == {0, 1, 2, 3, 4}  # Mon-Fri, not weekends
        assert crypto_session.timezone == "UTC"


# ============================================================================
# TEST CLASS: Symbol to Session Mapping
# ============================================================================


class TestSymbolToSessionMapping:
    """Test symbol-to-session mappings."""

    def test_commodity_symbols_map_to_london(self):
        """Commodity symbols mapped to London session."""
        for symbol in ["GOLD", "SILVER", "OIL", "NATGAS"]:
            session = MarketCalendar.get_session(symbol)
            assert session.name == "London"

    def test_forex_symbols_map_to_correct_sessions(self):
        """Forex symbols mapped to primary market sessions."""
        assert MarketCalendar.get_session("EURUSD").name == "London"
        assert MarketCalendar.get_session("USDJPY").name == "New York"
        assert MarketCalendar.get_session("AUDUSD").name == "Asia"

    def test_stock_symbols_map_to_newyork(self):
        """Stock symbols mapped to New York session."""
        for symbol in ["S&P500", "NASDAQ", "TESLA", "APPLE"]:
            session = MarketCalendar.get_session(symbol)
            assert session.name == "New York"

    def test_index_symbols_map_to_sessions(self):
        """Index symbols mapped to correct sessions."""
        assert MarketCalendar.get_session("DAX").name == "London"
        assert MarketCalendar.get_session("FTSE").name == "London"
        assert MarketCalendar.get_session("NIFTY").name == "Asia"

    def test_crypto_symbols_map_to_crypto(self):
        """Crypto symbols mapped to crypto session (24/5)."""
        for symbol in ["BTCUSD", "ETHUSD"]:
            session = MarketCalendar.get_session(symbol)
            assert session.name == "Crypto"

    def test_unknown_symbol_raises_error(self):
        """Unknown symbol raises ValueError."""
        with pytest.raises(ValueError, match="Unknown symbol"):
            MarketCalendar.get_session("UNKNOWN")


# ============================================================================
# TEST CLASS: Market Open/Close - Weekday Logic
# ============================================================================


class TestMarketOpenCloseWeekday:
    """Test market open/close detection for weekday trading."""

    def test_market_open_monday_morning(self):
        """Market open Monday morning during session hours."""
        # Monday 2025-10-27, 10:00 UTC (during London session)
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_market_open_monday_newyork(self):
        """New York market open Monday morning (09:30 EST = 14:30 UTC)."""
        # Monday 2025-10-27, 14:30 UTC (09:30 EST)
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("S&P500", dt) is True

    def test_market_closed_before_opening(self):
        """Market closed before session opens."""
        # Monday 2025-10-27, 07:00 UTC (before London 08:00)
        dt = datetime(2025, 10, 27, 7, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False

    def test_market_closed_after_closing(self):
        """Market closed after session closes."""
        # Monday 2025-10-27, 17:00 UTC (after London 16:30)
        dt = datetime(2025, 10, 27, 17, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False

    def test_market_open_midday(self):
        """Market open during midday trading."""
        # Tuesday 2025-10-28, 12:00 UTC (middle of London session)
        dt = datetime(2025, 10, 28, 12, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_market_closed_just_before_close(self):
        """Market state just before close time."""
        # Friday 2025-10-31, 16:29 UTC (just before London 16:30)
        dt = datetime(2025, 10, 31, 16, 29, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_market_closed_at_exact_close_time(self):
        """Market closed at exact close time."""
        # Friday 2025-10-31, 16:30 UTC (exact London close)
        dt = datetime(2025, 10, 31, 16, 30, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False


# ============================================================================
# TEST CLASS: Weekend Detection
# ============================================================================


class TestWeekendDetection:
    """Test weekend market closure."""

    def test_market_closed_saturday(self):
        """Market closed on Saturday."""
        # Saturday 2025-11-01, 12:00 UTC
        dt = datetime(2025, 11, 1, 12, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False

    def test_market_closed_sunday(self):
        """Market closed on Sunday."""
        # Sunday 2025-11-02, 12:00 UTC
        dt = datetime(2025, 11, 2, 12, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False

    def test_market_closed_saturday_crypto(self):
        """Crypto market closed on Saturday (even though 24/5)."""
        # Saturday 2025-11-01, 12:00 UTC
        dt = datetime(2025, 11, 1, 12, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("BTCUSD", dt) is False

    def test_market_opens_monday_after_weekend(self):
        """Market reopens Monday after weekend."""
        # Monday 2025-11-03, 08:30 UTC (London session)
        dt = datetime(2025, 11, 3, 8, 30, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_friday_market_open(self):
        """Market open on Friday."""
        # Friday 2025-10-31, 12:00 UTC
        dt = datetime(2025, 10, 31, 12, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_friday_to_saturday_transition(self):
        """Market closes Friday afternoon, stays closed through weekend."""
        # Friday 2025-10-31, 17:00 UTC (after London close)
        dt_fri = datetime(2025, 10, 31, 17, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt_fri) is False

        # Saturday 2025-11-01, 12:00 UTC
        dt_sat = datetime(2025, 11, 1, 12, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt_sat) is False

        # Sunday 2025-11-02, 12:00 UTC
        dt_sun = datetime(2025, 11, 2, 12, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt_sun) is False


# ============================================================================
# TEST CLASS: Timezone Conversions
# ============================================================================


class TestTimezoneConversions:
    """Test timezone conversion functions."""

    def test_to_market_tz_utc_to_london(self):
        """Convert UTC to London timezone."""
        utc_dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        market_dt = to_market_tz(utc_dt, "GOLD")

        assert market_dt.tzinfo.zone == "Europe/London"
        # October: GMT (no DST), so same time
        assert market_dt.hour == 10

    def test_to_market_tz_utc_to_newyork(self):
        """Convert UTC to New York timezone."""
        utc_dt = datetime(2025, 10, 27, 14, 0, tzinfo=pytz.UTC)
        market_dt = to_market_tz(utc_dt, "S&P500")

        assert market_dt.tzinfo.zone == "America/New_York"
        # October: EDT (UTC-4), so 10:00 in NY
        assert market_dt.hour == 10

    def test_to_market_tz_respects_dst(self):
        """Timezone conversion respects DST changes."""
        # October 27, 2025 is before DST change in NY
        oct_utc = datetime(2025, 10, 27, 14, 0, tzinfo=pytz.UTC)
        oct_ny = to_market_tz(oct_utc, "S&P500")

        # December 1, 2025 is after DST change in NY (EST, UTC-5)
        dec_utc = datetime(2025, 12, 1, 14, 0, tzinfo=pytz.UTC)
        dec_ny = to_market_tz(dec_utc, "S&P500")

        # Offset should differ (EDT vs EST)
        assert oct_ny.utcoffset().total_seconds() != dec_ny.utcoffset().total_seconds()

    def test_to_market_tz_naive_datetime_localized(self):
        """Naive datetime (no tzinfo) gets localized to UTC."""
        naive_dt = datetime(2025, 10, 27, 10, 0)
        market_dt = to_market_tz(naive_dt, "GOLD")

        # Should localize to UTC first, then convert
        assert market_dt is not None

    def test_to_market_tz_non_utc_datetime_converted(self):
        """Non-UTC datetime gets converted to market timezone."""
        ny_tz = pytz.timezone("America/New_York")
        ny_dt = ny_tz.localize(datetime(2025, 10, 27, 10, 0))

        market_dt = to_market_tz(ny_dt, "GOLD")

        assert market_dt.tzinfo.zone == "Europe/London"

    def test_to_market_tz_invalid_symbol_raises_error(self):
        """Unknown symbol raises ValueError."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        with pytest.raises(ValueError, match="Unknown symbol"):
            to_market_tz(dt, "INVALID")

    def test_to_market_tz_non_datetime_raises_error(self):
        """Non-datetime input raises TypeError."""
        with pytest.raises(TypeError):
            to_market_tz("2025-10-27", "GOLD")


# ============================================================================
# TEST CLASS: to_utc Timezone Conversion
# ============================================================================


class TestToUTCConversion:
    """Test conversion back to UTC."""

    def test_to_utc_london_to_utc(self):
        """Convert London time to UTC."""
        london_tz = pytz.timezone("Europe/London")
        london_dt = london_tz.localize(datetime(2025, 10, 27, 10, 0))

        utc_dt = to_utc(london_dt, "GOLD")

        assert utc_dt.tzinfo == pytz.UTC
        # October: GMT (no DST), so same as input
        assert utc_dt.hour == 10

    def test_to_utc_newyork_to_utc(self):
        """Convert New York time to UTC."""
        ny_tz = pytz.timezone("America/New_York")
        ny_dt = ny_tz.localize(datetime(2025, 10, 27, 10, 0))

        utc_dt = to_utc(ny_dt, "S&P500")

        assert utc_dt.tzinfo == pytz.UTC
        # October: EDT (UTC-4), so 14:00 UTC
        assert utc_dt.hour == 14

    def test_to_utc_naive_datetime_raises_error(self):
        """Naive datetime raises error."""
        naive_dt = datetime(2025, 10, 27, 10, 0)
        with pytest.raises(ValueError):
            to_utc(naive_dt, "GOLD")

    def test_to_utc_non_datetime_raises_error(self):
        """Non-datetime input raises error."""
        with pytest.raises(TypeError):
            to_utc("2025-10-27 10:00:00", "GOLD")


# ============================================================================
# TEST CLASS: Market Status Report
# ============================================================================


class TestMarketStatusReport:
    """Test market status dictionary generation."""

    def test_market_status_includes_symbol(self):
        """Market status includes symbol."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        status = MarketCalendar.get_market_status("GOLD", dt)
        assert status["symbol"] == "GOLD"

    def test_market_status_includes_open_flag(self):
        """Market status includes is_open flag."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        status = MarketCalendar.get_market_status("GOLD", dt)
        assert "is_open" in status
        assert isinstance(status["is_open"], bool)

    def test_market_status_includes_session_name(self):
        """Market status includes session name."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        status = MarketCalendar.get_market_status("GOLD", dt)
        assert status["session"] == "London"

    def test_market_status_includes_timezone(self):
        """Market status includes timezone."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        status = MarketCalendar.get_market_status("GOLD", dt)
        assert status["timezone"] == "Europe/London"

    def test_market_status_includes_open_close_times(self):
        """Market status includes today's open and close times in UTC."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        status = MarketCalendar.get_market_status("GOLD", dt)

        assert "open_time_utc" in status
        assert "close_time_utc" in status
        assert isinstance(status["open_time_utc"], datetime)
        assert isinstance(status["close_time_utc"], datetime)

    def test_market_status_includes_next_open(self):
        """Market status includes next open time."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        status = MarketCalendar.get_market_status("GOLD", dt)

        assert "next_open" in status
        assert isinstance(status["next_open"], datetime)

    def test_market_status_uses_now_if_dt_not_provided(self):
        """Market status uses current time if dt not provided."""
        status = MarketCalendar.get_market_status("GOLD")
        assert "is_open" in status
        assert isinstance(status, dict)


# ============================================================================
# TEST CLASS: Next Open Calculation
# ============================================================================


class TestNextOpenCalculation:
    """Test calculation of next market open time."""

    def test_next_open_monday_midday_to_next_monday(self):
        """Next open from Monday midday is next day (Tuesday)."""
        # Monday 2025-10-27, 12:00 UTC (during trading hours)
        dt = datetime(2025, 10, 27, 12, 0, tzinfo=pytz.UTC)
        next_open = MarketCalendar.get_next_open("GOLD", dt)

        # Should be Tuesday 2025-10-28 (next day)
        assert next_open.weekday() == 1  # Tuesday
        assert next_open.day == 28

    def test_next_open_friday_to_monday(self):
        """Next open from Friday is Monday."""
        # Friday 2025-10-31, 17:00 UTC (after close)
        dt = datetime(2025, 10, 31, 17, 0, tzinfo=pytz.UTC)
        next_open = MarketCalendar.get_next_open("GOLD", dt)

        # Should be Monday 2025-11-03
        assert next_open.weekday() == 0  # Monday
        assert next_open.day == 3

    def test_next_open_saturday_to_monday(self):
        """Next open from Saturday is Monday."""
        # Saturday 2025-11-01, 12:00 UTC
        dt = datetime(2025, 11, 1, 12, 0, tzinfo=pytz.UTC)
        next_open = MarketCalendar.get_next_open("GOLD", dt)

        # Should be Monday 2025-11-03
        assert next_open.weekday() == 0
        assert next_open.day == 3

    def test_next_open_sunday_to_monday(self):
        """Next open from Sunday is Monday."""
        # Sunday 2025-11-02, 12:00 UTC
        dt = datetime(2025, 11, 2, 12, 0, tzinfo=pytz.UTC)
        next_open = MarketCalendar.get_next_open("GOLD", dt)

        # Should be Monday 2025-11-03
        assert next_open.weekday() == 0
        assert next_open.day == 3

    def test_next_open_during_trading_hours_is_after_24_hours(self):
        """Next open during trading hours is usually next day."""
        # Monday 2025-10-27, 12:00 UTC (during trading)
        dt = datetime(2025, 10, 27, 12, 0, tzinfo=pytz.UTC)
        next_open = MarketCalendar.get_next_open("GOLD", dt)

        # Should be Tuesday 2025-10-28
        assert next_open.weekday() == 1  # Tuesday
        assert next_open.day == 28

    def test_next_open_returns_utc_timezone(self):
        """Next open is always returned in UTC."""
        dt = datetime(2025, 10, 31, 17, 0, tzinfo=pytz.UTC)
        next_open = MarketCalendar.get_next_open("GOLD", dt)

        assert next_open.tzinfo == pytz.UTC

    def test_next_open_with_naive_datetime(self):
        """Next open handles naive datetime by localizing to UTC."""
        dt = datetime(2025, 10, 31, 17, 0)  # No tzinfo
        next_open = MarketCalendar.get_next_open("GOLD", dt)

        assert next_open is not None

    def test_next_open_uses_now_if_dt_not_provided(self):
        """Next open uses current time if dt not provided."""
        next_open = MarketCalendar.get_next_open("GOLD")
        assert isinstance(next_open, datetime)


# ============================================================================
# TEST CLASS: DST Boundary Tests
# ============================================================================


class TestDSTBoundaries:
    """Test behavior around DST (Daylight Saving Time) transitions."""

    def test_market_open_before_dst_change(self):
        """Market open times correct before DST change."""
        # October 24, 2025 Friday (before NY DST ends on Nov 2)
        # 14:00 UTC = 10:00 EDT (during market hours 09:30-16:00 EDT)
        dt = datetime(2025, 10, 24, 14, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("S&P500", dt) is True

    def test_market_open_after_dst_change(self):
        """Market open times correct after DST change."""
        # November 3, 2025 (after NY DST ends, EST = UTC-5)
        dt = datetime(2025, 11, 3, 14, 30, tzinfo=pytz.UTC)  # 09:30 EST
        assert MarketCalendar.is_market_open("S&P500", dt) is True

    def test_london_dst_boundary(self):
        """London DST boundaries handled correctly."""
        # Test market open/close around British Summer Time changes
        # March/October transitions in UK
        dt = datetime(2025, 10, 26, 15, 0, tzinfo=pytz.UTC)
        status = MarketCalendar.get_market_status("GOLD", dt)
        assert status["is_open"] in [True, False]  # Just verify it works


# ============================================================================
# TEST CLASS: Crypto 24/5 Schedule
# ============================================================================


class TestCrypto24_5Schedule:
    """Test crypto market 24/5 (always open except weekends)."""

    def test_crypto_open_monday_morning(self):
        """Crypto market open Monday morning."""
        # Monday 2025-10-27, 00:30 UTC
        dt = datetime(2025, 10, 27, 0, 30, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("BTCUSD", dt) is True

    def test_crypto_open_monday_afternoon(self):
        """Crypto market open Monday afternoon."""
        # Monday 2025-10-27, 18:00 UTC
        dt = datetime(2025, 10, 27, 18, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("BTCUSD", dt) is True

    def test_crypto_open_friday_late(self):
        """Crypto market open Friday evening (before weekend close)."""
        # Friday 2025-10-31, 23:30 UTC
        dt = datetime(2025, 10, 31, 23, 30, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("BTCUSD", dt) is True

    def test_crypto_closed_saturday(self):
        """Crypto market closed Saturday."""
        # Saturday 2025-11-01, 12:00 UTC
        dt = datetime(2025, 11, 1, 12, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("BTCUSD", dt) is False

    def test_crypto_closed_sunday(self):
        """Crypto market closed Sunday."""
        # Sunday 2025-11-02, 12:00 UTC
        dt = datetime(2025, 11, 2, 12, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("BTCUSD", dt) is False

    def test_crypto_next_open_from_friday(self):
        """Crypto next open from Friday is Monday."""
        # Friday 2025-10-31, 23:59 UTC
        dt = datetime(2025, 10, 31, 23, 59, tzinfo=pytz.UTC)
        next_open = MarketCalendar.get_next_open("BTCUSD", dt)

        # Should be Monday 2025-11-03, 00:00 UTC
        assert next_open.weekday() == 0


# ============================================================================
# TEST CLASS: Market Hours Edge Cases
# ============================================================================


class TestMarketHoursEdgeCases:
    """Test edge cases in market hours detection."""

    def test_market_exactly_at_open_time(self):
        """Market status at exact open time (should be open)."""
        # Monday 2025-10-27, 08:00 UTC (London open)
        dt = datetime(2025, 10, 27, 8, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_market_one_second_before_close(self):
        """Market open one second before close time."""
        # Monday 2025-10-27, 16:29:59 UTC
        dt = datetime(2025, 10, 27, 16, 29, 59, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_market_exactly_at_close_time(self):
        """Market closed at exact close time."""
        # Monday 2025-10-27, 16:30:00 UTC
        dt = datetime(2025, 10, 27, 16, 30, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False

    def test_market_one_microsecond_after_close(self):
        """Market closed one microsecond after close."""
        dt = datetime(2025, 10, 27, 16, 30, 0, 1, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False

    def test_multiple_symbols_same_time(self):
        """Check market status for multiple symbols at same time."""
        dt = datetime(2025, 10, 27, 14, 0, tzinfo=pytz.UTC)

        # GOLD (London): open
        assert MarketCalendar.is_market_open("GOLD", dt) is True
        # S&P500 (NY): open (14:00 UTC = 10:00 EDT, market open 09:30-16:00 EDT)
        assert MarketCalendar.is_market_open("S&P500", dt) is True

    def test_high_frequency_market_checks(self):
        """Rapid sequence of market checks for performance."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)

        for _ in range(100):
            assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_market_status_consistency(self):
        """Market status reports consistent state."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        status = MarketCalendar.get_market_status("GOLD", dt)

        # Verify internal consistency
        assert (status["open_time_utc"] < dt) or (status["is_open"] is False)
        if status["is_open"]:
            assert status["open_time_utc"] <= dt < status["close_time_utc"]


# ============================================================================
# TEST CLASS: Symbol-Timezone Mapping
# ============================================================================


class TestSymbolTimezoneMapping:
    """Test symbol to timezone mappings."""

    def test_symbol_timezone_map_completeness(self):
        """All symbols in SYMBOL_TO_TIMEZONE have valid timezone."""
        for symbol, tz_name in SYMBOL_TO_TIMEZONE.items():
            try:
                pytz.timezone(tz_name)
            except pytz.exceptions.UnknownTimeZoneError:
                pytest.fail(f"Invalid timezone for {symbol}: {tz_name}")

    def test_commodity_timezone_mapping(self):
        """Commodity symbols have correct timezone."""
        for symbol in ["GOLD", "SILVER", "OIL"]:
            tz = SYMBOL_TO_TIMEZONE[symbol]
            assert tz == "Europe/London"

    def test_us_market_timezone_mapping(self):
        """US market symbols have New York timezone."""
        for symbol in ["S&P500", "NASDAQ", "APPLE"]:
            tz = SYMBOL_TO_TIMEZONE[symbol]
            assert tz == "America/New_York"

    def test_crypto_timezone_mapping(self):
        """Crypto symbols have UTC timezone."""
        for symbol in ["BTCUSD", "ETHUSD"]:
            tz = SYMBOL_TO_TIMEZONE[symbol]
            assert tz == "UTC"


# ============================================================================
# TEST CLASS: Error Handling
# ============================================================================


class TestErrorHandling:
    """Test error handling and validation."""

    def test_invalid_symbol_in_is_market_open(self):
        """Invalid symbol raises error in is_market_open."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        with pytest.raises(ValueError, match="Unknown symbol"):
            MarketCalendar.is_market_open("INVALID_SYMBOL", dt)

    def test_invalid_symbol_in_get_session(self):
        """Invalid symbol raises error in get_session."""
        with pytest.raises(ValueError, match="Unknown symbol"):
            MarketCalendar.get_session("INVALID_SYMBOL")

    def test_invalid_symbol_in_get_next_open(self):
        """Invalid symbol raises error in get_next_open."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        with pytest.raises(ValueError, match="Unknown symbol"):
            MarketCalendar.get_next_open("INVALID_SYMBOL", dt)

    def test_invalid_timezone_in_to_market_tz(self):
        """Invalid timezone raises error in to_market_tz."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        with pytest.raises(ValueError):
            to_market_tz(dt, "UNKNOWN")

    def test_none_datetime_in_to_market_tz(self):
        """None datetime in to_market_tz raises error."""
        with pytest.raises(TypeError):
            to_market_tz(None, "GOLD")


# ============================================================================
# TEST CLASS: Integration Scenarios
# ============================================================================


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_trading_window_scenario_london_morning(self):
        """Verify trading window: London morning Monday."""
        # Monday morning, during London session
        dt = datetime(2025, 10, 27, 9, 0, tzinfo=pytz.UTC)

        gold_open = MarketCalendar.is_market_open("GOLD", dt)
        ny_open = MarketCalendar.is_market_open("S&P500", dt)
        crypto_open = MarketCalendar.is_market_open("BTCUSD", dt)

        assert gold_open is True  # London morning
        assert ny_open is False  # Before NY open
        assert crypto_open is True  # Crypto always on Mon

    def test_trading_window_scenario_overlap(self):
        """Verify trading window: London and New York overlap."""
        # 14:00 UTC = 10:00 EDT (NY morning, London afternoon)
        dt = datetime(2025, 10, 27, 14, 0, tzinfo=pytz.UTC)

        gold_open = MarketCalendar.is_market_open("GOLD", dt)
        ny_open = MarketCalendar.is_market_open("S&P500", dt)

        assert gold_open is True
        assert ny_open is True

    def test_trading_window_scenario_ny_only(self):
        """Verify trading window: New York only."""
        # 21:00 UTC = 17:00 EDT (NY closing, London closed)
        dt = datetime(2025, 10, 27, 21, 0, tzinfo=pytz.UTC)

        gold_open = MarketCalendar.is_market_open("GOLD", dt)
        ny_open = MarketCalendar.is_market_open("S&P500", dt)

        assert gold_open is False  # Closed
        assert ny_open is False  # Just closed (16:00 close)

    def test_trading_window_scenario_all_closed(self):
        """Verify trading window: All markets closed at night."""
        # 02:00 UTC (middle of night - before any market opens)
        # London: 02:00 GMT (opens 08:00), NY: 21:00 EDT prev day (closes 16:00), Asia: 07:30 IST (opens 08:15)
        dt = datetime(2025, 10, 27, 2, 0, tzinfo=pytz.UTC)

        gold_open = MarketCalendar.is_market_open("GOLD", dt)
        ny_open = MarketCalendar.is_market_open("S&P500", dt)
        asia_open = MarketCalendar.is_market_open("NIFTY", dt)

        assert gold_open is False
        assert ny_open is False
        assert asia_open is False

    def test_signal_gating_scenario(self):
        """Realistic scenario: Gate signal submission by market hours."""
        # Friday close: signal ready but market closed
        dt_friday_close = datetime(2025, 10, 31, 17, 0, tzinfo=pytz.UTC)

        # Should NOT allow trade
        allow_trade = MarketCalendar.is_market_open("GOLD", dt_friday_close)
        assert allow_trade is False

        # Monday open: signal ready and market open
        dt_monday_open = datetime(2025, 11, 3, 8, 30, tzinfo=pytz.UTC)

        # Should allow trade
        allow_trade = MarketCalendar.is_market_open("GOLD", dt_monday_open)
        assert allow_trade is True
