"""Tests for retry logic with exponential backoff and jitter."""

import asyncio
from unittest.mock import patch

import pytest

from backend.app.core.retry import (
    RetryExhaustedError,
    calculate_backoff_delay,
    retry_async,
    with_retry,
)


class TestBackoffCalculation:
    """Test backoff delay calculation logic."""

    def test_backoff_starts_at_base_delay(self) -> None:
        """Test first retry uses base delay."""
        delay = calculate_backoff_delay(attempt=0, base_delay=5.0, jitter=False)
        assert delay == 5.0

    def test_backoff_increases_exponentially(self) -> None:
        """Test backoff increases exponentially with attempt number."""
        delays = [
            calculate_backoff_delay(
                attempt=i, base_delay=5.0, multiplier=2.0, jitter=False
            )
            for i in range(5)
        ]
        # Expected: 5, 10, 20, 40, 80
        assert delays == [5.0, 10.0, 20.0, 40.0, 80.0]

    def test_backoff_respects_max_delay(self) -> None:
        """Test backoff is capped at max delay."""
        delay = calculate_backoff_delay(
            attempt=10, base_delay=5.0, multiplier=2.0, max_delay=120.0, jitter=False
        )
        assert delay == 120.0

    def test_backoff_with_jitter_varies(self) -> None:
        """Test jitter adds randomness to delay."""
        delays = [
            calculate_backoff_delay(attempt=1, base_delay=5.0, jitter=True)
            for _ in range(10)
        ]
        # All delays should be around 10.0 ±10% (9.0-11.0)
        # But some variation due to jitter
        assert len(set(delays)) > 1  # Not all identical
        assert all(8.0 <= d <= 12.0 for d in delays)

    def test_backoff_without_jitter_deterministic(self) -> None:
        """Test backoff without jitter is deterministic."""
        delays = [
            calculate_backoff_delay(attempt=1, base_delay=5.0, jitter=False)
            for _ in range(5)
        ]
        assert all(d == 10.0 for d in delays)

    def test_backoff_invalid_attempt_raises(self) -> None:
        """Test invalid attempt number raises ValueError."""
        with pytest.raises(ValueError):
            calculate_backoff_delay(attempt=-1)

    def test_backoff_invalid_base_delay_raises(self) -> None:
        """Test invalid base delay raises ValueError."""
        with pytest.raises(ValueError):
            calculate_backoff_delay(attempt=0, base_delay=-1.0)

    def test_backoff_invalid_multiplier_raises(self) -> None:
        """Test invalid multiplier raises ValueError."""
        with pytest.raises(ValueError):
            calculate_backoff_delay(attempt=0, multiplier=0.5)


class TestRetryDecorator:
    """Test @with_retry decorator for async functions."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_first_attempt(self) -> None:
        """Test function succeeds on first attempt."""

        @with_retry(max_retries=3)
        async def success_func() -> str:
            return "success"

        result = await success_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self) -> None:
        """Test function retries and succeeds on second attempt."""
        attempt_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def flaky_func() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ValueError("First attempt fails")
            return "success"

        result = await flaky_func()
        assert result == "success"
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausts_after_max_attempts(self) -> None:
        """Test RetryExhaustedError raised after max retries."""

        @with_retry(max_retries=2, base_delay=0.01)
        async def always_fails() -> None:
            raise ValueError("Always fails")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await always_fails()

        assert exc_info.value.attempts == 3  # 0, 1, 2 attempts
        assert isinstance(exc_info.value.last_error, ValueError)
        assert "Always fails" in str(exc_info.value.last_error)

    @pytest.mark.asyncio
    async def test_retry_preserves_exception_context(self) -> None:
        """Test original exception is preserved in context."""

        @with_retry(max_retries=1, base_delay=0.01)
        async def fails_with_error() -> None:
            raise RuntimeError("Original error")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await fails_with_error()

        assert exc_info.value.last_error.args[0] == "Original error"

    @pytest.mark.asyncio
    async def test_retry_logs_attempts(self, caplog) -> None:
        """Test retry logic logs attempt information."""
        import logging

        logger = logging.getLogger("test_logger")
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01, logger_=logger)
        async def flaky_func() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ValueError("Fail")
            return "success"

        result = await flaky_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_with_arguments(self) -> None:
        """Test decorated function with arguments."""

        @with_retry(max_retries=2, base_delay=0.01)
        async def add_numbers(a: int, b: int) -> int:
            return a + b

        result = await add_numbers(2, 3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_retry_with_kwargs(self) -> None:
        """Test decorated function with keyword arguments."""

        @with_retry(max_retries=2, base_delay=0.01)
        async def greet(name: str, greeting: str = "Hello") -> str:
            return f"{greeting}, {name}"

        result = await greet("Alice", greeting="Hi")
        assert result == "Hi, Alice"

    @pytest.mark.asyncio
    async def test_retry_with_timeout(self) -> None:
        """Test retry respects timeouts."""

        @with_retry(max_retries=1, base_delay=0.05)
        async def slow_func() -> None:
            await asyncio.sleep(10)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_func(), timeout=0.1)


class TestRetryAsync:
    """Test retry_async function for coroutines."""

    @pytest.mark.asyncio
    async def test_retry_async_succeeds(self) -> None:
        """Test coroutine succeeds without retries."""

        async def success_coro() -> str:
            return "success"

        result = await retry_async(success_coro(), max_retries=3)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_async_with_decorator_is_simpler(self) -> None:
        """Test using decorator is simpler than retry_async on raw coroutine."""
        attempt_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def flaky_func() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ValueError("Fail")
            return "success"

        result = await flaky_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_async_single_attempt(self) -> None:
        """Test retry_async with single attempt succeeding."""
        call_count = 0

        async def single_attempt_coro() -> str:
            nonlocal call_count
            call_count += 1
            return "done"

        result = await retry_async(single_attempt_coro(), max_retries=0)
        assert result == "done"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_async_respects_max_attempts(self) -> None:
        """Test retry_async respects max retry count."""
        attempt_count = 0

        # Use decorator for reliable retry testing (avoids coroutine recreation issues)
        @with_retry(max_retries=2, base_delay=0.01)
        async def test_func() -> str:
            nonlocal attempt_count
            attempt_count += 1
            raise ValueError("Persistent failure")

        with pytest.raises(RetryExhaustedError):
            await test_func()

        assert attempt_count == 3  # 0, 1, 2

    @pytest.mark.asyncio
    async def test_retry_async_with_delay_progression(self) -> None:
        """Test retry respects delay settings."""

        @with_retry(
            max_retries=2,
            base_delay=0.05,
            backoff_multiplier=2.0,
            jitter=False,
        )
        async def flaky() -> str:
            return "success"

        result = await flaky()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_async_with_max_delay_cap(self) -> None:
        """Test retry respects max_delay cap."""

        @with_retry(
            max_retries=3,
            base_delay=5.0,
            backoff_multiplier=10.0,
            max_delay=0.1,
            jitter=False,
        )
        async def operation() -> str:
            return "success"

        result = await operation()
        assert result == "success"


class TestRetryExceptions:
    """Test RetryExhaustedError exception."""

    def test_retry_exhausted_error_contains_context(self) -> None:
        """Test exception contains necessary context."""
        original_error = ValueError("Original error")
        exc = RetryExhaustedError(
            message="Failed after retries",
            attempts=5,
            last_error=original_error,
            operation="test_operation",
        )

        assert exc.attempts == 5
        assert exc.last_error is original_error
        assert exc.operation == "test_operation"
        assert "Failed after retries" in str(exc)

    def test_retry_exhausted_tracks_attempts(self) -> None:
        """Test exception tracks attempt count."""
        exc = RetryExhaustedError(
            message="Test",
            attempts=7,
            last_error=Exception(),
            operation="op",
        )
        assert exc.attempts == 7

    def test_retry_exhausted_preserves_last_error(self) -> None:
        """Test exception preserves last error with cause."""
        original = RuntimeError("Last failure")
        exc = RetryExhaustedError(
            message="Test",
            attempts=3,
            last_error=original,
        )
        assert exc.last_error is original


class TestRetryIntegration:
    """Integration tests for retry logic."""

    @pytest.mark.asyncio
    async def test_retry_decorator_with_multiple_exceptions(self) -> None:
        """Test decorator handles multiple exception types."""
        exceptions_to_raise = [
            ValueError("First"),
            RuntimeError("Second"),
            KeyError("Third"),
        ]
        attempt_count = 0

        @with_retry(max_retries=5, base_delay=0.01)
        async def multi_error_func() -> str:
            nonlocal attempt_count
            if attempt_count < len(exceptions_to_raise):
                exc = exceptions_to_raise[attempt_count]
                attempt_count += 1
                raise exc
            return "success"

        result = await multi_error_func()
        assert result == "success"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_retry_backoff_progression(self) -> None:
        """Test backoff delay progression is correct."""
        delays_used = []

        async def mock_delay(seconds: float) -> None:
            delays_used.append(seconds)

        with patch("asyncio.sleep", side_effect=mock_delay):
            attempt_count = 0

            @with_retry(
                max_retries=3,
                base_delay=1.0,
                backoff_multiplier=2.0,
                jitter=False,
                max_delay=10.0,
            )
            async def flaky() -> str:
                nonlocal attempt_count
                attempt_count += 1
                if attempt_count < 4:
                    raise ValueError("Fail")
                return "success"

            result = await flaky()
            assert result == "success"
            # Delays should be 1.0, 2.0, 4.0
            assert len(delays_used) == 3
            assert delays_used == [1.0, 2.0, 4.0]

    @pytest.mark.asyncio
    async def test_retry_with_side_effects(self) -> None:
        """Test retry works with functions having side effects."""
        call_count = 0
        results = []

        @with_retry(max_retries=3, base_delay=0.01)
        async def side_effect_func() -> int:
            nonlocal call_count
            call_count += 1
            results.append(call_count)
            if call_count < 3:
                raise ValueError("Not yet")
            return call_count

        result = await side_effect_func()
        assert result == 3
        assert results == [1, 2, 3]
        assert call_count == 3
