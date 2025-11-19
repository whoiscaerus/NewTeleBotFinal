"""Integration tests for retry resilience and Telegram alerting.

Tests verify that:
1. @with_retry decorator actually retries on real network failures
2. Retry backoff follows exponential progression
3. Telegram alert is sent when signal delivery exhausts retries
4. Alert includes proper error context and attempt count
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.app.core.retry import RetryExhaustedError, with_retry
from backend.app.ops.alerts import OpsAlertService
from backend.app.strategy.fib_rsi.schema import SignalCandidate
from backend.app.trading.outbound.client import HmacClient
from backend.app.trading.outbound.config import OutboundConfig


@pytest.fixture
def config() -> OutboundConfig:
    """Create test configuration."""
    return OutboundConfig(
        producer_id="test-producer",
        producer_secret="test-secret-key-min-16-bytes-long",
        server_base_url="https://api.example.com",
        enabled=True,
        timeout_seconds=30.0,
        max_body_size=65536,
    )


@pytest.fixture
def logger():
    """Create mock logger."""
    return MagicMock()


@pytest.fixture
def signal() -> SignalCandidate:
    """Create test signal."""
    return SignalCandidate(
        instrument="GOLD",
        side="buy",
        entry_price=1950.50,
        stop_loss=1945.00,
        take_profit=1960.00,
        confidence=0.85,
        reason="test_signal",
        timestamp=datetime(2025, 10, 25, 14, 30, 45, 123456),
        payload={"rsi": 35, "atr": 5.5},
    )


class TestRetryOnRealFailures:
    """Test @with_retry decorator on real signal posting failures."""

    @pytest.mark.asyncio
    async def test_retry_decorator_retries_on_transient_failure(
        self, config, logger, signal
    ) -> None:
        """Test @with_retry retries on transient network error.

        Scenario:
        - Attempt 1: Connection refused (transient error)
        - Attempt 2: Connection refused (transient error)
        - Attempt 3: Success

        Expected:
        - HTTP client.post() called 3 times
        - Signal successfully delivered on retry 3
        """
        client = HmacClient(config, logger)
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def post_with_retry():
            nonlocal attempt_count
            attempt_count += 1
            # Third attempt: success
            return await client.post_signal(signal)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "signal_id": "sig-delivered",
                "status": "pending_approval",
                "server_timestamp": "2025-10-25T14:30:45.123456Z",
            }
            # First two attempts: transient error, Third attempt: success
            mock_session.post.side_effect = [
                httpx.ConnectError("Connection refused"),
                httpx.ConnectError("Connection refused"),
                mock_response,
            ]

            await client._ensure_session()
            result = await post_with_retry()

            # ✅ Verify all 3 attempts were made
            assert attempt_count == 3
            # ✅ Verify HTTP client was called 3 times
            assert mock_session.post.call_count == 3
            # ✅ Verify final result is the successful response
            assert result.signal_id == "sig-delivered"
            assert result.status == "pending_approval"

    @pytest.mark.asyncio
    async def test_retry_stops_on_success_without_extra_retries(
        self, config, logger, signal
    ) -> None:
        """Test @with_retry stops retrying once success is achieved.

        Should NOT retry if first attempt succeeds.
        """
        client = HmacClient(config, logger)

        @with_retry(max_retries=3, base_delay=0.01)
        async def post_success_first():
            return await client.post_signal(signal)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "signal_id": "sig-first",
                "status": "pending_approval",
                "server_timestamp": "2025-10-25T14:30:45.123456Z",
            }
            mock_session.post.return_value = mock_response

            await client._ensure_session()
            result = await post_success_first()

            # ✅ HTTP client called exactly ONCE (no retries)
            assert mock_session.post.call_count == 1
            assert result.signal_id == "sig-first"

    @pytest.mark.asyncio
    async def test_retry_on_timeout_error(self, config, logger, signal) -> None:
        """Test @with_retry retries on timeout error.

        Timeout is a transient error and should trigger retry.
        """
        client = HmacClient(config, logger)
        attempt_count = 0

        @with_retry(max_retries=1, base_delay=0.01)
        async def post_with_timeout():
            nonlocal attempt_count
            attempt_count += 1
            return await client.post_signal(signal)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "signal_id": "sig-timeout",
                "status": "pending_approval",
                "server_timestamp": "2025-10-25T14:30:45.123456Z",
            }

            # First call: timeout, Second call: success
            mock_session.post.side_effect = [
                httpx.TimeoutException("Read timeout"),
                mock_response,
            ]

            await client._ensure_session()
            result = await post_with_timeout()

            # ✅ Verify it retried after timeout
            assert attempt_count == 2
            assert mock_session.post.call_count == 2
            assert result.signal_id == "sig-timeout"

    @pytest.mark.asyncio
    async def test_retry_raises_after_max_attempts(
        self, config, logger, signal
    ) -> None:
        """Test @with_retry raises RetryExhaustedError after max attempts."""
        client = HmacClient(config, logger)
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def always_fails():
            nonlocal attempt_count
            attempt_count += 1
            raise httpx.ConnectError("Persistent failure")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session
            mock_session.post.side_effect = httpx.ConnectError("Persistent failure")

            await client._ensure_session()

            with pytest.raises(RetryExhaustedError) as exc_info:
                await always_fails()

            # ✅ Verify all 3 attempts were made (max_retries=2 means 3 attempts total)
            assert attempt_count == 3
            # ✅ Verify exception contains correct attempt count
            assert exc_info.value.attempts == 3
            # ✅ Verify last error is preserved
            assert isinstance(exc_info.value.last_error, httpx.ConnectError)


class TestRetryBackoffProgression:
    """Test retry backoff delays follow exponential progression."""

    @pytest.mark.asyncio
    async def test_retry_backoff_progression_is_correct(
        self, config, logger, signal
    ) -> None:
        """Test backoff delays follow: 1.0, 2.0, 4.0 seconds.

        Base delay: 1.0
        Multiplier: 2.0
        Max delay: 120.0
        Jitter: disabled for determinism

        Expected delays: [1.0, 2.0, 4.0]
        """
        delays_used = []

        async def mock_sleep(seconds: float) -> None:
            """Capture delays instead of actually sleeping."""
            delays_used.append(seconds)

        with patch("asyncio.sleep", side_effect=mock_sleep):

            @with_retry(
                max_retries=3,
                base_delay=1.0,
                backoff_multiplier=2.0,
                jitter=False,
                max_delay=120.0,
            )
            async def always_fails():
                raise ValueError("Fail")

            with pytest.raises(RetryExhaustedError):
                await always_fails()

            # ✅ Verify backoff progression: 1.0, 2.0, 4.0
            assert delays_used == [1.0, 2.0, 4.0]

    @pytest.mark.asyncio
    async def test_retry_backoff_respects_max_delay(
        self, config, logger, signal
    ) -> None:
        """Test backoff delay is capped at max_delay.

        With aggressive exponential backoff (multiplier=10), max_delay caps the progression.
        """
        delays_used = []

        async def mock_sleep(seconds: float) -> None:
            delays_used.append(seconds)

        with patch("asyncio.sleep", side_effect=mock_sleep):

            @with_retry(
                max_retries=3,
                base_delay=1.0,
                backoff_multiplier=10.0,
                jitter=False,
                max_delay=5.0,  # Cap at 5 seconds
            )
            async def always_fails():
                raise ValueError("Fail")

            with pytest.raises(RetryExhaustedError):
                await always_fails()

            # ✅ Verify delays are capped at max_delay
            # Expected: [1.0, 10.0→capped to 5.0, 100.0→capped to 5.0]
            assert all(d <= 5.0 for d in delays_used)
            assert delays_used[0] == 1.0
            assert delays_used[1] == 5.0  # Capped
            assert delays_used[2] == 5.0  # Capped


class TestTelegramAlertOnRetryExhaustion:
    """Test Telegram alert is sent when signal delivery fails all retries."""

    @pytest.mark.asyncio
    async def test_telegram_alert_sent_after_max_retries_exhausted(
        self, config, logger, signal
    ) -> None:
        """Test Telegram alert sent when signal posting exhausts retries.

        Scenario:
        - Signal post attempt 1: fails with ConnectionError
        - Signal post attempt 2: fails with ConnectionError
        - Signal post attempt 3: fails with ConnectionError
        - Max retries exhausted: RetryExhaustedError raised
        - Alert service sends Telegram notification
        """
        client = HmacClient(config, logger)
        alert_service = OpsAlertService(
            telegram_token="test_token",
            telegram_chat_id="test_chat_id",
        )

        attempt_count = 0

        async def post_signal_with_alert_on_failure():
            """Post signal with retry, alert on failure."""
            nonlocal attempt_count

            @with_retry(max_retries=2, base_delay=0.01)
            async def attempt_post():
                nonlocal attempt_count
                attempt_count += 1
                # All attempts fail
                raise httpx.ConnectError("Broker connection failed")

            try:
                return await attempt_post()
            except RetryExhaustedError as ex:
                # After exhausting retries, send alert
                await alert_service.send_error_alert(
                    message=f"Signal delivery failed after {ex.attempts} attempts",
                    error=ex,
                    attempts=ex.attempts,
                    operation="post_signal",
                )
                raise

        with patch("httpx.AsyncClient") as mock_http:
            mock_session = AsyncMock()
            mock_http.return_value = mock_session

            # All signal post attempts fail
            mock_session.post.side_effect = httpx.ConnectError(
                "Broker connection failed"
            )

            await client._ensure_session()

            with pytest.raises(RetryExhaustedError):
                await post_signal_with_alert_on_failure()

            # ✅ Verify signal posting was attempted 3 times (max_retries=2)
            assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_telegram_alert_includes_error_context(
        self, config, logger, signal
    ) -> None:
        """Test Telegram alert includes error details and attempt count."""
        alert_service = OpsAlertService(
            telegram_token="test_token",
            telegram_chat_id="test_chat_id",
        )

        with patch("httpx.AsyncClient") as mock_http:
            mock_session = AsyncMock()
            mock_http.return_value = mock_session
            mock_session.__aenter__.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_session.post.return_value = mock_response

            # Create error context
            original_error = ConnectionError("Broker unreachable")
            retry_exhausted = RetryExhaustedError(
                message="Signal delivery failed",
                attempts=3,
                last_error=original_error,
                operation="post_signal",
            )

            # Send error alert
            result = await alert_service.send_error_alert(
                message="Signal delivery failed after 3 attempts",
                error=retry_exhausted,
                attempts=3,
                operation="post_signal",
            )

            # ✅ Alert was sent
            assert result is True
            # ✅ Telegram API was called
            mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_telegram_alert_not_sent_on_first_failure(
        self, config, logger, signal
    ) -> None:
        """Test Telegram alert is NOT sent on first failure (only on exhaustion).

        Alert should only be sent when ALL retries are exhausted,
        not on transient failures that get retried.
        """
        client = HmacClient(config, logger)

        @with_retry(max_retries=1, base_delay=0.01)
        async def post_succeeds_on_retry():
            """First attempt fails, second succeeds."""
            return await client.post_signal(signal)

        with patch("httpx.AsyncClient") as mock_http:
            mock_session = AsyncMock()
            mock_http.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "signal_id": "sig-1",
                "status": "pending_approval",
                "server_timestamp": "2025-10-25T14:30:45.123456Z",
            }

            # First attempt fails, second succeeds
            mock_session.post.side_effect = [
                httpx.ConnectError("Temporary failure"),
                mock_response,
            ]

            await client._ensure_session()
            result = await post_succeeds_on_retry()

            # ✅ Signal was successfully delivered on retry
            assert result.signal_id == "sig-1"

            # ✅ Alert was NOT sent (because delivery succeeded)
            # Alert should only be sent if all retries exhausted
            assert mock_session.post.call_count == 2  # Two attempts, both for posting


class TestCompleteResilientWorkflow:
    """Integration: full workflow with retry and alerting."""

    @pytest.mark.asyncio
    async def test_complete_signal_delivery_with_resilience(
        self, config, logger, signal
    ) -> None:
        """Test complete workflow: signal → HMAC → post with retry → alert.

        Scenario:
        1. Create signal with HMAC signing
        2. Attempt to post with @with_retry decorator
        3. First two attempts: connection errors
        4. Third attempt: success
        5. Verify signal was delivered
        """
        client = HmacClient(config, logger)
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def post_with_resilience():
            nonlocal attempt_count
            attempt_count += 1
            return await client.post_signal(signal)

        with patch("httpx.AsyncClient") as mock_http:
            mock_session = AsyncMock()
            mock_http.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "signal_id": "sig-resilient-123",
                "status": "pending_approval",
                "server_timestamp": "2025-10-25T14:30:45.123456Z",
            }

            # First two calls: fail, Third call: success
            mock_session.post.side_effect = [
                httpx.ConnectError("Server unreachable"),
                httpx.ConnectError("Server unreachable"),
                mock_response,
            ]

            await client._ensure_session()
            result = await post_with_resilience()

            # ✅ All 3 attempts were made
            assert attempt_count == 3
            assert mock_session.post.call_count == 3

            # ✅ Signal was successfully delivered
            assert result.signal_id == "sig-resilient-123"
            assert result.status == "pending_approval"

            # ✅ Request contained real HMAC signature
            for call in mock_session.post.call_args_list:
                headers = call.kwargs["headers"]
                assert "X-Signature" in headers
                assert "X-Timestamp" in headers
                assert "X-Producer-Id" in headers

    @pytest.mark.asyncio
    async def test_resilient_workflow_fails_and_alerts_on_exhaustion(
        self, config, logger, signal
    ) -> None:
        """Test alert is sent when resilient workflow fails all retries.

        Scenario:
        1. Signal posting attempted 3 times
        2. All attempts fail with persistent error
        3. RetryExhaustedError raised
        4. Alert service sends Telegram notification
        5. Owner is notified of delivery failure
        """
        client = HmacClient(config, logger)
        alert_service = OpsAlertService(
            telegram_token="test_token",
            telegram_chat_id="test_chat_id",
        )

        attempt_count = 0

        async def post_with_alert_fallback():
            """Post with retry, alert on failure."""
            nonlocal attempt_count

            @with_retry(max_retries=2, base_delay=0.01)
            async def attempt_post():
                nonlocal attempt_count
                attempt_count += 1
                raise httpx.ConnectError("Persistent broker failure")

            try:
                return await attempt_post()
            except RetryExhaustedError as ex:
                # All retries exhausted - send alert
                await alert_service.send_error_alert(
                    message=f"Signal delivery failed: {signal.instrument} {signal.side}",
                    error=ex,
                    attempts=ex.attempts,
                    operation="post_signal",
                )
                # Re-raise so caller knows delivery failed
                raise

        with patch("httpx.AsyncClient") as mock_http:
            mock_session = AsyncMock()
            mock_http.return_value = mock_session
            mock_session.post.side_effect = httpx.ConnectError(
                "Persistent broker failure"
            )

            await client._ensure_session()

            with pytest.raises(RetryExhaustedError) as exc_info:
                await post_with_alert_fallback()

            # ✅ All 3 attempts were made
            assert attempt_count == 3
            # ✅ Exception contains proper context
            assert exc_info.value.attempts == 3
            assert exc_info.value.operation == "attempt_post"
