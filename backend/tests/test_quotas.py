"""Comprehensive tests for PR-082 quota system.

Tests quota checking, consumption, reset behavior, plan limits, and error handling.
Validates real business logic with fakeredis backend.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.quotas.models import (
    QuotaDefinition,
    QuotaPeriod,
    QuotaType,
    QuotaUsage,
)
from backend.app.quotas.service import QuotaExceededException, QuotaService
from backend.app.subscriptions.models import SubscriptionTier


# Test fixtures
@pytest_asyncio.fixture
async def quota_service(db_session: AsyncSession) -> QuotaService:
    """Create quota service instance."""
    return QuotaService(db_session)


@pytest.fixture
def test_user_id() -> str:
    """Test user ID - unique per test to avoid Redis state leaking."""
    return f"test-user-{uuid4().hex[:8]}"


# ========== Model Tests ==========


@pytest.mark.asyncio
async def test_quota_definition_model(db_session: AsyncSession):
    """Test QuotaDefinition model creation and retrieval."""
    # Create quota definition
    quota = QuotaDefinition(
        id="quota-1",
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        limit=10,
        period=QuotaPeriod.DAY.value,
    )

    db_session.add(quota)
    await db_session.commit()
    await db_session.refresh(quota)

    # Verify fields
    assert quota.id == "quota-1"
    assert quota.tier == "free"
    assert quota.quota_type == "signals_per_day"
    assert quota.limit == 10
    assert quota.period == "day"
    assert quota.created_at is not None
    assert quota.updated_at is not None


@pytest.mark.asyncio
async def test_quota_usage_model(db_session: AsyncSession, test_user_id: str):
    """Test QuotaUsage model creation and retrieval."""
    now = datetime.utcnow()
    period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + timedelta(days=1)

    # Create usage record
    usage = QuotaUsage(
        id="usage-1",
        user_id=test_user_id,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        count=5,
        period_start=period_start,
        period_end=period_end,
    )

    db_session.add(usage)
    await db_session.commit()
    await db_session.refresh(usage)

    # Verify fields
    assert usage.id == "usage-1"
    assert usage.user_id == test_user_id
    assert usage.quota_type == "signals_per_day"
    assert usage.count == 5
    assert usage.period_start == period_start
    assert usage.period_end == period_end


@pytest.mark.asyncio
async def test_quota_definition_unique_constraint(db_session: AsyncSession):
    """Test unique constraint on tier + quota_type."""
    # Create first definition
    quota1 = QuotaDefinition(
        id="quota-1",
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        limit=10,
        period=QuotaPeriod.DAY.value,
    )
    db_session.add(quota1)
    await db_session.commit()

    # Attempt to create duplicate
    quota2 = QuotaDefinition(
        id="quota-2",
        tier=SubscriptionTier.FREE.value,  # Same tier
        quota_type=QuotaType.SIGNALS_PER_DAY.value,  # Same quota_type
        limit=20,
        period=QuotaPeriod.DAY.value,
    )
    db_session.add(quota2)

    # Should raise IntegrityError
    with pytest.raises(Exception):  # SQLAlchemy IntegrityError
        await db_session.commit()


# ========== Service Tests - Basic Functionality ==========


@pytest.mark.asyncio
async def test_ensure_quota_definitions(
    quota_service: QuotaService, db_session: AsyncSession
):
    """Test that default quota definitions are created."""
    # Ensure definitions exist
    await quota_service._ensure_quota_definitions()

    # Verify FREE tier definitions
    from sqlalchemy import select

    stmt = select(QuotaDefinition).where(
        QuotaDefinition.tier == SubscriptionTier.FREE.value
    )
    result = await db_session.execute(stmt)
    free_quotas = result.scalars().all()

    # Should have all quota types defined
    assert len(free_quotas) == len(QuotaType)

    # Verify specific limits
    signals_quota = next(
        (q for q in free_quotas if q.quota_type == QuotaType.SIGNALS_PER_DAY.value),
        None,
    )
    assert signals_quota is not None
    assert signals_quota.limit == 10
    assert signals_quota.period == QuotaPeriod.DAY.value


@pytest.mark.asyncio
async def test_check_and_consume_success(
    quota_service: QuotaService, test_user_id: str
):
    """Test successful quota consumption."""
    # Check and consume 1 signal
    result = await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=1,
    )

    # Verify result
    assert result["allowed"] is True
    assert result["current"] == 1
    assert result["limit"] == 10
    assert result["remaining"] == 9
    assert "reset_at" in result

    # Consume another
    result2 = await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=1,
    )

    assert result2["current"] == 2
    assert result2["remaining"] == 8


@pytest.mark.asyncio
async def test_check_and_consume_multiple_amount(
    quota_service: QuotaService, test_user_id: str
):
    """Test consuming multiple quota units at once."""
    # Consume 5 signals
    result = await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=5,
    )

    assert result["current"] == 5
    assert result["remaining"] == 5


@pytest.mark.asyncio
async def test_quota_exceeded_exception(quota_service: QuotaService, test_user_id: str):
    """Test that QuotaExceededException is raised when limit exceeded."""
    # Consume up to limit (10 for free tier)
    for i in range(10):
        await quota_service.check_and_consume(
            user_id=test_user_id,
            tier=SubscriptionTier.FREE.value,
            quota_type=QuotaType.SIGNALS_PER_DAY.value,
            amount=1,
        )

    # Attempt to exceed limit
    with pytest.raises(QuotaExceededException) as exc_info:
        await quota_service.check_and_consume(
            user_id=test_user_id,
            tier=SubscriptionTier.FREE.value,
            quota_type=QuotaType.SIGNALS_PER_DAY.value,
            amount=1,
        )

    # Verify exception details
    exception = exc_info.value
    assert exception.quota_type == QuotaType.SIGNALS_PER_DAY.value
    assert exception.limit == 10
    assert exception.current == 10
    assert exception.reset_at is not None


@pytest.mark.asyncio
async def test_get_quota_status(quota_service: QuotaService, test_user_id: str):
    """Test getting quota status without consuming."""
    # Consume some quota first
    await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=3,
    )

    # Get status
    status = await quota_service.get_quota_status(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
    )

    # Verify status
    assert status["current"] == 3
    assert status["limit"] == 10
    assert status["remaining"] == 7
    assert "reset_at" in status


@pytest.mark.asyncio
async def test_get_all_quotas(quota_service: QuotaService, test_user_id: str):
    """Test getting status for all quota types."""
    # Get all quotas
    all_quotas = await quota_service.get_all_quotas(
        user_id=test_user_id, tier=SubscriptionTier.FREE.value
    )

    # Verify all quota types present
    assert QuotaType.SIGNALS_PER_DAY.value in all_quotas
    assert QuotaType.ALERTS_PER_DAY.value in all_quotas
    assert QuotaType.EXPORTS_PER_MONTH.value in all_quotas

    # Verify structure
    signals_quota = all_quotas[QuotaType.SIGNALS_PER_DAY.value]
    assert "current" in signals_quota
    assert "limit" in signals_quota
    assert "remaining" in signals_quota
    assert "reset_at" in signals_quota


# ========== Service Tests - Different Tiers ==========


@pytest.mark.asyncio
async def test_premium_tier_higher_limits(
    quota_service: QuotaService, test_user_id: str
):
    """Test that premium tier has higher limits than free tier."""
    # Free tier limit: 10 signals/day
    # Premium tier limit: 100 signals/day

    # Check premium tier status
    status = await quota_service.get_quota_status(
        user_id=test_user_id,
        tier=SubscriptionTier.PREMIUM.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
    )

    assert status["limit"] == 100  # Premium limit


@pytest.mark.asyncio
async def test_pro_tier_highest_limits(quota_service: QuotaService, test_user_id: str):
    """Test that pro tier has highest limits."""
    # Pro tier limit: 1000 signals/day

    # Check pro tier status
    status = await quota_service.get_quota_status(
        user_id=test_user_id,
        tier=SubscriptionTier.PRO.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
    )

    assert status["limit"] == 1000  # Pro limit


@pytest.mark.asyncio
async def test_plan_upgrade_increases_limits(
    quota_service: QuotaService, test_user_id: str
):
    """Test that upgrading plan increases available quota."""
    # Use free tier, consume 8 out of 10
    for i in range(8):
        await quota_service.check_and_consume(
            user_id=test_user_id,
            tier=SubscriptionTier.FREE.value,
            quota_type=QuotaType.SIGNALS_PER_DAY.value,
            amount=1,
        )

    # Free tier: 2 remaining
    free_status = await quota_service.get_quota_status(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
    )
    assert free_status["remaining"] == 2

    # Upgrade to premium (same usage counter, but higher limit)
    premium_status = await quota_service.get_quota_status(
        user_id=test_user_id,
        tier=SubscriptionTier.PREMIUM.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
    )
    assert premium_status["current"] == 8  # Same usage
    assert premium_status["limit"] == 100  # Higher limit
    assert premium_status["remaining"] == 92  # More remaining


# ========== Service Tests - Period Boundaries ==========


@pytest.mark.asyncio
async def test_calculate_period_boundaries_day(quota_service: QuotaService):
    """Test period boundary calculation for daily quota."""
    now = datetime(2025, 11, 9, 14, 30, 0)  # 2:30 PM

    start, end = quota_service._calculate_period_boundaries(QuotaPeriod.DAY.value, now)

    # Should be midnight to midnight
    assert start == datetime(2025, 11, 9, 0, 0, 0)
    assert end == datetime(2025, 11, 10, 0, 0, 0)


@pytest.mark.asyncio
async def test_calculate_period_boundaries_month(quota_service: QuotaService):
    """Test period boundary calculation for monthly quota."""
    now = datetime(2025, 11, 15, 14, 30, 0)  # Mid-November

    start, end = quota_service._calculate_period_boundaries(
        QuotaPeriod.MONTH.value, now
    )

    # Should be first of month to first of next month
    assert start == datetime(2025, 11, 1, 0, 0, 0)
    assert end == datetime(2025, 12, 1, 0, 0, 0)


@pytest.mark.asyncio
async def test_calculate_period_boundaries_month_year_rollover(
    quota_service: QuotaService,
):
    """Test period boundary calculation for December (year rollover)."""
    now = datetime(2025, 12, 15, 14, 30, 0)

    start, end = quota_service._calculate_period_boundaries(
        QuotaPeriod.MONTH.value, now
    )

    assert start == datetime(2025, 12, 1, 0, 0, 0)
    assert end == datetime(2026, 1, 1, 0, 0, 0)  # Next year


@pytest.mark.asyncio
async def test_calculate_period_boundaries_minute(quota_service: QuotaService):
    """Test period boundary calculation for minute-based quota."""
    now = datetime(2025, 11, 9, 14, 30, 45)  # 2:30:45 PM

    start, end = quota_service._calculate_period_boundaries(
        QuotaPeriod.MINUTE.value, now
    )

    # Should be start of minute to start of next minute
    assert start == datetime(2025, 11, 9, 14, 30, 0)
    assert end == datetime(2025, 11, 9, 14, 31, 0)


# ========== Service Tests - Redis Counter Integrity ==========


@pytest.mark.asyncio
async def test_redis_counter_persistence(
    quota_service: QuotaService, test_user_id: str
):
    """Test that Redis counter persists across service calls."""
    # First consumption
    await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=1,
    )

    # Create new service instance (simulates new request)
    new_service = QuotaService(quota_service.db)

    # Second consumption with new service
    result = await new_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=1,
    )

    # Counter should persist
    assert result["current"] == 2


@pytest.mark.asyncio
async def test_redis_key_isolation_per_user(quota_service: QuotaService):
    """Test that quota counters are isolated per user."""
    user1 = "user-1"
    user2 = "user-2"

    # User 1 consumes 5
    await quota_service.check_and_consume(
        user_id=user1,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=5,
    )

    # User 2 consumes 3
    await quota_service.check_and_consume(
        user_id=user2,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=3,
    )

    # Check user 1 status
    status1 = await quota_service.get_quota_status(
        user_id=user1,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
    )
    assert status1["current"] == 5

    # Check user 2 status
    status2 = await quota_service.get_quota_status(
        user_id=user2,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
    )
    assert status2["current"] == 3


@pytest.mark.asyncio
async def test_redis_key_isolation_per_quota_type(
    quota_service: QuotaService, test_user_id: str
):
    """Test that different quota types have separate counters."""
    # Consume signals quota
    await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=7,
    )

    # Consume alerts quota
    await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.ALERTS_PER_DAY.value,
        amount=3,
    )

    # Check signals status
    signals_status = await quota_service.get_quota_status(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
    )
    assert signals_status["current"] == 7

    # Check alerts status
    alerts_status = await quota_service.get_quota_status(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.ALERTS_PER_DAY.value,
    )
    assert alerts_status["current"] == 3


# ========== Service Tests - Database Audit Trail ==========


@pytest.mark.asyncio
async def test_usage_record_created(
    quota_service: QuotaService, db_session: AsyncSession, test_user_id: str
):
    """Test that usage record is created in database."""
    # Consume quota
    await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=5,
    )

    # Wait for async DB update
    await db_session.commit()

    # Query usage record
    from sqlalchemy import select

    stmt = select(QuotaUsage).where(
        QuotaUsage.user_id == test_user_id,
        QuotaUsage.quota_type == QuotaType.SIGNALS_PER_DAY.value,
    )
    result = await db_session.execute(stmt)
    usage = result.scalar_one_or_none()

    # Verify record exists
    assert usage is not None
    assert usage.count == 5
    assert usage.period_start is not None
    assert usage.period_end is not None


@pytest.mark.asyncio
async def test_usage_record_updated(
    quota_service: QuotaService, db_session: AsyncSession, test_user_id: str
):
    """Test that usage record is updated on subsequent consumption."""
    # First consumption
    await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=3,
    )
    await db_session.commit()

    # Second consumption
    await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=2,
    )
    await db_session.commit()

    # Query usage record
    from sqlalchemy import select

    stmt = select(QuotaUsage).where(
        QuotaUsage.user_id == test_user_id,
        QuotaUsage.quota_type == QuotaType.SIGNALS_PER_DAY.value,
    )
    result = await db_session.execute(stmt)
    usage = result.scalar_one_or_none()

    # Should be updated, not duplicated
    assert usage is not None
    assert usage.count == 5  # 3 + 2


# ========== API Route Tests ==========


@pytest.mark.asyncio
async def test_get_my_quotas_endpoint(client: AsyncClient):
    """Test GET /api/v1/quotas/me endpoint."""
    response = await client.get("/api/v1/quotas/me")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "user_id" in data
    assert "tier" in data
    assert "quotas" in data

    # Verify all quota types present
    quotas = data["quotas"]
    assert QuotaType.SIGNALS_PER_DAY.value in quotas
    assert QuotaType.ALERTS_PER_DAY.value in quotas

    # Verify quota structure
    signals_quota = quotas[QuotaType.SIGNALS_PER_DAY.value]
    assert "current" in signals_quota
    assert "limit" in signals_quota
    assert "remaining" in signals_quota
    assert "reset_at" in signals_quota


@pytest.mark.asyncio
async def test_get_quota_status_endpoint(client: AsyncClient):
    """Test GET /api/v1/quotas/{quota_type} endpoint."""
    response = await client.get(f"/api/v1/quotas/{QuotaType.SIGNALS_PER_DAY.value}")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert data["quota_type"] == QuotaType.SIGNALS_PER_DAY.value
    assert "current" in data
    assert "limit" in data
    assert "remaining" in data
    assert "reset_at" in data


@pytest.mark.asyncio
async def test_quota_exceeded_returns_429(
    client: AsyncClient, db_session: AsyncSession, test_user_id: str
):
    """Test that exceeding quota returns 429 with problem+json."""
    # Manually consume quota to limit
    service = QuotaService(db_session)
    for i in range(10):
        await service.check_and_consume(
            user_id=test_user_id,
            tier=SubscriptionTier.FREE.value,
            quota_type=QuotaType.SIGNALS_PER_DAY.value,
            amount=1,
        )

    # Attempt to consume more (this would be done in actual endpoint)
    from fastapi import HTTPException

    from backend.app.quotas.routes import check_quota

    with pytest.raises(HTTPException) as exc_info:
        await check_quota(
            user_id=test_user_id,
            tier=SubscriptionTier.FREE.value,
            quota_type=QuotaType.SIGNALS_PER_DAY.value,
            db=db_session,
            amount=1,
        )

    # Verify 429 status
    assert exc_info.value.status_code == 429

    # Verify problem+json format
    detail = exc_info.value.detail
    assert "type" in detail
    assert "title" in detail
    assert detail["status"] == 429
    assert "reset_at" in detail
    assert "limit" in detail
    assert "current" in detail


# ========== Service Tests - Reset Functionality ==========


@pytest.mark.asyncio
async def test_reset_quota(quota_service: QuotaService, test_user_id: str):
    """Test admin reset quota functionality."""
    # Consume some quota
    await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=7,
    )

    # Verify usage
    status_before = await quota_service.get_quota_status(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
    )
    assert status_before["current"] == 7

    # Reset quota
    await quota_service.reset_quota(
        user_id=test_user_id, quota_type=QuotaType.SIGNALS_PER_DAY.value
    )

    # Verify reset
    status_after = await quota_service.get_quota_status(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
    )
    assert status_after["current"] == 0
    assert status_after["remaining"] == status_after["limit"]


# ========== Edge Cases ==========


@pytest.mark.asyncio
async def test_quota_at_exact_limit(quota_service: QuotaService, test_user_id: str):
    """Test consuming quota up to exact limit."""
    # Consume exactly 10 (the limit)
    result = await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=10,
    )

    assert result["current"] == 10
    assert result["remaining"] == 0

    # Next consumption should fail
    with pytest.raises(QuotaExceededException):
        await quota_service.check_and_consume(
            user_id=test_user_id,
            tier=SubscriptionTier.FREE.value,
            quota_type=QuotaType.SIGNALS_PER_DAY.value,
            amount=1,
        )


@pytest.mark.asyncio
async def test_zero_amount_consumption(quota_service: QuotaService, test_user_id: str):
    """Test consuming zero amount (should still work)."""
    result = await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type=QuotaType.SIGNALS_PER_DAY.value,
        amount=0,
    )

    assert result["allowed"] is True
    assert result["current"] == 0


@pytest.mark.asyncio
async def test_large_amount_consumption(quota_service: QuotaService, test_user_id: str):
    """Test consuming large amount at once."""
    # Attempt to consume more than limit in one go
    with pytest.raises(QuotaExceededException):
        await quota_service.check_and_consume(
            user_id=test_user_id,
            tier=SubscriptionTier.FREE.value,
            quota_type=QuotaType.SIGNALS_PER_DAY.value,
            amount=100,  # More than 10 limit
        )


@pytest.mark.asyncio
async def test_quota_for_nonexistent_quota_type(
    quota_service: QuotaService, test_user_id: str
):
    """Test handling of non-existent quota type."""
    # Should allow by default (fail open)
    result = await quota_service.check_and_consume(
        user_id=test_user_id,
        tier=SubscriptionTier.FREE.value,
        quota_type="nonexistent_quota_type",
        amount=1,
    )

    assert result["allowed"] is True


# ========== Telemetry Tests ==========


@pytest.mark.asyncio
async def test_quota_block_metric_incremented(
    quota_service: QuotaService, test_user_id: str, monkeypatch
):
    """Test that quota_block_total metric is incremented on block."""
    from backend.app.observability.metrics import metrics

    # Track metric calls
    metric_calls = []

    def mock_inc():
        metric_calls.append(1)

    # Monkeypatch metric
    original_metric = metrics.quota_block_total.labels(
        key=QuotaType.SIGNALS_PER_DAY.value
    )
    monkeypatch.setattr(original_metric, "inc", mock_inc)

    # Consume up to limit
    for i in range(10):
        await quota_service.check_and_consume(
            user_id=test_user_id,
            tier=SubscriptionTier.FREE.value,
            quota_type=QuotaType.SIGNALS_PER_DAY.value,
            amount=1,
        )

    # Attempt to exceed (should increment metric)
    try:
        await quota_service.check_and_consume(
            user_id=test_user_id,
            tier=SubscriptionTier.FREE.value,
            quota_type=QuotaType.SIGNALS_PER_DAY.value,
            amount=1,
        )
    except QuotaExceededException:
        pass

    # Verify metric was incremented
    assert len(metric_calls) == 1
