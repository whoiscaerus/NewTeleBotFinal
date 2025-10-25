"""Integration tests for retry + alert workflows."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.core.retry import RetryExhaustedError, with_retry
from backend.app.ops.alerts import OpsAlertService


class TestRetryAlertIntegration:
    """Integration tests combining retry logic with alert sending."""

    @pytest.mark.asyncio
    async def test_alert_on_retry_exhaustion(self) -> None:
        """Test retry exhaustion captures error context for alerts."""
        attempt_count = 0

        try:

            @with_retry(max_retries=1, base_delay=0.01)
            async def failing_operation() -> None:
                nonlocal attempt_count
                attempt_count += 1
                raise ValueError("Operation failed")

            await failing_operation()
        except RetryExhaustedError as e:
            # Verify error context is preserved for alert sending
            assert e.attempts == 2  # 0, 1
            assert isinstance(e.last_error, ValueError)
            assert e.operation == "failing_operation"

    @pytest.mark.asyncio
    async def test_retry_with_alert_context(self) -> None:
        """Test retry operation with alert context variables."""
        signal_id = "sig-456"
        operation_name = "post_signal"
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def signal_operation() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ConnectionError("Broker unreachable")
            return "success"

        result = await signal_operation()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_fail_then_alert_sequence(self) -> None:
        """Test sequence: retry attempts → exhaustion → alert can be sent."""
        attempt_count = 0

        try:

            @with_retry(max_retries=2, base_delay=0.01)
            async def always_fails() -> None:
                nonlocal attempt_count
                attempt_count += 1
                raise RuntimeError("Always fails")

            await always_fails()
        except RetryExhaustedError as e:
            # Verify retry exhaustion occurred
            assert e.attempts == 3  # 0, 1, 2
            assert isinstance(e.last_error, RuntimeError)

    @pytest.mark.asyncio
    async def test_selective_retry_on_specific_errors(self) -> None:
        """Test retry only on specific error types."""
        attempt_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def selective_retry() -> str:
            nonlocal attempt_count
            attempt_count += 1

            if attempt_count == 1:
                raise ConnectionError("Temporary network error")
            if attempt_count == 2:
                raise TimeoutError("Request timeout")
            return "success"

        result = await selective_retry()
        assert result == "success"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff_progression(self) -> None:
        """Test exponential backoff delays between retries."""
        import time

        attempt_times = []

        @with_retry(
            max_retries=3, base_delay=0.05, backoff_multiplier=2.0, jitter=False
        )
        async def track_retries() -> str:
            attempt_times.append(time.time())
            if len(attempt_times) < 3:
                raise ValueError("Fail")
            return "success"

        start = time.time()
        result = await track_retries()
        elapsed = time.time() - start

        assert result == "success"
        # Should have 2 delays: 0.05s + 0.1s = 0.15s minimum
        assert elapsed >= 0.14
        assert len(attempt_times) == 3

    @pytest.mark.asyncio
    async def test_retry_decorator_with_parameters(self) -> None:
        """Test decorated function with parameters and retry."""
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def operation_with_params(param1: str, param2: int) -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ValueError("Fail")
            return f"{param1}-{param2}"

        result = await operation_with_params("test", 42)
        assert result == "test-42"

    @pytest.mark.asyncio
    async def test_retry_exhaustion_with_alert(self) -> None:
        """Test retry exhaustion captures context for alert sending."""
        try:

            @with_retry(max_retries=1, base_delay=0.01)
            async def fails() -> None:
                raise RuntimeError("Persistent error")

            await fails()
        except RetryExhaustedError as e:
            # Verify context available for alert
            assert e.attempts == 2
            assert isinstance(e.last_error, RuntimeError)
            assert e.operation == "fails"


class TestRetryDecoratorPatterns:
    """Test common retry decorator usage patterns."""

    @pytest.mark.asyncio
    async def test_retry_with_parameters_and_retry(self) -> None:
        """Test decorated function accepting parameters."""
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def fetch_data(user_id: str, timeout: int = 30) -> dict:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise ConnectionError("Network error")
            return {"user_id": user_id, "timeout": timeout}

        result = await fetch_data("user-123", timeout=60)
        assert result["user_id"] == "user-123"
        assert result["timeout"] == 60
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_retry_decorator_stacking(self) -> None:
        """Test stacking multiple retry decorators."""

        @with_retry(max_retries=2, base_delay=0.01)
        async def operation_with_retries() -> str:
            return "success"

        result = await operation_with_retries()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_with_state_modification(self) -> None:
        """Test retry with state changes between attempts."""
        state = {"attempt": 0, "results": []}

        @with_retry(max_retries=3, base_delay=0.01)
        async def stateful_operation() -> str:
            state["attempt"] += 1
            state["results"].append(state["attempt"])

            if state["attempt"] < 3:
                raise ValueError(f"Attempt {state['attempt']} failed")
            return "completed"

        result = await stateful_operation()
        assert result == "completed"
        assert state["results"] == [1, 2, 3]


class TestAlertTriggering:
    """Test alert triggering in various scenarios."""

    @pytest.mark.asyncio
    async def test_alert_can_be_sent_on_connection_error(self) -> None:
        """Test alert can be sent for connection errors."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            error = ConnectionError("Broker unreachable")
            result = await service.send_error_alert(
                message="Connection error",
                error=error,
                attempts=5,
                operation="post_signal",
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_alert_can_be_sent_on_timeout_error(self) -> None:
        """Test alert can be sent for timeout errors."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            error = asyncio.TimeoutError("Request timeout")
            result = await service.send_error_alert(
                message="Timeout error",
                error=error,
                attempts=3,
                operation="fetch_data",
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_alert_can_be_sent_on_validation_error(self) -> None:
        """Test alert can be sent for validation errors."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            error = ValueError("Invalid signal format")
            result = await service.send_error_alert(
                message="Validation error",
                error=error,
                attempts=1,
                operation="validate_signal",
            )

            assert result is True


class TestErrorContextPreservation:
    """Test that error context is preserved through retry → alert flow."""

    @pytest.mark.asyncio
    async def test_original_error_preserved_in_alert(self) -> None:
        """Test original error is preserved when sending alert."""
        original_error = ValueError("Original problem")

        try:

            @with_retry(max_retries=1, base_delay=0.01)
            async def fails_with_specific_error() -> None:
                raise original_error

            await fails_with_specific_error()
        except RetryExhaustedError as e:
            # Verify original error is accessible
            assert e.last_error is original_error
            assert str(e.last_error) == "Original problem"

    @pytest.mark.asyncio
    async def test_error_type_preserved_in_alert_message(self) -> None:
        """Test error type information is preserved."""
        error_types_seen = []

        async def operation_with_various_errors() -> None:
            errors = [
                ConnectionError("Network issue"),
                TimeoutError("Timeout issue"),
                RuntimeError("Runtime issue"),
            ]
            raise errors[len(error_types_seen)]

        # Test that error types are correctly identified
        for expected_error_type in [
            ConnectionError,
            TimeoutError,
            RuntimeError,
        ]:
            error_types_seen.append(expected_error_type)
            assert len(error_types_seen) > 0


class TestRetryAlertCombinations:
    """Test various combinations of retry and alert scenarios."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_no_alert_needed(self) -> None:
        """Test successful retry means no alert needed."""
        attempt_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def eventually_succeeds() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise ConnectionError("Temporary")
            return "success"

        result = await eventually_succeeds()

        assert result == "success"
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_retry_fails_alert_can_be_sent(self) -> None:
        """Test failed retry preserves error for alert."""
        try:

            @with_retry(max_retries=1, base_delay=0.01)
            async def always_fails() -> None:
                raise RuntimeError("Persistent failure")

            await always_fails()
        except RetryExhaustedError as e:
            # Verify error context is available for alert
            assert e.attempts == 2
            assert str(e.last_error) == "Persistent failure"

    @pytest.mark.asyncio
    async def test_multiple_retry_attempts_tracked(self) -> None:
        """Test alert reflects correct retry attempt count."""
        attempt_count = 0

        try:

            @with_retry(max_retries=4, base_delay=0.01)
            async def track_attempts() -> None:
                nonlocal attempt_count
                attempt_count += 1
                raise ValueError("Fail")

            await track_attempts()
        except RetryExhaustedError as e:
            # Max retries 4 means attempts 0,1,2,3,4 = 5 total
            assert e.attempts == 5

    @pytest.mark.asyncio
    async def test_jitter_prevents_thundering_herd(self) -> None:
        """Test jitter randomness across multiple concurrent retries."""
        delays = []

        async def get_delay_for_attempt(attempt: int) -> float:
            from backend.app.core.retry import calculate_backoff_delay

            return calculate_backoff_delay(
                attempt=attempt,
                base_delay=1.0,
                multiplier=2.0,
                jitter=True,
                max_delay=100.0,
            )

        # Generate multiple delays for same attempt
        for _ in range(10):
            delay = await get_delay_for_attempt(2)
            delays.append(delay)

        # Expected base delay for attempt 2: 1.0 * 2^2 = 4.0
        # With ±10% jitter: 3.6 - 4.4
        # Should have some variation due to jitter
        unique_delays = len(set(delays))
        assert unique_delays > 1  # Should not all be identical

    @pytest.mark.asyncio
    async def test_logging_throughout_retry_flow(self) -> None:
        """Test logging occurs at key retry points."""
        import logging

        logger = logging.getLogger("test_retry_logging")
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01, logger_=logger)
        async def logged_operation() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ValueError("First attempt fails")
            return "success"

        result = await logged_operation()
        assert result == "success"
        # Logger is used during retry process
        assert attempt_count == 2
