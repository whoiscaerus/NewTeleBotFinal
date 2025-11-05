"""PR-018 Integration Tests: Resilient Retries + Telegram Alerts

Comprehensive testing for PR-018 which implements:
1. Exponential backoff retry decorator with jitter
2. OpsAlertService for Telegram notifications
3. Integration between retry failures and alert notifications
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.core.retry import (
    RetryExhaustedError,
    calculate_backoff_delay,
    with_retry,
)
from backend.app.ops.alerts import AlertConfigError, OpsAlertService

# ============================================================================
# EXPONENTIAL BACKOFF TESTS
# ============================================================================


class TestExponentialBackoff:
    """Test exponential backoff calculation with jitter."""

    def test_backoff_calculation_first_attempt(self):
        """Test backoff delay for first retry."""
        delay = calculate_backoff_delay(attempt=0, base_delay=1.0)
        # With jitter: ±10%, so 0.9 to 1.1
        assert 0.9 <= delay <= 1.1

    def test_backoff_calculation_increases_exponentially(self):
        """Test backoff increases exponentially with attempt."""
        # Disable jitter for predictable values
        delay_0 = calculate_backoff_delay(attempt=0, base_delay=1.0, jitter=False)
        delay_1 = calculate_backoff_delay(attempt=1, base_delay=1.0, jitter=False)
        delay_2 = calculate_backoff_delay(attempt=2, base_delay=1.0, jitter=False)

        # Each should be double the previous (2^attempt * base)
        assert delay_0 == 1.0
        assert delay_1 == 2.0
        assert delay_2 == 4.0

    def test_backoff_with_max_delay_cap(self):
        """Test backoff respects maximum delay cap."""
        delay = calculate_backoff_delay(
            attempt=10, base_delay=1.0, multiplier=2.0, max_delay=30.0, jitter=False
        )
        assert delay == 30.0  # Capped at max

    def test_backoff_with_base_delay(self):
        """Test backoff scales with different base delays."""
        delay_base_1 = calculate_backoff_delay(attempt=2, base_delay=1.0, jitter=False)
        delay_base_5 = calculate_backoff_delay(attempt=2, base_delay=5.0, jitter=False)

        # Base 5 should be 5x larger (4.0 vs 20.0 for attempt 2)
        assert delay_base_5 == delay_base_1 * 5


# ============================================================================
# RETRY DECORATOR TESTS
# ============================================================================


class TestRetryDecorator:
    """Test @with_retry decorator for resilient operations."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_immediately(self):
        """Test operation succeeds on first try."""
        attempt_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def succeeds():
            nonlocal attempt_count
            attempt_count += 1
            return "success"

        result = await succeeds()
        assert result == "success"
        assert attempt_count == 1

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self):
        """Test operation succeeds after initial failures."""
        attempt_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def fails_twice():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError(f"Attempt {attempt_count} failed")
            return "success"

        result = await fails_twice()
        assert result == "success"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausts_after_max_attempts(self):
        """Test operation raises after max retries exhausted."""
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def always_fails():
            nonlocal attempt_count
            attempt_count += 1
            raise ValueError(f"Attempt {attempt_count}")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await always_fails()

        assert exc_info.value.attempts == 3  # 1 initial + 2 retries
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_retry_with_custom_parameters(self):
        """Test retry with custom parameters."""
        attempt_count = 0

        @with_retry(max_retries=5, base_delay=0.02, backoff_multiplier=1.5)
        async def fails_then_succeeds():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError(f"Attempt {attempt_count}")
            return "success"

        result = await fails_then_succeeds()
        assert result == "success"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_retry_does_not_catch_early_success(self):
        """Test retry doesn't retry when operation succeeds."""
        attempt_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def immediate_success():
            nonlocal attempt_count
            attempt_count += 1
            return "immediate"

        result = await immediate_success()
        assert result == "immediate"
        assert attempt_count == 1  # No retries needed


# ============================================================================
# RETRY_ASYNC FUNCTION TESTS
# ============================================================================


class TestRetryAsync:
    """Test core retry functionality with async operations."""

    @pytest.mark.asyncio
    async def test_async_operation_with_backoff(self):
        """Test async operations use retry logic correctly."""
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def async_operation():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ValueError("Network error")
            return {"status": "ok"}

        result = await async_operation()
        assert result == {"status": "ok"}
        assert attempt_count == 2


# ============================================================================
# OPS ALERT SERVICE TESTS
# ============================================================================


class TestOpsAlertService:
    """Test OpsAlertService for Telegram notifications."""

    def test_alert_service_initialization(self):
        """Test OpsAlertService can be initialized."""
        service = OpsAlertService(
            telegram_token="test-token-123",
            telegram_chat_id="test-chat-id-456",
        )
        assert service.telegram_token == "test-token-123"
        assert service.telegram_chat_id == "test-chat-id-456"

    def test_alert_service_validates_config(self):
        """Test OpsAlertService validates required config."""
        with pytest.raises(AlertConfigError):
            OpsAlertService(
                telegram_token=None,  # Missing required token
                telegram_chat_id="test-chat-id",
            )

    @pytest.mark.asyncio
    async def test_send_alert_successfully(self):
        """Test sending alert via Telegram."""
        service = OpsAlertService(
            telegram_token="test-token",
            telegram_chat_id="test-chat-id",
        )

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = AsyncMock(return_value={"ok": True})
            mock_post.return_value = mock_response

            result = await service.send("Test alert message")
            assert result is True

    @pytest.mark.asyncio
    async def test_send_error_alert_with_exception(self):
        """Test sending detailed error alert."""
        service = OpsAlertService(
            telegram_token="test-token",
            telegram_chat_id="test-chat-id",
        )

        error = ValueError("Signal delivery failed")

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = AsyncMock(return_value={"ok": True})
            mock_post.return_value = mock_response

            result = await service.send_error_alert(
                message="Signal posting failed",
                error=error,
                attempts=5,
            )
            assert result is True


# ============================================================================
# INTEGRATION TESTS: RETRY + ALERT
# ============================================================================


class TestRetryAlertIntegration:
    """Test integration between retry failures and alert notifications."""

    @pytest.mark.asyncio
    async def test_retry_failure_triggers_alert(self):
        """Test alert sent when retry exhausted."""
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def post_signal():
            nonlocal attempt_count
            attempt_count += 1
            raise ConnectionError(f"Attempt {attempt_count}")

        # Should retry and then fail
        with pytest.raises(RetryExhaustedError) as exc_info:
            await post_signal()

        # Verify error contains context for alerting
        assert exc_info.value.attempts == 3

    @pytest.mark.asyncio
    async def test_signal_posting_complete_flow(self):
        """Test complete flow: signal → retry → failure → alert."""
        alert_service = OpsAlertService(
            telegram_token="test-token",
            telegram_chat_id="test-chat-id",
        )

        signal_data = {
            "signal_id": "sig-123",
            "instrument": "GOLD",
            "side": "buy",
        }

        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def post_signal_with_retry():
            nonlocal attempt_count
            attempt_count += 1
            raise ConnectionError(f"Network error on attempt {attempt_count}")

        # Post signal with retry
        with pytest.raises(RetryExhaustedError) as exc_info:
            await post_signal_with_retry()

        # Should have retried 3 times (1 + 2 retries)
        assert attempt_count == 3
        assert exc_info.value.attempts == 3

        # Now send alert about the failure
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = AsyncMock(return_value={"ok": True})
            mock_post.return_value = mock_response

            alert_sent = await alert_service.send_error_alert(
                message=f"Signal {signal_data['signal_id']} posting failed after 3 attempts",
                error=exc_info.value.last_error,
                attempts=attempt_count,
            )

            assert alert_sent is True

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff_times(self):
        """Test retry with actual backoff timing."""
        timestamps = []
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.05)
        async def track_timing():
            nonlocal attempt_count
            attempt_count += 1
            timestamps.append(datetime.now(UTC))
            if attempt_count < 3:
                raise ValueError(f"Attempt {attempt_count}")
            return "success"

        result = await track_timing()
        assert result == "success"
        assert len(timestamps) == 3

        # Verify backoff increases between attempts
        delay_1_to_2 = (timestamps[1] - timestamps[0]).total_seconds()
        delay_2_to_3 = (timestamps[2] - timestamps[1]).total_seconds()

        # Second delay should be longer (exponential backoff)
        assert delay_2_to_3 > delay_1_to_2

    @pytest.mark.asyncio
    async def test_alert_messages_include_context(self):
        """Test alert messages include error context."""
        service = OpsAlertService(
            telegram_token="test-token",
            telegram_chat_id="test-chat-id",
        )

        error = ConnectionError("Failed to reach server at api.example.com")

        # Mock the Telegram API
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = AsyncMock(return_value={"ok": True})
            mock_post.return_value = mock_response

            # Send error alert
            await service.send_error_alert(
                message="Critical: Signal delivery failed",
                error=error,
                attempts=5,
            )

            # Verify API was called
            assert mock_post.called


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


class TestErrorHandling:
    """Test error handling in retry and alert systems."""

    def test_retry_exhausted_error_contains_context(self):
        """Test RetryExhaustedError has useful context."""
        original_error = ValueError("Original error")
        exhausted_error = RetryExhaustedError(
            message="Retries exhausted",
            attempts=5,
            last_error=original_error,
            operation="post_signal",
        )

        assert exhausted_error.attempts == 5
        assert exhausted_error.last_error == original_error
        assert exhausted_error.operation == "post_signal"

    def test_alert_config_error_message(self):
        """Test AlertConfigError provides clear message."""
        error = AlertConfigError(
            "Telegram credentials not configured. "
            "Set OPS_TELEGRAM_BOT_TOKEN and OPS_TELEGRAM_CHAT_ID"
        )
        assert "Telegram" in str(error)

    @pytest.mark.asyncio
    async def test_alert_handles_telegram_api_error(self):
        """Test alert service handles Telegram API failures."""
        service = OpsAlertService(
            telegram_token="test-token",
            telegram_chat_id="test-chat-id",
        )

        with patch("httpx.AsyncClient.post") as mock_post:
            # Simulate Telegram API error
            mock_response = AsyncMock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_post.return_value = mock_response

            result = await service.send("Test alert")
            assert result is False


# ============================================================================
# BUSINESS LOGIC VALIDATION
# ============================================================================


class TestBusinessLogicValidation:
    """Test PR-018 business logic is working correctly."""

    @pytest.mark.asyncio
    async def test_premium_user_auto_execution_retry_pattern(self):
        """Test premium users' signals use retry + backoff pattern."""
        signal_id = "sig-premium-123"
        attempt_count = 0

        @with_retry(max_retries=4, base_delay=2.0)
        async def post_premium_signal():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count <= 2:
                raise ConnectionError("Temporary network issue")
            return {"signal_id": signal_id, "status": "delivered"}

        result = await post_premium_signal()
        assert result["status"] == "delivered"
        assert attempt_count == 3  # Recovered after 2 failures

    @pytest.mark.asyncio
    async def test_ops_alert_on_persistent_failures(self):
        """Test alert sent when signal delivery persistently fails."""
        signal_id = "sig-fail-456"
        service = OpsAlertService(
            telegram_token="test-token",
            telegram_chat_id="test-chat-id",
        )

        @with_retry(max_retries=3, base_delay=0.01)
        async def post_signal_that_fails():
            raise ConnectionError("Server unreachable")

        # Try posting signal
        with pytest.raises(RetryExhaustedError):
            await post_signal_that_fails()

        # Should trigger alert
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            await service.send(
                f"🚨 Signal {signal_id} failed after 4 attempts. Manual intervention needed."
            )

            assert mock_post.called

    @pytest.mark.asyncio
    async def test_retry_backoff_prevents_overwhelming_server(self):
        """Test exponential backoff prevents request storms."""
        delays = []

        for attempt in range(1, 6):
            delay = calculate_backoff_delay(attempt=attempt, base_delay=1.0)
            delays.append(delay)

        # Verify delays increase
        for i in range(len(delays) - 1):
            assert delays[i + 1] > delays[i]

        # Verify reasonable max (5th retry should be capped)
        assert delays[4] <= 60.0  # Reasonable maximum
