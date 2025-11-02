"""
PR-044: Price Alerts & Notifications - Comprehensive Tests

Tests for alert creation, evaluation, throttling, validation, and notification.
Coverage target: 90%+
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.app.alerts.service import (
    THROTTLE_MINUTES,
    VALID_SYMBOLS,
    AlertNotification,
    PriceAlert,
    PriceAlertService,
)
from backend.app.core.errors import ValidationError

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def alert_service():
    """Create alert service instance."""
    return PriceAlertService()


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create test user."""
    from backend.app.auth.models import User

    user = User(
        id=str(uuid4()),
        email=f"test_user_{uuid4()}@example.com",
        password_hash="hashed_password_test",
        telegram_user_id="123456789",
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_alert(db_session, test_user):
    """Create test alert."""
    alert = PriceAlert(
        id=str(uuid4()),
        user_id=test_user.id,
        symbol="GOLD",
        operator="above",
        price_level=2000.0,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)
    return alert


# ============================================================================
# TESTS: CREATE ALERT
# ============================================================================


@pytest.mark.asyncio
async def test_create_alert_valid(db_session, alert_service, test_user):
    """Test creating alert with valid input."""
    result = await alert_service.create_alert(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        operator="above",
        price_level=2000.0,
    )

    assert result["alert_id"] is not None
    assert result["symbol"] == "GOLD"
    assert result["operator"] == "above"
    assert result["price_level"] == 2000.0
    assert result["is_active"] is True


@pytest.mark.asyncio
async def test_create_alert_below_operator(db_session, alert_service, test_user):
    """Test creating alert with 'below' operator."""
    result = await alert_service.create_alert(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        operator="below",
        price_level=1950.0,
    )

    assert result["operator"] == "below"
    assert result["price_level"] == 1950.0


@pytest.mark.asyncio
async def test_create_alert_invalid_operator(db_session, alert_service, test_user):
    """Test alert creation rejects invalid operator."""
    with pytest.raises(ValidationError, match="Operator must be"):
        await alert_service.create_alert(
            db=db_session,
            user_id=test_user.id,
            symbol="GOLD",
            operator="between",
            price_level=2000.0,
        )


@pytest.mark.asyncio
async def test_create_alert_invalid_symbol(db_session, alert_service, test_user):
    """Test alert creation rejects unsupported symbol."""
    with pytest.raises(ValidationError, match="not supported"):
        await alert_service.create_alert(
            db=db_session,
            user_id=test_user.id,
            symbol="INVALID_SYMBOL",
            operator="above",
            price_level=2000.0,
        )


@pytest.mark.asyncio
async def test_create_alert_negative_price(db_session, alert_service, test_user):
    """Test alert creation rejects negative price."""
    with pytest.raises(ValidationError, match="between 0 and 1"):
        await alert_service.create_alert(
            db=db_session,
            user_id=test_user.id,
            symbol="GOLD",
            operator="above",
            price_level=-100.0,
        )


@pytest.mark.asyncio
async def test_create_alert_zero_price(db_session, alert_service, test_user):
    """Test alert creation rejects zero price."""
    with pytest.raises(ValidationError, match="between 0 and 1"):
        await alert_service.create_alert(
            db=db_session,
            user_id=test_user.id,
            symbol="GOLD",
            operator="above",
            price_level=0.0,
        )


@pytest.mark.asyncio
async def test_create_alert_excessive_price(db_session, alert_service, test_user):
    """Test alert creation rejects extremely high price."""
    with pytest.raises(ValidationError, match="between 0 and 1"):
        await alert_service.create_alert(
            db=db_session,
            user_id=test_user.id,
            symbol="GOLD",
            operator="above",
            price_level=10000000.0,
        )


@pytest.mark.asyncio
async def test_create_alert_duplicate(db_session, alert_service, test_user):
    """Test alert creation rejects duplicate."""
    # Create first alert
    await alert_service.create_alert(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        operator="above",
        price_level=2000.0,
    )

    # Try to create duplicate
    with pytest.raises(ValidationError, match="same parameters"):
        await alert_service.create_alert(
            db=db_session,
            user_id=test_user.id,
            symbol="GOLD",
            operator="above",
            price_level=2000.0,
        )


@pytest.mark.asyncio
async def test_create_alert_persists_to_db(db_session, alert_service, test_user):
    """Test that created alert is saved in database."""
    result = await alert_service.create_alert(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        operator="above",
        price_level=2000.0,
    )

    # Query database to verify
    query_result = await db_session.execute(
        select(PriceAlert).where(PriceAlert.id == result["alert_id"])
    )
    alert = query_result.scalar()

    assert alert is not None
    assert alert.symbol == "GOLD"
    assert alert.user_id == test_user.id


# ============================================================================
# TESTS: LIST ALERTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_alerts_empty(db_session, alert_service, test_user):
    """Test listing alerts when user has none."""
    result = await alert_service.list_user_alerts(db=db_session, user_id=test_user.id)

    assert result == []


@pytest.mark.asyncio
async def test_list_alerts_single(db_session, alert_service, test_user):
    """Test listing alerts when user has one."""
    alert = await alert_service.create_alert(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        operator="above",
        price_level=2000.0,
    )

    result = await alert_service.list_user_alerts(db=db_session, user_id=test_user.id)

    assert len(result) == 1
    assert result[0]["alert_id"] == alert["alert_id"]


@pytest.mark.asyncio
async def test_list_alerts_multiple(db_session, alert_service, test_user):
    """Test listing multiple alerts."""
    alert1 = await alert_service.create_alert(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        operator="above",
        price_level=2000.0,
    )

    alert2 = await alert_service.create_alert(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        operator="below",
        price_level=1950.0,
    )

    result = await alert_service.list_user_alerts(db=db_session, user_id=test_user.id)

    assert len(result) == 2


# ============================================================================
# TESTS: DELETE ALERT
# ============================================================================


@pytest.mark.asyncio
async def test_delete_alert_valid(db_session, alert_service, test_alert):
    """Test deleting an alert."""
    deleted = await alert_service.delete_alert(
        db=db_session, alert_id=test_alert.id, user_id=test_alert.user_id
    )

    assert deleted is True

    # Verify deletion
    query_result = await db_session.execute(
        select(PriceAlert).where(PriceAlert.id == test_alert.id)
    )
    assert query_result.scalar() is None


@pytest.mark.asyncio
async def test_delete_alert_not_found(db_session, alert_service, test_user):
    """Test deleting non-existent alert."""
    deleted = await alert_service.delete_alert(
        db=db_session, alert_id="non-existent", user_id=test_user.id
    )

    assert deleted is False


@pytest.mark.asyncio
async def test_delete_alert_wrong_user(db_session, alert_service, test_alert):
    """Test that user can't delete another user's alert."""
    from backend.app.auth.models import User

    other_user = User(
        id=str(uuid4()),
        email=f"other_user_{uuid4()}@example.com",
        password_hash="hashed_password_test",
        telegram_user_id=f"{uuid4()}",
    )
    db_session.add(other_user)
    await db_session.commit()

    deleted = await alert_service.delete_alert(
        db=db_session, alert_id=test_alert.id, user_id=other_user.id
    )

    assert deleted is False


# ============================================================================
# TESTS: EVALUATE ALERTS
# ============================================================================


@pytest.mark.asyncio
async def test_evaluate_alerts_above_trigger(db_session, alert_service, test_alert):
    """Test alert triggers when price goes above threshold."""
    # Create 'above' alert at 2000
    test_alert.operator = "above"
    test_alert.price_level = 2000.0
    await db_session.commit()

    # Current price above threshold
    triggered = await alert_service.evaluate_alerts(
        db=db_session, current_prices={"GOLD": 2050.0}
    )

    assert len(triggered) == 1
    assert triggered[0]["alert_id"] == test_alert.id
    assert triggered[0]["current_price"] == 2050.0


@pytest.mark.asyncio
async def test_evaluate_alerts_below_trigger(db_session, alert_service, test_alert):
    """Test alert triggers when price goes below threshold."""
    # Create 'below' alert at 2000
    test_alert.operator = "below"
    test_alert.price_level = 2000.0
    await db_session.commit()

    # Current price below threshold
    triggered = await alert_service.evaluate_alerts(
        db=db_session, current_prices={"GOLD": 1950.0}
    )

    assert len(triggered) == 1
    assert triggered[0]["current_price"] == 1950.0


@pytest.mark.asyncio
async def test_evaluate_alerts_above_no_trigger(db_session, alert_service, test_alert):
    """Test 'above' alert doesn't trigger when price is below."""
    test_alert.operator = "above"
    test_alert.price_level = 2000.0
    await db_session.commit()

    triggered = await alert_service.evaluate_alerts(
        db=db_session, current_prices={"GOLD": 1950.0}
    )

    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_evaluate_alerts_below_no_trigger(db_session, alert_service, test_alert):
    """Test 'below' alert doesn't trigger when price is above."""
    test_alert.operator = "below"
    test_alert.price_level = 2000.0
    await db_session.commit()

    triggered = await alert_service.evaluate_alerts(
        db=db_session, current_prices={"GOLD": 2050.0}
    )

    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_evaluate_alerts_inactive_not_evaluated(
    db_session, alert_service, test_alert
):
    """Test that inactive alerts are not evaluated."""
    test_alert.is_active = False
    test_alert.operator = "above"
    test_alert.price_level = 1000.0
    await db_session.commit()

    triggered = await alert_service.evaluate_alerts(
        db=db_session, current_prices={"GOLD": 2050.0}
    )

    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_evaluate_alerts_no_prices(db_session, alert_service, test_alert):
    """Test evaluation with no prices provided."""
    triggered = await alert_service.evaluate_alerts(db=db_session, current_prices={})

    assert len(triggered) == 0


# ============================================================================
# TESTS: THROTTLING
# ============================================================================


@pytest.mark.asyncio
async def test_throttle_first_notification(db_session, alert_service, test_alert):
    """Test first notification is always sent (no throttle)."""
    should_notify = await alert_service._should_notify(
        db=db_session, alert_id=test_alert.id
    )

    assert should_notify is True


@pytest.mark.asyncio
async def test_throttle_within_window(db_session, alert_service, test_alert):
    """Test throttle prevents notification within window."""
    # Record a notification just now
    notif = AlertNotification(
        id=str(uuid4()),
        alert_id=test_alert.id,
        user_id=test_alert.user_id,
        price_triggered=2000.0,
        sent_at=datetime.utcnow(),
        channel="telegram",
    )
    db_session.add(notif)
    await db_session.commit()

    # Should be throttled
    should_notify = await alert_service._should_notify(
        db=db_session, alert_id=test_alert.id
    )

    assert should_notify is False


@pytest.mark.asyncio
async def test_throttle_after_window(db_session, alert_service, test_alert):
    """Test throttle allows notification after window passes."""
    # Record a notification in the past (past throttle window)
    past_time = datetime.utcnow() - timedelta(minutes=THROTTLE_MINUTES + 1)
    notif = AlertNotification(
        id=str(uuid4()),
        alert_id=test_alert.id,
        user_id=test_alert.user_id,
        price_triggered=2000.0,
        sent_at=past_time,
        channel="telegram",
    )
    db_session.add(notif)
    await db_session.commit()

    # Should not be throttled
    should_notify = await alert_service._should_notify(
        db=db_session, alert_id=test_alert.id
    )

    assert should_notify is True


# ============================================================================
# TESTS: RECORD NOTIFICATION
# ============================================================================


@pytest.mark.asyncio
async def test_record_notification_telegram(db_session, alert_service, test_alert):
    """Test recording Telegram notification."""
    await alert_service.record_notification(
        db=db_session,
        alert_id=test_alert.id,
        user_id=test_alert.user_id,
        channel="telegram",
        current_price=2050.0,
    )

    # Verify in database
    query_result = await db_session.execute(
        select(AlertNotification).where(AlertNotification.alert_id == test_alert.id)
    )
    notif = query_result.scalar()

    assert notif is not None
    assert notif.channel == "telegram"
    assert notif.price_triggered == 2050.0


@pytest.mark.asyncio
async def test_record_notification_miniapp(db_session, alert_service, test_alert):
    """Test recording Mini App notification."""
    await alert_service.record_notification(
        db=db_session,
        alert_id=test_alert.id,
        user_id=test_alert.user_id,
        channel="miniapp",
        current_price=2050.0,
    )

    query_result = await db_session.execute(
        select(AlertNotification).where(AlertNotification.alert_id == test_alert.id)
    )
    notif = query_result.scalar()

    assert notif.channel == "miniapp"


# ============================================================================
# TESTS: SEND NOTIFICATIONS
# ============================================================================


@pytest.mark.asyncio
async def test_send_notifications_empty_list(db_session, alert_service):
    """Test sending notifications with empty triggered list."""
    # Should not raise
    await alert_service.send_notifications(db=db_session, triggered_alerts=[])


@pytest.mark.asyncio
async def test_send_notifications_with_mock_service(
    db_session, alert_service, test_alert
):
    """Test sending notifications with mocked Telegram service."""
    mock_telegram = AsyncMock()
    alert_service.telegram_service = mock_telegram

    triggered_alerts = [
        {
            "alert_id": test_alert.id,
            "user_id": test_alert.user_id,
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
            "current_price": 2050.0,
        }
    ]

    await alert_service.send_notifications(
        db=db_session, triggered_alerts=triggered_alerts
    )

    # Verify Telegram was called
    mock_telegram.send_telegram_dm.assert_called_once()


@pytest.mark.asyncio
async def test_send_notifications_error_handling(db_session, alert_service, test_alert):
    """Test sending notifications handles errors gracefully."""
    # Mock Telegram to raise error
    mock_telegram = AsyncMock()
    mock_telegram.send_telegram_dm.side_effect = Exception("Telegram service down")
    alert_service.telegram_service = mock_telegram

    triggered_alerts = [
        {
            "alert_id": test_alert.id,
            "user_id": test_alert.user_id,
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
            "current_price": 2050.0,
        }
    ]

    # Should not raise despite error
    await alert_service.send_notifications(
        db=db_session, triggered_alerts=triggered_alerts
    )


# ============================================================================
# TESTS: GET ALERT
# ============================================================================


@pytest.mark.asyncio
async def test_get_alert_valid(db_session, alert_service, test_alert):
    """Test getting an alert by ID."""
    result = await alert_service.get_alert(
        db=db_session, alert_id=test_alert.id, user_id=test_alert.user_id
    )

    assert result is not None
    assert result["alert_id"] == test_alert.id
    assert result["symbol"] == test_alert.symbol


@pytest.mark.asyncio
async def test_get_alert_not_found(db_session, alert_service, test_user):
    """Test getting non-existent alert."""
    result = await alert_service.get_alert(
        db=db_session, alert_id="non-existent", user_id=test_user.id
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_alert_wrong_user(db_session, alert_service, test_alert):
    """Test getting alert for another user returns None."""
    from backend.app.auth.models import User

    other_user = User(
        id=str(uuid4()),
        email=f"other_user_{uuid4()}@example.com",
        password_hash="hashed_password",
        telegram_user_id="999999999",
        created_at=datetime.utcnow(),
    )
    db_session.add(other_user)
    await db_session.commit()

    result = await alert_service.get_alert(
        db=db_session, alert_id=test_alert.id, user_id=other_user.id
    )

    assert result is None


# ============================================================================
# TESTS: EDGE CASES
# ============================================================================


@pytest.mark.asyncio
async def test_create_alert_boundary_price_low(db_session, alert_service, test_user):
    """Test creating alert at low price boundary."""
    result = await alert_service.create_alert(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        operator="above",
        price_level=0.01,  # Very low but valid
    )

    assert result["price_level"] == 0.01


@pytest.mark.asyncio
async def test_create_alert_boundary_price_high(db_session, alert_service, test_user):
    """Test creating alert at high price boundary."""
    result = await alert_service.create_alert(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        operator="above",
        price_level=999999.99,  # Just below limit
    )

    assert result["price_level"] == 999999.99


@pytest.mark.asyncio
async def test_evaluate_alerts_exact_price(db_session, alert_service, test_alert):
    """Test alert triggers at exact price (inclusive)."""
    test_alert.operator = "above"
    test_alert.price_level = 2000.0
    await db_session.commit()

    # Price exactly at threshold should trigger
    triggered = await alert_service.evaluate_alerts(
        db=db_session, current_prices={"GOLD": 2000.0}
    )

    assert len(triggered) == 1


@pytest.mark.asyncio
async def test_multiple_alerts_same_symbol(db_session, alert_service, test_user):
    """Test multiple alerts on same symbol with different operators."""
    alert1 = await alert_service.create_alert(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        operator="above",
        price_level=2100.0,
    )

    alert2 = await alert_service.create_alert(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        operator="below",
        price_level=1900.0,
    )

    alerts = await alert_service.list_user_alerts(db=db_session, user_id=test_user.id)

    assert len(alerts) == 2


@pytest.mark.asyncio
async def test_all_valid_symbols(db_session, alert_service, test_user):
    """Test creating alerts for all valid symbols."""
    for symbol in VALID_SYMBOLS:
        result = await alert_service.create_alert(
            db=db_session,
            user_id=test_user.id,
            symbol=symbol,
            operator="above",
            price_level=1000.0,
        )
        assert result["symbol"] == symbol
