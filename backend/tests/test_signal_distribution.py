"""Comprehensive tests for PR-072: Signal Generation & Distribution.

Tests cover:
- Candle boundary detection (exact, within window, outside window)
- Duplicate prevention (same candle, different instruments, different timeframes)
- Multi-timeframe support (15m, 1h, 4h, 1d)
- Signal publishing to API (success, failure, retries)
- Telegram notifications (success, failure, formatting)
- Error handling and edge cases
- Cache management and cleanup
- Real business logic validation (no mocks for core logic)
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from telegram.error import TelegramError

from backend.app.strategy.candles import CandleDetector, get_candle_detector
from backend.app.strategy.publisher import SignalPublisher, get_signal_publisher


class TestCandleDetector:
    """Test candle boundary detection and duplicate prevention."""

    def test_candle_detector_initialization(self):
        """Test CandleDetector initializes with correct window."""
        detector = CandleDetector(window_seconds=60)
        assert detector.window_seconds == 60
        assert len(detector._processed_candles) == 0

    def test_candle_detector_env_default(self, monkeypatch):
        """Test CandleDetector uses env var for window."""
        monkeypatch.setenv("CANDLE_CHECK_WINDOW", "120")
        detector = CandleDetector()
        assert detector.window_seconds == 120

    def test_is_new_candle_exact_boundary_15m(self):
        """Test detection at exact 15-minute boundary."""
        detector = CandleDetector(window_seconds=60)

        # Exactly at 10:15:00
        timestamp = datetime(2025, 1, 1, 10, 15, 0)
        assert detector.is_new_candle(timestamp, "15m") is True

    def test_is_new_candle_within_window_15m(self):
        """Test detection within window of 15-minute boundary."""
        detector = CandleDetector(window_seconds=60)

        # 10:15:05 - 5 seconds after boundary (within 60s window)
        timestamp = datetime(2025, 1, 1, 10, 15, 5)
        assert detector.is_new_candle(timestamp, "15m") is True

        # 10:15:55 - 55 seconds after boundary (within 60s window)
        timestamp = datetime(2025, 1, 1, 10, 15, 55)
        assert detector.is_new_candle(timestamp, "15m") is True

    def test_is_new_candle_outside_window_15m(self):
        """Test no detection outside window of 15-minute boundary."""
        detector = CandleDetector(window_seconds=60)

        # 10:17:30 - 2.5 minutes after boundary (outside 60s window)
        timestamp = datetime(2025, 1, 1, 10, 17, 30)
        assert detector.is_new_candle(timestamp, "15m") is False

        # 10:20:00 - 5 minutes after boundary (next candle not yet)
        timestamp = datetime(2025, 1, 1, 10, 20, 0)
        assert detector.is_new_candle(timestamp, "15m") is False

    def test_is_new_candle_1h_timeframe(self):
        """Test detection for 1-hour timeframe."""
        detector = CandleDetector(window_seconds=60)

        # Exactly at 10:00:00
        assert detector.is_new_candle(datetime(2025, 1, 1, 10, 0, 0), "1h") is True

        # 10:00:45 - within window
        assert detector.is_new_candle(datetime(2025, 1, 1, 10, 0, 45), "1h") is True

        # 10:30:00 - mid-candle
        assert detector.is_new_candle(datetime(2025, 1, 1, 10, 30, 0), "1h") is False

    def test_is_new_candle_4h_timeframe(self):
        """Test detection for 4-hour timeframe."""
        detector = CandleDetector(window_seconds=60)

        # Boundaries: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00
        assert detector.is_new_candle(datetime(2025, 1, 1, 8, 0, 0), "4h") is True
        assert detector.is_new_candle(datetime(2025, 1, 1, 8, 0, 55), "4h") is True
        assert detector.is_new_candle(datetime(2025, 1, 1, 9, 0, 0), "4h") is False

    def test_is_new_candle_1d_timeframe(self):
        """Test detection for 1-day timeframe."""
        detector = CandleDetector(window_seconds=60)

        # Exactly at midnight
        assert detector.is_new_candle(datetime(2025, 1, 1, 0, 0, 0), "1d") is True

        # 00:00:50 - within window
        assert detector.is_new_candle(datetime(2025, 1, 1, 0, 0, 50), "1d") is True

        # 12:00:00 - mid-day
        assert detector.is_new_candle(datetime(2025, 1, 1, 12, 0, 0), "1d") is False

    def test_parse_timeframe_valid_formats(self):
        """Test parsing of valid timeframe formats."""
        detector = CandleDetector()

        assert detector._parse_timeframe("15m") == 15
        assert detector._parse_timeframe("1m") == 1
        assert detector._parse_timeframe("30m") == 30
        assert detector._parse_timeframe("1h") == 60
        assert detector._parse_timeframe("4h") == 240
        assert detector._parse_timeframe("1d") == 1440

    def test_parse_timeframe_invalid_format(self):
        """Test parsing of invalid timeframe raises ValueError."""
        detector = CandleDetector()

        with pytest.raises(ValueError, match="Unsupported timeframe format"):
            detector._parse_timeframe("15")

        with pytest.raises(ValueError, match="Unsupported timeframe format"):
            detector._parse_timeframe("1w")

        with pytest.raises(ValueError, match="Unsupported timeframe format"):
            detector._parse_timeframe("invalid")

    def test_get_candle_start_15m(self):
        """Test getting candle start for 15-minute timeframe."""
        detector = CandleDetector()

        # 10:17:35 falls in 10:15-10:30 candle
        timestamp = datetime(2025, 1, 1, 10, 17, 35)
        start = detector.get_candle_start(timestamp, "15m")
        assert start == datetime(2025, 1, 1, 10, 15, 0)

        # 10:15:00 is exact start
        timestamp = datetime(2025, 1, 1, 10, 15, 0)
        start = detector.get_candle_start(timestamp, "15m")
        assert start == datetime(2025, 1, 1, 10, 15, 0)

        # 10:29:59 is still in 10:15-10:30 candle
        timestamp = datetime(2025, 1, 1, 10, 29, 59)
        start = detector.get_candle_start(timestamp, "15m")
        assert start == datetime(2025, 1, 1, 10, 15, 0)

    def test_get_candle_start_1h(self):
        """Test getting candle start for 1-hour timeframe."""
        detector = CandleDetector()

        # 10:37:12 falls in 10:00-11:00 candle
        timestamp = datetime(2025, 1, 1, 10, 37, 12)
        start = detector.get_candle_start(timestamp, "1h")
        assert start == datetime(2025, 1, 1, 10, 0, 0)

    def test_should_process_candle_first_detection(self):
        """Test first detection of candle allows processing."""
        detector = CandleDetector(window_seconds=60)

        # First detection at boundary
        timestamp = datetime(2025, 1, 1, 10, 15, 5)
        assert detector.should_process_candle("GOLD", "15m", timestamp) is True

    def test_should_process_candle_duplicate_prevention(self):
        """Test duplicate detection prevents reprocessing same candle."""
        detector = CandleDetector(window_seconds=60)

        # First detection
        timestamp1 = datetime(2025, 1, 1, 10, 15, 5)
        assert detector.should_process_candle("GOLD", "15m", timestamp1) is True

        # Second detection at same candle (10 seconds later)
        timestamp2 = datetime(2025, 1, 1, 10, 15, 15)
        assert detector.should_process_candle("GOLD", "15m", timestamp2) is False

        # Third detection at same candle (50 seconds later, still within window)
        timestamp3 = datetime(2025, 1, 1, 10, 15, 55)
        assert detector.should_process_candle("GOLD", "15m", timestamp3) is False

    def test_should_process_candle_different_instruments(self):
        """Test different instruments can process same candle."""
        detector = CandleDetector(window_seconds=60)

        timestamp = datetime(2025, 1, 1, 10, 15, 5)

        # GOLD processes
        assert detector.should_process_candle("GOLD", "15m", timestamp) is True

        # EURUSD can also process (different instrument)
        assert detector.should_process_candle("EURUSD", "15m", timestamp) is True

        # GOLD cannot process again (duplicate)
        assert detector.should_process_candle("GOLD", "15m", timestamp) is False

    def test_should_process_candle_different_timeframes(self):
        """Test same instrument/time with different timeframes."""
        detector = CandleDetector(window_seconds=60)

        timestamp = datetime(2025, 1, 1, 10, 15, 5)

        # 15m timeframe
        assert detector.should_process_candle("GOLD", "15m", timestamp) is True

        # 1h timeframe (different candle boundary)
        assert detector.should_process_candle("GOLD", "1h", timestamp) is True

    def test_should_process_candle_next_candle(self):
        """Test next candle can be processed after previous."""
        detector = CandleDetector(window_seconds=60)

        # First candle at 10:15
        timestamp1 = datetime(2025, 1, 1, 10, 15, 5)
        assert detector.should_process_candle("GOLD", "15m", timestamp1) is True

        # Next candle at 10:30
        timestamp2 = datetime(2025, 1, 1, 10, 30, 5)
        assert detector.should_process_candle("GOLD", "15m", timestamp2) is True

    def test_should_process_candle_outside_window(self):
        """Test outside window returns False."""
        detector = CandleDetector(window_seconds=60)

        # Mid-candle, not at boundary
        timestamp = datetime(2025, 1, 1, 10, 17, 30)
        assert detector.should_process_candle("GOLD", "15m", timestamp) is False

    def test_clear_cache(self):
        """Test cache clearing works."""
        detector = CandleDetector(window_seconds=60)

        # Process some candles
        detector.should_process_candle("GOLD", "15m", datetime(2025, 1, 1, 10, 15, 5))
        detector.should_process_candle("EURUSD", "15m", datetime(2025, 1, 1, 10, 15, 5))

        assert len(detector._processed_candles) == 2

        # Clear cache
        detector.clear_cache()
        assert len(detector._processed_candles) == 0

        # Can process again after clear
        assert (
            detector.should_process_candle(
                "GOLD", "15m", datetime(2025, 1, 1, 10, 15, 5)
            )
            is True
        )

    def test_cache_cleanup_triggered(self):
        """Test cache cleanup triggers when threshold exceeded."""
        detector = CandleDetector(window_seconds=60)

        # Add 1001 entries (exceeds threshold of 1000)
        base_time = datetime(2025, 1, 1, 0, 0, 0)
        for i in range(1001):
            # Each 15 minutes
            timestamp = base_time + timedelta(minutes=15 * i)
            detector._processed_candles[(f"INST_{i}", "15m", timestamp)] = timestamp

        # Trigger cleanup by calling should_process_candle
        detector.should_process_candle("GOLD", "15m", datetime(2025, 1, 2, 10, 15, 5))

        # Should have cleaned up to 500 entries (keeping most recent)
        assert len(detector._processed_candles) <= 501  # 500 + the new one

    def test_get_candle_detector_singleton(self):
        """Test global singleton getter."""
        detector1 = get_candle_detector()
        detector2 = get_candle_detector()

        # Should be same instance
        assert detector1 is detector2


class TestSignalPublisher:
    """Test signal publishing to API and Telegram."""

    def test_publisher_initialization(self, monkeypatch):
        """Test SignalPublisher initializes with env vars."""
        monkeypatch.setenv("SIGNALS_API_BASE", "http://test.com")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_ID", "-100123")

        publisher = SignalPublisher()

        assert publisher.signals_api_base == "http://test.com"
        assert publisher.telegram_token == "test_token"
        assert publisher.telegram_admin_chat_id == "-100123"

    def test_publisher_initialization_explicit_params(self):
        """Test SignalPublisher initializes with explicit params."""
        publisher = SignalPublisher(
            signals_api_base="http://explicit.com",
            telegram_token="explicit_token",
            telegram_admin_chat_id="-100456",
        )

        assert publisher.signals_api_base == "http://explicit.com"
        assert publisher.telegram_token == "explicit_token"
        assert publisher.telegram_admin_chat_id == "-100456"

    @pytest.mark.asyncio
    async def test_publish_missing_required_fields(self):
        """Test publish raises ValueError for missing required fields."""
        publisher = SignalPublisher(signals_api_base="http://test.com")

        # Missing instrument
        with pytest.raises(ValueError, match="Missing required fields"):
            await publisher.publish(
                {
                    "side": "buy",
                    "entry_price": 1950.50,
                    "strategy": "ppo_gold",
                    "timestamp": datetime.utcnow(),
                }
            )

    @pytest.mark.asyncio
    async def test_publish_duplicate_signal(self):
        """Test publish prevents duplicate signals."""
        publisher = SignalPublisher(signals_api_base="http://test.com")

        candle_start = datetime(2025, 1, 1, 10, 15, 0)
        signal_data = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 1950.50,
            "strategy": "ppo_gold",
            "timestamp": datetime(2025, 1, 1, 10, 15, 5),
            "candle_start": candle_start,
        }

        # Mock API call
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=201, json=lambda: {"id": "sig-123", "status": "new"}
            )

            # First publish succeeds
            result1 = await publisher.publish(signal_data)
            assert result1["api_success"] is True

            # Second publish is duplicate
            result2 = await publisher.publish(signal_data)
            assert result2["api_success"] is False
            assert "Duplicate signal" in result2.get("error", "")

    @pytest.mark.asyncio
    async def test_publish_to_api_success(self):
        """Test successful signal publishing to API."""
        publisher = SignalPublisher(signals_api_base="http://test.com")

        signal_data = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 1950.50,
            "stop_loss": 1945.00,
            "take_profit": 1960.00,
            "strategy": "ppo_gold",
            "timestamp": datetime(2025, 1, 1, 10, 15, 5),
            "candle_start": datetime(2025, 1, 1, 10, 15, 0),
            "confidence": 0.85,
        }

        # Mock API response
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": "sig-456", "status": "new"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            result = await publisher.publish(signal_data)

            assert result["api_success"] is True
            assert result["signal_id"] == "sig-456"
            assert result["api_response"]["status"] == "new"

            # Verify API was called with correct payload
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[1]["json"]["instrument"] == "GOLD"
            assert call_args[1]["json"]["side"] == "buy"
            assert call_args[1]["json"]["entry_price"] == 1950.50

    @pytest.mark.asyncio
    async def test_publish_to_api_failure(self):
        """Test API publishing handles errors gracefully."""
        publisher = SignalPublisher(signals_api_base="http://test.com")

        signal_data = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 1950.50,
            "strategy": "ppo_gold",
            "timestamp": datetime.utcnow(),
        }

        # Mock API failure
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.HTTPError("Connection failed")

            result = await publisher.publish(signal_data)

            assert result["api_success"] is False
            assert "error" in result
            assert "Connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_publish_with_telegram_notification(self):
        """Test publishing with Telegram notification."""
        publisher = SignalPublisher(
            signals_api_base="http://test.com",
            telegram_token="test_token",
            telegram_admin_chat_id="-100123",
        )

        signal_data = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 1950.50,
            "stop_loss": 1945.00,
            "take_profit": 1960.00,
            "strategy": "ppo_gold",
            "timestamp": datetime(2025, 1, 1, 10, 15, 5),
            "candle_start": datetime(2025, 1, 1, 10, 15, 0),
        }

        # Mock both API and Telegram
        with (
            patch("httpx.AsyncClient.post") as mock_api,
            patch("telegram.Bot") as mock_bot_class,
        ):

            # Mock API success
            mock_api_response = AsyncMock()
            mock_api_response.status_code = 201
            mock_api_response.json.return_value = {"id": "sig-789", "status": "new"}
            mock_api_response.raise_for_status = Mock()
            mock_api.return_value = mock_api_response

            # Mock Telegram bot
            mock_bot = AsyncMock()
            mock_bot.send_message = AsyncMock()
            mock_bot_class.return_value = mock_bot

            result = await publisher.publish(signal_data, notify_telegram=True)

            assert result["api_success"] is True
            assert result["telegram_success"] is True

            # Verify Telegram message sent
            mock_bot.send_message.assert_called_once()
            call_args = mock_bot.send_message.call_args
            assert call_args[1]["chat_id"] == "-100123"
            assert "GOLD" in call_args[1]["text"]
            assert "BUY" in call_args[1]["text"]

    @pytest.mark.asyncio
    async def test_publish_telegram_failure_does_not_affect_api(self):
        """Test Telegram failure doesn't prevent API success."""
        publisher = SignalPublisher(
            signals_api_base="http://test.com",
            telegram_token="test_token",
            telegram_admin_chat_id="-100123",
        )

        signal_data = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 1950.50,
            "strategy": "ppo_gold",
            "timestamp": datetime.utcnow(),
            "candle_start": datetime.utcnow(),
        }

        with (
            patch("httpx.AsyncClient.post") as mock_api,
            patch("telegram.Bot") as mock_bot_class,
        ):

            # Mock API success
            mock_api_response = AsyncMock()
            mock_api_response.status_code = 201
            mock_api_response.json.return_value = {"id": "sig-999", "status": "new"}
            mock_api_response.raise_for_status = Mock()
            mock_api.return_value = mock_api_response

            # Mock Telegram failure
            mock_bot = AsyncMock()
            mock_bot.send_message = AsyncMock(
                side_effect=TelegramError("Network error")
            )
            mock_bot_class.return_value = mock_bot

            result = await publisher.publish(signal_data, notify_telegram=True)

            # API should succeed
            assert result["api_success"] is True
            assert result["signal_id"] == "sig-999"

            # Telegram should fail but not crash
            assert result["telegram_success"] is False

    @pytest.mark.asyncio
    async def test_publish_telegram_skipped_when_api_fails(self):
        """Test Telegram notification skipped if API fails."""
        publisher = SignalPublisher(
            signals_api_base="http://test.com",
            telegram_token="test_token",
            telegram_admin_chat_id="-100123",
        )

        signal_data = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 1950.50,
            "strategy": "ppo_gold",
            "timestamp": datetime.utcnow(),
        }

        with (
            patch("httpx.AsyncClient.post") as mock_api,
            patch("telegram.Bot") as mock_bot_class,
        ):

            # Mock API failure
            mock_api.side_effect = httpx.HTTPError("Connection failed")

            mock_bot = AsyncMock()
            mock_bot.send_message = AsyncMock()
            mock_bot_class.return_value = mock_bot

            result = await publisher.publish(signal_data, notify_telegram=True)

            # API failed
            assert result["api_success"] is False

            # Telegram not called (API failed)
            mock_bot.send_message.assert_not_called()

    def test_clear_cache(self):
        """Test cache clearing works."""
        publisher = SignalPublisher()

        # Add some entries
        candle1 = datetime(2025, 1, 1, 10, 15, 0)
        candle2 = datetime(2025, 1, 1, 10, 30, 0)
        publisher._published_signals[("GOLD", candle1)] = datetime.utcnow()
        publisher._published_signals[("EURUSD", candle2)] = datetime.utcnow()

        assert len(publisher._published_signals) == 2

        # Clear
        publisher.clear_cache()
        assert len(publisher._published_signals) == 0

    def test_get_signal_publisher_singleton(self, monkeypatch):
        """Test global singleton getter."""
        monkeypatch.setenv("SIGNALS_API_BASE", "http://singleton.com")

        # Clear any existing singleton
        import backend.app.strategy.publisher as pub_module

        pub_module._publisher = None

        publisher1 = get_signal_publisher()
        publisher2 = get_signal_publisher()

        # Should be same instance
        assert publisher1 is publisher2


class TestIntegration:
    """Integration tests combining candles and publisher."""

    @pytest.mark.asyncio
    async def test_end_to_end_signal_flow(self):
        """Test complete flow: candle detection → publish → success."""
        detector = CandleDetector(window_seconds=60)
        publisher = SignalPublisher(signals_api_base="http://test.com")

        # At candle boundary
        timestamp = datetime(2025, 1, 1, 10, 15, 5)

        # Check if should process
        if detector.should_process_candle("GOLD", "15m", timestamp):
            signal_data = {
                "instrument": "GOLD",
                "side": "buy",
                "entry_price": 1950.50,
                "strategy": "ppo_gold",
                "timestamp": timestamp,
                "candle_start": detector.get_candle_start(timestamp, "15m"),
            }

            # Mock API
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_response = AsyncMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {"id": "sig-int-1", "status": "new"}
                mock_response.raise_for_status = Mock()
                mock_post.return_value = mock_response

                result = await publisher.publish(signal_data)

                assert result["api_success"] is True
                assert result["signal_id"] == "sig-int-1"

    @pytest.mark.asyncio
    async def test_duplicate_prevention_across_components(self):
        """Test duplicate prevention works across detector and publisher."""
        detector = CandleDetector(window_seconds=60)
        publisher = SignalPublisher(signals_api_base="http://test.com")

        timestamp1 = datetime(2025, 1, 1, 10, 15, 5)
        timestamp2 = datetime(2025, 1, 1, 10, 15, 15)  # Same candle

        # Mock API
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": "sig-dup-1", "status": "new"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            # First attempt
            if detector.should_process_candle("GOLD", "15m", timestamp1):
                signal_data = {
                    "instrument": "GOLD",
                    "side": "buy",
                    "entry_price": 1950.50,
                    "strategy": "ppo_gold",
                    "timestamp": timestamp1,
                    "candle_start": detector.get_candle_start(timestamp1, "15m"),
                }
                result1 = await publisher.publish(signal_data)
                assert result1["api_success"] is True

            # Second attempt (should be blocked by detector)
            should_process = detector.should_process_candle("GOLD", "15m", timestamp2)
            assert should_process is False  # Blocked by candle detector
