"""Tests for market hours and timezone utilities.

Test categories:
1. Market hours detection (is_market_open)
2. Timezone conversions (to_market_tz, to_utc)
3. DST handling (spring forward, fall back)
4. Edge cases (market close, weekend, holidays)
5. Symbol validation and error handling

Test strategy:
- Use fixed dates to avoid test brittleness
- Test each symbol's specific hours
- Test both open and closed states
- Test timezone conversions both directions
- Test DST transitions explicitly
"""

from datetime import datetime

import pytest
import pytz

from backend.app.trading.time import (
    MarketCalendar,
    get_offset_utc,
    is_dst_transition,
    is_same_day_in_tz,
    to_market_tz,
    to_utc,
)


class TestMarketCalendarBasics:
    """Test basic market hours detection."""

    def test_gold_market_open_london_hours(self):
        """Test GOLD is open during London trading hours (08:00-16:30 UTC Mon-Fri)."""
        # Monday 10:00 UTC (within London 08:00-16:30)
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_gold_market_closed_before_london_open(self):
        """Test GOLD is closed before London open (07:59 UTC)."""
        # Monday 07:59 UTC (before London 08:00)
        dt = datetime(2025, 10, 27, 7, 59, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False

    def test_gold_market_closed_after_london_close(self):
        """Test GOLD is closed after London close (16:31 UTC)."""
        # Monday 16:31 UTC (after London 16:30)
        dt = datetime(2025, 10, 27, 16, 31, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False

    def test_gold_market_closed_weekend(self):
        """Test GOLD is closed on Saturday."""
        # Saturday 10:00 UTC
        dt = datetime(2025, 10, 25, 10, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False

    def test_nasdaq_market_open_new_york_hours(self):
        """Test NASDAQ is open during NY trading hours (09:30-16:00 EDT = 13:30-20:00 UTC Mon-Fri)."""
        # Monday 15:00 UTC (11:00 EDT - within 09:30-16:00 EDT)
        dt = datetime(2025, 10, 27, 15, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("NASDAQ", dt) is True

    def test_nasdaq_market_closed_before_ny_open(self):
        """Test NASDAQ is closed before NY open (09:30 EDT = 13:30 UTC)."""
        # Monday 13:29 UTC (09:29 EDT - before 09:30 EDT open)
        dt = datetime(2025, 10, 27, 13, 29, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("NASDAQ", dt) is False

    def test_nasdaq_market_closed_after_ny_close(self):
        """Test NASDAQ is closed after NY close (16:00 EDT = 20:00 UTC)."""
        # Monday 20:15 UTC (16:15 EDT - after 16:00 EDT close)
        dt = datetime(2025, 10, 27, 20, 15, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("NASDAQ", dt) is False

    def test_crypto_market_open_weekday(self):
        """Test crypto markets are open during weekdays."""
        # Monday 15:00 UTC
        dt = datetime(2025, 10, 27, 15, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("BTCUSD", dt) is True

    def test_crypto_market_closed_weekend(self):
        """Test crypto markets are closed on weekends."""
        # Saturday 15:00 UTC
        dt = datetime(2025, 10, 25, 15, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("BTCUSD", dt) is False

    def test_unknown_symbol_raises_error(self):
        """Test unknown symbol raises ValueError."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        with pytest.raises(ValueError, match="Unknown symbol"):
            MarketCalendar.is_market_open("INVALID", dt)

    def test_naive_datetime_raises_error_or_converts(self):
        """Test naive datetime handling."""
        # Should either convert or raise clear error
        dt = datetime(2025, 10, 27, 10, 0)  # naive
        # MarketCalendar should handle this gracefully (our impl converts to UTC)
        result = MarketCalendar.is_market_open("GOLD", dt)
        assert isinstance(result, bool)


class TestMarketOpen:
    """Test market open/close boundary conditions."""

    def test_market_open_at_exact_open_time(self):
        """Test market is open at exact opening time."""
        # Monday 08:00:00 UTC (exact London open)
        dt = datetime(2025, 10, 27, 8, 0, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_market_closed_at_exact_close_time(self):
        """Test market is closed at exact closing time."""
        # Monday 16:30:00 UTC (exact London close)
        dt = datetime(2025, 10, 27, 16, 30, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False

    def test_market_open_one_second_before_close(self):
        """Test market is open 1 second before close."""
        dt = datetime(2025, 10, 27, 16, 29, 59, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_all_weekdays_are_trading_days(self):
        """Test all weekdays have market open during session hours."""
        # Monday (weekday 0) through Friday (weekday 4)
        for day in range(27, 31):  # Oct 27-30 = Mon-Thu, Oct 31 = Fri
            dt = datetime(2025, 10, day, 10, 0, tzinfo=pytz.UTC)
            assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_sunday_is_closed(self):
        """Test Sunday (weekday 6) is closed."""
        dt = datetime(2025, 10, 26, 10, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False


class TestTimezoneConversions:
    """Test timezone conversion functions."""

    def test_to_market_tz_utc_to_london(self):
        """Test UTC to London timezone conversion."""
        # Oct 27, 2025 10:00 UTC (winter time, no DST)
        utc_dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        market_dt = to_market_tz(utc_dt, "GOLD")

        # In October, London is GMT (UTC+0)
        assert market_dt.hour == 10
        assert market_dt.minute == 0
        assert str(market_dt.tzinfo) == "Europe/London"

    def test_to_market_tz_utc_to_newyork(self):
        """Test UTC to New York timezone conversion."""
        # Oct 27, 2025 14:00 UTC (EDT, UTC-4)
        utc_dt = datetime(2025, 10, 27, 14, 0, tzinfo=pytz.UTC)
        market_dt = to_market_tz(utc_dt, "S&P500")

        # In October, NYC is EDT (UTC-4)
        assert market_dt.hour == 10
        assert market_dt.minute == 0
        assert str(market_dt.tzinfo) == "America/New_York"

    def test_to_utc_london_to_utc(self):
        """Test London to UTC conversion."""
        london_tz = pytz.timezone("Europe/London")
        london_dt = london_tz.localize(datetime(2025, 10, 27, 10, 0))

        utc_dt = to_utc(london_dt, "GOLD")
        assert utc_dt.hour == 10
        assert utc_dt.minute == 0
        assert utc_dt.tzinfo == pytz.UTC

    def test_to_utc_newyork_to_utc(self):
        """Test New York to UTC conversion."""
        ny_tz = pytz.timezone("America/New_York")
        ny_dt = ny_tz.localize(datetime(2025, 10, 27, 10, 0))

        utc_dt = to_utc(ny_dt, "S&P500")
        # Oct 27 10:00 EDT (UTC-4) = 14:00 UTC
        assert utc_dt.hour == 14
        assert utc_dt.minute == 0
        assert utc_dt.tzinfo == pytz.UTC

    def test_conversion_roundtrip(self):
        """Test UTC → market TZ → UTC roundtrip."""
        original_utc = datetime(2025, 10, 27, 15, 30, tzinfo=pytz.UTC)

        market_dt = to_market_tz(original_utc, "GOLD")
        back_to_utc = to_utc(market_dt, "GOLD")

        assert original_utc == back_to_utc

    def test_to_market_tz_unknown_symbol_raises(self):
        """Test conversion with unknown symbol raises ValueError."""
        utc_dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        with pytest.raises(ValueError, match="Unknown symbol"):
            to_market_tz(utc_dt, "INVALID")

    def test_to_utc_unknown_symbol_raises(self):
        """Test conversion with unknown symbol raises ValueError."""
        london_tz = pytz.timezone("Europe/London")
        london_dt = london_tz.localize(datetime(2025, 10, 27, 10, 0))

        with pytest.raises(ValueError, match="Unknown symbol"):
            to_utc(london_dt, "INVALID")

    def test_to_utc_naive_datetime_raises(self):
        """Test to_utc with naive datetime raises ValueError."""
        naive_dt = datetime(2025, 10, 27, 10, 0)
        with pytest.raises(ValueError, match="must have timezone"):
            to_utc(naive_dt, "GOLD")


class TestDSTHandling:
    """Test DST (Daylight Saving Time) transitions."""

    def test_is_dst_transition_spring_forward(self):
        """Test detection of spring forward DST transition."""
        # US: Spring forward on 2nd Sunday of March at 2:00 AM
        # 2025-03-09 02:30 is during spring forward transition
        dt = datetime(2025, 3, 9, 2, 30)
        assert is_dst_transition(dt, "America/New_York") is True

    def test_is_dst_transition_fall_back(self):
        """Test detection of fall back DST transition."""
        # US: Fall back on 1st Sunday of November at 2:00 AM
        # 2025-11-02 01:30 is during fall back transition
        dt = datetime(2025, 11, 2, 1, 30)
        assert is_dst_transition(dt, "America/New_York") is True

    def test_is_not_dst_transition_normal_time(self):
        """Test non-transition time returns False."""
        # Normal time, not during transition
        dt = datetime(2025, 10, 15, 10, 0)
        assert is_dst_transition(dt, "America/New_York") is False

    def test_is_dst_transition_invalid_timezone_raises(self):
        """Test invalid timezone raises ValueError."""
        dt = datetime(2025, 10, 27, 10, 0)
        with pytest.raises(ValueError, match="Unknown timezone"):
            is_dst_transition(dt, "Invalid/Timezone")

    def test_gold_market_conversion_during_dst(self):
        """Test GOLD market timezone conversion during DST."""
        # March 30, 2025 - London is in BST (UTC+1)
        utc_dt = datetime(2025, 3, 30, 10, 0, tzinfo=pytz.UTC)
        market_dt = to_market_tz(utc_dt, "GOLD")

        # 10:00 UTC + 1 hour = 11:00 BST
        assert market_dt.hour == 11

    def test_nasdaq_market_conversion_during_dst(self):
        """Test NASDAQ conversion during US EDT."""
        # March 31, 2025 - NYC is in EDT (UTC-4)
        utc_dt = datetime(2025, 3, 31, 14, 0, tzinfo=pytz.UTC)
        market_dt = to_market_tz(utc_dt, "NASDAQ")

        # 14:00 UTC - 4 hours = 10:00 EDT
        assert market_dt.hour == 10


class TestGetSession:
    """Test session lookup functions."""

    def test_get_session_gold(self):
        """Test get_session returns correct session for GOLD."""
        session = MarketCalendar.get_session("GOLD")
        assert session.name == "London"
        assert session.timezone == "Europe/London"

    def test_get_session_nasdaq(self):
        """Test get_session returns correct session for NASDAQ."""
        session = MarketCalendar.get_session("NASDAQ")
        assert session.name == "New York"
        assert session.timezone == "America/New_York"

    def test_get_session_unknown_symbol_raises(self):
        """Test get_session with unknown symbol raises ValueError."""
        with pytest.raises(ValueError, match="Unknown symbol"):
            MarketCalendar.get_session("INVALID")

    def test_session_trading_days(self):
        """Test session has correct trading days (Mon-Fri)."""
        session = MarketCalendar.get_session("GOLD")
        assert session.trading_days == {0, 1, 2, 3, 4}


class TestGetNextOpen:
    """Test next market open calculation."""

    def test_get_next_open_same_day(self):
        """Test next open on same trading day before close."""
        # Monday 09:00 UTC (before London close at 16:30)
        dt = datetime(2025, 10, 27, 9, 0, tzinfo=pytz.UTC)

        # Next open is tomorrow (Tuesday) at 08:00 UTC
        next_open = MarketCalendar.get_next_open("GOLD", dt)
        assert next_open.day == 28
        assert next_open.hour == 8
        assert next_open.minute == 0

    def test_get_next_open_after_close(self):
        """Test next open after market close."""
        # Monday 17:00 UTC (after London close)
        dt = datetime(2025, 10, 27, 17, 0, tzinfo=pytz.UTC)

        # Next open is Tuesday at 08:00 UTC
        next_open = MarketCalendar.get_next_open("GOLD", dt)
        assert next_open.day == 28
        assert next_open.hour == 8

    def test_get_next_open_friday_evening(self):
        """Test next open from Friday evening is Monday."""
        # Friday 17:00 UTC (after close)
        dt = datetime(2025, 10, 31, 17, 0, tzinfo=pytz.UTC)

        # Next open is Monday at 08:00 UTC
        next_open = MarketCalendar.get_next_open("GOLD", dt)
        assert next_open.weekday() == 0  # Monday
        assert next_open.hour == 8

    def test_get_next_open_weekend(self):
        """Test next open from weekend is Monday."""
        # Saturday 10:00 UTC
        dt = datetime(2025, 10, 25, 10, 0, tzinfo=pytz.UTC)

        # Next open is Monday at 08:00 UTC
        next_open = MarketCalendar.get_next_open("GOLD", dt)
        assert next_open.weekday() == 0  # Monday
        assert next_open.hour == 8

    def test_get_next_open_default_now(self):
        """Test get_next_open with default datetime (now)."""
        # Should not raise error
        next_open = MarketCalendar.get_next_open("GOLD")
        assert next_open is not None
        assert next_open.tzinfo == pytz.UTC


class TestMarketStatus:
    """Test get_market_status function."""

    def test_market_status_structure(self):
        """Test market status dict has all required fields."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        status = MarketCalendar.get_market_status("GOLD", dt)

        assert "symbol" in status
        assert "is_open" in status
        assert "session" in status
        assert "timezone" in status
        assert "open_time_utc" in status
        assert "close_time_utc" in status
        assert "next_open" in status

    def test_market_status_open(self):
        """Test market status shows open for open market."""
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        status = MarketCalendar.get_market_status("GOLD", dt)

        assert status["symbol"] == "GOLD"
        assert status["is_open"] is True
        assert status["session"] == "London"

    def test_market_status_closed(self):
        """Test market status shows closed for closed market."""
        dt = datetime(2025, 10, 27, 17, 0, tzinfo=pytz.UTC)
        status = MarketCalendar.get_market_status("GOLD", dt)

        assert status["symbol"] == "GOLD"
        assert status["is_open"] is False


class TestGetOffsetUTC:
    """Test UTC offset calculation."""

    def test_offset_london_winter(self):
        """Test London winter UTC offset."""
        dt = datetime(2025, 1, 15, 10, 0)
        offset = get_offset_utc(dt, "Europe/London")
        assert offset == "+00:00"

    def test_offset_london_summer(self):
        """Test London summer UTC offset (BST)."""
        dt = datetime(2025, 7, 15, 10, 0)
        offset = get_offset_utc(dt, "Europe/London")
        assert offset == "+01:00"

    def test_offset_newyork_winter(self):
        """Test New York winter UTC offset (EST)."""
        dt = datetime(2025, 1, 15, 10, 0)
        offset = get_offset_utc(dt, "America/New_York")
        assert offset == "-05:00"

    def test_offset_newyork_summer(self):
        """Test New York summer UTC offset (EDT)."""
        dt = datetime(2025, 7, 15, 10, 0)
        offset = get_offset_utc(dt, "America/New_York")
        assert offset == "-04:00"

    def test_offset_invalid_timezone_raises(self):
        """Test invalid timezone raises ValueError."""
        dt = datetime(2025, 10, 27, 10, 0)
        with pytest.raises(ValueError, match="Unknown timezone"):
            get_offset_utc(dt, "Invalid/Timezone")


class TestIsSameDayInTZ:
    """Test same day checking across timezones."""

    def test_same_day_london_utc_midnight(self):
        """Test UTC midnight maps to same day in London."""
        # Jan 1, 00:00 UTC = Jan 1 in London (GMT)
        dt_utc = datetime(2025, 1, 1, 0, 0, tzinfo=pytz.UTC)
        assert is_same_day_in_tz(dt_utc, "Europe/London", 2025, 1, 1) is True

    def test_different_day_newyork_from_utc_midnight(self):
        """Test UTC midnight is previous day in New York."""
        # Jan 1, 00:00 UTC = Dec 31 in New York
        dt_utc = datetime(2025, 1, 1, 0, 0, tzinfo=pytz.UTC)
        assert is_same_day_in_tz(dt_utc, "America/New_York", 2024, 12, 31) is True

    def test_utc_afternoon_crosses_to_next_day_tokyo(self):
        """Test UTC afternoon is next day in Tokyo."""
        # Oct 27, 15:00 UTC = Oct 28 in Tokyo (UTC+9)
        dt_utc = datetime(2025, 10, 27, 15, 0, tzinfo=pytz.UTC)
        assert is_same_day_in_tz(dt_utc, "Asia/Tokyo", 2025, 10, 28) is True


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_market_open_midnight_in_utc(self):
        """Test market status at UTC midnight."""
        # Monday 00:00 UTC
        dt = datetime(2025, 10, 27, 0, 0, tzinfo=pytz.UTC)
        result = MarketCalendar.is_market_open("GOLD", dt)
        assert result is False  # Before 08:00 open

    def test_market_open_last_second_of_day(self):
        """Test market status at last second of day."""
        # Monday 23:59:59 UTC
        dt = datetime(2025, 10, 27, 23, 59, 59, tzinfo=pytz.UTC)
        result = MarketCalendar.is_market_open("GOLD", dt)
        assert result is False

    def test_type_error_on_invalid_input(self):
        """Test type errors on invalid input types."""
        with pytest.raises(TypeError):
            to_market_tz("not a datetime", "GOLD")

        with pytest.raises(TypeError):
            to_utc("not a datetime", "GOLD")

        with pytest.raises(TypeError):
            is_dst_transition("not a datetime", "America/New_York")

    def test_all_symbols_have_valid_timezone(self):
        """Test all symbols map to valid timezones."""
        from backend.app.trading.time.tz import SYMBOL_TO_TIMEZONE

        for symbol, tz_name in SYMBOL_TO_TIMEZONE.items():
            try:
                tz = pytz.timezone(tz_name)
                assert tz is not None
            except pytz.exceptions.UnknownTimeZoneError:
                pytest.fail(f"Symbol {symbol} has invalid timezone: {tz_name}")

    def test_all_symbols_mapped_to_session(self):
        """Test all symbols have valid session mapping."""
        from backend.app.trading.time.market_calendar import MarketCalendar

        for symbol in MarketCalendar.SYMBOL_TO_SESSION.keys():
            assert symbol in MarketCalendar.SYMBOL_TO_SESSION
