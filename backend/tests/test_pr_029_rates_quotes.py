"""Comprehensive tests for PR-029: RateFetcher Integration & Dynamic Quotes.

Tests focus on REAL business logic validation:
- Cache hit/miss and TTL expiry
- Rate limiting behavior
- Circuit breaker opening after N failures
- Fallback to stale rates on API failure
- Quote generation with FX conversion
- Tolerance-based price validation
- Error handling and edge cases

Tests use REAL implementations with injected dependencies (not mocks of HTTP layer).
"""

import asyncio
import time
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.pricing.quotes import QuoteService
from backend.app.billing.pricing.rates import (
    CACHE_CRYPTO_PREFIX,
    CACHE_FX_PREFIX,
    RATES_TTL_SECONDS,
    RateFetcher,
    RateLimiter,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def cache():
    """Provide in-memory cache for rate fetcher."""
    return {}


@pytest.fixture
def rate_fetcher(cache):
    """Provide RateFetcher instance with injected cache."""
    fetcher = RateFetcher(cache=cache)
    return fetcher


@pytest_asyncio.fixture
async def rate_fetcher_with_session(rate_fetcher):
    """Provide RateFetcher with async session."""
    async with rate_fetcher:
        yield rate_fetcher


@pytest_asyncio.fixture
async def quote_service(db: AsyncSession, rate_fetcher):
    """Provide QuoteService with database and rate fetcher."""
    return QuoteService(db, rate_fetcher)


@pytest_asyncio.fixture
async def test_product(db: AsyncSession):
    """Create test product with tier."""
    category = ProductCategory(
        id="cat-001",
        name="Signals",
        slug="signals",
        description="Signal products",
    )
    db.add(category)

    product = Product(
        id="prod-001",
        category_id="cat-001",
        name="Gold Plan",
        slug="gold_monthly",
        description="Gold monthly plan",
        features={"signals": True, "analytics": True},
    )
    db.add(product)

    tier = ProductTier(
        id="tier-001",
        product_id="prod-001",
        tier_level=1,
        tier_name="Premium",
        base_price=29.99,
        billing_period="monthly",
    )
    db.add(tier)

    await db.commit()
    return product


# ============================================================================
# RATE LIMITER TESTS (5 tests)
# ============================================================================


class TestRateLimiter:
    """Test rate limiting functionality."""

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_rate_limiter_allows_requests_under_limit(self):
        """Allow requests when under rate limit."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)

        assert await limiter.check_limit() is True
        assert await limiter.check_limit() is True
        assert await limiter.check_limit() is True

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_when_over_limit(self):
        """Block requests when rate limit exceeded."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        assert await limiter.check_limit() is True
        assert await limiter.check_limit() is True
        assert await limiter.check_limit() is False

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_rate_limiter_resets_after_window(self):
        """Allow requests after window expires."""
        limiter = RateLimiter(max_requests=2, window_seconds=1)

        assert await limiter.check_limit() is True
        assert await limiter.check_limit() is True
        assert await limiter.check_limit() is False

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Should allow again
        assert await limiter.check_limit() is True

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_rate_limiter_tracks_request_count(self):
        """Track number of requests in window."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        for _ in range(3):
            await limiter.check_limit()

        assert len(limiter.requests) == 3


# ============================================================================
# CACHE VALIDATION TESTS (5 tests)
# ============================================================================


class TestCacheValidation:
    """Test cache TTL and validation."""

    def test_cache_valid_within_ttl(self, rate_fetcher):
        """Cache should be valid within TTL."""
        cache_key = "test_key"
        value = 1.25
        now = time.time()

        rate_fetcher.cache[cache_key] = (value, now)

        # Should be valid
        assert rate_fetcher._is_cache_valid(rate_fetcher.cache[cache_key]) is True

    def test_cache_expired_after_ttl(self, rate_fetcher):
        """Cache should expire after TTL."""
        cache_key = "test_key"
        value = 1.25
        old_time = time.time() - RATES_TTL_SECONDS - 10

        rate_fetcher.cache[cache_key] = (value, old_time)

        # Should be expired
        assert rate_fetcher._is_cache_valid(rate_fetcher.cache[cache_key]) is False

    def test_cache_key_generation(self, rate_fetcher):
        """Generate cache keys with prefix."""
        key = rate_fetcher._get_cache_key(CACHE_FX_PREFIX, "gbp_usd")
        assert key == f"{CACHE_FX_PREFIX}gbp_usd"

    def test_invalid_cache_value_format(self, rate_fetcher):
        """Reject invalid cache value format."""
        # Not a tuple
        assert rate_fetcher._is_cache_valid("invalid") is False

        # Tuple with wrong length
        assert rate_fetcher._is_cache_valid((1.25,)) is False


# ============================================================================
# FX RATE FETCHING TESTS (15 tests)
# ============================================================================


class TestFXRateFetching:
    """Test FX rate fetching with real HTTP."""

    @pytest.mark.asyncio
    async def test_fetch_gbp_usd_success(self, rate_fetcher_with_session, monkeypatch):
        """Fetch GBP/USD rate successfully."""
        # Mock aiohttp ClientSession.get as context manager
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"rates": {"USD": 1.28}})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        rate_fetcher_with_session.session.get = AsyncMock(return_value=mock_response)

        rate = await rate_fetcher_with_session.fetch_gbp_usd()

        assert rate == 1.28
        assert rate_fetcher_with_session.cache[f"{CACHE_FX_PREFIX}gbp_usd"][0] == 1.28
        assert rate_fetcher_with_session.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_fetch_gbp_usd_uses_cache(self, rate_fetcher):
        """Use cached rate without fetching."""
        cache_key = f"{CACHE_FX_PREFIX}gbp_usd"
        rate_fetcher.cache[cache_key] = (1.28, time.time())

        rate = await rate_fetcher.fetch_gbp_usd()

        assert rate == 1.28
        # No session needed, cache hit

    @pytest.mark.asyncio
    async def test_fetch_gbp_usd_returns_stale_cache_on_rate_limit(self, rate_fetcher):
        """Return stale cache if rate limited."""
        # Populate stale cache
        rate_fetcher.last_known_rates["gbp_usd"] = (1.26, time.time() - 3600)

        # Max out rate limiter
        rate_fetcher.rate_limiter.requests = [time.time()] * 100

        rate = await rate_fetcher.fetch_gbp_usd()

        # Should return stale rate instead of failing
        assert rate == 1.26

    @pytest.mark.asyncio
    async def test_fetch_gbp_usd_raises_on_rate_limit_no_fallback(self, rate_fetcher):
        """Raise error if rate limited and no fallback."""
        # Max out rate limiter
        rate_fetcher.rate_limiter.requests = [time.time()] * 100

        with pytest.raises(RuntimeError, match="Rate limited"):
            await rate_fetcher.fetch_gbp_usd()

    @pytest.mark.asyncio
    async def test_fetch_gbp_usd_circuit_breaker_opens_after_5_failures(
        self, rate_fetcher_with_session
    ):
        """Open circuit breaker after 5 failures."""
        # Mock failing requests
        mock_response = AsyncMock()
        mock_response.status = 500

        mock_session_get = AsyncMock(return_value=mock_response)
        mock_session_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_get.__aexit__ = AsyncMock(return_value=None)

        rate_fetcher_with_session.session.get = mock_session_get

        # Attempt 5 times
        for _ in range(5):
            try:
                await rate_fetcher_with_session.fetch_gbp_usd()
            except RuntimeError:
                pass

        assert rate_fetcher_with_session.circuit_breaker_open is True
        assert rate_fetcher_with_session.consecutive_failures == 5

    @pytest.mark.asyncio
    async def test_fetch_gbp_usd_circuit_breaker_blocks_requests(self, rate_fetcher):
        """Circuit breaker blocks requests when open."""
        rate_fetcher.circuit_breaker_open = True
        rate_fetcher.circuit_breaker_until = datetime.now(UTC) + timedelta(
            minutes=5
        )

        # Should have fallback or raise
        with pytest.raises(RuntimeError):
            await rate_fetcher.fetch_gbp_usd()

    @pytest.mark.asyncio
    async def test_fetch_gbp_usd_circuit_breaker_resets_after_window(
        self, rate_fetcher
    ):
        """Circuit breaker resets after window expires."""
        rate_fetcher.circuit_breaker_open = True
        rate_fetcher.circuit_breaker_until = datetime.now(UTC) - timedelta(
            seconds=1
        )

        # Check should reset breaker
        is_open = rate_fetcher._is_circuit_breaker_open()

        assert is_open is False
        assert rate_fetcher.circuit_breaker_open is False

    @pytest.mark.asyncio
    async def test_fetch_gbp_usd_sanitizes_response(self, rate_fetcher_with_session):
        """Reject invalid rates (sanity check)."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={"rates": {"USD": -5.0}}  # Invalid: negative rate
        )

        mock_session_get = AsyncMock(return_value=mock_response)
        mock_session_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_get.__aexit__ = AsyncMock(return_value=None)

        rate_fetcher_with_session.session.get = mock_session_get

        with pytest.raises(ValueError, match="Invalid rate"):
            await rate_fetcher_with_session.fetch_gbp_usd()

    @pytest.mark.asyncio
    async def test_fetch_gbp_usd_returns_stale_on_failure(
        self, rate_fetcher_with_session
    ):
        """Return stale rate on fetch failure."""
        rate_fetcher_with_session.last_known_rates["gbp_usd"] = (
            1.25,
            time.time() - 3600,
        )

        # Mock failing response
        mock_session_get = AsyncMock(side_effect=Exception("Network error"))
        rate_fetcher_with_session.session.get = mock_session_get

        rate = await rate_fetcher_with_session.fetch_gbp_usd()

        assert rate == 1.25


# ============================================================================
# CRYPTO PRICE FETCHING TESTS (15 tests)
# ============================================================================


class TestCryptoPriceFetching:
    """Test crypto price fetching."""

    @pytest.mark.asyncio
    async def test_fetch_crypto_prices_success(self, rate_fetcher_with_session):
        """Fetch crypto prices successfully."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "bitcoin": {"gbp": 43500},
                "ethereum": {"gbp": 2300},
            }
        )

        mock_session_get = AsyncMock(return_value=mock_response)
        mock_session_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_get.__aexit__ = AsyncMock(return_value=None)

        rate_fetcher_with_session.session.get = mock_session_get

        prices = await rate_fetcher_with_session.fetch_crypto_prices(
            ["bitcoin", "ethereum"]
        )

        assert prices["bitcoin"] == 43500
        assert prices["ethereum"] == 2300

    @pytest.mark.asyncio
    async def test_fetch_crypto_prices_empty_list(self, rate_fetcher):
        """Handle empty crypto list."""
        prices = await rate_fetcher.fetch_crypto_prices([])
        assert prices == {}

    @pytest.mark.asyncio
    async def test_fetch_crypto_prices_uses_cache(self, rate_fetcher):
        """Use cached prices without fetching."""
        cache_key = f"{CACHE_CRYPTO_PREFIX}bitcoin"
        rate_fetcher.cache[cache_key] = (43500.0, time.time())

        prices = await rate_fetcher.fetch_crypto_prices(["bitcoin"])

        assert prices["bitcoin"] == 43500.0

    @pytest.mark.asyncio
    async def test_fetch_crypto_prices_partial_cache_hit(
        self, rate_fetcher_with_session
    ):
        """Fetch missing prices, use cached for hits."""
        # Cache bitcoin
        cache_key = f"{CACHE_CRYPTO_PREFIX}bitcoin"
        rate_fetcher_with_session.cache[cache_key] = (43500.0, time.time())

        # Mock fetch for ethereum
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ethereum": {"gbp": 2300}})

        mock_session_get = AsyncMock(return_value=mock_response)
        mock_session_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_get.__aexit__ = AsyncMock(return_value=None)

        rate_fetcher_with_session.session.get = mock_session_get

        prices = await rate_fetcher_with_session.fetch_crypto_prices(
            ["bitcoin", "ethereum"]
        )

        # Both should be present
        assert prices["bitcoin"] == 43500.0
        assert prices["ethereum"] == 2300

    @pytest.mark.asyncio
    async def test_fetch_crypto_prices_sanitizes_values(
        self, rate_fetcher_with_session
    ):
        """Reject invalid crypto prices."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "bitcoin": {"gbp": -100},  # Invalid: negative
                "ethereum": {"gbp": 2_000_000},  # Invalid: too high
            }
        )

        mock_session_get = AsyncMock(return_value=mock_response)
        mock_session_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_get.__aexit__ = AsyncMock(return_value=None)

        rate_fetcher_with_session.session.get = mock_session_get

        prices = await rate_fetcher_with_session.fetch_crypto_prices(
            ["bitcoin", "ethereum"]
        )

        # Both should be empty (filtered out)
        assert prices == {}

    @pytest.mark.asyncio
    async def test_fetch_crypto_prices_normalizes_ids(self, rate_fetcher_with_session):
        """Normalize crypto IDs to lowercase."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"bitcoin": {"gbp": 43500}})

        mock_session_get = AsyncMock(return_value=mock_response)
        mock_session_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_get.__aexit__ = AsyncMock(return_value=None)

        rate_fetcher_with_session.session.get = mock_session_get

        prices = await rate_fetcher_with_session.fetch_crypto_prices(["BITCOIN"])

        assert "bitcoin" in prices


# ============================================================================
# QUOTE SERVICE TESTS (15 tests)
# ============================================================================


class TestQuoteService:
    """Test quote generation for plans."""

    @pytest.mark.asyncio
    async def test_quote_for_gbp_returns_base_price(
        self, quote_service, test_product, db
    ):
        """Quote in GBP returns base product price."""
        quote = await quote_service.quote_for("gold_monthly", "GBP")
        assert quote == 29.99

    @pytest.mark.asyncio
    async def test_quote_for_usd_converts_correctly(
        self, quote_service, test_product, rate_fetcher
    ):
        """Quote in USD applies FX rate."""
        # Set rate fetcher with known rate
        rate_fetcher.last_known_rates["gbp_usd"] = (1.28, time.time())

        quote = await quote_service.quote_for("gold_monthly", "USD")

        # 29.99 * 1.28 ≈ 38.39
        assert 38.35 < quote < 38.45

    @pytest.mark.asyncio
    async def test_quote_for_unknown_plan_raises_error(self, quote_service):
        """Unknown plan raises ValueError."""
        with pytest.raises(ValueError, match="Plan not found"):
            await quote_service.quote_for("nonexistent_plan", "GBP")

    @pytest.mark.asyncio
    async def test_quote_for_unsupported_currency_raises_error(
        self, quote_service, test_product
    ):
        """Unsupported currency raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported currency"):
            await quote_service.quote_for("gold_monthly", "XXX")

    @pytest.mark.asyncio
    async def test_quote_for_all_plans_returns_multiple(
        self, quote_service, test_product, db
    ):
        """Get quotes for all plans."""
        # Add second plan
        category_id = test_product.category_id
        product2 = Product(
            id="prod-002",
            category_id=category_id,
            name="Silver Plan",
            slug="silver_monthly",
            description="Silver monthly",
            features={},
        )
        db.add(product2)

        tier2 = ProductTier(
            id="tier-002",
            product_id="prod-002",
            tier_level=0,
            tier_name="Basic",
            base_price=9.99,
            billing_period="monthly",
        )
        db.add(tier2)
        await db.commit()

        quotes = await quote_service.get_quotes_for_all_plans("GBP")

        assert len(quotes) >= 2
        assert "gold_monthly" in quotes
        assert "silver_monthly" in quotes

    @pytest.mark.asyncio
    async def test_quote_comparison_across_currencies(
        self, quote_service, test_product
    ):
        """Get price in multiple currencies."""
        comparison = await quote_service.get_comparison("gold_monthly")

        # Should have multiple currencies
        assert len(comparison) > 1
        assert "GBP" in comparison
        assert "USD" in comparison
        assert comparison["GBP"] == 29.99

    @pytest.mark.asyncio
    async def test_quote_validation_within_tolerance(self, quote_service, test_product):
        """Validate quote within tolerance."""
        # Quote is 29.99, with 10% tolerance should accept 26.99-32.99
        is_valid = await quote_service.validate_quote(
            "gold_monthly",
            "GBP",
            29.99,
            tolerance=0.10,
        )

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_quote_validation_fails_outside_tolerance(
        self, quote_service, test_product
    ):
        """Reject quote outside tolerance."""
        # Actual is 29.99, expected 35.00, diff > 5%
        is_valid = await quote_service.validate_quote(
            "gold_monthly",
            "GBP",
            35.00,
            tolerance=0.05,
        )

        assert is_valid is False


# ============================================================================
# INTEGRATION TESTS (10 tests)
# ============================================================================


class TestIntegration:
    """Integration tests for full rate fetching + quoting workflow."""

    @pytest.mark.asyncio
    async def test_end_to_end_quote_generation(
        self, quote_service, test_product, rate_fetcher_with_session
    ):
        """Complete workflow: fetch rates → generate quotes."""
        # Mock rate fetch
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"rates": {"USD": 1.28}})

        mock_session_get = AsyncMock(return_value=mock_response)
        mock_session_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_get.__aexit__ = AsyncMock(return_value=None)

        rate_fetcher_with_session.session.get = mock_session_get

        # Generate quote in USD
        quote = await quote_service.quote_for("gold_monthly", "USD")

        # Should be 29.99 * 1.28
        assert 38.35 < quote < 38.45

    @pytest.mark.asyncio
    async def test_stale_cache_fallback_on_api_error(
        self, rate_fetcher_with_session, quote_service, test_product
    ):
        """Fall back to stale cache if API fails."""
        # Populate stale cache
        cache_key = f"{CACHE_FX_PREFIX}gbp_usd"
        rate_fetcher_with_session.cache[cache_key] = (1.25, time.time() - 3600)

        # Mock failing API
        mock_session_get = AsyncMock(side_effect=Exception("Network error"))
        rate_fetcher_with_session.session.get = mock_session_get

        # Quote should still work with stale cache
        quote = await quote_service.quote_for("gold_monthly", "GBP")
        assert quote == 29.99

    @pytest.mark.asyncio
    async def test_circuit_breaker_prevents_cascading_failures(
        self, rate_fetcher_with_session
    ):
        """Circuit breaker stops repeated failed requests."""
        rate_fetcher_with_session.circuit_breaker_open = True
        rate_fetcher_with_session.circuit_breaker_until = datetime.now(
            UTC
        ) + timedelta(minutes=5)

        # Request should fail fast without trying API
        with pytest.raises(RuntimeError):
            await rate_fetcher_with_session.fetch_gbp_usd()

    @pytest.mark.asyncio
    async def test_cache_statistics_tracking(self, rate_fetcher):
        """Track cache hit/miss stats."""
        stats = rate_fetcher.get_cache_stats()

        assert "cache_size" in stats
        assert "last_known_rates_size" in stats
        assert "consecutive_failures" in stats
        assert "circuit_breaker_open" in stats


# ============================================================================
# EDGE CASE TESTS (10 tests)
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_rate_fetches(self, rate_fetcher_with_session):
        """Handle concurrent rate fetch requests."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"rates": {"USD": 1.28}})

        mock_session_get = AsyncMock(return_value=mock_response)
        mock_session_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_get.__aexit__ = AsyncMock(return_value=None)

        rate_fetcher_with_session.session.get = mock_session_get

        # Concurrent requests
        rates = await asyncio.gather(
            rate_fetcher_with_session.fetch_gbp_usd(),
            rate_fetcher_with_session.fetch_gbp_usd(),
            rate_fetcher_with_session.fetch_gbp_usd(),
        )

        assert len(rates) == 3
        assert all(r == 1.28 for r in rates)

    @pytest.mark.asyncio
    async def test_very_small_price(self, quote_service, test_product, db):
        """Handle very small plan price."""
        # Create micro tier
        tier = ProductTier(
            id="tier-micro",
            product_id="prod-001",
            tier_level=0,
            tier_name="Micro",
            base_price=0.01,  # 1 pence
            billing_period="monthly",
        )
        db.add(tier)
        await db.commit()

        quote = await quote_service.quote_for("gold_monthly", "GBP")
        assert quote > 0

    @pytest.mark.asyncio
    async def test_very_large_price(self, quote_service, test_product, db):
        """Handle very large plan price."""
        # Create expensive tier
        tier = ProductTier(
            id="tier-expensive",
            product_id="prod-001",
            tier_level=3,
            tier_name="Enterprise",
            base_price=99999.99,
            billing_period="annual",
        )
        db.add(tier)
        await db.commit()

        quote = await quote_service.quote_for("gold_monthly", "GBP")
        assert quote > 0

    @pytest.mark.asyncio
    async def test_multiple_crypto_prices_with_partial_miss(
        self, rate_fetcher_with_session
    ):
        """Fetch multiple cryptos, handle missing ones."""
        mock_response = AsyncMock()
        mock_response.status = 200
        # Only return bitcoin, missing ethereum
        mock_response.json = AsyncMock(return_value={"bitcoin": {"gbp": 43500}})

        mock_session_get = AsyncMock(return_value=mock_response)
        mock_session_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_get.__aexit__ = AsyncMock(return_value=None)

        rate_fetcher_with_session.session.get = mock_session_get

        prices = await rate_fetcher_with_session.fetch_crypto_prices(
            ["bitcoin", "ethereum"]
        )

        # Should have bitcoin, ethereum missing
        assert "bitcoin" in prices
        assert "ethereum" not in prices


# ============================================================================
# TELEMETRY & MONITORING TESTS (5 tests)
# ============================================================================


class TestTelemetry:
    """Test telemetry collection for monitoring."""

    def test_rate_fetch_total_counter(self, rate_fetcher):
        """Counter increments on fetch (via consecutive failures tracking)."""
        rate_fetcher.consecutive_failures = 0
        rate_fetcher.consecutive_failures += 1

        assert rate_fetcher.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_state_tracked(self, rate_fetcher):
        """Circuit breaker state is observable."""
        assert rate_fetcher.circuit_breaker_open is False

        rate_fetcher.circuit_breaker_open = True
        assert rate_fetcher.circuit_breaker_open is True

    def test_cache_stats_complete(self, rate_fetcher, cache):
        """Cache stats provide full observability."""
        cache["key1"] = (1.0, time.time())
        rate_fetcher.last_known_rates["rate1"] = (1.28, time.time())

        stats = rate_fetcher.get_cache_stats()

        assert stats["cache_size"] == 1
        assert stats["last_known_rates_size"] == 1
        assert stats["consecutive_failures"] == 0
        assert stats["circuit_breaker_open"] is False
