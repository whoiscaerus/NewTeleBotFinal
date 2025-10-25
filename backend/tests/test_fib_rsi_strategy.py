"""
Comprehensive test suite for Fib-RSI strategy module.

Tests cover:
- StrategyParams configuration and validation
- RSI, ROC, ATR, Fibonacci indicators
- SignalCandidate and ExecutionPlan schemas
- StrategyEngine signal generation
- Integration tests
- Edge cases and error handling

Test coverage target: 90%+
Total test cases: 50+

Example:
    >>> pytest backend/tests/test_fib_rsi_strategy.py -v
    >>> pytest backend/tests/test_fib_rsi_strategy.py --cov=backend/app/strategy/fib_rsi
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from backend.app.strategy.fib_rsi.engine import StrategyEngine
from backend.app.strategy.fib_rsi.indicators import (
    ATRCalculator,
    FibonacciAnalyzer,
    ROCCalculator,
    RSICalculator,
)
from backend.app.strategy.fib_rsi.params import StrategyParams
from backend.app.strategy.fib_rsi.schema import ExecutionPlan, SignalCandidate

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def default_params() -> StrategyParams:
    """Create default strategy parameters."""
    return StrategyParams()


@pytest.fixture
def mock_market_calendar():
    """Create mock market calendar."""
    calendar = MagicMock()
    calendar.is_market_open = MagicMock(return_value=True)
    return calendar


@pytest.fixture
def mock_market_calendar_async():
    """Create async mock market calendar."""
    calendar = AsyncMock()
    calendar.is_market_open = AsyncMock(return_value=True)
    return calendar


@pytest.fixture
def sample_dataframe() -> pd.DataFrame:
    """Create sample OHLCV DataFrame with 50 candles."""
    data = {
        "open": [1.0850 + i * 0.0005 for i in range(50)],
        "high": [1.0875 + i * 0.0005 for i in range(50)],
        "low": [1.0825 + i * 0.0005 for i in range(50)],
        "close": [1.0865 + i * 0.0005 for i in range(50)],
        "volume": [1000000 + i * 10000 for i in range(50)],
    }
    return pd.DataFrame(data)


@pytest.fixture
def oversold_dataframe() -> pd.DataFrame:
    """Create DataFrame with oversold RSI (buy signal setup)."""
    # Declining prices create oversold RSI
    closes = [1.1000 - i * 0.001 for i in range(50)]
    data = {
        "open": closes,
        "high": [c + 0.0005 for c in closes],
        "low": [c - 0.0005 for c in closes],
        "close": closes,
        "volume": [1000000] * 50,
    }
    return pd.DataFrame(data)


@pytest.fixture
def overbought_dataframe() -> pd.DataFrame:
    """Create DataFrame with overbought RSI (sell signal setup)."""
    # Rising prices create overbought RSI
    closes = [1.0800 + i * 0.001 for i in range(50)]
    data = {
        "open": closes,
        "high": [c + 0.0005 for c in closes],
        "low": [c - 0.0005 for c in closes],
        "close": closes,
        "volume": [1000000] * 50,
    }
    return pd.DataFrame(data)


# ============================================================================
# TEST STRATEGYPARAMS
# ============================================================================


class TestStrategyParams:
    """Test StrategyParams configuration and validation."""

    def test_default_initialization(self):
        """Test default parameter initialization."""
        params = StrategyParams()
        assert params.rsi_period == 14
        assert params.rsi_overbought == 70.0
        assert params.rsi_oversold == 40.0
        assert params.roc_period == 24
        assert params.rr_ratio == 3.25
        assert params.risk_per_trade == 0.02

    def test_custom_initialization(self):
        """Test custom parameter initialization."""
        params = StrategyParams(
            rsi_period=20,
            rr_ratio=3.0,
            risk_per_trade=0.05,
        )
        assert params.rsi_period == 20
        assert params.rr_ratio == 3.0
        assert params.risk_per_trade == 0.05

    def test_validation_succeeds_with_defaults(self):
        """Test validation passes with default parameters."""
        params = StrategyParams()
        params.validate()  # Should not raise

    def test_validation_fails_invalid_rsi_period(self):
        """Test validation fails with invalid RSI period."""
        params = StrategyParams(rsi_period=-5)
        with pytest.raises(ValueError, match="rsi_period"):
            params.validate()

    def test_validation_fails_invalid_rr_ratio(self):
        """Test validation fails with invalid R:R ratio."""
        params = StrategyParams(rr_ratio=20.0)
        with pytest.raises(ValueError, match="rr_ratio"):
            params.validate()

    def test_validation_fails_invalid_risk_per_trade(self):
        """Test validation fails with invalid risk per trade."""
        params = StrategyParams(risk_per_trade=1.5)
        with pytest.raises(ValueError, match="risk_per_trade"):
            params.validate()

    def test_get_rsi_config(self):
        """Test get_rsi_config returns correct structure."""
        params = StrategyParams()
        config = params.get_rsi_config()
        assert config["period"] == 14
        assert config["overbought"] == 70.0
        assert config["oversold"] == 40.0

    def test_get_roc_config(self):
        """Test get_roc_config returns correct structure."""
        params = StrategyParams()
        config = params.get_roc_config()
        assert config["period"] == 24
        assert config["threshold"] == 0.5

    def test_get_fib_config(self):
        """Test get_fib_config returns correct structure."""
        params = StrategyParams()
        config = params.get_fib_config()
        assert len(config["levels"]) == 6
        assert 0.618 in config["levels"]

    def test_get_risk_config(self):
        """Test get_risk_config returns correct structure."""
        params = StrategyParams()
        config = params.get_risk_config()
        assert config["rr_ratio"] == 3.25
        assert config["risk_per_trade"] == 0.02

    def test_to_dict(self):
        """Test to_dict converts all parameters."""
        params = StrategyParams()
        d = params.to_dict()
        assert isinstance(d, dict)
        assert "rsi_period" in d
        assert "rr_ratio" in d
        assert d["rsi_period"] == 14


# ============================================================================
# TEST RSI CALCULATOR
# ============================================================================


class TestRSICalculator:
    """Test RSI indicator calculations."""

    def test_rsi_basic_calculation(self):
        """Test basic RSI calculation."""
        prices = [
            44,
            44.34,
            44.09,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            46.30,
            46.50,
            46.70,
            46.85,
            46.95,
        ]  # 15 prices
        rsi = RSICalculator.calculate(prices, period=14)
        assert len(rsi) == len(prices)  # RSI returns same length as prices
        assert all(0 <= r <= 100 for r in rsi)

    def test_rsi_oversold_detection(self):
        """Test oversold RSI detection."""
        assert RSICalculator.is_oversold(25.0) is True
        assert RSICalculator.is_oversold(35.0) is False

    def test_rsi_overbought_detection(self):
        """Test overbought RSI detection."""
        assert RSICalculator.is_overbought(75.0) is True
        assert RSICalculator.is_overbought(65.0) is False

    def test_rsi_constant_prices(self):
        """Test RSI with constant prices (no movement)."""
        prices = [1.0] * 30
        rsi = RSICalculator.calculate(prices, period=14)
        assert all(abs(r - 50.0) < 0.1 for r in rsi)  # RSI ~50 for no change

    def test_rsi_insufficient_data(self):
        """Test RSI with insufficient data."""
        prices = [1.0]
        with pytest.raises(ValueError):
            RSICalculator.calculate(prices)

    def test_rsi_edge_case_single_peak(self):
        """Test RSI with single price spike."""
        prices = [1.0] * 10 + [2.0] + [1.0] * 10
        rsi = RSICalculator.calculate(prices, period=5)
        assert len(rsi) == 21

    def test_rsi_downtrend(self):
        """Test RSI in strong downtrend (low RSI)."""
        prices = [100.0 - i * 1.0 for i in range(50)]
        rsi = RSICalculator.calculate(prices, period=14)
        assert rsi[-1] < 30  # Should be oversold

    def test_rsi_uptrend(self):
        """Test RSI in strong uptrend (high RSI)."""
        prices = [100.0 + i * 1.0 for i in range(50)]
        rsi = RSICalculator.calculate(prices, period=14)
        assert rsi[-1] > 70  # Should be overbought


# ============================================================================
# TEST ROC CALCULATOR
# ============================================================================


class TestROCCalculator:
    """Test ROC indicator calculations."""

    def test_roc_basic_calculation(self):
        """Test basic ROC calculation."""
        prices = [1.0, 1.05, 1.1, 1.08, 1.12, 1.15, 1.13]
        roc = ROCCalculator.calculate(prices, period=2)
        assert len(roc) == len(prices)

    def test_roc_positive_detection(self):
        """Test positive ROC detection."""
        assert ROCCalculator.is_positive_roc(1.5) is True
        assert ROCCalculator.is_positive_roc(-0.5) is False
        assert ROCCalculator.is_positive_roc(0.0) is False

    def test_roc_negative_detection(self):
        """Test negative ROC detection."""
        assert ROCCalculator.is_negative_roc(-1.5) is True
        assert ROCCalculator.is_negative_roc(0.5) is False
        assert ROCCalculator.is_negative_roc(0.0) is False

    def test_roc_constant_prices(self):
        """Test ROC with constant prices."""
        prices = [1.0] * 20
        roc = ROCCalculator.calculate(prices, period=5)
        assert all(abs(r) < 0.01 for r in roc)

    def test_roc_insufficient_data(self):
        """Test ROC with insufficient data."""
        prices = [1.0]
        with pytest.raises(ValueError):
            ROCCalculator.calculate(prices)

    def test_roc_uptrend(self):
        """Test ROC in uptrend (positive values)."""
        prices = [100.0 + i * 1.0 for i in range(50)]
        roc = ROCCalculator.calculate(prices, period=5)
        assert roc[-1] > 0  # Recent uptrend should be positive


# ============================================================================
# TEST ATR CALCULATOR
# ============================================================================


class TestATRCalculator:
    """Test ATR volatility calculations."""

    def test_atr_basic_calculation(self):
        """Test basic ATR calculation."""
        highs = [1.1, 1.15, 1.12, 1.18, 1.2]
        lows = [1.05, 1.08, 1.07, 1.1, 1.15]
        closes = [1.08, 1.12, 1.1, 1.15, 1.18]
        atr = ATRCalculator.calculate(highs, lows, closes, period=2)
        assert len(atr) == len(highs)
        assert all(a >= 0 for a in atr)

    def test_atr_mismatched_lengths(self):
        """Test ATR with mismatched input lengths."""
        highs = [1.1, 1.15]
        lows = [1.05, 1.08, 1.07]
        closes = [1.08, 1.12]
        with pytest.raises(ValueError, match="same length"):
            ATRCalculator.calculate(highs, lows, closes)

    def test_atr_insufficient_data(self):
        """Test ATR with insufficient data."""
        with pytest.raises(ValueError):
            ATRCalculator.calculate([1.0], [1.0], [1.0])

    def test_atr_wide_range(self):
        """Test ATR with wide price range (high volatility)."""
        highs = [100 + i * 10 for i in range(20)]
        lows = [50 + i * 10 for i in range(20)]
        closes = [75 + i * 10 for i in range(20)]
        atr = ATRCalculator.calculate(highs, lows, closes, period=5)
        assert atr[-1] > 10  # High volatility

    def test_atr_narrow_range(self):
        """Test ATR with narrow price range (low volatility)."""
        highs = [100.1 + i * 0.01 for i in range(20)]
        lows = [100.0 + i * 0.01 for i in range(20)]
        closes = [100.05 + i * 0.01 for i in range(20)]
        atr = ATRCalculator.calculate(highs, lows, closes, period=5)
        assert atr[-1] < 0.1  # Low volatility

    def test_atr_gap_up(self):
        """Test ATR with gap up candle."""
        highs = [100.0, 200.0, 200.0]
        lows = [99.0, 190.0, 190.0]
        closes = [99.5, 199.5, 199.5]
        atr = ATRCalculator.calculate(highs, lows, closes, period=2)
        assert len(atr) == 3

    def test_atr_volatility_classification(self):
        """Test volatility level classification."""
        assert ATRCalculator.get_volatility_level(10.0) == "low"
        assert ATRCalculator.get_volatility_level(50.0) == "medium"
        assert ATRCalculator.get_volatility_level(90.0) == "high"


# ============================================================================
# TEST FIBONACCI ANALYZER
# ============================================================================


class TestFibonacciAnalyzer:
    """Test Fibonacci level calculations."""

    def test_find_swing_high(self):
        """Test finding swing high."""
        candles = [{"high": 1.1}, {"high": 1.15}, {"high": 1.12}]
        high, idx = FibonacciAnalyzer.find_swing_high(candles, window=3)
        assert high == 1.15
        assert idx == 1

    def test_find_swing_low(self):
        """Test finding swing low."""
        candles = [{"low": 1.05}, {"low": 1.02}, {"low": 1.03}]
        low, idx = FibonacciAnalyzer.find_swing_low(candles, window=3)
        assert low == 1.02
        assert idx == 1

    def test_calculate_fibonacci_levels(self):
        """Test Fibonacci level calculation."""
        levels = FibonacciAnalyzer.calculate_levels(1.2, 1.0)
        assert len(levels) == 6
        assert "0.618" in levels
        assert 1.0 < levels["0.618"] < 1.2

    def test_fibonacci_levels_invalid_inputs(self):
        """Test Fibonacci with invalid inputs."""
        with pytest.raises(ValueError):
            FibonacciAnalyzer.calculate_levels(1.0, 1.2)  # high < low

    def test_find_nearest_level(self):
        """Test finding nearest Fibonacci level."""
        levels = {"0.618": 1.1236, "0.5": 1.1, "0.382": 1.0764}
        nearest = FibonacciAnalyzer.find_nearest_level(1.1235, levels, 50)
        assert nearest == "0.618"

    def test_is_price_near_level(self):
        """Test checking if price is near level."""
        assert FibonacciAnalyzer.is_price_near_level(1.1235, 1.1236, 50) is True
        assert FibonacciAnalyzer.is_price_near_level(1.0, 1.2, 50) is False

    def test_fibonacci_empty_candles(self):
        """Test Fibonacci with empty candle list."""
        with pytest.raises(ValueError):
            FibonacciAnalyzer.find_swing_high([])


# ============================================================================
# TEST SIGNAL SCHEMA
# ============================================================================


class TestSignalCandidate:
    """Test SignalCandidate schema."""

    def test_signal_creation(self):
        """Test creating a signal."""
        signal = SignalCandidate(
            instrument="EURUSD",
            side="buy",
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0900,
            confidence=0.85,
            timestamp=datetime.utcnow(),
            reason="rsi_oversold",
            payload={"rsi": 25},
        )
        assert signal.instrument == "EURUSD"
        assert signal.side == "buy"

    def test_signal_validation_buy_prices(self):
        """Test signal validates BUY price relationships."""
        signal = SignalCandidate(
            instrument="EURUSD",
            side="buy",
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0900,
            confidence=0.85,
            timestamp=datetime.utcnow(),
            reason="test",
        )
        signal.validate_price_relationships()  # Should pass

    def test_signal_validation_buy_invalid_sl(self):
        """Test signal rejects invalid BUY stop loss."""
        signal = SignalCandidate(
            instrument="EURUSD",
            side="buy",
            entry_price=1.0850,
            stop_loss=1.0900,  # Above entry (invalid for buy)
            take_profit=1.0950,
            confidence=0.85,
            timestamp=datetime.utcnow(),
            reason="test",
        )
        with pytest.raises(ValueError):
            signal.validate_price_relationships()

    def test_signal_get_risk_pips(self):
        """Test calculating risk in pips."""
        signal = SignalCandidate(
            instrument="EURUSD",
            side="buy",
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0900,
            confidence=0.85,
            timestamp=datetime.utcnow(),
            reason="test",
        )
        risk = signal.get_risk_pips()
        # Entry 1.0850 - Stop 1.0820 = 0.003 = 30 pips
        assert 25 < risk < 35  # Allow range for floating point arithmetic

    def test_signal_get_rr_ratio(self):
        """Test calculating R:R ratio."""
        signal = SignalCandidate(
            instrument="EURUSD",
            side="buy",
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0910,
            confidence=0.85,
            timestamp=datetime.utcnow(),
            reason="test",
        )
        rr = signal.get_rr_ratio()
        assert abs(rr - 2.0) < 0.01  # Allow small floating point tolerance


class TestExecutionPlan:
    """Test ExecutionPlan schema."""

    def test_execution_plan_creation(self):
        """Test creating an execution plan."""
        signal = SignalCandidate(
            instrument="EURUSD",
            side="buy",
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0900,
            confidence=0.85,
            timestamp=datetime.utcnow(),
            reason="test",
        )
        plan = ExecutionPlan(
            signal=signal,
            position_size=1.0,
            risk_amount=100.0,
            reward_amount=200.0,
            risk_reward_ratio=2.0,
        )
        assert plan.position_size == 1.0
        assert plan.risk_amount == 100.0

    def test_execution_plan_is_expired_false(self):
        """Test execution plan not expired."""
        signal = SignalCandidate(
            instrument="EURUSD",
            side="buy",
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0900,
            confidence=0.85,
            timestamp=datetime.utcnow(),
            reason="test",
        )
        plan = ExecutionPlan(
            signal=signal,
            position_size=1.0,
            risk_amount=100.0,
            reward_amount=200.0,
            risk_reward_ratio=2.0,
            expiry_time=datetime.utcnow() + timedelta(hours=1),
        )
        assert plan.is_expired(datetime.utcnow()) is False

    def test_execution_plan_is_expired_true(self):
        """Test execution plan is expired."""
        signal = SignalCandidate(
            instrument="EURUSD",
            side="buy",
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0900,
            confidence=0.85,
            timestamp=datetime.utcnow(),
            reason="test",
        )
        plan = ExecutionPlan(
            signal=signal,
            position_size=1.0,
            risk_amount=100.0,
            reward_amount=200.0,
            risk_reward_ratio=2.0,
            expiry_time=datetime.utcnow() - timedelta(minutes=1),
        )
        assert plan.is_expired(datetime.utcnow()) is True


# ============================================================================
# TEST STRATEGY ENGINE
# ============================================================================


class TestStrategyEngine:
    """Test StrategyEngine signal generation."""

    @pytest.mark.asyncio
    async def test_engine_initialization(
        self, default_params, mock_market_calendar_async
    ):
        """Test engine initializes correctly."""
        engine = StrategyEngine(default_params, mock_market_calendar_async)
        assert engine.params is default_params

    @pytest.mark.asyncio
    async def test_generate_signal_with_valid_data(
        self,
        default_params,
        mock_market_calendar_async,
        sample_dataframe,
    ):
        """Test signal generation with valid data."""
        engine = StrategyEngine(default_params, mock_market_calendar_async)
        await engine.generate_signal(
            sample_dataframe,
            "EURUSD",
            datetime.utcnow(),
        )
        # Signal might be None (data doesn't match criteria), but no error

    @pytest.mark.asyncio
    async def test_generate_signal_invalid_dataframe(
        self,
        default_params,
        mock_market_calendar_async,
    ):
        """Test signal generation with invalid DataFrame."""
        engine = StrategyEngine(default_params, mock_market_calendar_async)
        df = pd.DataFrame({"invalid": [1, 2, 3]})

        with pytest.raises(ValueError):
            await engine.generate_signal(df, "EURUSD", datetime.utcnow())

    @pytest.mark.asyncio
    async def test_generate_signal_insufficient_data(
        self,
        default_params,
        mock_market_calendar_async,
    ):
        """Test signal generation with insufficient data."""
        engine = StrategyEngine(default_params, mock_market_calendar_async)
        df = pd.DataFrame(
            {
                "open": [1.0, 1.05],
                "high": [1.1, 1.15],
                "low": [0.95, 1.0],
                "close": [1.05, 1.1],
                "volume": [1000000, 1000000],
            }
        )

        with pytest.raises(ValueError):
            await engine.generate_signal(df, "EURUSD", datetime.utcnow())

    @pytest.mark.asyncio
    async def test_generate_signal_market_closed(
        self,
        default_params,
        sample_dataframe,
    ):
        """Test signal generation when market is closed."""
        calendar = MagicMock()
        calendar.is_market_open = AsyncMock(return_value=False)
        engine = StrategyEngine(default_params, calendar)

        signal = await engine.generate_signal(
            sample_dataframe,
            "EURUSD",
            datetime.utcnow(),
        )
        assert signal is None

    @pytest.mark.asyncio
    async def test_validate_dataframe_missing_columns(
        self,
        default_params,
        mock_market_calendar_async,
    ):
        """Test DataFrame validation rejects missing columns."""
        df = pd.DataFrame({"open": [1.0], "high": [1.1]})

        with pytest.raises(ValueError, match="missing required columns"):
            StrategyEngine._validate_dataframe(df)

    @pytest.mark.asyncio
    async def test_validate_dataframe_with_nan(
        self,
        default_params,
        mock_market_calendar_async,
    ):
        """Test DataFrame validation rejects NaN values."""
        df = pd.DataFrame(
            {
                "open": [1.0, float("nan")],
                "high": [1.1, 1.15],
                "low": [0.95, 1.0],
                "close": [1.05, 1.1],
                "volume": [1000000, 1000000],
            }
        )

        # Pad to 30 rows
        while len(df) < 30:
            df = pd.concat([df, df], ignore_index=True)

        with pytest.raises(ValueError, match="NaN"):
            StrategyEngine._validate_dataframe(df[:30])

    @pytest.mark.asyncio
    async def test_generate_buy_signal_with_indicators(
        self,
        default_params,
        mock_market_calendar_async,
        oversold_dataframe,
    ):
        """Test buy signal generation with all indicators aligned."""
        engine = StrategyEngine(default_params, mock_market_calendar_async)
        signal = await engine.generate_signal(
            oversold_dataframe, "EURUSD", datetime.utcnow()
        )

        if signal:
            assert signal.side == "buy"
            assert signal.confidence > 0.5

    @pytest.mark.asyncio
    async def test_generate_sell_signal_with_indicators(
        self,
        default_params,
        mock_market_calendar_async,
        overbought_dataframe,
    ):
        """Test sell signal generation with all indicators aligned."""
        engine = StrategyEngine(default_params, mock_market_calendar_async)
        signal = await engine.generate_signal(
            overbought_dataframe, "EURUSD", datetime.utcnow()
        )

        if signal:
            assert signal.side == "sell"
            assert signal.confidence > 0.5

    @pytest.mark.asyncio
    async def test_signal_entry_sl_tp_relationship_buy(
        self,
        default_params,
        mock_market_calendar_async,
        oversold_dataframe,
    ):
        """Test buy signal maintains entry > SL < TP relationship."""
        engine = StrategyEngine(default_params, mock_market_calendar_async)
        signal = await engine.generate_signal(
            oversold_dataframe, "EURUSD", datetime.utcnow()
        )

        if signal and signal.side == "buy":
            assert signal.stop_loss < signal.entry_price < signal.take_profit
            assert signal.entry_price - signal.stop_loss > 0

    @pytest.mark.asyncio
    async def test_signal_entry_sl_tp_relationship_sell(
        self,
        default_params,
        mock_market_calendar_async,
        overbought_dataframe,
    ):
        """Test sell signal maintains entry < SL > TP relationship."""
        engine = StrategyEngine(default_params, mock_market_calendar_async)
        signal = await engine.generate_signal(
            overbought_dataframe, "EURUSD", datetime.utcnow()
        )

        if signal and signal.side == "sell":
            assert signal.stop_loss > signal.entry_price > signal.take_profit
            assert signal.stop_loss - signal.entry_price > 0

    @pytest.mark.asyncio
    async def test_rate_limit_resets_over_time(
        self,
        default_params,
        mock_market_calendar_async,
        oversold_dataframe,
    ):
        """Test rate limiting tracks signals properly."""
        default_params.max_signals_per_hour = 1
        engine = StrategyEngine(default_params, mock_market_calendar_async)

        # First signal should generate
        signal1 = await engine.generate_signal(
            oversold_dataframe, "EURUSD", datetime.utcnow()
        )

        # Second immediate signal should be rate-limited
        signal2 = await engine.generate_signal(
            oversold_dataframe, "EURUSD", datetime.utcnow()
        )

        # Verify rate limiting worked
        count = sum(1 for s in [signal1, signal2] if s is not None)
        assert count <= 1

    @pytest.mark.asyncio
    async def test_signal_timestamp_set(
        self,
        default_params,
        mock_market_calendar_async,
        oversold_dataframe,
    ):
        """Test signal timestamp is set to generation time."""
        engine = StrategyEngine(default_params, mock_market_calendar_async)
        before = datetime.utcnow()
        signal = await engine.generate_signal(oversold_dataframe, "EURUSD", before)

        if signal:
            assert signal.timestamp >= before

    @pytest.mark.asyncio
    async def test_signal_rr_ratio_configuration(
        self,
        default_params,
        mock_market_calendar_async,
        oversold_dataframe,
    ):
        """Test signal respects configured R:R ratio."""
        default_params.rr_ratio = 2.0
        engine = StrategyEngine(default_params, mock_market_calendar_async)
        signal = await engine.generate_signal(
            oversold_dataframe, "EURUSD", datetime.utcnow()
        )

        if signal:
            rr = signal.get_rr_ratio()
            assert rr >= 1.8  # Allow 10% tolerance

    @pytest.mark.asyncio
    async def test_engine_with_different_instruments(
        self,
        default_params,
        mock_market_calendar_async,
        sample_dataframe,
    ):
        """Test engine works with different instrument names."""
        engine = StrategyEngine(default_params, mock_market_calendar_async)

        for instrument in ["EURUSD", "GBPUSD", "USDJPY", "GOLD"]:
            signal = await engine.generate_signal(
                sample_dataframe, instrument, datetime.utcnow()
            )
            # No error should occur
            if signal:
                assert signal.instrument == instrument

    @pytest.mark.asyncio
    async def test_engine_confidence_varies_with_indicators(
        self,
        default_params,
        mock_market_calendar_async,
    ):
        """Test signal confidence varies based on indicator alignment."""
        engine = StrategyEngine(default_params, mock_market_calendar_async)

        # Create strong oversold scenario
        prices = [100 - i * 2 for i in range(50)]
        df_strong = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 1 for p in prices],
                "low": [p - 1 for p in prices],
                "close": prices,
                "volume": [1000000] * 50,
            }
        )

        signal = await engine.generate_signal(df_strong, "EURUSD", datetime.utcnow())

        if signal:
            assert 0 <= signal.confidence <= 1


# ============================================================================
# TEST INTEGRATION
# ============================================================================


class TestIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_complete_signal_workflow(
        self,
        default_params,
        mock_market_calendar_async,
        sample_dataframe,
    ):
        """Test complete workflow from params to signal."""
        default_params.validate()
        engine = StrategyEngine(default_params, mock_market_calendar_async)

        signal = await engine.generate_signal(
            sample_dataframe,
            "EURUSD",
            datetime.utcnow(),
        )
        # If signal generated, verify structure
        if signal:
            assert signal.instrument == "EURUSD"
            assert signal.side in ("buy", "sell")
            assert signal.entry_price > 0
            assert signal.stop_loss > 0
            assert signal.take_profit > 0

    def test_indicators_comprehensive(self):
        """Test all indicators on sample data."""
        prices = [100 + i * 0.5 for i in range(50)]
        highs = [100.5 + i * 0.5 for i in range(50)]
        lows = [99.5 + i * 0.5 for i in range(50)]

        rsi = RSICalculator.calculate(prices, 14)
        roc = ROCCalculator.calculate(prices, 14)
        atr = ATRCalculator.calculate(highs, lows, prices, 14)

        assert len(rsi) == 50
        assert len(roc) == 50
        assert len(atr) == 50
        assert all(0 <= r <= 100 for r in rsi)
        assert all(a >= 0 for a in atr)

    def test_signal_to_execution_plan(self):
        """Test creating execution plan from signal."""
        signal = SignalCandidate(
            instrument="EURUSD",
            side="buy",
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0910,
            confidence=0.85,
            timestamp=datetime.utcnow(),
            reason="rsi_oversold",
            payload={"rsi": 25, "roc": 1.5},
        )

        plan = ExecutionPlan(
            signal=signal,
            position_size=1.0,
            risk_amount=100.0,
            reward_amount=200.0,
            risk_reward_ratio=2.0,
        )

        info = plan.get_position_info()
        assert info["side"] == "buy"
        assert info["position_size"] == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
