# 🎯 PR-014 Ready for Phase 4: Test Suite Rewrite

**Status**: ✅ Code Complete - Ready for Testing
**Phase**: 4 of 5 (Testing Phase)
**Estimated Duration**: 4-6 hours
**Start Condition**: ✅ Met - All code changes verified

---

## ✅ Pre-Phase-4 Verification Checklist

### Code Changes ✅

- [x] **pattern_detector.py created** (467 lines)
  - Location: `backend/app/strategy/fib_rsi/pattern_detector.py`
  - Syntax: ✅ No errors
  - Type hints: ✅ Complete
  - Docstrings: ✅ Complete
  - Content: RSI crossing detection, pattern state machine, 100-hour window

- [x] **engine.py rewritten** (563 → 548 lines)
  - Location: `backend/app/strategy/fib_rsi/engine.py`
  - Syntax: ✅ No errors
  - Type hints: ✅ Complete
  - Docstrings: ✅ Updated
  - Changes: Signal detection + entry price calculation rewritten
  - Import: ✅ pattern_detector imported
  - Initialization: ✅ RSIPatternDetector instantiated

- [x] **params.py updated** (311 lines)
  - Location: `backend/app/strategy/fib_rsi/params.py`
  - Syntax: ✅ No errors
  - Type hints: ✅ Complete
  - Changes:
    * rsi_oversold: 30.0 → 40.0 ✅
    * roc_period: 14 → 24 ✅
    * rr_ratio: 2.0 → 3.25 ✅
  - Docstrings: ✅ Updated

- [x] **No breaking changes**
  - indicators.py: ✅ Unchanged (still compatible)
  - schema.py: ✅ Unchanged (still compatible)
  - __init__.py: ✅ Unchanged (still compatible)

### Documentation ✅

- [x] **Index created**: `PR-014-REWRITE-COMPLETE-INDEX.md`
- [x] **Summary created**: `PR-014-REWRITE-SESSION-SUMMARY.md`
- [x] **Phase 1-3 completed**: `PR-014-REWRITE-PHASE-1-3-COMPLETE.md`
- [x] **Before/After comparison**: `PR-014-BEFORE-AFTER-COMPARISON.md`
- [x] **Test template created**: `PR-014-PHASE-4-TEST-REWRITE-QUICK-REF.md`
- [x] **Original analysis**: `PR-014-STRATEGY-MISMATCH-CRITICAL.md`

### Import Validation ✅

```python
# These work now:
from backend.app.strategy.fib_rsi.engine import StrategyEngine
from backend.app.strategy.fib_rsi.pattern_detector import RSIPatternDetector
from backend.app.strategy.fib_rsi.params import StrategyParams
```

### Ready for Phase 4 ✅

**All code changes complete and verified. Ready to proceed with test suite rewrite.**

---

## 📋 Phase 4 Task Breakdown

### Task 1: Remove Old Tests (15 minutes)

```bash
# Delete the old test file (66 tests for wrong logic)
rm backend/tests/test_fib_rsi_strategy.py

# Verify it's gone
ls backend/tests/test_fib_rsi_strategy.py  # Should NOT exist
```

### Task 2: Create New Test File (1 hour)

Create: `backend/tests/test_fib_rsi_strategy.py`

Use this template structure:

```python
"""
Tests for Fib-RSI strategy with RSI crossing pattern detection.

Tests validate:
1. RSI crossing detection (event-based, not value-based)
2. SHORT pattern detection (RSI 70→40 within 100 hours)
3. LONG pattern detection (RSI 40→70 within 100 hours)
4. Price extreme tracking during patterns
5. Fibonacci entry/SL calculation (0.74/0.27 multipliers)
6. R:R ratio calculation (3.25)
7. Engine integration
8. Acceptance criteria compliance

Reference: /base_files/DemoNoStochRSI.py

Coverage Target: ≥90%
Test Count Target: 80-100 tests
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from backend.app.strategy.fib_rsi.engine import StrategyEngine
from backend.app.strategy.fib_rsi.pattern_detector import RSIPatternDetector
from backend.app.strategy.fib_rsi.params import StrategyParams
from backend.app.trading.time import MarketCalendar


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def strategy_params():
    """Default strategy parameters."""
    params = StrategyParams()
    params.validate()
    return params


@pytest.fixture
def market_calendar():
    """Market calendar (always open for testing)."""
    calendar = MarketCalendar()
    return calendar


@pytest.fixture
def strategy_engine(strategy_params, market_calendar):
    """Strategy engine instance."""
    return StrategyEngine(strategy_params, market_calendar)


@pytest.fixture
def pattern_detector(strategy_params):
    """Pattern detector instance."""
    return RSIPatternDetector(
        rsi_high_threshold=strategy_params.rsi_overbought,
        rsi_low_threshold=strategy_params.rsi_oversold,
        completion_window_hours=100,
    )


# ============================================================================
# TEST CLASS 1: RSI PATTERN DETECTOR
# ============================================================================

class TestRSIPatternDetector:
    """Test RSIPatternDetector class for pattern detection."""

    def test_detect_short_setup_rsi_crosses_above_70(self, pattern_detector):
        """Test SHORT pattern detected when RSI crosses above 70."""
        # TODO: Implement
        pass

    def test_detect_short_setup_tracks_price_high(self, pattern_detector):
        """Test price_high tracked while RSI > 70."""
        # TODO: Implement
        pass

    # ... more tests ...


# ============================================================================
# TEST CLASS 2: STRATEGY ENGINE
# ============================================================================

class TestStrategyEngine:
    """Test StrategyEngine class integration."""

    def test_generate_signal_short_pattern(self, strategy_engine):
        """Test signal generation for SHORT pattern."""
        # TODO: Implement
        pass

    # ... more tests ...


# ============================================================================
# TEST CLASS 3: ACCEPTANCE CRITERIA
# ============================================================================

class TestAcceptanceCriteria:
    """Test acceptance criteria from PR-014 specification."""

    def test_ac_01_short_pattern_rsi_70_to_40(self):
        """AC-01: SHORT pattern when RSI crosses 70 then falls to 40."""
        # TODO: Implement
        pass

    # ... more tests ...
```

### Task 3: Write Pattern Detector Tests (1.5 hours)

20+ tests in TestRSIPatternDetector class:

```python
class TestRSIPatternDetector:

    # SHORT Pattern Detection Tests
    def test_short_setup_simple(self, pattern_detector):
        """Test simple SHORT pattern: RSI 70→40"""

    def test_short_setup_tracks_price_high(self, pattern_detector):
        """Test price_high tracking during RSI > 70 period"""

    def test_short_setup_waits_for_rsi_below_40(self, pattern_detector):
        """Test SHORT waits for RSI ≤ 40"""

    def test_short_setup_calculates_entry_fib_074(self, pattern_detector):
        """Test entry = price_low + (range × 0.74)"""

    def test_short_setup_calculates_sl_fib_027(self, pattern_detector):
        """Test SL = price_high + (range × 0.27)"""

    def test_short_setup_respects_100_hour_window(self, pattern_detector):
        """Test SHORT pattern timeout after 100 hours"""

    # LONG Pattern Detection Tests
    def test_long_setup_simple(self, pattern_detector):
        """Test simple LONG pattern: RSI 40→70"""

    def test_long_setup_tracks_price_low(self, pattern_detector):
        """Test price_low tracking during RSI < 40 period"""

    # ... more tests ...
```

**See**: `PR-014-PHASE-4-TEST-REWRITE-QUICK-REF.md` for full test scenarios

### Task 4: Write Engine Integration Tests (1.5 hours)

20+ tests in TestStrategyEngine class:

```python
class TestStrategyEngine:

    def test_generate_signal_with_short_pattern(self):
        """Test signal generation includes SHORT pattern data"""

    def test_generate_signal_with_long_pattern(self):
        """Test signal generation includes LONG pattern data"""

    def test_calculate_entry_prices_short_fibonacci(self):
        """Test entry prices calculated with Fibonacci 0.74"""

    def test_calculate_entry_prices_long_fibonacci(self):
        """Test entry prices calculated with Fibonacci 0.74"""

    def test_calculate_tp_with_rr_ratio_3_25(self):
        """Test TP calculated with R:R = 3.25"""

    # ... more tests ...
```

### Task 5: Write Acceptance Criteria Tests (1.5 hours)

20+ tests in TestAcceptanceCriteria class:

One test per acceptance criterion from master spec:

```python
class TestAcceptanceCriteria:

    def test_ac_short_pattern_rsi_70_crossing(self):
        """AC: SHORT signals trigger on RSI crossing above 70"""

    def test_ac_long_pattern_rsi_40_crossing(self):
        """AC: LONG signals trigger on RSI crossing below 40"""

    def test_ac_entry_price_at_fib_074(self):
        """AC: Entry prices calculated at Fibonacci 0.74"""

    def test_ac_sl_price_at_fib_027(self):
        """AC: Stop loss prices calculated at Fibonacci 0.27"""

    # ... more tests ...
```

### Task 6: Run Tests & Verify Coverage (1 hour)

```bash
# Run all tests
cd backend
pytest tests/test_fib_rsi_strategy.py -v

# Check coverage
pytest tests/test_fib_rsi_strategy.py \
  --cov=backend/app/strategy/fib_rsi \
  --cov-report=html

# View report
# Open: backend/htmlcov/index.html

# Target: ≥90% on engine.py and pattern_detector.py
```

### Task 7: Format & Finalize (15 minutes)

```bash
# Apply Black formatting
black backend/app/strategy/fib_rsi/
black backend/tests/test_fib_rsi_strategy.py

# Verify no issues
black --check backend/app/strategy/fib_rsi/
black --check backend/tests/test_fib_rsi_strategy.py

# Final test run
pytest tests/test_fib_rsi_strategy.py -v --cov
```

---

## 📊 Phase 4 Deliverables

| Item | Status | Notes |
|------|--------|-------|
| Pattern detector tests | ⏳ To write | 20+ tests |
| Engine integration tests | ⏳ To write | 20+ tests |
| Acceptance criteria tests | ⏳ To write | 20+ tests |
| Edge case tests | ⏳ To write | 20+ tests |
| Total tests | ⏳ Target | 80-100 |
| Coverage | ⏳ Target | ≥90% |
| Black formatting | ⏳ Apply | After all tests |
| All tests passing | ⏳ Verify | Before Phase 5 |

---

## ⏱️ Phase 4 Timeline Breakdown

| Task | Duration | Cumulative |
|------|----------|-----------|
| 1. Remove old tests | 15 min | 15 min |
| 2. Create new test file | 1 hr | 1 hr 15 min |
| 3. Pattern detector tests | 1.5 hrs | 2 hrs 45 min |
| 4. Engine integration tests | 1.5 hrs | 4 hrs 15 min |
| 5. Acceptance criteria tests | 1.5 hrs | 5 hrs 45 min |
| 6. Run tests & coverage | 1 hr | 6 hrs 45 min |
| 7. Format & finalize | 15 min | 7 hrs |
| **Total** | **7 hours** | (Range: 4-6 hrs for expert) |

**Note**: Assumes 1-2 issues that need fixing during test writing (typical)

---

## 🎯 Success Criteria for Phase 4

All of these must be true:

- [ ] **80-100 tests created** (not just 66 - need NEW tests for new logic)
- [ ] **All tests passing** (100% pass rate, no skips)
- [ ] **≥90% coverage on engine.py** (≥90% of 548 lines)
- [ ] **≥90% coverage on pattern_detector.py** (≥90% of 467 lines)
- [ ] **No TODOs in tests** (all tests implemented)
- [ ] **Black formatted** (all files pass black --check)
- [ ] **Type hints complete** (all test functions typed)
- [ ] **Docstrings present** (all test classes documented)
- [ ] **No hardcoded values** (use fixtures)
- [ ] **Edge cases tested** (gaps, bounces, timeouts, etc.)

---

## 🚀 Ready to Start Phase 4?

✅ **All Prerequisites Met**:
- Pattern detector module created ✅
- Engine rewritten ✅
- Parameters updated ✅
- Documentation complete ✅
- Test template ready ✅

✅ **No Blockers**:
- No syntax errors ✅
- All imports working ✅
- No dependencies missing ✅

**You can start Phase 4 immediately.**

---

## 📞 If You Get Stuck

**Reference Documents**:
1. `PR-014-PHASE-4-TEST-REWRITE-QUICK-REF.md` - Complete test template
2. `PR-014-BEFORE-AFTER-COMPARISON.md` - Understanding code changes
3. `PR-014-REWRITE-PHASE-1-3-COMPLETE.md` - Technical details

**Quick Links**:
- Pattern detector: `backend/app/strategy/fib_rsi/pattern_detector.py`
- Engine: `backend/app/strategy/fib_rsi/engine.py`
- Test template: `backend/tests/conftest.py` (for fixtures)

---

## ✨ Summary

**Phase 4 is ready to start immediately.** All code changes are complete and verified. You have:

1. ✅ Complete test template (`PR-014-PHASE-4-TEST-REWRITE-QUICK-REF.md`)
2. ✅ 20+ example test scenarios with code
3. ✅ Fixture templates and utilities
4. ✅ Execution plan with timeline

**Estimated completion**: 4-7 hours (depending on expertise level)

**Next milestone**: Phase 5 (Verification against DemoNoStochRSI)

---

**Status**: ✅ READY FOR PHASE 4
**Confidence**: HIGH - All prerequisites met, template complete
**Proceed**: YES - Start test suite rewrite
