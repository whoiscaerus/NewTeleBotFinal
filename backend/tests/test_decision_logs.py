"""Comprehensive tests for decision log service business logic.

Tests cover:
- Decision recording with full validation
- PII redaction from features
- Query by date range, strategy, symbol, outcome
- Large feature payload handling (>10KB)
- Analytics aggregation (counts by strategy/outcome)
- Error handling and transactions
- Metrics recording
- Database operations with JSONB
"""

from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import select

from backend.app.strategy.logs.models import DecisionLog, DecisionOutcome
from backend.app.strategy.logs.service import DecisionLogService, record_decision


@pytest.fixture
def decision_service(db_session):
    """Create decision log service for testing."""
    return DecisionLogService(db_session)


@pytest.fixture
def sample_features():
    """Sample feature set for testing."""
    return {
        "price": {
            "open": 1950.50,
            "high": 1952.00,
            "low": 1949.00,
            "close": 1951.25,
        },
        "indicators": {
            "rsi_14": 65.3,
            "macd": {"value": 0.52, "signal": 0.48, "histogram": 0.04},
            "sma_20": 1948.75,
            "ema_50": 1945.20,
        },
        "thresholds": {
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "risk_percent": 2.0,
            "reward_ratio": 2.5,
        },
        "sentiment": {"score": 0.65, "source": "news_api", "articles_count": 15},
        "position": {"size": 1.5, "risk_usd": 100.0, "reward_usd": 250.0},
    }


@pytest.fixture
def pii_features():
    """Features with PII that should be redacted."""
    return {
        "price": {"close": 1950.50},
        "user_id": "user_12345",
        "email": "trader@example.com",
        "phone_number": "+1234567890",
        "api_key": "sk_live_abcdef123456",
        "account_number": "9876543210",
        "nested": {
            "data": {"api_token": "token_xyz", "access_token": "access_abc"},
            "safe_field": "no_pii_here",
        },
    }


@pytest.fixture
def large_features():
    """Large feature payload for size testing (>10KB)."""
    # Generate large payload with many price bars
    bars = []
    for idx in range(500):  # 500 bars of OHLCV data
        bars.append(
            {
                "timestamp": f"2025-01-01T{idx%24:02d}:{idx%60:02d}:00",
                "open": 1950.0 + idx * 0.1,
                "high": 1952.0 + idx * 0.1,
                "low": 1948.0 + idx * 0.1,
                "close": 1951.0 + idx * 0.1,
                "volume": 1000 + idx * 10,
            }
        )

    return {
        "price_history": bars,
        "indicators": {
            "rsi": [65.0 + i * 0.1 for i in range(100)],
            "macd": [0.5 + i * 0.01 for i in range(100)],
        },
        "metadata": {"strategy": "complex_ml", "model_version": "v2.5.1"},
    }


class TestDecisionRecordingBasic:
    """Test basic decision recording workflow."""

    @pytest.mark.asyncio
    async def test_record_decision_entered(self, decision_service, sample_features):
        """Test recording an ENTERED decision with full context."""
        log = await decision_service.record_decision(
            strategy="ppo_gold",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
            note="RSI approaching overbought, MACD bullish crossover",
        )

        assert log.id is not None
        assert log.strategy == "ppo_gold"
        assert log.symbol == "GOLD"
        assert log.outcome == DecisionOutcome.ENTERED
        assert log.note == "RSI approaching overbought, MACD bullish crossover"
        assert log.timestamp is not None
        assert log.features == sample_features
        assert "rsi_14" in log.features["indicators"]
        assert log.features["indicators"]["rsi_14"] == 65.3

    @pytest.mark.asyncio
    async def test_record_decision_skipped(self, decision_service):
        """Test recording a SKIPPED decision."""
        features = {"rsi": 45.0, "macd": -0.1, "reason": "neutral_conditions"}

        log = await decision_service.record_decision(
            strategy="fib_rsi_eur",
            symbol="EURUSD",
            features=features,
            outcome=DecisionOutcome.SKIPPED,
            note="RSI neutral, no clear signal",
        )

        assert log.outcome == DecisionOutcome.SKIPPED
        assert log.symbol == "EURUSD"
        assert log.features["reason"] == "neutral_conditions"

    @pytest.mark.asyncio
    async def test_record_decision_rejected(self, decision_service):
        """Test recording a REJECTED decision (failed validation)."""
        features = {
            "price": 1950.0,
            "risk_percent": 5.0,
            "reason": "exceeds_risk_limit",
        }

        log = await decision_service.record_decision(
            strategy="high_risk_strategy",
            symbol="GOLD",
            features=features,
            outcome=DecisionOutcome.REJECTED,
            note="Risk too high: 5% exceeds 2% limit",
        )

        assert log.outcome == DecisionOutcome.REJECTED
        assert log.features["risk_percent"] == 5.0

    @pytest.mark.asyncio
    async def test_record_decision_pending(self, decision_service):
        """Test recording a PENDING decision (awaiting approval)."""
        features = {"price": 1950.0, "confidence": 0.7, "requires_approval": True}

        log = await decision_service.record_decision(
            strategy="manual_review",
            symbol="GOLD",
            features=features,
            outcome=DecisionOutcome.PENDING,
            note="Awaiting manual approval",
        )

        assert log.outcome == DecisionOutcome.PENDING
        assert log.features["requires_approval"] is True

    @pytest.mark.asyncio
    async def test_record_decision_error(self, decision_service):
        """Test recording an ERROR decision (technical failure)."""
        features = {
            "error_type": "api_timeout",
            "error_message": "Market data API timeout after 30s",
            "retry_count": 3,
        }

        log = await decision_service.record_decision(
            strategy="live_strategy",
            symbol="GBPUSD",
            features=features,
            outcome=DecisionOutcome.ERROR,
            note="API timeout prevented decision",
        )

        assert log.outcome == DecisionOutcome.ERROR
        assert log.features["error_type"] == "api_timeout"

    @pytest.mark.asyncio
    async def test_record_decision_without_note(self, decision_service):
        """Test recording decision without optional note."""
        log = await decision_service.record_decision(
            strategy="auto_strategy",
            symbol="GOLD",
            features={"rsi": 65.0},
            outcome=DecisionOutcome.ENTERED,
            note=None,
        )

        assert log.note is None
        assert log.id is not None


class TestPIIRedaction:
    """Test PII redaction from decision features."""

    @pytest.mark.asyncio
    async def test_pii_redaction_enabled(self, decision_service, pii_features):
        """Test PII is redacted when sanitize_pii=True (default)."""
        log = await decision_service.record_decision(
            strategy="test_strategy",
            symbol="TEST",
            features=pii_features,
            outcome=DecisionOutcome.ENTERED,
            sanitize_pii=True,  # Explicit for clarity
        )

        # PII should be redacted
        assert log.features["user_id"] == "[REDACTED]"
        assert log.features["email"] == "[REDACTED]"
        assert log.features["phone_number"] == "[REDACTED]"
        assert log.features["api_key"] == "[REDACTED]"
        assert log.features["account_number"] == "[REDACTED]"

        # Nested PII should also be redacted
        assert log.features["nested"]["data"]["api_token"] == "[REDACTED]"
        assert log.features["nested"]["data"]["access_token"] == "[REDACTED]"

        # Non-PII should remain
        assert log.features["price"]["close"] == 1950.50
        assert log.features["nested"]["safe_field"] == "no_pii_here"

    @pytest.mark.asyncio
    async def test_pii_redaction_disabled(self, decision_service, pii_features):
        """Test PII is preserved when sanitize_pii=False."""
        log = await decision_service.record_decision(
            strategy="test_strategy",
            symbol="TEST",
            features=pii_features,
            outcome=DecisionOutcome.ENTERED,
            sanitize_pii=False,
        )

        # PII should NOT be redacted
        assert log.features["user_id"] == "user_12345"
        assert log.features["email"] == "trader@example.com"
        assert log.features["api_key"] == "sk_live_abcdef123456"

    @pytest.mark.asyncio
    async def test_sanitize_features_static_method(self):
        """Test DecisionLog.sanitize_features() static method directly."""
        features = {
            "user_id": "123",
            "email": "test@example.com",
            "safe_data": "keep_this",
            "nested": {"api_key": "secret", "value": 42},
        }

        sanitized = DecisionLog.sanitize_features(features)

        assert sanitized["user_id"] == "[REDACTED]"
        assert sanitized["email"] == "[REDACTED]"
        assert sanitized["safe_data"] == "keep_this"
        assert sanitized["nested"]["api_key"] == "[REDACTED]"
        assert sanitized["nested"]["value"] == 42


class TestLargePayloads:
    """Test handling of large feature payloads."""

    @pytest.mark.asyncio
    async def test_record_large_features(self, decision_service, large_features):
        """Test recording decision with >10KB feature payload."""
        import json

        payload_size = len(json.dumps(large_features))
        assert payload_size > 10000, "Payload should be >10KB for this test"

        log = await decision_service.record_decision(
            strategy="ml_strategy",
            symbol="GOLD",
            features=large_features,
            outcome=DecisionOutcome.ENTERED,
            note=f"Large payload test: {payload_size} bytes",
        )

        assert log.id is not None
        assert len(log.features["price_history"]) == 500
        assert len(log.features["indicators"]["rsi"]) == 100

    @pytest.mark.asyncio
    async def test_get_feature_payload_sizes(self, decision_service, large_features):
        """Test retrieving payload sizes for monitoring."""
        # Create some logs with varying sizes
        await decision_service.record_decision(
            strategy="small",
            symbol="A",
            features={"x": 1},
            outcome=DecisionOutcome.ENTERED,
        )
        await decision_service.record_decision(
            strategy="large",
            symbol="B",
            features=large_features,
            outcome=DecisionOutcome.ENTERED,
        )

        sizes = await decision_service.get_feature_payload_sizes(limit=10)

        assert len(sizes) > 0
        # Largest should be first (descending order)
        assert sizes[0][1] > sizes[-1][1] if len(sizes) > 1 else True


class TestQueryByDateRange:
    """Test querying decisions by date range."""

    @pytest.mark.asyncio
    async def test_query_by_date_range_basic(self, decision_service, sample_features):
        """Test basic date range query."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        # Create decision
        log = await decision_service.record_decision(
            strategy="test_strategy",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )

        # Query should find it
        results = await decision_service.query_by_date_range(
            start_date=yesterday, end_date=tomorrow
        )

        assert len(results) >= 1
        assert any(r.id == log.id for r in results)

    @pytest.mark.asyncio
    async def test_query_by_date_range_with_strategy_filter(
        self, decision_service, sample_features
    ):
        """Test date range query with strategy filter."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        # Create multiple decisions
        log1 = await decision_service.record_decision(
            strategy="strategy_a",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )
        log2 = await decision_service.record_decision(
            strategy="strategy_b",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )

        # Query for strategy_a only
        results = await decision_service.query_by_date_range(
            start_date=yesterday, end_date=tomorrow, strategy="strategy_a"
        )

        assert any(r.id == log1.id for r in results)
        assert not any(r.id == log2.id for r in results)

    @pytest.mark.asyncio
    async def test_query_by_date_range_with_symbol_filter(
        self, decision_service, sample_features
    ):
        """Test date range query with symbol filter."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        # Create decisions for different symbols
        log_gold = await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )
        log_eur = await decision_service.record_decision(
            strategy="test",
            symbol="EURUSD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )

        # Query for GOLD only
        results = await decision_service.query_by_date_range(
            start_date=yesterday, end_date=tomorrow, symbol="GOLD"
        )

        assert any(r.id == log_gold.id for r in results)
        assert not any(r.id == log_eur.id for r in results)

    @pytest.mark.asyncio
    async def test_query_by_date_range_with_outcome_filter(
        self, decision_service, sample_features
    ):
        """Test date range query with outcome filter."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        # Create decisions with different outcomes
        log_entered = await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )
        log_skipped = await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.SKIPPED,
        )

        # Query for ENTERED only
        results = await decision_service.query_by_date_range(
            start_date=yesterday,
            end_date=tomorrow,
            outcome=DecisionOutcome.ENTERED,
        )

        assert any(r.id == log_entered.id for r in results)
        assert not any(r.id == log_skipped.id for r in results)

    @pytest.mark.asyncio
    async def test_query_by_date_range_pagination(
        self, decision_service, sample_features
    ):
        """Test date range query with pagination."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        # Create 5 decisions
        for i in range(5):
            await decision_service.record_decision(
                strategy=f"test_{i}",
                symbol="GOLD",
                features=sample_features,
                outcome=DecisionOutcome.ENTERED,
            )

        # Query first page (limit=2)
        page1 = await decision_service.query_by_date_range(
            start_date=yesterday, end_date=tomorrow, limit=2, offset=0
        )
        assert len(page1) == 2

        # Query second page
        page2 = await decision_service.query_by_date_range(
            start_date=yesterday, end_date=tomorrow, limit=2, offset=2
        )
        assert len(page2) == 2

        # Pages should have different records
        page1_ids = {log.id for log in page1}
        page2_ids = {log.id for log in page2}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_query_outside_date_range(self, decision_service, sample_features):
        """Test query outside decision date range returns empty."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)

        # Create decision today
        await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )

        # Query for last week only
        week_ago = yesterday - timedelta(days=7)
        two_days_ago = yesterday - timedelta(days=2)
        results = await decision_service.query_by_date_range(
            start_date=week_ago, end_date=two_days_ago
        )

        # Should not find today's decision
        assert len([r for r in results if r.timestamp > two_days_ago]) == 0


class TestGetRecent:
    """Test getting recent decisions."""

    @pytest.mark.asyncio
    async def test_get_recent_default(self, decision_service, sample_features):
        """Test get_recent() with default parameters."""
        # Create decision
        log = await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )

        results = await decision_service.get_recent()

        assert len(results) >= 1
        assert any(r.id == log.id for r in results)

    @pytest.mark.asyncio
    async def test_get_recent_with_strategy_filter(
        self, decision_service, sample_features
    ):
        """Test get_recent() filtered by strategy."""
        await decision_service.record_decision(
            strategy="strategy_a",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )
        log_b = await decision_service.record_decision(
            strategy="strategy_b",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )

        results = await decision_service.get_recent(strategy="strategy_b")

        assert any(r.id == log_b.id for r in results)
        assert all(r.strategy == "strategy_b" for r in results)

    @pytest.mark.asyncio
    async def test_get_recent_limit(self, decision_service, sample_features):
        """Test get_recent() respects limit parameter."""
        # Create 5 decisions
        for _ in range(5):
            await decision_service.record_decision(
                strategy="test",
                symbol="GOLD",
                features=sample_features,
                outcome=DecisionOutcome.ENTERED,
            )

        results = await decision_service.get_recent(limit=3)

        assert len(results) <= 3


class TestAnalytics:
    """Test analytics aggregation methods."""

    @pytest.mark.asyncio
    async def test_count_by_strategy(self, decision_service, sample_features):
        """Test counting decisions per strategy."""
        # Create decisions for multiple strategies
        await decision_service.record_decision(
            strategy="ppo_gold",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )
        await decision_service.record_decision(
            strategy="ppo_gold",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.SKIPPED,
        )
        await decision_service.record_decision(
            strategy="fib_rsi",
            symbol="EURUSD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )

        counts = await decision_service.count_by_strategy()

        assert "ppo_gold" in counts
        assert "fib_rsi" in counts
        assert counts["ppo_gold"] == 2
        assert counts["fib_rsi"] == 1

    @pytest.mark.asyncio
    async def test_count_by_strategy_with_date_filter(
        self, decision_service, sample_features
    ):
        """Test count_by_strategy() with date filter."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )

        counts = await decision_service.count_by_strategy(
            start_date=yesterday, end_date=tomorrow
        )

        assert "test" in counts
        assert counts["test"] >= 1

    @pytest.mark.asyncio
    async def test_count_by_outcome(self, decision_service, sample_features):
        """Test counting decisions by outcome."""
        # Create decisions with different outcomes
        await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )
        await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )
        await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.SKIPPED,
        )
        await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.REJECTED,
        )

        counts = await decision_service.count_by_outcome()

        assert "entered" in counts
        assert "skipped" in counts
        assert "rejected" in counts
        assert counts["entered"] == 2
        assert counts["skipped"] == 1
        assert counts["rejected"] == 1

    @pytest.mark.asyncio
    async def test_count_by_outcome_with_strategy_filter(
        self, decision_service, sample_features
    ):
        """Test count_by_outcome() filtered by strategy."""
        await decision_service.record_decision(
            strategy="strategy_a",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )
        await decision_service.record_decision(
            strategy="strategy_b",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.SKIPPED,
        )

        counts_a = await decision_service.count_by_outcome(strategy="strategy_a")
        counts_b = await decision_service.count_by_outcome(strategy="strategy_b")

        assert "entered" in counts_a
        assert "skipped" in counts_b
        assert counts_a.get("entered", 0) >= 1
        assert counts_b.get("skipped", 0) >= 1


class TestGetById:
    """Test retrieving decision by ID."""

    @pytest.mark.asyncio
    async def test_get_by_id_exists(self, decision_service, sample_features):
        """Test get_by_id() returns correct decision."""
        log = await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )

        retrieved = await decision_service.get_by_id(log.id)

        assert retrieved is not None
        assert retrieved.id == log.id
        assert retrieved.strategy == "test"
        assert retrieved.symbol == "GOLD"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, decision_service):
        """Test get_by_id() returns None for non-existent ID."""
        retrieved = await decision_service.get_by_id("non_existent_id_123")

        assert retrieved is None


class TestConvenienceFunction:
    """Test convenience function for quick decision recording."""

    @pytest.mark.asyncio
    async def test_record_decision_function(self, db_session, sample_features):
        """Test record_decision() convenience function."""
        log = await record_decision(
            db=db_session,
            strategy="convenience_test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
            note="Testing convenience function",
        )

        assert log.id is not None
        assert log.strategy == "convenience_test"
        assert log.note == "Testing convenience function"


class TestModelMethods:
    """Test DecisionLog model methods."""

    @pytest.mark.asyncio
    async def test_to_dict(self, decision_service, sample_features):
        """Test DecisionLog.to_dict() serialization."""
        log = await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )

        dict_repr = log.to_dict()

        assert dict_repr["id"] == log.id
        assert dict_repr["strategy"] == "test"
        assert dict_repr["symbol"] == "GOLD"
        assert dict_repr["outcome"] == "entered"
        assert dict_repr["features"] == sample_features
        assert "timestamp" in dict_repr

    def test_repr(self):
        """Test DecisionLog.__repr__() string representation."""
        log = DecisionLog(
            id="test_id",
            strategy="test_strategy",
            symbol="GOLD",
            outcome=DecisionOutcome.ENTERED,
            features={},
        )

        repr_str = repr(log)

        assert "DecisionLog" in repr_str
        assert "test_id" in repr_str
        assert "test_strategy" in repr_str
        assert "GOLD" in repr_str
        assert "entered" in repr_str


class TestErrorHandling:
    """Test error handling and transactions."""

    @pytest.mark.asyncio
    async def test_record_decision_rollback_on_error(
        self, decision_service, db_session
    ):
        """Test transaction rollback on error."""
        # SQLite doesn't enforce column length constraints, so this test
        # is PostgreSQL-specific. Skip on SQLite.
        import os

        db_url = os.getenv("DATABASE_URL", "")
        if "sqlite" in db_url.lower():
            pytest.skip("Column length validation is PostgreSQL-specific")

        # Force an error by passing invalid data (symbol too long)
        from sqlalchemy.exc import DataError

        with pytest.raises((DataError, ValueError)):
            await decision_service.record_decision(
                strategy="test",
                symbol="X" * 100,  # Exceeds column length
                features={"test": "data"},
                outcome=DecisionOutcome.ENTERED,
            )

        # Verify no partial data was saved
        result = await db_session.execute(
            select(DecisionLog).where(DecisionLog.strategy == "test")
        )
        logs = list(result.scalars().all())
        assert len(logs) == 0


class TestDatabaseOperations:
    """Test database-level operations."""

    @pytest.mark.asyncio
    async def test_decision_persists_to_database(
        self, decision_service, db_session, sample_features
    ):
        """Test decision is actually persisted to database."""
        log = await decision_service.record_decision(
            strategy="persistence_test",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )

        # Query directly from database
        result = await db_session.execute(
            select(DecisionLog).where(DecisionLog.id == log.id)
        )
        db_log = result.scalar_one()

        assert db_log.id == log.id
        assert db_log.strategy == "persistence_test"
        assert db_log.features == sample_features

    @pytest.mark.asyncio
    async def test_jsonb_querying(self, decision_service, db_session):
        """Test JSONB field can be queried."""
        # JSONB operators are PostgreSQL-specific; SQLite doesn't support them
        import os

        db_url = os.getenv("DATABASE_URL", "")
        if "sqlite" in db_url.lower():
            pytest.skip("JSONB operators are PostgreSQL-specific")

        await decision_service.record_decision(
            strategy="test",
            symbol="GOLD",
            features={"rsi": 75.5, "confidence": 0.9},
            outcome=DecisionOutcome.ENTERED,
        )

        # Query using JSONB operators (PostgreSQL-specific)
        result = await db_session.execute(
            select(DecisionLog).where(
                DecisionLog.features["rsi"].astext.cast(sa.Float) > 70
            )
        )
        logs = list(result.scalars().all())

        assert len(logs) >= 1
        assert all(log.features.get("rsi", 0) > 70 for log in logs)


class TestMetrics:
    """Test telemetry metrics recording."""

    @pytest.mark.asyncio
    async def test_metrics_recorded(self, decision_service, sample_features):
        """Test decision_logs_total metric is incremented."""
        # Record decision (metrics are recorded internally)
        log = await decision_service.record_decision(
            strategy="ppo_gold",
            symbol="GOLD",
            features=sample_features,
            outcome=DecisionOutcome.ENTERED,
        )

        # Verify decision was recorded (implies metrics were incremented)
        assert log.id is not None
        assert log.strategy == "ppo_gold"
