# PR-014 Implementation Plan: Fib-RSI Strategy Module

**Status**: Planning Phase
**Date**: 2025-10-24
**Depends On**: PR-011 ✅, PR-012 ✅, PR-013 ✅

---

## 1. Overview

Implement a production-grade Fib-RSI trading strategy module that converts your existing trading bot logic into a deterministic service with:
- RSI and ROC indicator calculations
- Fibonacci support/resistance level detection
- Signal generation with entry/SL/TP computation
- Market hours validation (integrates PR-012)
- Comprehensive testing and telemetry

**Target Quality**:
- ✅ 90%+ test coverage
- ✅ 100% type hints and docstrings
- ✅ Zero TODOs/FIXMEs
- ✅ Black formatted code
- ✅ 50+ test cases across all components

---

## 2. File Structure

```
backend/app/strategy/
  __init__.py                          # Public API exports
  fib_rsi/
    __init__.py                        # Module exports
    params.py                          # Configuration and constants
    indicators.py                      # RSI, ROC, ATR calculations
    engine.py                          # Main signal generation engine
    schema.py                          # Pydantic models (SignalCandidate, ExecutionPlan)

backend/tests/
  test_fib_rsi_strategy.py            # 50+ comprehensive tests
```

---

## 3. Detailed Component Specifications

### 3.1 params.py (Configuration)

**Purpose**: Centralize all strategy parameters and validation

**Classes/Functions**:

```python
class StrategyParams:
    """Fib-RSI strategy parameters."""

    # RSI parameters
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0

    # ROC parameters
    roc_period: int = 14
    roc_threshold: float = 0.5

    # Fibonacci parameters
    fib_levels: list[float] = [0.236, 0.382, 0.5, 0.618, 0.786, 1.0]

    # Risk management
    risk_per_trade: float = 0.02  # 2% of account
    rr_ratio: float = 2.0  # Reward:Risk ratio
    min_stop_distance_points: int = 10  # Minimum SL distance

    # Market hours validation
    check_market_hours: bool = True

    # Attributes to validate on init
    def validate(self) -> None:
        """Validate all parameters are within acceptable ranges."""
```

**Methods**:
- `validate()` - Ensure all parameters are valid
- `get_rsi_config()` - Return RSI-specific params
- `get_fib_config()` - Return Fibonacci-specific params
- `get_risk_config()` - Return risk management params

---

### 3.2 indicators.py (Technical Analysis)

**Purpose**: Implement core technical indicators

**Classes**:

```python
class RSICalculator:
    """Relative Strength Index calculator."""

    @staticmethod
    def calculate(prices: list[float], period: int = 14) -> list[float]:
        """Calculate RSI values."""

    @staticmethod
    def is_oversold(rsi: float, threshold: float = 30.0) -> bool:
        """Check if RSI indicates oversold."""

    @staticmethod
    def is_overbought(rsi: float, threshold: float = 70.0) -> bool:
        """Check if RSI indicates overbought."""


class ROCCalculator:
    """Rate of Change indicator calculator."""

    @staticmethod
    def calculate(prices: list[float], period: int = 14) -> list[float]:
        """Calculate ROC values."""

    @staticmethod
    def is_positive_roc(roc: float, threshold: float = 0.0) -> bool:
        """Check if ROC is positive/bullish."""

    @staticmethod
    def is_negative_roc(roc: float, threshold: float = 0.0) -> bool:
        """Check if ROC is negative/bearish."""


class ATRCalculator:
    """Average True Range calculator for volatility."""

    @staticmethod
    def calculate(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 14
    ) -> list[float]:
        """Calculate ATR values."""


class FibonacciAnalyzer:
    """Fibonacci support/resistance level analyzer."""

    @staticmethod
    def find_swing_high(candles: list[dict], window: int = 20) -> float:
        """Find recent swing high."""

    @staticmethod
    def find_swing_low(candles: list[dict], window: int = 20) -> float:
        """Find recent swing low."""

    @staticmethod
    def calculate_levels(
        swing_high: float,
        swing_low: float,
        fib_ratios: list[float] = [0.236, 0.382, 0.618, 0.786]
    ) -> dict[str, float]:
        """Calculate Fibonacci levels between swing high/low."""
```

---

### 3.3 schema.py (Pydantic Models)

**Purpose**: Define data structures with validation

**Models**:

```python
class SignalCandidate(BaseModel):
    """Generated trading signal from strategy."""

    instrument: str
    side: str  # "buy" or "sell"
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    reason: str  # "rsi_oversold_fib_support" etc.
    payload: dict  # RSI, ROC, Fib levels, etc.
    version: str = "1.0"

    class Config:
        validate_assignment = True


class ExecutionPlan(BaseModel):
    """Complete execution plan for a signal."""

    signal: SignalCandidate
    position_size: float
    risk_amount: float
    reward_amount: float
    risk_reward_ratio: float
    expiry_time: Optional[datetime] = None

    class Config:
        validate_assignment = True
```

---

### 3.4 engine.py (Main Strategy Logic)

**Purpose**: Orchestrate signal generation

**Class: StrategyEngine**

```python
class StrategyEngine:
    """Fib-RSI trading strategy engine."""

    def __init__(
        self,
        params: StrategyParams,
        market_calendar: MarketCalendar,  # From PR-012
        logger: Logger = None
    ):
        """Initialize strategy engine."""
        self.params = params
        self.market_calendar = market_calendar
        self.logger = logger

    async def generate_signal(
        self,
        df: pd.DataFrame,
        instrument: str,
        current_time: datetime
    ) -> Optional[SignalCandidate]:
        """
        Generate trading signal from OHLC data.

        Args:
            df: DataFrame with columns [open, high, low, close, volume]
            instrument: Trading symbol
            current_time: Current time for market hours check

        Returns:
            SignalCandidate if signal generated, None otherwise

        Raises:
            ValueError: If data is invalid

        Example:
            >>> df = pd.DataFrame({
            ...     'open': [1.0850, 1.0855],
            ...     'high': [1.0875, 1.0880],
            ...     'low': [1.0840, 1.0845],
            ...     'close': [1.0865, 1.0870],
            ...     'volume': [1000000, 1100000]
            ... })
            >>> signal = await engine.generate_signal(df, "EURUSD", now)
        """

    async def _check_market_hours(
        self,
        instrument: str,
        timestamp: datetime
    ) -> bool:
        """Check if market is open for instrument."""

    async def _calculate_indicators(
        self,
        df: pd.DataFrame
    ) -> dict[str, Any]:
        """Calculate all technical indicators."""

    async def _detect_buy_signal(
        self,
        indicators: dict[str, Any],
        df: pd.DataFrame
    ) -> Optional[dict]:
        """Detect buy signal setup."""

    async def _detect_sell_signal(
        self,
        indicators: dict[str, Any],
        df: pd.DataFrame
    ) -> Optional[dict]:
        """Detect sell signal setup."""

    async def _calculate_entry_prices(
        self,
        df: pd.DataFrame,
        side: str,
        indicators: dict
    ) -> tuple[float, float, float]:
        """Calculate entry, SL, TP prices."""
```

---

## 4. Signal Detection Logic

### Buy Signal Criteria

A BUY signal is generated when:
1. ✅ Market is open for the instrument (PR-012 check)
2. ✅ RSI < 30 (oversold) OR recent oversold bounce
3. ✅ ROC positive (price momentum positive)
4. ✅ Price is near Fibonacci support level (within 50 pips)
5. ✅ Volume confirms the move
6. ✅ ATR sufficient for SL placement (> min_stop_distance_points)

### Sell Signal Criteria

A SELL signal is generated when:
1. ✅ Market is open for the instrument (PR-012 check)
2. ✅ RSI > 70 (overbought) OR recent overbought bounce
3. ✅ ROC negative (price momentum negative)
4. ✅ Price is near Fibonacci resistance level (within 50 pips)
5. ✅ Volume confirms the move
6. ✅ ATR sufficient for SL placement (> min_stop_distance_points)

---

## 5. Entry/SL/TP Calculation

### For BUY Signals

```
Entry Price = Current Close
Stop Loss = Entry - (ATR * 1.5) → Rounded to min_stop_distance
Take Profit = Entry + (ATR * RR Ratio)
Risk Amount = (Entry - Stop) * Position Size
Reward Amount = (Take Profit - Entry) * Position Size
```

### For SELL Signals

```
Entry Price = Current Close
Stop Loss = Entry + (ATR * 1.5) → Rounded to min_stop_distance
Take Profit = Entry - (ATR * RR Ratio)
Risk Amount = (Stop - Entry) * Position Size
Reward Amount = (Entry - Take Profit) * Position Size
```

---

## 6. Test Strategy (50+ test cases)

### Test Classes

**TestRSICalculator** (8 tests)
- ✅ Basic RSI calculation with known values
- ✅ Oversold detection (RSI < 30)
- ✅ Overbought detection (RSI > 70)
- ✅ Edge case: Constant prices (RSI = 50)
- ✅ Edge case: Small dataset (< period)
- ✅ Single peak/trough
- ✅ Multiple peaks
- ✅ Extreme values (100, 0)

**TestROCCalculator** (6 tests)
- ✅ Basic ROC calculation
- ✅ Positive ROC detection
- ✅ Negative ROC detection
- ✅ ROC at threshold
- ✅ Zero ROC (constant prices)
- ✅ Edge case: Small dataset

**TestATRCalculator** (5 tests)
- ✅ Basic ATR calculation
- ✅ Wide range (high ATR)
- ✅ Narrow range (low ATR)
- ✅ Gap up/down
- ✅ True range edge cases

**TestFibonacciAnalyzer** (8 tests)
- ✅ Swing high detection
- ✅ Swing low detection
- ✅ Fib level calculation
- ✅ All standard levels (0.236, 0.382, 0.618, 0.786)
- ✅ Custom levels
- ✅ High near swing high
- ✅ Low near swing low
- ✅ Multiple swings

**TestStrategyParams** (4 tests)
- ✅ Valid parameters initialization
- ✅ Parameter validation (ranges)
- ✅ Invalid parameters raise ValueError
- ✅ Config accessors

**TestSignalSchema** (4 tests)
- ✅ SignalCandidate creation
- ✅ SignalCandidate validation
- ✅ ExecutionPlan creation
- ✅ Invalid data raises ValidationError

**TestStrategyEngine** (15 tests)
- ✅ Market hours check (market open)
- ✅ Market hours check (market closed)
- ✅ Buy signal generation (oversold + support)
- ✅ Sell signal generation (overbought + resistance)
- ✅ No signal when market closed
- ✅ No signal when RSI neutral
- ✅ No signal when volume low
- ✅ No signal when ATR too small
- ✅ Entry/SL/TP calculation (buy)
- ✅ Entry/SL/TP calculation (sell)
- ✅ Min stop distance enforcement
- ✅ R:R ratio enforcement
- ✅ Multiple signals in sequence
- ✅ Error handling: invalid DataFrame
- ✅ Error handling: insufficient data

**TestIntegration** (4 tests)
- ✅ Full workflow: init → generate_signal → validate output
- ✅ Signal confidence calculation
- ✅ Payload contains all required fields
- ✅ Golden input/output snapshot test

---

## 7. Telemetry Metrics

**Prometheus Metrics**:

```python
# Counter: Signals generated by type
strategy_signals_total = Counter(
    "strategy_signals_total",
    "Total signals generated",
    ["instrument", "side", "reason"]
)

# Histogram: Signal evaluation time
strategy_eval_seconds = Histogram(
    "strategy_eval_seconds",
    "Time to evaluate and generate signal",
    ["instrument"]
)

# Gauge: Last signal confidence
strategy_signal_confidence = Gauge(
    "strategy_signal_confidence",
    "Confidence of last generated signal",
    ["instrument", "side"]
)

# Counter: Signal rejections
strategy_signals_rejected = Counter(
    "strategy_signals_rejected",
    "Signals rejected",
    ["instrument", "reason"]
)
```

---

## 8. Integration Points

**Depends On**:
- ✅ **PR-011**: MT5SessionManager - Not directly, but data comes from MT5
- ✅ **PR-012**: MarketCalendar - For market hours checking
- ✅ **PR-013**: DataPipeline - Consumes OHLC data

**Integrates With**:
- PR-015: Order Construction - Signals feed into order builder
- PR-016: Trade Store - Generated signals logged

---

## 9. Acceptance Criteria

1. ✅ All 4 modules created with 100% type hints and docstrings
2. ✅ RSI calculation matches TA library output
3. ✅ ROC calculation accurate with known test data
4. ✅ ATR calculation correct for volatility
5. ✅ Fibonacci levels correctly calculated
6. ✅ Buy signals generated when criteria met
7. ✅ Sell signals generated when criteria met
8. ✅ Market hours properly validated (closes market off-hours)
9. ✅ Entry/SL/TP calculations match spec
10. ✅ Min stop distance enforced
11. ✅ R:R ratio validated
12. ✅ 50+ test cases, all passing
13. ✅ 90%+ code coverage
14. ✅ Zero TODOs/FIXMEs
15. ✅ Black formatted
16. ✅ All metrics/telemetry working
17. ✅ Integration with PR-012 (market calendar) verified
18. ✅ Golden input/output snapshot tests passing
19. ✅ Edge cases tested (low volume, tiny ATR, etc.)
20. ✅ Error handling comprehensive

---

## 10. Implementation Order

**Phase 1: Setup & Configuration** (15 min)
- [ ] Create directory structure
- [ ] Create params.py with StrategyParams class
- [ ] Create schema.py with Pydantic models

**Phase 2: Indicators** (30 min)
- [ ] Create indicators.py
- [ ] Implement RSICalculator
- [ ] Implement ROCCalculator
- [ ] Implement ATRCalculator
- [ ] Implement FibonacciAnalyzer

**Phase 3: Engine** (45 min)
- [ ] Create engine.py
- [ ] Implement StrategyEngine class
- [ ] Implement signal generation logic
- [ ] Implement entry/SL/TP calculations

**Phase 4: Tests** (60 min)
- [ ] Create test_fib_rsi_strategy.py
- [ ] Write all 50+ test cases
- [ ] Achieve 90%+ coverage

**Phase 5: Polish** (30 min)
- [ ] Black formatting
- [ ] Documentation review
- [ ] Final verification

**Total Estimated Time**: 2.5-3 hours

---

## 11. Success Criteria

Project is COMPLETE when:

✅ All 4 files created in exact paths
✅ 50+ tests passing (100%)
✅ 90%+ code coverage achieved
✅ 100% type hints on all functions
✅ 100% docstrings on all classes/functions
✅ Zero TODOs or FIXMEs
✅ Black formatting applied
✅ All acceptance criteria verified
✅ Integration with PR-012 tested
✅ Telemetry metrics working
✅ No merge conflicts
✅ Comprehensive documentation created

---

**Next Steps**: Proceed to Phase 1 implementation
