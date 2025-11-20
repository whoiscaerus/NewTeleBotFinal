import asyncio

import pytest

from backend.app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitState,
)


class MockRedis:
    """Simple in-memory Redis mock for testing."""

    def __init__(self):
        self.data = {}

    async def get(self, key):
        val = self.data.get(key)
        if val is not None:
            # Redis returns bytes
            if isinstance(val, bytes):
                return val
            return str(val).encode("utf-8")
        return None

    async def set(self, key, value):
        self.data[key] = value
        return True

    async def incr(self, key):
        val = int(self.data.get(key, 0))
        self.data[key] = val + 1
        return self.data[key]

    async def delete(self, key):
        if key in self.data:
            del self.data[key]
        return 1


@pytest.mark.asyncio
async def test_circuit_breaker_flow():
    """Test the full lifecycle of the circuit breaker."""
    redis = MockRedis()
    cb = CircuitBreaker(
        "test_circuit", redis, failure_threshold=2, recovery_timeout=0.1
    )

    # 1. Success case (CLOSED)
    async def success_func():
        return "ok"

    res = await cb.call(success_func)
    assert res == "ok"
    assert await cb._get_state() == CircuitState.CLOSED

    # 2. Failure case (1/2)
    async def fail_func():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await cb.call(fail_func)

    assert await cb._get_state() == CircuitState.CLOSED

    # 3. Failure case (2/2) -> OPEN
    with pytest.raises(ValueError):
        await cb.call(fail_func)

    assert await cb._get_state() == CircuitState.OPEN

    # 4. Fast fail (OPEN)
    with pytest.raises(CircuitBreakerOpenException):
        await cb.call(success_func)

    # 5. Wait for recovery timeout
    await asyncio.sleep(0.2)

    # 6. Half-Open (probe success) -> CLOSED
    # The call checks timeout, sees it passed, sets HALF_OPEN, executes func, succeeds, sets CLOSED
    res = await cb.call(success_func)
    assert res == "ok"
    assert await cb._get_state() == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_failure():
    """Test failure during HALF_OPEN state."""
    redis = MockRedis()
    cb = CircuitBreaker(
        "test_circuit_2", redis, failure_threshold=1, recovery_timeout=0.1
    )

    async def fail_func():
        raise ValueError("boom")

    # 1. Fail -> OPEN
    with pytest.raises(ValueError):
        await cb.call(fail_func)
    assert await cb._get_state() == CircuitState.OPEN

    # 2. Wait
    await asyncio.sleep(0.2)

    # 3. Probe fails -> OPEN
    with pytest.raises(ValueError):
        await cb.call(fail_func)

    assert await cb._get_state() == CircuitState.OPEN

    # 4. Still OPEN (fast fail)
    with pytest.raises(CircuitBreakerOpenException):
        await cb.call(fail_func)
