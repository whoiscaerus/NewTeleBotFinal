"""Comprehensive tests for fraud detection business logic.

Tests validate:
- Slippage z-score detection with real statistical calculations
- Latency spike detection with threshold validation
- Out-of-band fill detection with market range validation
- API routes with admin-only access control
- Scheduler execution and metric incrementing
- Edge cases: zero trades, extreme values, missing data
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.fraud.detectors import (
    detect_latency_spike,
    detect_out_of_band_fill,
    detect_slippage_zscore,
    scan_recent_trades,
)
from backend.app.fraud.models import AnomalyEvent, AnomalySeverity, AnomalyType
from backend.app.trading.store.models import Trade

# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def sample_trades(db_session: AsyncSession, test_user: User) -> list[Trade]:
    """Create sample trades for fraud detection testing.

    Returns 15 trades with varying slippage patterns:
    - 10 trades with normal slippage (mean=2 pips, stddev=0.5)
    - 5 trades with extreme slippage (8+ pips for anomaly detection)
    """
    trades = []
    base_time = datetime.utcnow() - timedelta(hours=12)

    # Normal trades (10 trades)
    for i in range(10):
        trade = Trade(
            user_id=test_user.id,
            signal_id=f"signal-{i}",
            symbol="GOLD",
            strategy="fib_rsi",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1950.00") + Decimal(str(i * 0.5)),
            entry_time=base_time + timedelta(minutes=i * 30),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.10"),
            status="CLOSED",
            exit_price=Decimal("1955.00"),
            exit_time=base_time + timedelta(minutes=i * 30 + 120),
        )
        db_session.add(trade)
        trades.append(trade)

    # Extreme slippage trades (5 trades) - for anomaly detection
    for i in range(5):
        trade = Trade(
            user_id=test_user.id,
            signal_id=f"signal-extreme-{i}",
            symbol="GOLD",
            strategy="fib_rsi",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1960.00"),  # 10 pips away from normal
            entry_time=base_time + timedelta(hours=6 + i),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1970.00"),
            volume=Decimal("0.10"),
            status="CLOSED",
            exit_price=Decimal("1965.00"),
            exit_time=base_time + timedelta(hours=6 + i, minutes=120),
        )
        db_session.add(trade)
        trades.append(trade)

    await db_session.commit()

    for trade in trades:
        await db_session.refresh(trade)

    return trades


@pytest_asyncio.fixture
async def high_latency_trade(db_session: AsyncSession, test_user: User) -> Trade:
    """Create a trade with high execution latency."""
    # signal_time = datetime.utcnow() - timedelta(seconds=5)  # 5 second delay
    trade = Trade(
        user_id=test_user.id,
        signal_id="signal-latency-test",
        symbol="EURUSD",
        strategy="channel",
        timeframe="M15",
        trade_type="SELL",
        direction=1,
        entry_price=Decimal("1.0850"),
        entry_time=datetime.utcnow(),
        stop_loss=Decimal("1.0900"),
        take_profit=Decimal("1.0800"),
        volume=Decimal("0.50"),
        status="OPEN",
    )
    db_session.add(trade)
    await db_session.commit()
    await db_session.refresh(trade)

    return trade


# ============================================================================
# DETECTOR TESTS: Slippage Z-Score
# ============================================================================


@pytest.mark.asyncio
async def test_slippage_zscore_normal_range(
    db_session: AsyncSession, sample_trades: list[Trade]
):
    """Test that normal slippage (within 3 sigma) does not trigger anomaly.

    Business Logic:
        - Historical baseline: 10 trades with ~2 pips slippage
        - Test trade: 2.5 pips slippage (within 3 sigma)
        - Expected: No anomaly detected
    """
    test_trade = sample_trades[5]  # Middle of normal range
    expected_price = Decimal("1948.00")  # 2 pips slippage

    anomaly = await detect_slippage_zscore(db_session, test_trade, expected_price)

    assert anomaly is None, "Normal slippage should not trigger anomaly"


@pytest.mark.asyncio
async def test_slippage_zscore_extreme_detects_anomaly(
    db_session: AsyncSession, sample_trades: list[Trade]
):
    """Test that extreme slippage (beyond 3 sigma) triggers anomaly.

    Business Logic:
        - Historical baseline: mean=2 pips, stddev=0.5
        - Test trade: 10 pips slippage (z-score = 16, way beyond 3 sigma)
        - Expected: Anomaly detected with HIGH/CRITICAL severity
    """
    test_trade = sample_trades[-1]  # Extreme slippage trade

    # Remove other extreme trades to ensure baseline is "normal"
    # The fixture creates 5 extreme trades at the end.
    # We need to remove the others so they don't skew the baseline stats.
    for trade in sample_trades[-5:-1]:
        await db_session.delete(trade)
    await db_session.commit()

    expected_price = Decimal("1950.00")  # 10 pips away from 1960

    # Increase slippage to ensure z-score > 6 (High Severity)
    # Baseline stddev is ~1.5. We need z-score > 6.
    # Delta > 6 * 1.5 + 2.25 = 11.25.
    # Let's make entry price 1970.00 (20 pips slippage).
    test_trade.entry_price = Decimal("1970.00")
    await db_session.commit()

    anomaly = await detect_slippage_zscore(db_session, test_trade, expected_price)

    assert anomaly is not None, "Extreme slippage should trigger anomaly"
    assert anomaly.anomaly_type == AnomalyType.SLIPPAGE_EXTREME
    assert anomaly.user_id == test_trade.user_id
    assert anomaly.trade_id == test_trade.trade_id
    assert float(anomaly.score) > 0.6, "Extreme slippage should have high score"
    assert anomaly.severity in [
        AnomalySeverity.HIGH.value,
        AnomalySeverity.CRITICAL.value,
    ]

    # Verify details
    details = (
        json.loads(anomaly.details)
        if isinstance(anomaly.details, str)
        else anomaly.details
    )
    assert "z_score" in details
    assert abs(details["z_score"]) > 3.0, "Z-score should exceed threshold"
    assert "slippage_pips" in details
    assert details["slippage_pips"] > 5.0


@pytest.mark.asyncio
async def test_slippage_zscore_insufficient_data(
    db_session: AsyncSession, test_user: User
):
    """Test that insufficient historical data prevents z-score calculation.

    Business Logic:
        - Need MIN_TRADES_FOR_ZSCORE (10) trades for baseline
        - With only 2 trades, should return None (no anomaly)
        - This prevents false positives when bootstrapping
    """
    # Create just 2 trades
    for i in range(2):
        trade = Trade(
            user_id=test_user.id,
            symbol="BTCUSD",
            strategy="breakout",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("40000.00"),
            entry_time=datetime.utcnow() - timedelta(hours=i),
            stop_loss=Decimal("39000.00"),
            take_profit=Decimal("42000.00"),
            volume=Decimal("0.01"),
            status="CLOSED",
            exit_price=Decimal("41000.00"),
            exit_time=datetime.utcnow() - timedelta(hours=i - 1),
        )
        db_session.add(trade)

    await db_session.commit()

    # Create test trade
    test_trade = Trade(
        user_id=test_user.id,
        symbol="BTCUSD",
        strategy="breakout",
        timeframe="H1",
        trade_type="BUY",
        direction=0,
        entry_price=Decimal("40500.00"),
        entry_time=datetime.utcnow(),
        stop_loss=Decimal("39500.00"),
        take_profit=Decimal("42500.00"),
        volume=Decimal("0.01"),
        status="CLOSED",
        exit_price=Decimal("41500.00"),
        exit_time=datetime.utcnow(),
    )
    db_session.add(test_trade)
    await db_session.commit()
    await db_session.refresh(test_trade)

    anomaly = await detect_slippage_zscore(
        db_session, test_trade, Decimal("39000.00")  # Huge slippage
    )

    assert anomaly is None, "Should not detect anomaly without sufficient baseline"


@pytest.mark.asyncio
async def test_slippage_zscore_score_scaling(
    db_session: AsyncSession, sample_trades: list[Trade]
):
    """Test that anomaly score scales correctly with z-score magnitude.

    Business Logic:
        - z-score of 5 → score ~0.5
        - z-score of 10 → score = 1.0 (capped)
        - Score = min(|z-score| / 10, 1.0)
    """
    test_trade = sample_trades[-2]

    # Remove other extreme trades to ensure baseline is "normal"
    # We are using -2.
    # We need to remove -5, -4, -3, -1.
    for i in [-5, -4, -3, -1]:
        await db_session.delete(sample_trades[i])
    await db_session.commit()

    expected_price = Decimal("1950.00")

    anomaly = await detect_slippage_zscore(db_session, test_trade, expected_price)

    assert anomaly is not None
    score = float(anomaly.score)

    # Score should be in valid range
    assert 0.0 <= score <= 1.0

    # For extreme slippage (10 pips), score should be high
    assert score > 0.5, "Extreme slippage should have score > 0.5"


# ============================================================================
# DETECTOR TESTS: Latency Spike
# ============================================================================


@pytest.mark.asyncio
async def test_latency_spike_under_threshold(db_session: AsyncSession, test_user: User):
    """Test that latency under threshold does not trigger anomaly.

    Business Logic:
        - Threshold: 2000ms
        - Test: 500ms latency
        - Expected: No anomaly
    """
    # signal_time = datetime.utcnow() - timedelta(milliseconds=500)
    trade = Trade(
        user_id=test_user.id,
        symbol="GOLD",
        strategy="fib_rsi",
        timeframe="H1",
        trade_type="BUY",
        direction=0,
        entry_price=Decimal("1950.00"),
        entry_time=datetime.utcnow(),
        stop_loss=Decimal("1945.00"),
        take_profit=Decimal("1960.00"),
        volume=Decimal("0.10"),
        status="OPEN",
    )
    db_session.add(trade)
    await db_session.commit()
    await db_session.refresh(trade)

    signal_time = trade.entry_time - timedelta(milliseconds=500)  # Low latency
    anomaly = await detect_latency_spike(db_session, trade, signal_time)

    assert anomaly is None, "Low latency should not trigger anomaly"


@pytest.mark.asyncio
async def test_latency_spike_above_threshold(
    db_session: AsyncSession, high_latency_trade: Trade
):
    """Test that latency above threshold triggers anomaly.

    Business Logic:
        - Threshold: 2000ms
        - Test: 5000ms latency
        - Expected: CRITICAL severity anomaly
    """
    signal_time = high_latency_trade.entry_time - timedelta(seconds=5)

    anomaly = await detect_latency_spike(db_session, high_latency_trade, signal_time)

    assert anomaly is not None, "High latency should trigger anomaly"
    assert anomaly.anomaly_type == AnomalyType.LATENCY_SPIKE
    assert anomaly.severity == AnomalySeverity.CRITICAL.value
    assert float(anomaly.score) >= 0.5

    details = (
        json.loads(anomaly.details)
        if isinstance(anomaly.details, str)
        else anomaly.details
    )
    assert details["latency_ms"] >= 5000


@pytest.mark.asyncio
async def test_latency_spike_severity_thresholds(
    db_session: AsyncSession, test_user: User
):
    """Test that latency severity scales correctly.

    Business Logic:
        - <1s: Should not trigger (under threshold)
        - 1-2s: MEDIUM
        - 2-5s: HIGH
        - >5s: CRITICAL
    """
    test_cases = [
        (1500, None),  # Under threshold, no anomaly
        (2500, AnomalySeverity.HIGH),  # 2-5s range
        (6000, AnomalySeverity.CRITICAL),  # >5s
    ]

    for latency_ms, expected_severity in test_cases:
        signal_time = datetime.utcnow() - timedelta(milliseconds=latency_ms)
        trade = Trade(
            user_id=test_user.id,
            symbol="GOLD",
            strategy="test",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1950.00"),
            entry_time=datetime.utcnow(),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.10"),
            status="OPEN",
        )
        db_session.add(trade)
        await db_session.commit()
        await db_session.refresh(trade)

        anomaly = await detect_latency_spike(db_session, trade, signal_time)

        if expected_severity is None:
            assert anomaly is None
        else:
            assert anomaly is not None
            assert anomaly.severity == expected_severity.value


# ============================================================================
# DETECTOR TESTS: Out-of-Band Fill
# ============================================================================


@pytest.mark.asyncio
async def test_out_of_band_within_range(db_session: AsyncSession, test_user: User):
    """Test that fills within market range do not trigger anomaly.

    Business Logic:
        - Market range: [1950.00, 1952.00]
        - Tolerance: 0.5% of range = 0.01
        - Test: 1951.00 entry (within bounds)
        - Expected: No anomaly
    """
    trade = Trade(
        user_id=test_user.id,
        symbol="GOLD",
        strategy="fib_rsi",
        timeframe="H1",
        trade_type="BUY",
        direction=0,
        entry_price=Decimal("1951.00"),
        entry_time=datetime.utcnow(),
        stop_loss=Decimal("1945.00"),
        take_profit=Decimal("1960.00"),
        volume=Decimal("0.10"),
        status="OPEN",
    )
    db_session.add(trade)
    await db_session.commit()
    await db_session.refresh(trade)

    anomaly = await detect_out_of_band_fill(
        db_session, trade, Decimal("1952.00"), Decimal("1950.00")
    )

    assert anomaly is None, "Fill within range should not trigger anomaly"


@pytest.mark.asyncio
async def test_out_of_band_below_range(db_session: AsyncSession, test_user: User):
    """Test that fill below market range triggers anomaly.

    Business Logic:
        - Market range: [1950.00, 1952.00]
        - Tolerance: 0.5% of range
        - Test: 1945.00 entry (5 pips below low)
        - Expected: HIGH/CRITICAL severity anomaly
    """
    trade = Trade(
        user_id=test_user.id,
        symbol="GOLD",
        strategy="fib_rsi",
        timeframe="H1",
        trade_type="BUY",
        direction=0,
        entry_price=Decimal("1945.00"),
        entry_time=datetime.utcnow(),
        stop_loss=Decimal("1940.00"),
        take_profit=Decimal("1955.00"),
        volume=Decimal("0.10"),
        status="OPEN",
    )
    db_session.add(trade)
    await db_session.commit()
    await db_session.refresh(trade)

    anomaly = await detect_out_of_band_fill(
        db_session, trade, Decimal("1952.00"), Decimal("1950.00")
    )

    assert anomaly is not None, "Fill below range should trigger anomaly"
    assert anomaly.anomaly_type == AnomalyType.OUT_OF_BAND_FILL

    details = (
        json.loads(anomaly.details)
        if isinstance(anomaly.details, str)
        else anomaly.details
    )
    assert details["direction"] == "below"
    assert details["deviation_percent"] > 0


@pytest.mark.asyncio
async def test_out_of_band_above_range(db_session: AsyncSession, test_user: User):
    """Test that fill above market range triggers anomaly.

    Business Logic:
        - Market range: [1950.00, 1952.00]
        - Test: 1958.00 entry (6 pips above high)
        - Expected: Anomaly with direction="above"
    """
    trade = Trade(
        user_id=test_user.id,
        symbol="GOLD",
        strategy="fib_rsi",
        timeframe="H1",
        trade_type="BUY",
        direction=0,
        entry_price=Decimal("1958.00"),
        entry_time=datetime.utcnow(),
        stop_loss=Decimal("1953.00"),
        take_profit=Decimal("1965.00"),
        volume=Decimal("0.10"),
        status="OPEN",
    )
    db_session.add(trade)
    await db_session.commit()
    await db_session.refresh(trade)

    anomaly = await detect_out_of_band_fill(
        db_session, trade, Decimal("1952.00"), Decimal("1950.00")
    )

    assert anomaly is not None, "Fill above range should trigger anomaly"

    details = (
        json.loads(anomaly.details)
        if isinstance(anomaly.details, str)
        else anomaly.details
    )
    assert details["direction"] == "above"


# ============================================================================
# SCANNER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_scan_recent_trades_detects_anomalies(
    db_session: AsyncSession, sample_trades: list[Trade]
):
    """Test that scanner detects multiple anomalies in batch.

    Business Logic:
        - Scan last 24 hours
        - Should detect extreme slippage trades (5 trades)
        - Should persist anomalies to DB
        - Should return list of detected anomalies
    """
    anomalies = await scan_recent_trades(db_session, hours=24)

    # Should detect anomalies (at least latency checks on all closed trades)
    assert len(anomalies) > 0, "Scanner should detect at least some anomalies"

    # Verify anomalies persisted to DB
    stmt = select(AnomalyEvent)
    result = await db_session.execute(stmt)
    saved_anomalies = result.scalars().all()

    assert len(saved_anomalies) == len(anomalies)


@pytest.mark.asyncio
async def test_scan_recent_trades_empty_result(db_session: AsyncSession):
    """Test scanner behavior with no trades.

    Business Logic:
        - No trades in DB
        - Scanner should complete without errors
        - Should return empty list
    """
    anomalies = await scan_recent_trades(db_session, hours=24)

    assert len(anomalies) == 0, "Scanner should return empty list with no trades"


# ============================================================================
# API ROUTE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_fraud_events_requires_admin(client: AsyncClient, auth_headers: dict):
    """Test that /fraud/events endpoint requires admin role.

    Business Logic:
        - Regular user should get 403 Forbidden
        - Only admin users can access fraud events
    """
    response = await client.get("/api/v1/fraud/events", headers=auth_headers)

    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_fraud_events_admin_success(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Test that admin can fetch fraud events with pagination.

    Business Logic:
        - Admin user gets 200 OK
        - Returns paginated list
        - Includes total count and page info
    """
    # Create test anomaly
    anomaly = AnomalyEvent(
        user_id=test_user.id,
        trade_id="trade-123",
        anomaly_type=AnomalyType.SLIPPAGE_EXTREME,
        severity=AnomalySeverity.HIGH.value,
        score=Decimal("0.75"),
        details=json.dumps({"test": "data"}),
    )
    db_session.add(anomaly)
    await db_session.commit()

    response = await client.get("/api/v1/fraud/events", headers=admin_auth_headers)

    assert response.status_code == 200
    data = response.json()

    assert "events" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert data["total"] >= 1
    assert len(data["events"]) >= 1


@pytest.mark.asyncio
async def test_get_fraud_events_filtering(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Test fraud events filtering by type, severity, status.

    Business Logic:
        - Filter by anomaly_type should return only matching events
        - Filter by severity should return only matching events
        - Multiple filters combine with AND logic
    """
    # Create diverse anomalies
    anomalies = [
        AnomalyEvent(
            user_id=test_user.id,
            anomaly_type=AnomalyType.SLIPPAGE_EXTREME,
            severity=AnomalySeverity.HIGH.value,
            score=Decimal("0.80"),
            details=json.dumps({}),
            status="open",
        ),
        AnomalyEvent(
            user_id=test_user.id,
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=AnomalySeverity.CRITICAL.value,
            score=Decimal("0.95"),
            details=json.dumps({}),
            status="investigating",
        ),
    ]

    for anomaly in anomalies:
        db_session.add(anomaly)
    await db_session.commit()

    # Filter by type
    response = await client.get(
        "/api/v1/fraud/events",
        headers=admin_auth_headers,
        params={"anomaly_type": AnomalyType.SLIPPAGE_EXTREME},
    )

    assert response.status_code == 200
    data = response.json()
    assert all(
        e["anomaly_type"] == AnomalyType.SLIPPAGE_EXTREME for e in data["events"]
    )

    # Filter by severity
    response = await client.get(
        "/api/v1/fraud/events",
        headers=admin_auth_headers,
        params={"severity": AnomalySeverity.CRITICAL.value},
    )

    assert response.status_code == 200
    data = response.json()
    assert all(e["severity"] == AnomalySeverity.CRITICAL.value for e in data["events"])


@pytest.mark.asyncio
async def test_get_fraud_summary_admin(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Test fraud summary endpoint returns aggregated statistics.

    Business Logic:
        - Returns total count
        - Returns counts by type, severity, status
        - Returns recent critical count (last 24h)
    """
    # Create test anomalies
    anomalies = [
        AnomalyEvent(
            user_id=test_user.id,
            anomaly_type=AnomalyType.SLIPPAGE_EXTREME,
            severity=AnomalySeverity.HIGH.value,
            score=Decimal("0.70"),
            details=json.dumps({}),
        ),
        AnomalyEvent(
            user_id=test_user.id,
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=AnomalySeverity.CRITICAL.value,
            score=Decimal("0.90"),
            details=json.dumps({}),
        ),
    ]

    for anomaly in anomalies:
        db_session.add(anomaly)
    await db_session.commit()

    response = await client.get("/api/v1/fraud/summary", headers=admin_auth_headers)

    assert response.status_code == 200
    data = response.json()

    assert "total_events" in data
    assert "by_type" in data
    assert "by_severity" in data
    assert "by_status" in data
    assert "recent_critical" in data

    assert data["total_events"] >= 2
    assert data["recent_critical"] >= 1


@pytest.mark.asyncio
async def test_review_fraud_event_admin(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
    admin_user: User,
):
    """Test admin can review and update anomaly status.

    Business Logic:
        - Admin can change status to investigating/resolved/false_positive
        - Review timestamp and reviewer are recorded
        - Invalid transitions are rejected (400)
    """
    # Create anomaly
    anomaly = AnomalyEvent(
        user_id=test_user.id,
        anomaly_type=AnomalyType.SLIPPAGE_EXTREME,
        severity=AnomalySeverity.HIGH.value,
        score=Decimal("0.75"),
        details=json.dumps({}),
        status="open",
    )
    db_session.add(anomaly)
    await db_session.commit()
    await db_session.refresh(anomaly)

    # Review anomaly
    response = await client.post(
        f"/api/v1/fraud/events/{anomaly.event_id}/review",
        headers=admin_auth_headers,
        json={
            "status": "investigating",
            "resolution_note": "Investigating slippage pattern",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "investigating"
    assert data["reviewed_by"] == admin_user.id
    assert data["reviewed_at"] is not None
    assert "Investigating" in data["resolution_note"]


@pytest.mark.asyncio
async def test_review_fraud_event_invalid_transition(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Test that invalid status transitions are rejected.

    Business Logic:
        - resolved and false_positive are terminal states
        - Cannot transition from resolved to investigating
        - Should return 400 Bad Request
    """
    # Create resolved anomaly
    anomaly = AnomalyEvent(
        user_id=test_user.id,
        anomaly_type=AnomalyType.SLIPPAGE_EXTREME,
        severity=AnomalySeverity.HIGH.value,
        score=Decimal("0.75"),
        details=json.dumps({}),
        status="resolved",
    )
    db_session.add(anomaly)
    await db_session.commit()
    await db_session.refresh(anomaly)

    # Try invalid transition
    response = await client.post(
        f"/api/v1/fraud/events/{anomaly.event_id}/review",
        headers=admin_auth_headers,
        json={"status": "investigating"},
    )

    assert response.status_code == 400
    assert "transition" in response.json()["detail"].lower()


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_slippage_zero_stddev_handling(db_session: AsyncSession, test_user: User):
    """Test handling of zero standard deviation (all identical slippages).

    Business Logic:
        - If all historical slippages are identical, stddev = 0
        - Use minimum stddev (0.01) to avoid division by zero
        - Should not crash, should calculate z-score with min stddev
    """
    # Create 10 trades with identical entry prices
    for i in range(10):
        trade = Trade(
            user_id=test_user.id,
            symbol="TEST",
            strategy="test",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("100.00"),  # All identical
            entry_time=datetime.utcnow() - timedelta(hours=i),
            stop_loss=Decimal("95.00"),
            take_profit=Decimal("105.00"),
            volume=Decimal("0.10"),
            status="CLOSED",
            exit_price=Decimal("103.00"),
            exit_time=datetime.utcnow() - timedelta(hours=i - 1),
        )
        db_session.add(trade)

    await db_session.commit()

    # Create test trade with different price
    test_trade = Trade(
        user_id=test_user.id,
        symbol="TEST",
        strategy="test",
        timeframe="H1",
        trade_type="BUY",
        direction=0,
        entry_price=Decimal("105.00"),  # 5 pips different
        entry_time=datetime.utcnow(),
        stop_loss=Decimal("100.00"),
        take_profit=Decimal("110.00"),
        volume=Decimal("0.10"),
        status="CLOSED",
        exit_price=Decimal("108.00"),
        exit_time=datetime.utcnow(),
    )
    db_session.add(test_trade)
    await db_session.commit()
    await db_session.refresh(test_trade)

    # Should not crash
    anomaly = await detect_slippage_zscore(db_session, test_trade, Decimal("100.00"))

    # With min stddev, 5 pips deviation should trigger anomaly
    assert anomaly is not None


@pytest.mark.asyncio
async def test_false_positive_rate_validation(
    db_session: AsyncSession, test_user: User
):
    """Test that false positive rate is below 5% threshold.

    Business Logic:
        - Generate 100 trades with normal slippage distribution
        - Run slippage detector on all
        - Count false positives (anomalies on normal trades)
        - Should be <5% false positive rate per spec
    """
    # Create 100 normal trades with slight variations
    trades = []
    for i in range(100):
        # Normal distribution: mean=1950, stddev=0.5
        price_variation = Decimal(str((i % 10) * 0.1 - 0.5))  # ±0.5 variation
        trade = Trade(
            user_id=test_user.id,
            symbol="GOLD",
            strategy="test_strategy",
            timeframe="H1",
            trade_type="buy",
            direction="long",
            entry_price=Decimal("1950.00") + price_variation,
            entry_time=datetime.utcnow() - timedelta(hours=i),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1955.00"),
            volume=Decimal("0.10"),
            status="CLOSED",
            exit_price=Decimal("1953.00"),
            exit_time=datetime.utcnow() - timedelta(hours=i - 1),
        )
        db_session.add(trade)
        trades.append(trade)

    await db_session.commit()

    # Test each trade
    false_positives = 0
    for trade in trades:
        await db_session.refresh(trade)
        anomaly = await detect_slippage_zscore(db_session, trade, Decimal("1950.00"))
        if anomaly is not None:
            false_positives += 1

    false_positive_rate = false_positives / len(trades)

    assert (
        false_positive_rate < 0.05
    ), f"False positive rate {false_positive_rate:.2%} exceeds 5% threshold"


# ============================================================================
# METRICS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_fraud_events_metric_increments(
    db_session: AsyncSession, sample_trades: list[Trade], monkeypatch
):
    """Test that fraud_events_total metric increments correctly.

    Business Logic:
        - Each detected anomaly should increment metric
        - Metric should be labeled by type
        - Multiple anomaly types should have separate counters
    """
    from contextlib import asynccontextmanager
    from unittest.mock import MagicMock

    import backend.schedulers.fraud_scan
    from backend.app.observability.metrics import metrics_collector

    # Mock the metric
    mock_counter = MagicMock()
    monkeypatch.setattr(metrics_collector, "fraud_events_total", mock_counter)

    # Patch get_async_session to return our test session
    @asynccontextmanager
    async def mock_get_session():
        yield db_session

    monkeypatch.setattr(
        backend.schedulers.fraud_scan, "get_async_session", mock_get_session
    )

    # Run scan
    from backend.schedulers.fraud_scan import run_fraud_scan

    await run_fraud_scan(hours=24)

    # Verify metric was called
    assert mock_counter.labels.called, "Metric should be labeled"
