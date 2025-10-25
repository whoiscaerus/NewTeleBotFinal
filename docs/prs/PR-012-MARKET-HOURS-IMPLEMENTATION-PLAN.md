# PR-012: Market Hours & Timezone Gating - Implementation Plan

**Status**: Ready to Start
**Duration**: 1-2 hours
**Dependencies**: PR-001 (baseline) ✅
**Date**: October 24, 2025

---

## 📋 Objective

Implement market calendar and timezone utilities to gate trading signals based on market hours. This prevents signals from being generated or executed outside of market operating hours.

---

## 🎯 Acceptance Criteria

### Criterion 1: Market Calendar Lookup
- [ ] `is_market_open(symbol: str, datetime: dt) -> bool` returns True/False based on market schedule
- [ ] Test case: `is_market_open("GOLD", friday_17_00_UTC) == False` (markets closed)
- [ ] Test case: `is_market_open("GOLD", monday_14_30_UTC) == True` (markets open)
- [ ] Support symbols: GOLD, EURUSD, GBPUSD, USDJPY, S&P500, NASDAQ

### Criterion 2: Timezone Handling
- [ ] Accept both UTC and broker timezone inputs
- [ ] Correct handling of daylight saving time (DST) transitions
- [ ] Test: DST boundary cases (spring forward/fall back)
- [ ] Test: Different timezones for same symbol

### Criterion 3: Market Session Definitions
- [ ] Define market sessions (London, US, Asia)
- [ ] Map symbols to sessions
- [ ] Pre-market, regular, post-market times
- [ ] Weekend detection

### Criterion 4: Performance
- [ ] `is_market_open()` runs in <5ms
- [ ] Cacheable results (no unnecessary recalculation)
- [ ] Memory efficient (no excessive object creation)

### Criterion 5: Documentation
- [ ] All functions have docstrings with examples
- [ ] Market hour definitions documented
- [ ] Integration with PR-014 documented

---

## 📁 Files to Create/Modify

### New Files

#### `backend/app/trading/time/market_calendar.py` (150-200 lines)
```python
"""Market calendar and trading hours definitions.

Provides market hours lookup, timezone handling, and market session detection.
"""

from dataclasses import dataclass
from typing import Dict, Set
from datetime import datetime, time, timezone
import pytz

@dataclass
class MarketSession:
    """Market trading session definition."""
    name: str                    # "London", "New York", "Asia"
    open_time: time             # 08:00 UTC
    close_time: time            # 16:30 UTC
    trading_days: Set[int]      # {0,1,2,3,4} = Mon-Fri
    timezone: str               # "Europe/London"

class MarketCalendar:
    """Market hours and trading session management."""

    SESSIONS: Dict[str, MarketSession] = {...}
    SYMBOL_TO_SESSION: Dict[str, str] = {...}

    @staticmethod
    def is_market_open(symbol: str, dt: datetime) -> bool:
        """Check if market is open for symbol at given time.

        Args:
            symbol: Trading symbol (GOLD, EURUSD, etc.)
            dt: Datetime to check (should be UTC)

        Returns:
            True if market is open, False otherwise

        Example:
            >>> dt = datetime(2025, 10, 24, 15, 30, tzinfo=pytz.UTC)
            >>> MarketCalendar.is_market_open("EURUSD", dt)
            True
        """

    @staticmethod
    def get_next_open(symbol: str) -> datetime:
        """Get next market open time for symbol."""

    @staticmethod
    def get_session(symbol: str) -> MarketSession:
        """Get session for a symbol."""
```

#### `backend/app/trading/time/tz.py` (100-150 lines)
```python
"""Timezone utilities for market time conversions."""

from datetime import datetime
import pytz

def to_market_tz(dt: datetime, symbol: str) -> datetime:
    """Convert UTC datetime to market's local timezone."""

def to_utc(dt: datetime, symbol: str) -> datetime:
    """Convert market timezone to UTC."""

def is_dst_transition(dt: datetime, tz_name: str) -> bool:
    """Check if datetime is during DST transition."""
```

#### `backend/app/trading/time/__init__.py` (20-30 lines)
```python
"""Trading time and market hours utilities."""

from .market_calendar import MarketCalendar
from .tz import to_market_tz, to_utc

__all__ = ["MarketCalendar", "to_market_tz", "to_utc"]
```

### Test File

#### `backend/tests/trading/test_market_calendar.py` (200-250 lines)
```python
"""Tests for market calendar and timezone gating."""

import pytest
from datetime import datetime, time
import pytz

from backend.app.trading.time import MarketCalendar

class TestMarketCalendarBasics:
    """Test basic market hour lookups."""

    def test_market_open_during_london_session(self):
        """Test GOLD is open during London session."""
        # Monday 10:00 UTC (London session open)
        dt = datetime(2025, 10, 27, 10, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is True

    def test_market_closed_weekend(self):
        """Test markets closed on Saturday."""
        # Saturday 10:00 UTC
        dt = datetime(2025, 10, 25, 10, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False

    def test_market_closed_after_hours(self):
        """Test GOLD closed after London session ends."""
        # Friday 17:00 UTC (after market close)
        dt = datetime(2025, 10, 24, 17, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("GOLD", dt) is False

    def test_market_open_us_session(self):
        """Test EURUSD open during US session."""
        # Monday 16:00 UTC (US session open)
        dt = datetime(2025, 10, 27, 16, 0, tzinfo=pytz.UTC)
        assert MarketCalendar.is_market_open("EURUSD", dt) is True

class TestTimezoneConversion:
    """Test timezone conversions."""

    def test_utc_to_london(self):
        """Test UTC to London conversion."""
        dt_utc = datetime(2025, 10, 27, 12, 0, tzinfo=pytz.UTC)
        dt_london = to_market_tz(dt_utc, "GOLD")
        assert dt_london.hour == 12  # or 13 if DST

    def test_london_to_utc(self):
        """Test London to UTC conversion."""
        london_tz = pytz.timezone("Europe/London")
        dt_london = london_tz.localize(datetime(2025, 10, 27, 12, 0))
        dt_utc = to_utc(dt_london, "GOLD")
        assert dt_utc.tzinfo == pytz.UTC

class TestDSTHandling:
    """Test daylight saving time transitions."""

    def test_spring_forward_dst(self):
        """Test DST spring forward (US March 2025)."""
        # Typically 2nd Sunday of March at 2 AM
        # 2025: March 9, 2 AM → 3 AM
        ...

    def test_fall_back_dst(self):
        """Test DST fall back (US November 2025)."""
        # Typically 1st Sunday of November at 2 AM
        # 2025: November 2, 2 AM → 1 AM
        ...
```

---

## 🛠️ Implementation Steps

### Step 1: Define Market Sessions (30 min)
1. Research and document market hours for:
   - London (forex, commodities) - 08:00-16:30 UTC, Mon-Fri
   - New York (stocks, forex) - 13:30-20:00 UTC, Mon-Fri (pre-market from 12:00)
   - Asia (forex, stocks) - 23:00 UTC (previous day)-07:00 UTC, Mon-Sat
   - Crypto (24/5) - Mon 00:00 UTC to Fri 23:59 UTC

2. Create market session definitions in `market_calendar.py`
3. Map symbols to sessions in a dict

### Step 2: Implement is_market_open() (30 min)
1. Parse symbol to get session
2. Check if weekday is trading day
3. Convert datetime to market timezone
4. Check if time is between open_time and close_time
5. Return boolean

### Step 3: Implement Timezone Utils (20 min)
1. `to_market_tz()`: Convert UTC to market timezone using pytz
2. `to_utc()`: Convert market timezone to UTC
3. Handle DST automatically (pytz handles this)

### Step 4: Write Tests (30 min)
1. Test basic market open/closed scenarios
2. Test DST transitions
3. Test all supported symbols
4. Test edge cases (market open/close boundaries)

### Step 5: Integration Verification (10 min)
1. Verify can import from `backend.app.trading.time`
2. Verify pytest discovers and runs all tests
3. Verify coverage >90%

---

## 📊 Market Hours Reference

### GOLD (Commodities) - London Session
- Open: 08:00 UTC (Mon-Fri)
- Close: 16:30 UTC
- Pre-market: 07:30-08:00 UTC
- Session: London

### EURUSD (Forex) - 24-hour, market overlap
- London: 08:00-16:30 UTC
- New York: 13:30-20:00 UTC
- Overlap: 13:30-16:30 UTC (most liquid)
- Session: Multiple/24-hour

### S&P500 (Stocks) - US Session
- Pre-market: 12:00 UTC (4:00 AM ET)
- Open: 13:30 UTC (9:30 AM ET)
- Close: 20:00 UTC (4:00 PM ET)
- After-hours: 20:00-00:00 UTC (4 PM - 8 PM ET)
- Session: New York

### NIFTY (India) - Asia Session
- Open: 23:15 UTC (previous day)
- Close: 09:45 UTC
- Session: Asia

---

## ✅ Success Criteria Checklist

Before marking PR complete:

- [ ] `backend/app/trading/time/market_calendar.py` created (150-200 lines)
- [ ] `backend/app/trading/time/tz.py` created (100-150 lines)
- [ ] `backend/app/trading/time/__init__.py` created
- [ ] `backend/tests/trading/test_market_calendar.py` created (200+ lines)
- [ ] All test cases passing
- [ ] Coverage >90%
- [ ] Type hints 100%
- [ ] Docstrings 100%
- [ ] No TODOs or FIXMEs
- [ ] Black formatted
- [ ] All symbols covered (GOLD, EURUSD, GBPUSD, USDJPY, S&P500, NASDAQ)
- [ ] DST handling tested
- [ ] Edge cases (market open/close times) tested

---

## 🔗 Integration Points

### Used By
- **PR-014** (Fib-RSI Strategy): `is_market_open("GOLD", now)` gates signal generation
- **PR-019** (Trading Loop): Checks if market open before posting signals
- **PR-021** (Signals API): Returns market status in signal detail endpoint

### Depends On
- **PR-001**: Baseline (pytest, Black, imports)

---

## 📝 Implementation Checklist

- [ ] Create `backend/app/trading/time/` directory
- [ ] Create `__init__.py` with exports
- [ ] Implement `market_calendar.py` with MarketCalendar class
- [ ] Implement `tz.py` with timezone utilities
- [ ] Create test file
- [ ] Add 20+ test cases
- [ ] Verify coverage >90%
- [ ] All type hints present
- [ ] All docstrings present
- [ ] Black format applied
- [ ] No import errors
- [ ] Integration verified with existing code

---

## ⏱️ Time Estimate: 1-2 hours

- Implementation: 1 hour
- Testing: 45 minutes
- Documentation: 15 minutes

---

**Next PR After This**: PR-013 (Data Pull Pipelines)
**Dependency Chain**: PR-012 → PR-014 (strategy gating)

---

## 📞 Questions?

Refer to:
- Market hours data: Research via CME, London Stock Exchange, NSE websites
- pytz timezone docs: https://pytz.sourceforge.io/
- datetime docs: https://docs.python.org/3/library/datetime.html
