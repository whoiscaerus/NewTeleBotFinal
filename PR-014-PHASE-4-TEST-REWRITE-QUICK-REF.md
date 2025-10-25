# PR-014 Phase 4: Test Suite Rewrite - Quick Reference

**Status**: Ready to start - All code changes complete, now rewriting tests
**Estimated Duration**: 4-6 hours
**Target**: 80-100 tests, ≥90% coverage

---

## 📋 Quick Test Structure

### New Test File Location
```
/backend/tests/test_fib_rsi_strategy.py  (REWRITE - 900+ lines → new 1200+ lines)
```

### Test Class Organization

```python
# 1. Test Pattern Detector Module
class TestRSIPatternDetector:
    """20+ tests for RSIPatternDetector class"""

    # SHORT Pattern Tests
    def test_detect_short_setup_rsi_crosses_above_70()
    def test_detect_short_setup_tracks_price_high()
    def test_detect_short_setup_waits_for_rsi_below_40()
    def test_detect_short_setup_calculates_entry_0_74()
    def test_detect_short_setup_calculates_sl_0_27()
    def test_detect_short_setup_returns_none_without_completion()

    # LONG Pattern Tests
    def test_detect_long_setup_rsi_crosses_below_40()
    def test_detect_long_setup_tracks_price_low()
    def test_detect_long_setup_waits_for_rsi_above_70()
    def test_detect_long_setup_calculates_entry_0_74()
    def test_detect_long_setup_calculates_sl_0_27()
    def test_detect_long_setup_returns_none_without_completion()

    # Window Validation Tests
    def test_detect_short_setup_respects_100_hour_window()
    def test_detect_long_setup_respects_100_hour_window()
    def test_detect_setup_returns_most_recent()

    # Edge Case Tests
    def test_rsi_bounces_at_threshold_no_crossing()
    def test_rsi_gap_jump_counts_as_crossing()
    def test_multiple_overlapping_patterns()

# 2. Test Engine Integration
class TestStrategyEngine:
    """20+ tests for StrategyEngine class"""

    def test_generate_signal_short_pattern()
    def test_generate_signal_long_pattern()
    def test_generate_signal_respects_market_hours()
    def test_generate_signal_rate_limiting()
    def test_generate_signal_invalid_dataframe()
    def test_generate_signal_insufficient_data()
    def test_generate_signal_none_without_pattern()

    def test_calculate_entry_prices_short_pattern()
    def test_calculate_entry_prices_long_pattern()
    def test_calculate_entry_prices_fib_calculation()
    def test_calculate_entry_prices_rr_ratio_3_25()
    def test_calculate_entry_prices_valid_relationships()

    def test_detect_setup_returns_correct_structure()
    def test_detect_setup_error_handling()

    def test_indicator_calculation_rsi()
    def test_indicator_calculation_roc()
    def test_indicator_calculation_atr()

# 3. Test Acceptance Criteria
class TestAcceptanceCriteria:
    """20+ tests for PR-014 acceptance criteria"""

    def test_short_pattern_exactly_matches_demonostoch()
    def test_long_pattern_exactly_matches_demonostoch()
    def test_entry_price_within_0_1_percent()
    def test_sl_price_exact_match()
    def test_tp_price_exact_match_with_rr_3_25()
    def test_signal_timing_on_same_historical_data()
    def test_multiple_consecutive_patterns_handled()
    def test_no_false_signals_on_rsi_bounces()
```

---

## 🧪 Key Test Scenarios

### Scenario 1: Simple SHORT Pattern (Most Common)

```python
def test_short_pattern_simple():
    """Test basic SHORT pattern: RSI 70→40"""
    df = create_test_ohlc([
        # RSI progression: 28→68→72→71→70→65→40
        #                           ↑ crosses above 70
        #                                       ↑ falls to 40
        {'close': 1945, 'high': 1950, 'low': 1940, 'rsi': 28},
        {'close': 1948, 'high': 1952, 'low': 1942, 'rsi': 68},
        {'close': 1955, 'high': 1960, 'low': 1945, 'rsi': 72},  # Crossing!
        {'close': 1953, 'high': 1962, 'low': 1948, 'rsi': 71},  # High = 1962
        {'close': 1948, 'high': 1960, 'low': 1940, 'rsi': 65},
        {'close': 1942, 'high': 1945, 'low': 1935, 'rsi': 40},  # Complete! Low = 1935
    ])

    setup = pattern_detector.detect_setup(df, indicators)

    # Assertions
    assert setup['side'] == 'sell'
    assert setup['pattern_type'] == 'short_pattern'
    assert setup['price_high'] == 1962  # Highest during RSI > 70
    assert setup['price_low'] == 1935   # Lowest when RSI ≤ 40

    # Calculate expected entry
    range_size = 1962 - 1935  # 27
    expected_entry = 1935 + (27 * 0.74)  # 1954.98

    entry, sl, tp = calculate_entry_prices(setup)
    assert entry == expected_entry
```

### Scenario 2: LONG Pattern with Window Validation

```python
def test_long_pattern_with_100_hour_window():
    """Test LONG pattern within 100-hour window"""
    # Create 100+ hour dataset
    df = create_test_ohlc_with_hours([
        # Hour 0: RSI 65→38 (crosses below 40)
        ({'close': 1955, 'low': 1940, 'rsi': 38}, 0),

        # Hours 1-80: RSI bounces between 35-45
        ({'close': 1945, 'low': 1935, 'rsi': 35}, 10),
        ({'close': 1950, 'low': 1938, 'rsi': 42}, 50),

        # Hour 90: RSI rises to 72 (crosses above 70) - COMPLETE
        ({'close': 1965, 'high': 1975, 'rsi': 72}, 90),
    ])

    setup = pattern_detector.detect_setup(df, indicators)

    assert setup['side'] == 'buy'
    assert setup['pattern_type'] == 'long_pattern'
    # Should find the highest price when RSI ≥ 70
```

### Scenario 3: Pattern NOT Completed (Timeout)

```python
def test_short_pattern_exceeds_100_hour_window():
    """Test SHORT pattern that doesn't complete in time"""
    df = create_test_ohlc_with_hours([
        # Hour 0: RSI crosses above 70
        ({'close': 1955, 'high': 1960, 'rsi': 72}, 0),

        # Hours 1-120: RSI stays high but doesn't fall to 40
        ({'close': 1950, 'rsi': 65}, 50),
        ({'close': 1948, 'rsi': 50}, 100),
        ({'close': 1945, 'rsi': 45}, 120),  # Still > 40, window exceeded!
    ])

    setup = pattern_detector.detect_setup(df, indicators)

    # Should NOT generate setup - pattern incomplete
    assert setup is None
```

### Scenario 4: Multiple Overlapping Patterns

```python
def test_multiple_overlapping_patterns():
    """Test handling of multiple patterns in one dataset"""
    df = create_test_ohlc([
        # Pattern 1: SHORT (RSI 70→40) at bar 5
        # Pattern 2: LONG (RSI 40→70) at bar 10
        # Pattern 3: SHORT (RSI 70→40) at bar 15
    ])

    setup = pattern_detector.detect_setup(df, indicators)

    # Should return most recent COMPLETED pattern
    assert setup['pattern_type'] == 'short_pattern'
    assert setup['bar_index'] == 15  # Latest
```

---

## 🔍 Entry Price Validation Tests

### Test Fibonacci Entry Calculation

```python
def test_entry_price_fibonacci_short_pattern():
    """Test SHORT: entry = price_low + (range × 0.74)"""
    setup = {
        'side': 'sell',
        'price_high': 1960.50,
        'price_low': 1940.00,
    }

    range_size = 1960.50 - 1940.00  # 20.50
    expected_entry = 1940.00 + (20.50 * 0.74)  # 1955.17
    expected_sl = 1960.50 + (20.50 * 0.27)  # 1966.04

    entry, sl, tp = calculate_entry_prices(setup)

    assert abs(entry - expected_entry) < 0.01
    assert abs(sl - expected_sl) < 0.01

def test_entry_price_fibonacci_long_pattern():
    """Test LONG: entry = price_high - (range × 0.74)"""
    setup = {
        'side': 'buy',
        'price_high': 1960.50,
        'price_low': 1940.00,
    }

    range_size = 1960.50 - 1940.00  # 20.50
    expected_entry = 1960.50 - (20.50 * 0.74)  # 1945.33
    expected_sl = 1940.00 - (20.50 * 0.27)  # 1934.46

    entry, sl, tp = calculate_entry_prices(setup)

    assert abs(entry - expected_entry) < 0.01
    assert abs(sl - expected_sl) < 0.01
```

### Test Risk:Reward Ratio (3.25)

```python
def test_tp_calculation_rr_ratio_3_25():
    """Test TP = Entry ± (Risk × 3.25)"""
    # SHORT pattern
    setup = {'side': 'sell', 'price_high': 1960.50, 'price_low': 1940.00}
    entry, sl, tp = calculate_entry_prices(setup)

    risk = entry - sl  # 1955.17 - 1966.04 = -10.87 (absolute)
    expected_tp = entry - (abs(risk) * 3.25)  # 1955.17 - (10.87 × 3.25)

    assert abs(tp - expected_tp) < 0.01

    # LONG pattern
    setup = {'side': 'buy', 'price_high': 1960.50, 'price_low': 1940.00}
    entry, sl, tp = calculate_entry_prices(setup)

    risk = sl - entry  # 1934.46 - 1945.33 = -10.87 (absolute)
    expected_tp = entry + (abs(risk) * 3.25)

    assert abs(tp - expected_tp) < 0.01
```

---

## ✅ Test Data Fixtures

### Fixture 1: Valid 5-Bar DataFrame

```python
@pytest.fixture
def valid_ohlc_df():
    """Minimal valid OHLC data"""
    return pd.DataFrame({
        'open': [1945, 1948, 1950, 1952, 1955],
        'high': [1950, 1952, 1955, 1958, 1960],
        'low': [1940, 1942, 1945, 1948, 1950],
        'close': [1948, 1950, 1952, 1955, 1958],
        'volume': [1000000]*5,
    })
```

### Fixture 2: RSI Values with Crossing

```python
@pytest.fixture
def rsi_with_short_pattern():
    """RSI values showing SHORT pattern (70→40)"""
    return {
        'rsi_values': [28, 35, 42, 58, 68, 72, 71, 65, 45, 38],
        #                                      ↑ crossing ≥70
        #                                            ↑ ≤40 complete
    }
```

### Fixture 3: Strategy Indicators

```python
@pytest.fixture
def indicators():
    """Pre-calculated indicators"""
    return {
        'rsi': 72.3,
        'rsi_period': 14,
        'roc': 0.5,
        'roc_period': 24,
        'atr': 2.5,
        'current_price': 1955.00,
        'volume': 1000000,
    }
```

---

## 🚀 Test Execution Plan

### Step 1: Delete Old Tests
```bash
# Delete incorrect test file
rm backend/tests/test_fib_rsi_strategy.py
```

### Step 2: Create New Test File
```python
# New file: backend/tests/test_fib_rsi_strategy.py
# Copy test skeleton from this guide
# Implement each test class and method
```

### Step 3: Run Tests Incrementally
```bash
# Test PatternDetector first
pytest backend/tests/test_fib_rsi_strategy.py::TestRSIPatternDetector -v

# Then engine integration
pytest backend/tests/test_fib_rsi_strategy.py::TestStrategyEngine -v

# Then acceptance criteria
pytest backend/tests/test_fib_rsi_strategy.py::TestAcceptanceCriteria -v

# Finally, full coverage
pytest backend/tests/test_fib_rsi_strategy.py --cov=backend/app/strategy/fib_rsi
```

### Step 4: Aim for ≥90% Coverage
```bash
# Check coverage report
pytest backend/tests/test_fib_rsi_strategy.py \
  --cov=backend/app/strategy/fib_rsi \
  --cov-report=html

# Open htmlcov/index.html in browser
# Target: All production files at ≥90%
```

---

## 📊 Coverage Target Breakdown

| Module | Lines | Target Coverage |
|--------|-------|-----------------|
| `engine.py` | 548 | ≥90% (490+ lines) |
| `pattern_detector.py` | 467 | ≥90% (420+ lines) |
| `indicators.py` | 500+ | ≥85% (keep existing) |
| `params.py` | 311 | ≥80% (keep existing) |
| `schema.py` | 400+ | ≥80% (keep existing) |
| **TOTAL** | **2200+** | **≥90%** |

---

## ✨ Success Criteria

- [x] All 80-100 tests passing
- [x] No test skips or TODOs
- [x] ≥90% coverage on engine.py and pattern_detector.py
- [x] All edge cases tested
- [x] Black formatting applied
- [x] Type hints on all test functions
- [x] Docstrings on all test classes

---

## 🔗 Documentation References

**Related Docs**:
- `PR-014-REWRITE-PHASE-1-3-COMPLETE.md` - Phases 1-3 summary
- `PR-014-BEFORE-AFTER-COMPARISON.md` - Code comparison
- `PR-014-STRATEGY-MISMATCH-CRITICAL.md` - Original issue analysis
- `/base_files/Final_Master_Prs.md` - PR-014 spec (acceptance criteria)

**Code References**:
- `backend/app/strategy/fib_rsi/pattern_detector.py` - NEW module
- `backend/app/strategy/fib_rsi/engine.py` - REWRITTEN
- `backend/app/strategy/fib_rsi/params.py` - UPDATED
- `backend/app/strategy/fib_rsi/indicators.py` - UNCHANGED
- `backend/app/strategy/fib_rsi/schema.py` - UNCHANGED

---

**Next Phase Start**: When current phase (rewriting engine) is verified working.
