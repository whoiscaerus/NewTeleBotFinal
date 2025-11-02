"""Redis-backed rate limiting with token bucket algorithm."""

import logging
from datetime import UTC, datetime

import redis.asyncio as aioredis

from backend.app.core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RateLimiter:
    """Redis-backed rate limiter using token bucket algorithm.

    Maintains a bucket with tokens. Each request consumes 1 token.
    Tokens are replenished at rate: tokens_per_second.

    Example:
        limiter = RateLimiter()
        is_allowed = await limiter.is_allowed("user:123", max_tokens=100, refill_rate=10)
        if not is_allowed:
            raise HTTPException(429, "Too many requests")
    """

    def __init__(self):
        """Initialize rate limiter (requires Redis)."""
        self.redis_client = None
        self._initialized = False

    async def initialize(self):
        """Initialize Redis connection.

        Raises:
            RuntimeError: If Redis not enabled in settings
        """
        if not settings.redis.enabled:
            logger.warning("Redis disabled - rate limiting inactive")
            self._initialized = False
            return

        try:
            self.redis_client = aioredis.from_url(
                settings.redis.url, decode_responses=True
            )
            await self.redis_client.ping()
            self._initialized = True
            logger.info("Redis rate limiter initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Redis rate limiter: {e}")
            self._initialized = False

    async def is_allowed(
        self,
        key: str,
        max_tokens: int = 60,
        refill_rate: int = 1,
        window_seconds: int = 60,
    ) -> bool:
        """Check if request is allowed under rate limit.

        Args:
            key: Rate limit key (e.g., "user:123" or "ip:192.168.1.1")
            max_tokens: Maximum tokens in bucket
            refill_rate: Tokens added per second
            window_seconds: Time window for refill calculation

        Returns:
            bool: True if request allowed, False if rate limited

        Example:
            # 60 requests per minute (refill_rate=1, window_seconds=60)
            allowed = await limiter.is_allowed("user:123", max_tokens=60, refill_rate=1, window_seconds=60)
        """
        if not self._initialized or self.redis_client is None:
            logger.debug(f"Rate limiter inactive - allowing request for key: {key}")
            return True

        try:
            # Use Lua script for atomic operation (all-or-nothing)
            script = """
            local key = KEYS[1]
            local max_tokens = tonumber(ARGV[1])
            local refill_rate = tonumber(ARGV[2])
            local window_seconds = tonumber(ARGV[3])
            local now = tonumber(ARGV[4])

            -- Get current bucket state
            local state = redis.call('HGETALL', key)
            local tokens = max_tokens  -- Start full for new buckets (good UX)
            local last_refill = now

            if #state > 0 then
                tokens = tonumber(state[2]) or max_tokens
                last_refill = tonumber(state[4]) or now
            end

            -- Calculate tokens to add based on time passed
            local time_passed = math.max(0, now - last_refill)
            local tokens_to_add = math.floor(time_passed * refill_rate / window_seconds)
            tokens = math.min(max_tokens, tokens + tokens_to_add)

            -- Check if request allowed
            if tokens >= 1 then
                tokens = tokens - 1
                redis.call('HSET', key, 'tokens', tokens, 'last_refill', now)
                redis.call('EXPIRE', key, window_seconds * 2)  -- expire bucket if unused
                return 1  -- allowed
            else
                redis.call('HSET', key, 'tokens', tokens, 'last_refill', now)
                redis.call('EXPIRE', key, window_seconds * 2)
                return 0  -- rate limited
            end
            """

            now = datetime.now(UTC).timestamp()
            result = await self.redis_client.eval(
                script,
                1,
                key,
                max_tokens,
                refill_rate,
                window_seconds,
                now,
            )

            allowed = bool(result)
            if not allowed:
                logger.debug(f"Rate limit exceeded for key: {key}")

            return allowed

        except Exception as e:
            logger.error(f"Rate limiter error for key {key}: {e}", exc_info=True)
            # Fail open - allow request if rate limiter broken
            return True

    async def get_remaining(
        self,
        key: str,
        max_tokens: int = 60,
        refill_rate: int = 1,
        window_seconds: int = 60,
    ) -> int:
        """Get remaining tokens for a key.

        Args:
            key: Rate limit key
            max_tokens: Maximum tokens in bucket
            refill_rate: Tokens added per second
            window_seconds: Time window for refill calculation

        Returns:
            int: Number of remaining tokens (0-max_tokens)
        """
        if not self._initialized or self.redis_client is None:
            return max_tokens

        try:
            script = """
            local key = KEYS[1]
            local max_tokens = tonumber(ARGV[1])
            local refill_rate = tonumber(ARGV[2])
            local window_seconds = tonumber(ARGV[3])
            local now = tonumber(ARGV[4])

            local state = redis.call('HGETALL', key)
            local tokens = max_tokens  -- Start full for new buckets
            local last_refill = now

            if #state > 0 then
                tokens = tonumber(state[2]) or max_tokens
                last_refill = tonumber(state[4]) or now
            end

            local time_passed = math.max(0, now - last_refill)
            local tokens_to_add = math.floor(time_passed * refill_rate / window_seconds)
            tokens = math.min(max_tokens, tokens + tokens_to_add)

            return tokens
            """

            now = datetime.now(UTC).timestamp()
            result = await self.redis_client.eval(
                script,
                1,
                key,
                max_tokens,
                refill_rate,
                window_seconds,
                now,
            )

            return int(result)

        except Exception as e:
            logger.error(f"Failed to get remaining tokens for key {key}: {e}")
            return max_tokens

    async def reset(self, key: str):
        """Reset rate limit for a key (admin operation).

        Args:
            key: Rate limit key to reset
        """
        if not self._initialized or self.redis_client is None:
            return

        try:
            await self.redis_client.delete(key)
            logger.info(f"Rate limit reset for key: {key}")
        except Exception as e:
            logger.error(f"Failed to reset rate limit for key {key}: {e}")


# Global rate limiter instance
_limiter: RateLimiter | None = None


async def get_rate_limiter() -> RateLimiter:
    """Get or initialize global rate limiter.

    Returns:
        RateLimiter: Initialized rate limiter instance
    """
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
        await _limiter.initialize()
    return _limiter
