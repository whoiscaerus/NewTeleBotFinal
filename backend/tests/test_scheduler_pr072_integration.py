"""Integration tests for StrategyScheduler with PR-072 components.

Tests that StrategyScheduler correctly integrates with:
- CandleDetector for boundary detection and duplicate prevention
- SignalPublisher for API + Telegram routing

These tests validate the complete flow from candle detection → strategy execution
→ signal publishing.
"""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, Mock, patch

import pandas as pd
import pytest

from backend.app.strategy.candles import CandleDetector
from backend.app.strategy.fib_rsi.schema import SignalCandidate
from backend.app.strategy.publisher import SignalPublisher
from backend.app.strategy.registry import StrategyRegistry
from backend.app.strategy.scheduler import StrategyScheduler


@pytest.fixture
def mock_registry():
    """Create mock strategy registry."""
    registry = Mock(spec=StrategyRegistry)
    registry.get_enabled_strategies.return_value = ["test_strategy"]

    # Mock strategy that returns a signal
    mock_strategy = Mock()
    mock_strategy.generate_signal = AsyncMock(
        return_value=SignalCandidate(
            instrument="GOLD",
            side="buy",
            entry_price=1950.0,
            stop_loss=1945.0,
            take_profit=1960.0,
            confidence=0.85,
            timestamp=datetime(2025, 1, 1, 10, 15, 0, tzinfo=UTC),
            reason="test_signal",
            payload={"test": "data"},
        )
    )
    registry.get_strategy.return_value = mock_strategy

    return registry


@pytest.fixture
def sample_dataframe():
    """Create sample OHLC dataframe."""
    return pd.DataFrame(
        {
            "open": [1950.0],
            "high": [1955.0],
            "low": [1945.0],
            "close": [1952.0],
            "volume": [1000],
        }
    )


class TestSchedulerPR072Integration:
    """Test StrategyScheduler integration with PR-072 components."""

    @pytest.mark.asyncio
    async def test_scheduler_uses_candle_detector(
        self, mock_registry, sample_dataframe
    ):
        """Test scheduler uses CandleDetector for boundary detection."""
        # Create scheduler with custom CandleDetector
        candle_detector = CandleDetector(window_seconds=60)
        scheduler = StrategyScheduler(
            registry=mock_registry,
            candle_detector=candle_detector,
        )

        # Timestamp at 15-min boundary
        timestamp = datetime(2025, 1, 1, 10, 15, 5, tzinfo=UTC)

        # Mock signal publisher to avoid actual HTTP calls
        with patch.object(
            scheduler.signal_publisher, "publish", new_callable=AsyncMock
        ) as mock_publish:
            mock_publish.return_value = {"api_success": True, "signal_id": "123"}

            # Should detect new candle and run strategies
            result = await scheduler.run_on_new_candle(
                sample_dataframe, "GOLD", timestamp, "15m"
            )

            # Verify strategies ran
            assert result is not None
            assert "test_strategy" in result
            assert len(result["test_strategy"]) == 1

            # Verify signal was published
            assert mock_publish.called

    @pytest.mark.asyncio
    async def test_scheduler_prevents_duplicates(self, mock_registry, sample_dataframe):
        """Test scheduler prevents duplicate signal processing within same candle."""
        scheduler = StrategyScheduler(registry=mock_registry)

        # Timestamp at 15-min boundary
        timestamp = datetime(2025, 1, 1, 10, 15, 5, tzinfo=UTC)

        # Mock signal publisher
        with patch.object(
            scheduler.signal_publisher, "publish", new_callable=AsyncMock
        ) as mock_publish:
            mock_publish.return_value = {"api_success": True, "signal_id": "123"}

            # First call: should process
            result1 = await scheduler.run_on_new_candle(
                sample_dataframe, "GOLD", timestamp, "15m"
            )
            assert result1 is not None

            # Second call with same candle: should be skipped (duplicate prevention)
            result2 = await scheduler.run_on_new_candle(
                sample_dataframe, "GOLD", timestamp, "15m"
            )
            assert result2 is None  # Duplicate prevented

    @pytest.mark.asyncio
    async def test_scheduler_uses_signal_publisher(
        self, mock_registry, sample_dataframe
    ):
        """Test scheduler uses SignalPublisher for routing."""
        # Mock SignalPublisher
        mock_publisher = Mock(spec=SignalPublisher)
        mock_publisher.publish = AsyncMock(
            return_value={
                "api_success": True,
                "signal_id": "test-signal-123",
                "telegram_success": False,
            }
        )

        scheduler = StrategyScheduler(
            registry=mock_registry,
            signal_publisher=mock_publisher,
        )

        timestamp = datetime(2025, 1, 1, 10, 15, 0, tzinfo=timezone.utc)

        # Run strategies
        await scheduler.run_strategies(
            sample_dataframe, "GOLD", timestamp, post_to_api=True
        )

        # Verify signal was published via SignalPublisher
        assert mock_publisher.publish.called
        call_args = mock_publisher.publish.call_args

        # Verify signal_data format
        signal_data = call_args.kwargs["signal_data"]
        assert signal_data["instrument"] == "GOLD"
        assert signal_data["side"] == "buy"
        assert signal_data["entry_price"] == 1950.0
        assert signal_data["strategy"] == "test_strategy"

        # Verify candle_start for duplicate prevention
        assert "candle_start" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_scheduler_skips_mid_candle_timestamps(
        self, mock_registry, sample_dataframe
    ):
        """Test scheduler skips strategy execution for mid-candle timestamps."""
        scheduler = StrategyScheduler(registry=mock_registry)

        # Timestamp in middle of candle (not at boundary)
        timestamp = datetime(2025, 1, 1, 10, 17, 30, tzinfo=UTC)

        # Mock signal publisher
        with patch.object(
            scheduler.signal_publisher, "publish", new_callable=AsyncMock
        ):
            # Should skip (not a new candle)
            result = await scheduler.run_on_new_candle(
                sample_dataframe, "GOLD", timestamp, "15m"
            )

            assert result is None  # Skipped

    @pytest.mark.asyncio
    async def test_scheduler_handles_multiple_timeframes(
        self, mock_registry, sample_dataframe
    ):
        """Test scheduler handles different timeframes (15m, 1h, 4h)."""
        scheduler = StrategyScheduler(registry=mock_registry)

        # Mock signal publisher
        with patch.object(
            scheduler.signal_publisher, "publish", new_callable=AsyncMock
        ) as mock_publish:
            mock_publish.return_value = {"api_success": True, "signal_id": "123"}

            # Test 1h candle boundary
            timestamp_1h = datetime(2025, 1, 1, 10, 0, 5, tzinfo=UTC)
            result = await scheduler.run_on_new_candle(
                sample_dataframe, "GOLD", timestamp_1h, "1h"
            )
            assert result is not None  # 1h boundary detected

            # Reset for next test
            scheduler.candle_detector.clear_cache()

            # Test 4h candle boundary
            timestamp_4h = datetime(2025, 1, 1, 12, 0, 10, tzinfo=UTC)
            result = await scheduler.run_on_new_candle(
                sample_dataframe, "GOLD", timestamp_4h, "4h"
            )
            assert result is not None  # 4h boundary detected

    @pytest.mark.asyncio
    async def test_scheduler_handles_signal_publish_failure(
        self, mock_registry, sample_dataframe
    ):
        """Test scheduler continues despite signal publish failures."""
        # Mock publisher that fails
        mock_publisher = Mock(spec=SignalPublisher)
        mock_publisher.publish = AsyncMock(
            return_value={
                "api_success": False,
                "error": "API connection failed",
            }
        )

        scheduler = StrategyScheduler(
            registry=mock_registry,
            signal_publisher=mock_publisher,
        )

        timestamp = datetime(2025, 1, 1, 10, 15, 0, tzinfo=UTC)

        # Should not raise exception despite publish failure
        result = await scheduler.run_strategies(
            sample_dataframe, "GOLD", timestamp, post_to_api=True
        )

        # Strategies still executed
        assert result is not None
        assert "test_strategy" in result

    @pytest.mark.asyncio
    async def test_scheduler_backward_compatibility(
        self, mock_registry, sample_dataframe
    ):
        """Test scheduler maintains backward compatibility with _is_new_candle."""
        scheduler = StrategyScheduler(registry=mock_registry)

        # Old _is_new_candle method should still work (delegates to CandleDetector)
        timestamp_boundary = datetime(2025, 1, 1, 10, 15, 5, tzinfo=UTC)
        assert scheduler._is_new_candle(timestamp_boundary, "15m", 60) is True

        timestamp_mid = datetime(2025, 1, 1, 10, 17, 30, tzinfo=UTC)
        assert scheduler._is_new_candle(timestamp_mid, "15m", 60) is False


class TestSchedulerMetricsIntegration:
    """Test scheduler metrics integration with PR-060."""

    @pytest.mark.asyncio
    async def test_scheduler_records_metrics(self, mock_registry, sample_dataframe):
        """Test scheduler records telemetry metrics."""
        scheduler = StrategyScheduler(registry=mock_registry)

        # Mock signal publisher
        with patch.object(
            scheduler.signal_publisher, "publish", new_callable=AsyncMock
        ) as mock_publish:
            mock_publish.return_value = {"api_success": True, "signal_id": "123"}

            timestamp = datetime(2025, 1, 1, 10, 15, 0, tzinfo=UTC)

            # Get initial metrics count
            initial_runs = scheduler.metrics.strategy_runs_total.labels(
                name="test_strategy"
            )._value._value

            # Run strategies
            await scheduler.run_strategies(sample_dataframe, "GOLD", timestamp)

            # Verify metrics incremented
            final_runs = scheduler.metrics.strategy_runs_total.labels(
                name="test_strategy"
            )._value._value
            assert final_runs > initial_runs
