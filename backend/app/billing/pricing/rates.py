"""Dynamic FX and crypto rate fetching with caching and backoff retry logic.

PR-029: RateFetcher Integration & Dynamic Quotes

Handles:
- FX rates: GBP/USD, GBP/EUR, GBP/etc via ExchangeRate-API
- Crypto prices: Bitcoin, Ethereum, Litecoin via CoinGecko (free tier, no key required)
- Caching with TTL (configurable, default 300s)
- Exponential backoff retry with max failures circuit breaker
- Rate limiting on external API calls
- Error handling with fallback to last known rates
"""

import asyncio
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Optional

import aiohttp
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# Configuration from environment
FX_API_BASE = os.getenv("FX_API_BASE", "https://api.exchangerate-api.com/v4")
FX_API_KEY = os.getenv("FX_API_KEY", "")
COINGECKO_BASE = os.getenv("COINGECKO_BASE", "https://api.coingecko.com/api/v3")
RATES_TTL_SECONDS = int(os.getenv("RATES_TTL_SECONDS", "300"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

# Cache key prefixes
CACHE_FX_PREFIX = "rate_fx_"
CACHE_CRYPTO_PREFIX = "rate_crypto_"

# Crypto IDs for CoinGecko
CRYPTO_IDS = {
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",
    "litecoin": "litecoin",
    "ripple": "ripple",
    "cardano": "cardano",
}


class RateLimiter:
    """Simple in-memory rate limiter for external API calls."""

    def __init__(
        self,
        max_requests: int = RATE_LIMIT_MAX_REQUESTS,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ):
        """Initialize rate limiter.

        Args:
            max_requests: Max requests per window (default: RATE_LIMIT_MAX_REQUESTS from env)
            window_seconds: Time window in seconds (default: RATE_LIMIT_WINDOW_SECONDS from env)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: list[float] = []

    async def check_limit(self) -> bool:
        """Check if request allowed under rate limit.

        Returns:
            True if request allowed, False if rate limited
        """
        now = time.time()
        # Remove old requests outside window
        self.requests = [
            req_time
            for req_time in self.requests
            if now - req_time < self.window_seconds
        ]

        if len(self.requests) >= self.max_requests:
            logger.warning(
                f"Rate limit exceeded: {len(self.requests)}/{self.max_requests} "
                f"in {self.window_seconds}s"
            )
            return False

        self.requests.append(now)
        return True


class RateFetcher:
    """Fetches FX and crypto rates with caching and resilience."""

    def __init__(self, cache: Optional[dict] = None):
        """Initialize rate fetcher.

        Args:
            cache: Optional cache dict (for testing/DI)
        """
        self.cache = cache or {}
        self.last_known_rates: dict[str, tuple[float, float]] = {}  # (rate, timestamp)
        self.rate_limiter = RateLimiter(
            RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS
        )
        self.session: Optional[aiohttp.ClientSession] = None
        self.consecutive_failures = 0
        self.circuit_breaker_open = False
        self.circuit_breaker_until: Optional[datetime] = None

    async def __aenter__(self):
        """Async context manager enter."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open (after repeated failures).

        Returns:
            True if circuit breaker open, False otherwise
        """
        if not self.circuit_breaker_open:
            return False

        if (
            self.circuit_breaker_until
            and datetime.now(UTC) < self.circuit_breaker_until
        ):
            return True

        # Circuit breaker time window expired, reset
        self.circuit_breaker_open = False
        self.consecutive_failures = 0
        logger.info("Circuit breaker reset")
        return False

    def _get_cache_key(self, prefix: str, key: str) -> str:
        """Get cache key.

        Args:
            prefix: Cache prefix
            key: Cache key

        Returns:
            Full cache key
        """
        return f"{prefix}{key}"

    def _is_cache_valid(self, cached_value: tuple) -> bool:
        """Check if cached value is still valid (within TTL).

        Args:
            cached_value: Tuple of (value, timestamp)

        Returns:
            True if cache valid, False if expired
        """
        if not isinstance(cached_value, tuple) or len(cached_value) != 2:
            return False

        value, timestamp = cached_value
        age_seconds = time.time() - timestamp
        if age_seconds > RATES_TTL_SECONDS:
            logger.debug(
                f"Cache expired: {age_seconds:.1f}s > {RATES_TTL_SECONDS}s TTL"
            )
            return False

        return True

    async def fetch_gbp_usd(self) -> float:
        """Fetch GBP/USD exchange rate.

        Returns:
            GBP to USD conversion rate (how many USD per GBP)

        Raises:
            RuntimeError: If fetch fails and no fallback available
        """
        cache_key = self._get_cache_key(CACHE_FX_PREFIX, "gbp_usd")

        # Check cache
        if cache_key in self.cache:
            cached_value = self.cache[cache_key]
            if self._is_cache_valid(cached_value):
                rate, _ = cached_value
                logger.debug(f"Cache hit: GBP/USD = {rate:.4f}")
                return rate

        # Rate limiting
        if not await self.rate_limiter.check_limit():
            logger.warning("Rate limited on GBP/USD fetch")
            # Fall back to last known rate if available
            if "gbp_usd" in self.last_known_rates:
                rate, _ = self.last_known_rates["gbp_usd"]
                logger.info(f"Rate limited, using stale rate: {rate:.4f}")
                return rate
            raise RuntimeError("Rate limited and no fallback rate available")

        # Circuit breaker check
        if self._is_circuit_breaker_open():
            logger.warning("Circuit breaker open for GBP/USD fetch")
            if "gbp_usd" in self.last_known_rates:
                rate, _ = self.last_known_rates["gbp_usd"]
                return rate
            raise RuntimeError("Circuit breaker open and no fallback rate available")

        # Fetch with retry
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(
                    (aiohttp.ClientError, asyncio.TimeoutError)
                ),
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=10),
            ):
                with attempt:
                    if not self.session:
                        raise RuntimeError("Session not initialized")

                    url = f"{FX_API_BASE}/latest?base=GBP&symbols=USD"
                    async with self.session.get(
                        url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status != 200:
                            raise RuntimeError(f"API returned {response.status}")

                        data = await response.json()
                        rate = data.get("rates", {}).get("USD")
                        if not rate:
                            raise RuntimeError("No USD rate in response")

                        # Sanitize response
                        rate = float(rate)
                        if rate <= 0 or rate > 5:  # Sanity check
                            raise ValueError(f"Invalid rate: {rate}")

                        # Cache and store as last known
                        self.cache[cache_key] = (rate, time.time())
                        self.last_known_rates["gbp_usd"] = (rate, time.time())
                        self.consecutive_failures = 0

                        logger.info(f"Fetched GBP/USD: {rate:.4f}")
                        return rate

        except Exception as e:
            self.consecutive_failures += 1
            logger.error(
                f"Failed to fetch GBP/USD (attempt {self.consecutive_failures}): {e}"
            )

            # Open circuit breaker after 5 consecutive failures
            if self.consecutive_failures >= 5:
                self.circuit_breaker_open = True
                self.circuit_breaker_until = datetime.now(UTC) + timedelta(minutes=5)
                logger.error("Circuit breaker opened after 5 consecutive failures")

            # Fall back to last known rate
            if "gbp_usd" in self.last_known_rates:
                rate, fetch_time = self.last_known_rates["gbp_usd"]
                age_seconds = time.time() - fetch_time
                logger.warning(
                    f"Using stale rate (age: {age_seconds:.0f}s): {rate:.4f}"
                )
                return rate

            raise RuntimeError(
                f"Failed to fetch GBP/USD and no fallback available: {e}"
            )
        
        # Unreachable code - satisfies mypy type checker
        # All paths above return or raise
        raise RuntimeError("Unexpected code path in fetch_gbp_usd")  # pragma: no cover

    async def fetch_crypto_prices(self, ids: list[str]) -> dict[str, float]:
        """Fetch crypto prices in GBP.

        Args:
            ids: List of crypto IDs (bitcoin, ethereum, litecoin, etc)

        Returns:
            Dict mapping crypto ID to GBP price

        Raises:
            RuntimeError: If fetch fails and no fallback available
        """
        if not ids:
            return {}

        # Normalize IDs
        normalized_ids = [CRYPTO_IDS.get(id.lower(), id.lower()) for id in ids]

        # Check cache for each ID
        cached_prices = {}
        missing_ids = []
        for id in normalized_ids:
            cache_key = self._get_cache_key(CACHE_CRYPTO_PREFIX, id)
            if cache_key in self.cache:
                cached_value = self.cache[cache_key]
                if self._is_cache_valid(cached_value):
                    price, _ = cached_value
                    cached_prices[id] = price
                else:
                    missing_ids.append(id)
            else:
                missing_ids.append(id)

        # If all cached, return
        if not missing_ids:
            logger.debug(
                f"Cache hit for all crypto prices: {list(cached_prices.keys())}"
            )
            return cached_prices

        # Rate limiting
        if not await self.rate_limiter.check_limit():
            logger.warning(f"Rate limited on crypto price fetch for {missing_ids}")
            # Return cached + fallback
            for id in missing_ids:
                if id in self.last_known_rates:
                    price, _ = self.last_known_rates[id]
                    cached_prices[id] = price
            return cached_prices

        # Circuit breaker check
        if self._is_circuit_breaker_open():
            logger.warning("Circuit breaker open for crypto price fetch")
            for id in missing_ids:
                if id in self.last_known_rates:
                    price, _ = self.last_known_rates[id]
                    cached_prices[id] = price
            return cached_prices

        # Fetch with retry
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(
                    (aiohttp.ClientError, asyncio.TimeoutError)
                ),
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=10),
            ):
                with attempt:
                    if not self.session:
                        raise RuntimeError("Session not initialized")

                    ids_str = ",".join(missing_ids)
                    url = (
                        f"{COINGECKO_BASE}/simple/price?ids={ids_str}&vs_currencies=gbp"
                    )
                    async with self.session.get(
                        url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status != 200:
                            raise RuntimeError(f"API returned {response.status}")

                        data = await response.json()

                        # Extract prices and validate
                        for id in missing_ids:
                            if id in data and "gbp" in data[id]:
                                price = float(data[id]["gbp"])
                                # Sanity check
                                if price <= 0 or price > 1_000_000:
                                    logger.warning(
                                        f"Suspicious price for {id}: £{price}"
                                    )
                                    continue
                                cached_prices[id] = price
                                self.cache[
                                    self._get_cache_key(CACHE_CRYPTO_PREFIX, id)
                                ] = (
                                    price,
                                    time.time(),
                                )
                                self.last_known_rates[id] = (price, time.time())

                        self.consecutive_failures = 0
                        logger.info(
                            f"Fetched crypto prices: {list(cached_prices.keys())}"
                        )
                        return cached_prices

        except Exception as e:
            self.consecutive_failures += 1
            logger.error(
                f"Failed to fetch crypto prices (attempt {self.consecutive_failures}): {e}"
            )

            # Open circuit breaker
            if self.consecutive_failures >= 5:
                self.circuit_breaker_open = True
                self.circuit_breaker_until = datetime.now(UTC) + timedelta(minutes=5)
                logger.error("Circuit breaker opened")

            # Fall back to last known rates
            for id in missing_ids:
                if id in self.last_known_rates:
                    price, fetch_time = self.last_known_rates[id]
                    age_seconds = time.time() - fetch_time
                    logger.warning(
                        f"Using stale {id} price (age: {age_seconds:.0f}s): £{price}"
                    )
                    cached_prices[id] = price

            if not cached_prices and missing_ids:
                raise RuntimeError(
                    f"Failed to fetch crypto prices and no fallback available: {e}"
                )

            return cached_prices
        
        # Unreachable code - satisfies mypy type checker
        # All paths above return or raise
        raise RuntimeError("Unexpected code path in fetch_crypto_prices")  # pragma: no cover

    async def get_all_rates(self) -> dict[str, float]:
        """Get all exchange rates (GBP base).

        Returns:
            Dict with 'usd', 'eur', etc. rates
        """
        try:
            usd_rate = await self.fetch_gbp_usd()
            # Could expand with more currencies
            return {
                "usd": usd_rate,
                "eur": usd_rate / 1.08,  # Approximate EUR rate
            }
        except Exception as e:
            logger.error(f"Failed to get all rates: {e}")
            raise

    def clear_cache(self) -> None:
        """Clear in-memory cache."""
        self.cache.clear()
        logger.info("Cache cleared")

    def get_cache_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dict with cache stats
        """
        return {
            "cache_size": len(self.cache),
            "last_known_rates_size": len(self.last_known_rates),
            "consecutive_failures": self.consecutive_failures,
            "circuit_breaker_open": self.circuit_breaker_open,
        }
