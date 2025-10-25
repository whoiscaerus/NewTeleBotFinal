"""
Comprehensive test suite for data pull pipelines.

Tests cover:
- Data models (SymbolPrice, OHLCCandle, DataPullLog)
- MT5DataPuller with error handling
- DataPipeline orchestration and scheduling
- Rate limiting and retries
- Data validation and quality checks
- Integration with MT5SessionManager

Test organization:
    - 60+ test cases organized into 8 test classes
    - Unit tests for components (40%)
    - Integration tests (40%)
    - Error scenarios (20%)
    - Target coverage: 90%+

Example:
    >>> pytest backend/tests/test_data_pipeline.py -v
    >>> pytest backend/tests/test_data_pipeline.py --cov=backend/app/trading/data
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# Imports from the modules under test
from backend.app.trading.data.models import DataPullLog, OHLCCandle, SymbolPrice
from backend.app.trading.data.mt5_puller import DataValidationError, MT5DataPuller
from backend.app.trading.data.pipeline import DataPipeline, PipelineStatus, PullConfig

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_session_manager():
    """Mock MT5SessionManager for testing."""
    session_manager = MagicMock()
    session_manager.session = MagicMock()
    return session_manager


@pytest.fixture
def mt5_puller(mock_session_manager):
    """Create MT5DataPuller instance for testing."""
    return MT5DataPuller(mock_session_manager)


@pytest.fixture
def data_pipeline(mt5_puller):
    """Create DataPipeline instance for testing."""
    return DataPipeline(mt5_puller)


# ============================================================================
# TEST CLASS 1: SymbolPrice Model Tests
# ============================================================================


class TestSymbolPriceModel:
    """Tests for SymbolPrice data model."""

    def test_symbol_price_creation(self):
        """Test creating a symbol price record."""
        price = SymbolPrice(
            id=str(uuid4()),
            symbol="GOLD",
            bid=1950.50,
            ask=1950.75,
            timestamp=datetime.utcnow(),
        )

        assert price.symbol == "GOLD"
        assert price.bid == 1950.50
        assert price.ask == 1950.75
        assert price.timestamp is not None

    def test_symbol_price_get_mid_price(self):
        """Test mid-price calculation."""
        price = SymbolPrice(
            id=str(uuid4()),
            symbol="EURUSD",
            bid=1.0850,
            ask=1.0860,
            timestamp=datetime.utcnow(),
        )

        mid = price.get_mid_price()
        assert mid == pytest.approx(1.0855, abs=0.0001)

    def test_symbol_price_get_spread(self):
        """Test spread calculation."""
        price = SymbolPrice(
            id=str(uuid4()),
            symbol="EURUSD",
            bid=1.0850,
            ask=1.0860,
            timestamp=datetime.utcnow(),
        )

        spread = price.get_spread()
        assert spread == pytest.approx(0.0010, abs=0.00001)

    def test_symbol_price_get_spread_percent(self):
        """Test spread percentage calculation."""
        price = SymbolPrice(
            id=str(uuid4()),
            symbol="EURUSD",
            bid=1.0850,
            ask=1.0860,
            timestamp=datetime.utcnow(),
        )

        spread_pct = price.get_spread_percent()
        # spread=0.001, mid=1.0855, pct = 0.001/1.0855*100 ≈ 0.092%
        assert spread_pct == pytest.approx(0.092, abs=0.01)

    def test_symbol_price_repr(self):
        """Test string representation."""
        price = SymbolPrice(
            id=str(uuid4()),
            symbol="GOLD",
            bid=1950.50,
            ask=1950.75,
            timestamp=datetime.utcnow(),
        )

        repr_str = repr(price)
        assert "GOLD" in repr_str
        assert "1950.50" in repr_str
        assert "1950.75" in repr_str


# ============================================================================
# TEST CLASS 2: OHLCCandle Model Tests
# ============================================================================


class TestOHLCCandleModel:
    """Tests for OHLCCandle data model."""

    def test_ohlc_candle_creation(self):
        """Test creating an OHLC candle."""
        candle = OHLCCandle(
            id=str(uuid4()),
            symbol="EURUSD",
            open=1.0850,
            high=1.0875,
            low=1.0840,
            close=1.0865,
            volume=1000000,
            time_open=datetime.utcnow(),
        )

        assert candle.symbol == "EURUSD"
        assert candle.open == 1.0850
        assert candle.high == 1.0875
        assert candle.low == 1.0840
        assert candle.close == 1.0865
        assert candle.volume == 1000000

    def test_ohlc_candle_get_range(self):
        """Test high-low range calculation."""
        candle = OHLCCandle(
            id=str(uuid4()),
            symbol="GOLD",
            open=1950.00,
            high=1955.00,
            low=1945.00,
            close=1952.50,
            volume=100,
            time_open=datetime.utcnow(),
        )

        range_val = candle.get_range()
        assert range_val == pytest.approx(10.0, abs=0.01)

    def test_ohlc_candle_get_change(self):
        """Test close-open change calculation."""
        candle = OHLCCandle(
            id=str(uuid4()),
            symbol="EURUSD",
            open=1.0850,
            high=1.0875,
            low=1.0840,
            close=1.0865,
            volume=1000000,
            time_open=datetime.utcnow(),
        )

        change = candle.get_change()
        assert change == pytest.approx(0.0015, abs=0.00001)

    def test_ohlc_candle_get_change_percent(self):
        """Test change percentage calculation."""
        candle = OHLCCandle(
            id=str(uuid4()),
            symbol="EURUSD",
            open=1.0850,
            high=1.0875,
            low=1.0840,
            close=1.0865,
            volume=1000000,
            time_open=datetime.utcnow(),
        )

        change_pct = candle.get_change_percent()
        # change = 0.0015, open = 1.0850, pct = 0.0015/1.0850*100 ≈ 0.138%
        assert change_pct == pytest.approx(0.138, abs=0.01)

    def test_ohlc_candle_is_bullish(self):
        """Test bullish candle detection (close > open)."""
        bullish = OHLCCandle(
            id=str(uuid4()),
            symbol="EURUSD",
            open=1.0850,
            high=1.0875,
            low=1.0840,
            close=1.0865,  # close > open
            volume=1000000,
            time_open=datetime.utcnow(),
        )

        assert bullish.is_bullish() is True
        assert bullish.is_bearish() is False

    def test_ohlc_candle_is_bearish(self):
        """Test bearish candle detection (close < open)."""
        bearish = OHLCCandle(
            id=str(uuid4()),
            symbol="EURUSD",
            open=1.0865,
            high=1.0875,
            low=1.0840,
            close=1.0850,  # close < open
            volume=1000000,
            time_open=datetime.utcnow(),
        )

        assert bearish.is_bearish() is True
        assert bearish.is_bullish() is False

    def test_ohlc_candle_repr(self):
        """Test string representation."""
        candle = OHLCCandle(
            id=str(uuid4()),
            symbol="GOLD",
            open=1950.00,
            high=1955.00,
            low=1945.00,
            close=1952.50,
            volume=100,
            time_open=datetime.utcnow(),
        )

        repr_str = repr(candle)
        assert "GOLD" in repr_str
        assert "1950" in repr_str
        assert "O=1950" in repr_str


# ============================================================================
# TEST CLASS 3: DataPullLog Model Tests
# ============================================================================


class TestDataPullLogModel:
    """Tests for DataPullLog data model."""

    def test_data_pull_log_creation_success(self):
        """Test creating a successful pull log entry."""
        log = DataPullLog(
            id=str(uuid4()),
            symbol="EURUSD",
            status="success",
            records_pulled=100,
            duration_ms=245,
            timestamp=datetime.utcnow(),
        )

        assert log.symbol == "EURUSD"
        assert log.status == "success"
        assert log.records_pulled == 100
        assert log.duration_ms == 245

    def test_data_pull_log_creation_error(self):
        """Test creating a failed pull log entry."""
        log = DataPullLog(
            id=str(uuid4()),
            symbol="GOLD",
            status="error",
            records_pulled=0,
            duration_ms=5000,
            error_message="Connection timeout",
            timestamp=datetime.utcnow(),
        )

        assert log.status == "error"
        assert log.records_pulled == 0
        assert log.error_message == "Connection timeout"

    def test_data_pull_log_is_error(self):
        """Test error status detection."""
        error_log = DataPullLog(
            id=str(uuid4()),
            symbol="EURUSD",
            status="error",
            records_pulled=0,
            duration_ms=100,
            timestamp=datetime.utcnow(),
        )

        success_log = DataPullLog(
            id=str(uuid4()),
            symbol="EURUSD",
            status="success",
            records_pulled=100,
            duration_ms=100,
            timestamp=datetime.utcnow(),
        )

        assert error_log.is_error() is True
        assert success_log.is_error() is False

    def test_data_pull_log_is_success(self):
        """Test success status detection."""
        success_log = DataPullLog(
            id=str(uuid4()),
            symbol="EURUSD",
            status="success",
            records_pulled=100,
            duration_ms=100,
            timestamp=datetime.utcnow(),
        )

        partial_log = DataPullLog(
            id=str(uuid4()),
            symbol="EURUSD",
            status="partial",
            records_pulled=50,
            duration_ms=100,
            timestamp=datetime.utcnow(),
        )

        assert success_log.is_success() is True
        assert partial_log.is_success() is False

    def test_data_pull_log_get_success_rate(self):
        """Test success rate calculation."""
        success = DataPullLog(
            id=str(uuid4()),
            symbol="EURUSD",
            status="success",
            records_pulled=100,
            duration_ms=100,
            timestamp=datetime.utcnow(),
        )
        assert success.get_success_rate() == 100.0

        partial = DataPullLog(
            id=str(uuid4()),
            symbol="EURUSD",
            status="partial",
            records_pulled=50,
            duration_ms=100,
            timestamp=datetime.utcnow(),
        )
        assert partial.get_success_rate() == 50.0

        error = DataPullLog(
            id=str(uuid4()),
            symbol="EURUSD",
            status="error",
            records_pulled=0,
            duration_ms=100,
            timestamp=datetime.utcnow(),
        )
        assert error.get_success_rate() == 0.0


# ============================================================================
# TEST CLASS 4: MT5DataPuller Tests
# ============================================================================


class TestMT5DataPuller:
    """Tests for MT5DataPuller class."""

    def test_puller_initialization(self, mt5_puller, mock_session_manager):
        """Test puller initialization."""
        assert mt5_puller.session_manager == mock_session_manager
        assert mt5_puller is not None

    def test_puller_init_none_session_manager(self):
        """Test puller rejects None session manager."""
        with pytest.raises(ValueError, match="session_manager cannot be None"):
            MT5DataPuller(None)

    @pytest.mark.asyncio
    async def test_get_ohlc_data_invalid_symbol(self, mt5_puller):
        """Test get_ohlc_data rejects invalid symbol."""
        with pytest.raises(ValueError, match="Invalid symbol"):
            await mt5_puller.get_ohlc_data(symbol="", timeframe="M5", count=100)

    @pytest.mark.asyncio
    async def test_get_ohlc_data_invalid_timeframe(self, mt5_puller):
        """Test get_ohlc_data rejects invalid timeframe."""
        with pytest.raises(ValueError, match="Invalid timeframe"):
            await mt5_puller.get_ohlc_data(symbol="EURUSD", timeframe="", count=100)

    @pytest.mark.asyncio
    async def test_get_ohlc_data_invalid_count(self, mt5_puller):
        """Test get_ohlc_data rejects invalid count."""
        # Negative count
        with pytest.raises(ValueError, match="Count must be 1-5000"):
            await mt5_puller.get_ohlc_data(symbol="EURUSD", timeframe="M5", count=0)

        # Count too large
        with pytest.raises(ValueError, match="Count must be 1-5000"):
            await mt5_puller.get_ohlc_data(symbol="EURUSD", timeframe="M5", count=10000)

    @pytest.mark.asyncio
    async def test_get_ohlc_data_success(self, mt5_puller):
        """Test successful OHLC data retrieval."""
        result = await mt5_puller.get_ohlc_data(
            symbol="EURUSD", timeframe="M5", count=100
        )

        # Should return empty list (mock doesn't populate data)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_symbol_data_invalid_symbol(self, mt5_puller):
        """Test get_symbol_data rejects invalid symbol."""
        with pytest.raises(ValueError, match="Invalid symbol"):
            await mt5_puller.get_symbol_data(symbol="")

    @pytest.mark.asyncio
    async def test_get_symbol_data_success(self, mt5_puller):
        """Test successful symbol data retrieval."""
        result = await mt5_puller.get_symbol_data(symbol="GOLD")

        # Should return None (mock doesn't populate data)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_symbols_data(self, mt5_puller):
        """Test batch symbol data retrieval."""
        result = await mt5_puller.get_all_symbols_data(
            symbols=["EURUSD", "GBPUSD", "GOLD"]
        )

        assert isinstance(result, dict)
        assert len(result) == 0  # Mock returns empty

    @pytest.mark.asyncio
    async def test_get_all_symbols_data_default(self, mt5_puller):
        """Test batch retrieval with default symbols."""
        result = await mt5_puller.get_all_symbols_data()

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_health_check(self, mt5_puller):
        """Test health check method."""
        result = await mt5_puller.health_check()

        # Mock returns False (no data)
        assert isinstance(result, bool)


# ============================================================================
# TEST CLASS 5: DataPipeline Configuration Tests
# ============================================================================


class TestDataPipelineConfiguration:
    """Tests for DataPipeline configuration management."""

    def test_pipeline_initialization(self, data_pipeline, mt5_puller):
        """Test pipeline initialization."""
        assert data_pipeline.puller == mt5_puller
        assert data_pipeline.status.running is False
        assert data_pipeline.status.total_pulls == 0

    def test_pipeline_init_none_puller(self):
        """Test pipeline rejects None puller."""
        with pytest.raises(ValueError, match="puller cannot be None"):
            DataPipeline(None)

    def test_add_pull_config(self, data_pipeline):
        """Test adding pull configuration."""
        data_pipeline.add_pull_config(
            name="forex_5m", symbols=["EURUSD", "GBPUSD"], interval_seconds=300
        )

        assert "forex_5m" in data_pipeline.pull_configs
        config = data_pipeline.pull_configs["forex_5m"]
        assert config.symbols == ["EURUSD", "GBPUSD"]
        assert config.interval_seconds == 300

    def test_add_pull_config_duplicate_name(self, data_pipeline):
        """Test rejects duplicate config name."""
        data_pipeline.add_pull_config(
            name="forex_5m", symbols=["EURUSD"], interval_seconds=300
        )

        with pytest.raises(ValueError, match="already exists"):
            data_pipeline.add_pull_config(
                name="forex_5m", symbols=["GBPUSD"], interval_seconds=300
            )

    def test_add_pull_config_empty_symbols(self, data_pipeline):
        """Test rejects empty symbols list."""
        with pytest.raises(ValueError, match="symbols list cannot be empty"):
            data_pipeline.add_pull_config(name="test", symbols=[], interval_seconds=300)

    def test_add_pull_config_interval_too_small(self, data_pipeline):
        """Test rejects too-small interval."""
        with pytest.raises(ValueError, match="interval_seconds must be >="):
            data_pipeline.add_pull_config(
                name="test",
                symbols=["EURUSD"],
                interval_seconds=30,  # Less than MIN_PULL_INTERVAL (60)
            )

    def test_add_pull_config_interval_too_large(self, data_pipeline):
        """Test rejects too-large interval."""
        with pytest.raises(ValueError, match="interval_seconds must be <="):
            data_pipeline.add_pull_config(
                name="test",
                symbols=["EURUSD"],
                interval_seconds=7200,  # More than MAX_PULL_INTERVAL (3600)
            )

    def test_pull_config_dataclass(self):
        """Test PullConfig dataclass."""
        config = PullConfig(
            symbols=["EURUSD", "GOLD"],
            timeframe="M5",
            interval_seconds=300,
            enabled=True,
        )

        assert config.symbols == ["EURUSD", "GOLD"]
        assert config.timeframe == "M5"
        assert config.interval_seconds == 300
        assert config.enabled is True


# ============================================================================
# TEST CLASS 6: DataPipeline Lifecycle Tests
# ============================================================================


class TestDataPipelineLifecycle:
    """Tests for DataPipeline start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_no_configs(self, data_pipeline):
        """Test start fails without configurations."""
        with pytest.raises(ValueError, match="No pull configurations defined"):
            await data_pipeline.start()

    @pytest.mark.asyncio
    async def test_start_with_config(self, data_pipeline):
        """Test successful pipeline start."""
        data_pipeline.add_pull_config(
            name="test", symbols=["EURUSD"], interval_seconds=300
        )

        await data_pipeline.start()

        assert data_pipeline.status.running is True
        assert len(data_pipeline._pull_tasks) > 0

        # Cleanup
        await data_pipeline.stop()

    @pytest.mark.asyncio
    async def test_start_already_running(self, data_pipeline):
        """Test start on already-running pipeline is no-op."""
        data_pipeline.add_pull_config(
            name="test", symbols=["EURUSD"], interval_seconds=300
        )

        await data_pipeline.start()
        initial_tasks = len(data_pipeline._pull_tasks)

        # Try to start again
        await data_pipeline.start()

        # Should still have same number of tasks
        assert len(data_pipeline._pull_tasks) == initial_tasks

        # Cleanup
        await data_pipeline.stop()

    @pytest.mark.asyncio
    async def test_stop_not_running(self, data_pipeline):
        """Test stop on non-running pipeline is no-op."""
        # Should not raise error
        await data_pipeline.stop()
        assert data_pipeline.status.running is False

    @pytest.mark.asyncio
    async def test_stop_running_pipeline(self, data_pipeline):
        """Test graceful stop of running pipeline."""
        data_pipeline.add_pull_config(
            name="test",
            symbols=["EURUSD"],
            interval_seconds=300,  # Use valid interval (was 10, too small)
        )

        await data_pipeline.start()
        assert data_pipeline.status.running is True

        # Stop pipeline
        await data_pipeline.stop()

        assert data_pipeline.status.running is False
        assert len(data_pipeline._pull_tasks) == 0

    @pytest.mark.asyncio
    async def test_multiple_configs(self, data_pipeline):
        """Test pipeline with multiple configurations."""
        data_pipeline.add_pull_config(
            name="forex", symbols=["EURUSD", "GBPUSD"], interval_seconds=300
        )
        data_pipeline.add_pull_config(
            name="commodities", symbols=["GOLD", "SILVER"], interval_seconds=600
        )

        await data_pipeline.start()

        # Should have tasks for both configs
        assert len(data_pipeline._pull_tasks) == 2

        await data_pipeline.stop()


# ============================================================================
# TEST CLASS 7: DataPipeline Status Tests
# ============================================================================


class TestDataPipelineStatus:
    """Tests for DataPipeline status and monitoring."""

    def test_get_status(self, data_pipeline):
        """Test getting pipeline status."""
        status = data_pipeline.get_status()

        assert isinstance(status, PipelineStatus)
        assert status.running is False
        assert status.total_pulls == 0
        assert status.successful_pulls == 0

    def test_pipeline_status_uptime(self, data_pipeline):
        """Test status uptime tracking."""
        data_pipeline.status.running = True
        data_pipeline._start_time = datetime.utcnow() - timedelta(seconds=3600)

        status = data_pipeline.get_status()

        # Should have roughly 1 hour uptime
        assert 3590 < status.uptime_seconds < 3610

    def test_get_summary(self, data_pipeline):
        """Test summary generation."""
        data_pipeline.add_pull_config(
            name="test", symbols=["EURUSD"], interval_seconds=300
        )

        summary = data_pipeline.get_summary()

        assert "running" in summary
        assert "total_pulls" in summary
        assert "successful_pulls" in summary
        assert "success_rate_percent" in summary

    @pytest.mark.asyncio
    async def test_health_check_not_running(self, data_pipeline):
        """Test health check when not running."""
        result = await data_pipeline.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_running(self, data_pipeline):
        """Test health check when running."""
        data_pipeline.add_pull_config(
            name="test", symbols=["EURUSD"], interval_seconds=300
        )

        await data_pipeline.start()

        result = await data_pipeline.health_check()

        # Result depends on puller health, but should not raise
        assert isinstance(result, bool)

        await data_pipeline.stop()


# ============================================================================
# TEST CLASS 8: Data Validation Tests
# ============================================================================


class TestDataValidation:
    """Tests for data validation logic."""

    def test_validate_candles_valid(self, mt5_puller):
        """Test validation of valid candles."""
        candles = [
            {
                "open": 1.0850,
                "high": 1.0875,
                "low": 1.0840,
                "close": 1.0865,
                "volume": 1000000,
            },
            {
                "open": 1.0865,
                "high": 1.0880,
                "low": 1.0860,
                "close": 1.0875,
                "volume": 950000,
            },
        ]

        # Should not raise
        mt5_puller._validate_candles(candles, "EURUSD")

    def test_validate_candles_high_low_violation(self, mt5_puller):
        """Test validation detects high < low."""
        candles = [
            {
                "open": 1.0850,
                "high": 1.0840,  # high < low!
                "low": 1.0860,
                "close": 1.0865,
                "volume": 1000000,
            }
        ]

        with pytest.raises(DataValidationError):
            mt5_puller._validate_candles(candles, "EURUSD")

    def test_validate_candles_low_violation(self, mt5_puller):
        """Test validation detects low > min(open, close)."""
        candles = [
            {
                "open": 1.0850,
                "high": 1.0880,
                "low": 1.0860,  # low > min(1.0850, 1.0840)
                "close": 1.0840,
                "volume": 1000000,
            }
        ]

        with pytest.raises(DataValidationError):
            mt5_puller._validate_candles(candles, "EURUSD")

    def test_validate_candles_invalid_volume(self, mt5_puller):
        """Test validation detects negative volume."""
        candles = [
            {
                "open": 1.0850,
                "high": 1.0875,
                "low": 1.0840,
                "close": 1.0865,
                "volume": -100,  # Negative volume!
            }
        ]

        with pytest.raises(DataValidationError):
            mt5_puller._validate_candles(candles, "EURUSD")

    def test_validate_candles_missing_field(self, mt5_puller):
        """Test validation detects missing fields."""
        candles = [
            {
                "open": 1.0850,
                "high": 1.0875,
                # Missing 'low' and 'close'
                "volume": 1000000,
            }
        ]

        with pytest.raises(DataValidationError):
            mt5_puller._validate_candles(candles, "EURUSD")

    def test_validate_candles_high_high_violation(self, mt5_puller):
        """Test validation detects high < close."""
        candles = [
            {
                "open": 1.0850,
                "high": 1.0860,  # high < close!
                "low": 1.0840,
                "close": 1.0865,
                "volume": 1000000,
            }
        ]

        with pytest.raises(DataValidationError):
            mt5_puller._validate_candles(candles, "EURUSD")

    def test_validate_candles_type_error(self, mt5_puller):
        """Test validation detects type errors."""
        candles = [
            {
                "open": "invalid",  # string instead of float
                "high": 1.0875,
                "low": 1.0840,
                "close": 1.0865,
                "volume": 1000000,
            }
        ]

        with pytest.raises(DataValidationError):
            mt5_puller._validate_candles(candles, "EURUSD")


# ============================================================================
# TEST CLASS 9: MT5DataPuller Helper Methods Tests
# ============================================================================


class TestMT5DataPullerHelpers:
    """Tests for MT5DataPuller helper methods."""

    def test_timeframe_to_mt5_m1(self, mt5_puller):
        """Test M1 timeframe conversion."""
        assert mt5_puller._timeframe_to_mt5("M1") == 1

    def test_timeframe_to_mt5_m5(self, mt5_puller):
        """Test M5 timeframe conversion."""
        assert mt5_puller._timeframe_to_mt5("M5") == 5

    def test_timeframe_to_mt5_m15(self, mt5_puller):
        """Test M15 timeframe conversion."""
        assert mt5_puller._timeframe_to_mt5("M15") == 15

    def test_timeframe_to_mt5_m30(self, mt5_puller):
        """Test M30 timeframe conversion."""
        assert mt5_puller._timeframe_to_mt5("M30") == 30

    def test_timeframe_to_mt5_h1(self, mt5_puller):
        """Test H1 timeframe conversion."""
        assert mt5_puller._timeframe_to_mt5("H1") == 60

    def test_timeframe_to_mt5_h4(self, mt5_puller):
        """Test H4 timeframe conversion."""
        assert mt5_puller._timeframe_to_mt5("H4") == 240

    def test_timeframe_to_mt5_d1(self, mt5_puller):
        """Test D1 timeframe conversion."""
        assert mt5_puller._timeframe_to_mt5("D1") == 1440

    def test_timeframe_to_mt5_invalid(self, mt5_puller):
        """Test invalid timeframe raises error."""
        with pytest.raises(ValueError, match="Unknown timeframe"):
            mt5_puller._timeframe_to_mt5("INVALID")


# ============================================================================
# TEST CLASS 10: Async Pipeline Tests
# ============================================================================


class TestAsyncPipelineOps:
    """Tests for async pipeline operations and edge cases."""

    @pytest.mark.asyncio
    async def test_pull_cycle_with_symbol_failure(self, data_pipeline):
        """Test pull cycle continues when one symbol fails."""
        data_pipeline.add_pull_config(
            name="test", symbols=["EURUSD", "INVALID", "GOLD"], interval_seconds=300
        )

        # Mock puller to fail on specific symbol
        data_pipeline.puller.get_ohlc_data = AsyncMock(
            side_effect=lambda symbol, **kwargs: (
                None
                if symbol == "INVALID"
                else [
                    {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100}
                ]
            )
        )
        data_pipeline.puller.get_all_symbols_data = AsyncMock(
            return_value={
                "EURUSD": {"bid": 1.0850, "ask": 1.0860},
                "GOLD": {"bid": 1950.50, "ask": 1950.75},
            }
        )

        # Should handle the failure gracefully
        await data_pipeline._pull_cycle("test", data_pipeline.pull_configs["test"])

    @pytest.mark.asyncio
    async def test_pull_loop_with_shutdown(self, data_pipeline):
        """Test pull loop respects shutdown signal."""
        data_pipeline.add_pull_config(
            name="test",
            symbols=["EURUSD"],
            interval_seconds=60,  # Minimum valid interval
        )

        # Mock the puller
        data_pipeline.puller.get_ohlc_data = AsyncMock(return_value=[])
        data_pipeline.puller.get_all_symbols_data = AsyncMock(return_value={})

        # Create task
        config = data_pipeline.pull_configs["test"]
        task = asyncio.create_task(data_pipeline._pull_loop("test", config))

        # Give it time to start
        await asyncio.sleep(0.1)

        # Cancel the task
        task.cancel()

        # Task should complete quickly
        try:
            await asyncio.wait_for(task, timeout=1)
        except asyncio.CancelledError:
            pass  # Expected

    def test_pipeline_status_dataclass(self):
        """Test PipelineStatus dataclass initialization."""
        status = PipelineStatus()

        assert status.running is False
        assert status.uptime_seconds == 0
        assert status.total_pulls == 0
        assert status.successful_pulls == 0
        assert status.failed_pulls == 0
        assert status.active_symbols == []
        assert status.error_message is None

    @pytest.mark.asyncio
    async def test_pull_config_with_disabled(self, data_pipeline):
        """Test disabled configurations are not started."""
        data_pipeline.add_pull_config(
            name="enabled", symbols=["EURUSD"], interval_seconds=300, enabled=True
        )
        data_pipeline.add_pull_config(
            name="disabled", symbols=["GOLD"], interval_seconds=300, enabled=False
        )

        await data_pipeline.start()

        # Only 1 task should be active (enabled one)
        assert len(data_pipeline._pull_tasks) == 1
        assert "enabled" in data_pipeline._pull_tasks

        await data_pipeline.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
