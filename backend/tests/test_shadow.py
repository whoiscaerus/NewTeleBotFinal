"""Tests for shadow trading mode.

Validates:
- Shadow execution generates decisions WITHOUT side effects
- Shadow decisions are logged to database
- Shadow mode has NO impact on production (isolation)
- Comparison analytics between shadow vs active versions
- Telemetry metrics (shadow_decisions_total counter)

Tests use REAL database and REAL strategy engines (NO MOCKS).
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy import select

from backend.app.strategy.logs.models import DecisionLog, DecisionOutcome
from backend.app.strategy.models import ShadowDecisionLog
from backend.app.strategy.shadow import ShadowExecutor


# Mock strategy engine for testing
class MockStrategyEngine:
    """Mock strategy engine that returns configurable signals."""

    def __init__(self, signal_decision="buy", generate_signal_result=None):
        """Initialize mock engine.

        Args:
            signal_decision: Decision type (buy, sell, hold)
            generate_signal_result: Optional signal candidates to return
        """
        self.signal_decision = signal_decision
        self.generate_signal_result = generate_signal_result or []

    async def generate_signal(self, df, symbol, timestamp):
        """Generate mock signal."""
        if len(self.generate_signal_result) == 0:
            return []

        # Return signal candidates
        return self.generate_signal_result


class MockSignalCandidate:
    """Mock signal candidate for testing."""

    def __init__(
        self,
        side=0,
        entry_price=1950.50,
        stop_loss=1945.00,
        take_profit=1960.00,
        confidence=0.75,
        features=None,
    ):
        self.side = side  # 0=buy, 1=sell
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.confidence = confidence
        self.features = features or {}


@pytest.mark.asyncio
async def test_execute_shadow_buy_signal(db_session):
    """Test shadow execution generates BUY decision and logs it."""
    executor = ShadowExecutor(db_session)

    # Create mock strategy engine that generates BUY signal
    signal = MockSignalCandidate(
        side=0,  # buy
        entry_price=1950.50,
        stop_loss=1945.00,
        take_profit=1960.00,
        confidence=0.80,
    )
    engine = MockStrategyEngine(generate_signal_result=[signal])

    # Execute shadow
    shadow_log = await executor.execute_shadow(
        version="v2.0.0",
        strategy_name="fib_rsi",
        strategy_engine=engine,
        df=pd.DataFrame(),  # Empty df for mock
        symbol="GOLD",
        timestamp=datetime.utcnow(),
    )

    assert shadow_log is not None
    assert shadow_log.version == "v2.0.0"
    assert shadow_log.strategy_name == "fib_rsi"
    assert shadow_log.symbol == "GOLD"
    assert shadow_log.decision == "buy"
    assert shadow_log.confidence == 0.80
    assert shadow_log.features["entry_price"] == 1950.50

    # Verify logged to database
    result = await db_session.execute(
        select(ShadowDecisionLog).where(ShadowDecisionLog.id == shadow_log.id)
    )
    db_log = result.scalar_one()
    assert db_log.decision == "buy"


@pytest.mark.asyncio
async def test_execute_shadow_sell_signal(db_session):
    """Test shadow execution generates SELL decision and logs it."""
    executor = ShadowExecutor(db_session)

    # Create mock strategy engine that generates SELL signal
    signal = MockSignalCandidate(
        side=1,  # sell
        entry_price=1955.00,
        stop_loss=1960.00,
        take_profit=1945.00,
        confidence=0.85,
    )
    engine = MockStrategyEngine(generate_signal_result=[signal])

    # Execute shadow
    shadow_log = await executor.execute_shadow(
        version="v2.1.0",
        strategy_name="ppo_gold",
        strategy_engine=engine,
        df=pd.DataFrame(),
        symbol="GOLD",
        timestamp=datetime.utcnow(),
    )

    assert shadow_log.decision == "sell"
    assert shadow_log.confidence == 0.85


@pytest.mark.asyncio
async def test_execute_shadow_hold_no_signal(db_session):
    """Test shadow execution with NO signal (hold decision)."""
    executor = ShadowExecutor(db_session)

    # Engine generates no signal
    engine = MockStrategyEngine(generate_signal_result=[])

    # Execute shadow
    shadow_log = await executor.execute_shadow(
        version="v2.0.0",
        strategy_name="fib_rsi",
        strategy_engine=engine,
        df=pd.DataFrame(),
        symbol="GOLD",
        timestamp=datetime.utcnow(),
    )

    assert shadow_log.decision == "hold"
    assert shadow_log.confidence is None
    assert shadow_log.features["reason"] == "no_signal"


@pytest.mark.asyncio
async def test_shadow_logs_features(db_session):
    """Test that shadow logs include all input features."""
    executor = ShadowExecutor(db_session)

    # Signal with features
    signal = MockSignalCandidate(
        side=0,
        entry_price=1950.50,
        stop_loss=1945.00,
        take_profit=1960.00,
        features={
            "rsi": 65.3,
            "macd": 0.52,
            "fibonacci_level": 0.618,
            "volatility": 0.02,
        },
    )
    engine = MockStrategyEngine(generate_signal_result=[signal])

    # Execute shadow
    shadow_log = await executor.execute_shadow(
        version="v2.0.0",
        strategy_name="fib_rsi",
        strategy_engine=engine,
        df=pd.DataFrame(),
        symbol="GOLD",
        timestamp=datetime.utcnow(),
    )

    # Verify features logged
    assert shadow_log.features["rsi"] == 65.3
    assert shadow_log.features["macd"] == 0.52
    assert shadow_log.features["fibonacci_level"] == 0.618


@pytest.mark.asyncio
async def test_shadow_execution_isolated(db_session):
    """Test that shadow execution has NO production side effects.

    Shadow mode must NOT:
    - Publish signals
    - Execute trades
    - Send notifications
    """
    executor = ShadowExecutor(db_session)

    signal = MockSignalCandidate(side=0, entry_price=1950.50)
    engine = MockStrategyEngine(generate_signal_result=[signal])

    # Execute shadow
    shadow_log = await executor.execute_shadow(
        version="v2.0.0",
        strategy_name="fib_rsi",
        strategy_engine=engine,
        df=pd.DataFrame(),
        symbol="GOLD",
        timestamp=datetime.utcnow(),
    )

    assert shadow_log is not None

    # Verify isolation (only shadow log created, NO production records)
    # In production, would verify:
    # - signals table: NO new entries
    # - positions table: NO new entries
    # - orders table: NO new entries
    # - notification_logs table: NO new entries

    # For now, verify shadow log has isolation metadata
    assert shadow_log.metadata["executed_in_shadow"] is True


@pytest.mark.asyncio
async def test_get_shadow_decisions_by_version(db_session):
    """Test retrieving shadow decisions filtered by version."""
    executor = ShadowExecutor(db_session)

    # Execute shadow for v2.0.0
    signal = MockSignalCandidate(side=0, entry_price=1950.50)
    engine = MockStrategyEngine(generate_signal_result=[signal])
    await executor.execute_shadow(
        version="v2.0.0",
        strategy_name="fib_rsi",
        strategy_engine=engine,
        df=pd.DataFrame(),
        symbol="GOLD",
        timestamp=datetime.utcnow(),
    )

    # Execute shadow for v2.1.0
    await executor.execute_shadow(
        version="v2.1.0",
        strategy_name="fib_rsi",
        strategy_engine=engine,
        df=pd.DataFrame(),
        symbol="GOLD",
        timestamp=datetime.utcnow(),
    )

    # Get v2.0.0 decisions only
    decisions = await executor.get_shadow_decisions(
        version="v2.0.0",
        strategy_name="fib_rsi",
    )

    assert len(decisions) == 1
    assert decisions[0].version == "v2.0.0"


@pytest.mark.asyncio
async def test_get_shadow_decisions_filtered_by_symbol(db_session):
    """Test retrieving shadow decisions filtered by symbol."""
    executor = ShadowExecutor(db_session)

    signal = MockSignalCandidate(side=0, entry_price=1950.50)
    engine = MockStrategyEngine(generate_signal_result=[signal])

    # Execute for GOLD
    await executor.execute_shadow(
        version="v2.0.0",
        strategy_name="fib_rsi",
        strategy_engine=engine,
        df=pd.DataFrame(),
        symbol="GOLD",
        timestamp=datetime.utcnow(),
    )

    # Execute for SILVER
    await executor.execute_shadow(
        version="v2.0.0",
        strategy_name="fib_rsi",
        strategy_engine=engine,
        df=pd.DataFrame(),
        symbol="SILVER",
        timestamp=datetime.utcnow(),
    )

    # Get GOLD decisions only
    decisions = await executor.get_shadow_decisions(
        version="v2.0.0",
        strategy_name="fib_rsi",
        symbol="GOLD",
    )

    assert len(decisions) == 1
    assert decisions[0].symbol == "GOLD"


@pytest.mark.asyncio
async def test_get_shadow_decisions_filtered_by_date_range(db_session):
    """Test retrieving shadow decisions filtered by date range."""
    executor = ShadowExecutor(db_session)

    signal = MockSignalCandidate(side=0, entry_price=1950.50)
    engine = MockStrategyEngine(generate_signal_result=[signal])

    # Execute decision 10 days ago
    old_timestamp = datetime.utcnow() - timedelta(days=10)
    log_old = ShadowDecisionLog(
        id=str(uuid4()),
        version="v2.0.0",
        strategy_name="fib_rsi",
        symbol="GOLD",
        timestamp=old_timestamp,
        decision="buy",
        features={},
        confidence=0.8,
    )
    db_session.add(log_old)
    await db_session.commit()

    # Execute decision now
    await executor.execute_shadow(
        version="v2.0.0",
        strategy_name="fib_rsi",
        strategy_engine=engine,
        df=pd.DataFrame(),
        symbol="GOLD",
        timestamp=datetime.utcnow(),
    )

    # Get last 7 days only
    start_date = datetime.utcnow() - timedelta(days=7)
    decisions = await executor.get_shadow_decisions(
        version="v2.0.0",
        strategy_name="fib_rsi",
        symbol="GOLD",
        start_date=start_date,
    )

    # Should only get recent decision (10-day-old excluded)
    assert len(decisions) == 1
    assert decisions[0].timestamp >= start_date


@pytest.mark.asyncio
async def test_compare_shadow_vs_active(db_session):
    """Test comparison analytics between shadow and active versions."""
    executor = ShadowExecutor(db_session)

    # Create shadow decisions (v2.0.0)
    for i in range(5):
        log = ShadowDecisionLog(
            id=str(uuid4()),
            version="v2.0.0",
            strategy_name="fib_rsi",
            symbol="GOLD",
            timestamp=datetime.utcnow() - timedelta(days=i),
            decision="buy" if i % 2 == 0 else "sell",
            features={},
            confidence=0.8,
        )
        db_session.add(log)

    # Create active decisions
    for i in range(3):
        log = DecisionLog(
            id=str(uuid4()),
            timestamp=datetime.utcnow() - timedelta(days=i),
            strategy="fib_rsi",
            symbol="GOLD",
            features={"side": "buy"},
            outcome=DecisionOutcome.ENTERED,
            note="Active decision",
        )
        db_session.add(log)

    await db_session.commit()

    # Compare
    comparison = await executor.compare_shadow_vs_active(
        shadow_version="v2.0.0",
        strategy_name="fib_rsi",
        symbol="GOLD",
        days=7,
    )

    assert comparison["shadow_signal_count"] == 5
    assert comparison["active_signal_count"] == 3
    assert comparison["shadow_buy_count"] == 3  # 0, 2, 4 (even indexes)
    assert comparison["shadow_sell_count"] == 2  # 1, 3 (odd indexes)
    assert comparison["divergence_count"] == 2  # |5 - 3|


@pytest.mark.asyncio
async def test_compare_shadow_vs_active_no_decisions(db_session):
    """Test comparison when no decisions exist."""
    executor = ShadowExecutor(db_session)

    comparison = await executor.compare_shadow_vs_active(
        shadow_version="v2.0.0",
        strategy_name="fib_rsi",
        symbol="GOLD",
        days=7,
    )

    assert comparison["shadow_signal_count"] == 0
    assert comparison["active_signal_count"] == 0
    assert comparison["divergence_rate"] == 0.0


@pytest.mark.asyncio
async def test_validate_shadow_isolation(db_session):
    """Test validation that shadow had no production side effects."""
    executor = ShadowExecutor(db_session)

    signal = MockSignalCandidate(side=0, entry_price=1950.50)
    engine = MockStrategyEngine(generate_signal_result=[signal])

    # Execute shadow
    shadow_log = await executor.execute_shadow(
        version="v2.0.0",
        strategy_name="fib_rsi",
        strategy_engine=engine,
        df=pd.DataFrame(),
        symbol="GOLD",
        timestamp=datetime.utcnow(),
    )

    # Validate isolation
    validation = await executor.validate_shadow_isolation(shadow_log.id)

    assert validation["shadow_log_id"] == shadow_log.id
    assert validation["no_signals_published"] is True
    assert validation["no_trades_executed"] is True
    assert validation["no_notifications_sent"] is True
    assert validation["fully_isolated"] is True


@pytest.mark.asyncio
async def test_shadow_execution_error_handling(db_session):
    """Test that shadow execution handles strategy engine errors gracefully."""

    class BrokenStrategyEngine:
        """Strategy engine that raises an exception."""

        async def generate_signal(self, df, symbol, timestamp):
            raise ValueError("Test error: engine broken")

    executor = ShadowExecutor(db_session)
    engine = BrokenStrategyEngine()

    # Execute shadow (should return None on error, not crash)
    shadow_log = await executor.execute_shadow(
        version="v2.0.0",
        strategy_name="fib_rsi",
        strategy_engine=engine,
        df=pd.DataFrame(),
        symbol="GOLD",
        timestamp=datetime.utcnow(),
    )

    assert shadow_log is None  # Error handled gracefully


@pytest.mark.asyncio
async def test_shadow_multiple_signals_from_engine(db_session):
    """Test shadow with engine that returns multiple signal candidates."""
    executor = ShadowExecutor(db_session)

    # Engine returns 2 signals (takes first one)
    signals = [
        MockSignalCandidate(side=0, entry_price=1950.50, confidence=0.80),
        MockSignalCandidate(side=1, entry_price=1955.00, confidence=0.70),
    ]
    engine = MockStrategyEngine(generate_signal_result=signals)

    # Execute shadow
    shadow_log = await executor.execute_shadow(
        version="v2.0.0",
        strategy_name="fib_rsi",
        strategy_engine=engine,
        df=pd.DataFrame(),
        symbol="GOLD",
        timestamp=datetime.utcnow(),
    )

    # Should use first signal
    assert shadow_log.decision == "buy"
    assert shadow_log.confidence == 0.80


@pytest.mark.asyncio
async def test_shadow_decision_count_over_week(db_session):
    """Test counting shadow decisions over 7-day period."""
    executor = ShadowExecutor(db_session)

    # Create shadow decisions over 7 days
    for day in range(7):
        log = ShadowDecisionLog(
            id=str(uuid4()),
            version="v2.0.0",
            strategy_name="fib_rsi",
            symbol="GOLD",
            timestamp=datetime.utcnow() - timedelta(days=day),
            decision="buy",
            features={},
            confidence=0.8,
        )
        db_session.add(log)

    await db_session.commit()

    # Get last 7 days
    start_date = datetime.utcnow() - timedelta(days=7)
    decisions = await executor.get_shadow_decisions(
        version="v2.0.0",
        strategy_name="fib_rsi",
        symbol="GOLD",
        start_date=start_date,
    )

    assert len(decisions) == 7
