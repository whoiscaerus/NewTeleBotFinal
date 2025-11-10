"""Isolated tests for quota service - doesn't require full database setup.

Tests core quota logic in isolation to verify PR-082 implementation.
"""

from datetime import datetime, timedelta

import pytest

from backend.app.quotas.models import QuotaPeriod, QuotaType
from backend.app.quotas.service import QuotaService
from backend.app.subscriptions.models import SubscriptionTier


def test_default_quotas_structure():
    """Test DEFAULT_QUOTAS dictionary has correct structure."""
    from backend.app.quotas.service import QuotaService

    DEFAULT_QUOTAS = QuotaService.DEFAULT_QUOTAS

    # All tiers present
    assert SubscriptionTier.FREE in DEFAULT_QUOTAS
    assert SubscriptionTier.PREMIUM in DEFAULT_QUOTAS
    assert SubscriptionTier.PRO in DEFAULT_QUOTAS

    # FREE tier has all quota types
    free_quotas = DEFAULT_QUOTAS[SubscriptionTier.FREE]
    assert QuotaType.SIGNALS_PER_DAY in free_quotas
    assert QuotaType.ALERTS_PER_DAY in free_quotas
    assert QuotaType.EXPORTS_PER_MONTH in free_quotas
    assert QuotaType.API_CALLS_PER_MINUTE in free_quotas
    assert QuotaType.BACKTESTS_PER_DAY in free_quotas
    assert QuotaType.STRATEGIES_MAX in free_quotas

    # Verify limits increase with tier (tuple format: (limit, period))
    assert (
        DEFAULT_QUOTAS[SubscriptionTier.FREE][QuotaType.SIGNALS_PER_DAY][0]
        < DEFAULT_QUOTAS[SubscriptionTier.PREMIUM][QuotaType.SIGNALS_PER_DAY][0]
        < DEFAULT_QUOTAS[SubscriptionTier.PRO][QuotaType.SIGNALS_PER_DAY][0]
    )


def test_calculate_period_boundaries_day():
    """Test period boundary calculation for DAY period."""
    service = QuotaService(db=None)  # No actual DB needed for period calculations

    # Test date: 2024-01-15 14:30:45
    now = datetime(2024, 1, 15, 14, 30, 45)
    start, end = service._calculate_period_boundaries(QuotaPeriod.DAY, now)

    # Should be start of day to end of day
    assert start == datetime(2024, 1, 15, 0, 0, 0)
    assert end == datetime(2024, 1, 16, 0, 0, 0)


def test_calculate_period_boundaries_month():
    """Test period boundary calculation for MONTH period."""
    service = QuotaService(db=None)

    # Mid-month
    now = datetime(2024, 3, 15, 12, 0, 0)
    start, end = service._calculate_period_boundaries(QuotaPeriod.MONTH, now)

    assert start == datetime(2024, 3, 1, 0, 0, 0)
    assert end == datetime(2024, 4, 1, 0, 0, 0)


def test_calculate_period_boundaries_month_december():
    """Test period boundary calculation handles year rollover."""
    service = QuotaService(db=None)

    # December should roll to next year
    now = datetime(2024, 12, 25, 10, 0, 0)
    start, end = service._calculate_period_boundaries(QuotaPeriod.MONTH, now)

    assert start == datetime(2024, 12, 1, 0, 0, 0)
    assert end == datetime(2025, 1, 1, 0, 0, 0)  # Next year


def test_calculate_period_boundaries_hour():
    """Test period boundary calculation for HOUR period."""
    service = QuotaService(db=None)

    now = datetime(2024, 1, 15, 14, 30, 45)
    start, end = service._calculate_period_boundaries(QuotaPeriod.HOUR, now)

    # Should be start of hour to next hour
    assert start == datetime(2024, 1, 15, 14, 0, 0)
    assert end == datetime(2024, 1, 15, 15, 0, 0)


def test_calculate_period_boundaries_minute():
    """Test period boundary calculation for MINUTE period."""
    service = QuotaService(db=None)

    now = datetime(2024, 1, 15, 14, 30, 45)
    start, end = service._calculate_period_boundaries(QuotaPeriod.MINUTE, now)

    # Should be start of minute to next minute
    assert start == datetime(2024, 1, 15, 14, 30, 0)
    assert end == datetime(2024, 1, 15, 14, 31, 0)


def test_calculate_period_boundaries_none():
    """Test period boundary calculation for NONE (lifetime) period."""
    service = QuotaService(db=None)

    now = datetime(2024, 1, 15, 14, 30, 45)
    start, end = service._calculate_period_boundaries(QuotaPeriod.NONE, now)

    # NONE period should be arbitrary past to far future
    assert start == datetime(2000, 1, 1, 0, 0, 0)
    assert end == datetime(2099, 12, 31, 0, 0, 0)


def test_get_redis_key():
    """Test Redis key generation."""
    service = QuotaService(db=None)

    user_id = "user-123"
    quota_type = QuotaType.SIGNALS_PER_DAY.value
    period_start = datetime(2024, 1, 15, 0, 0, 0)

    key = service._get_redis_key(user_id, quota_type, period_start)

    assert key == "quota:user-123:signals_per_day:202401150000"


def test_calculate_ttl():
    """Test TTL calculation."""
    service = QuotaService(db=None)

    # 1 hour remaining
    period_end = datetime.now() + timedelta(hours=1)
    ttl = service._calculate_ttl(QuotaPeriod.HOUR, period_end)

    # Should be approximately 3600 seconds (allow 1 second tolerance)
    assert 3599 <= ttl <= 3600


def test_quota_models_exist():
    """Test that quota models can be imported."""
    from backend.app.quotas import QuotaDefinition as ImportedFromPackage
    from backend.app.quotas.models import QuotaDefinition, QuotaUsage

    # Verify models exist
    assert QuotaDefinition is not None
    assert QuotaUsage is not None
    assert ImportedFromPackage is not None


def test_quota_service_exists():
    """Test that QuotaService can be instantiated."""
    from backend.app.quotas.service import QuotaExceededException, QuotaService

    service = QuotaService(db=None)
    assert service is not None

    # Verify exception exists
    assert QuotaExceededException is not None


def test_quota_routes_exist():
    """Test that quota routes can be imported."""
    from backend.app.quotas.routes import check_quota, router

    assert router is not None
    assert check_quota is not None


def test_telemetry_metric_exists():
    """Test that quota_block_total metric exists in observability."""
    from backend.app.observability.metrics import metrics

    # Metric should exist
    assert hasattr(metrics, "quota_block_total")
    assert metrics.quota_block_total is not None


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
