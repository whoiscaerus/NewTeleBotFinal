"""Decision logging service for trade audit trails.

Provides:
- Decision recording with automatic PII redaction
- Query by date range, strategy, symbol, outcome
- Analytics aggregation (decisions per strategy, outcomes distribution)
- Telemetry integration
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.observability.metrics import metrics
from backend.app.strategy.logs.models import DecisionLog, DecisionOutcome

logger = logging.getLogger(__name__)


class DecisionLogService:
    """Service for recording and querying trading decisions."""

    def __init__(self, db: AsyncSession):
        """Initialize decision log service.

        Args:
            db: Async database session
        """
        self.db = db

    async def record_decision(
        self,
        strategy: str,
        symbol: str,
        features: dict[str, Any],
        outcome: DecisionOutcome,
        note: str | None = None,
        sanitize_pii: bool = True,
    ) -> DecisionLog:
        """Record a trading decision with full context.

        Args:
            strategy: Strategy name (e.g., "ppo_gold", "fib_rsi_eur")
            symbol: Trading symbol (e.g., "GOLD", "EURUSD")
            features: Complete feature set used in decision
            outcome: Decision outcome (entered/skipped/rejected/pending/error)
            note: Optional human-readable rationale
            sanitize_pii: Whether to redact PII from features (default: True)

        Returns:
            Created DecisionLog instance

        Example:
            >>> service = DecisionLogService(db)
            >>> features = {
            ...     "price": {"close": 1950.50},
            ...     "indicators": {"rsi": 65.3, "macd": 0.52},
            ...     "thresholds": {"rsi_overbought": 70}
            ... }
            >>> log = await service.record_decision(
            ...     strategy="ppo_gold",
            ...     symbol="GOLD",
            ...     features=features,
            ...     outcome=DecisionOutcome.ENTERED,
            ...     note="RSI approaching overbought, MACD bullish"
            ... )
        """
        try:
            # Sanitize PII if requested
            if sanitize_pii:
                features = DecisionLog.sanitize_features(features)

            # Create decision log
            decision_log = DecisionLog(
                id=str(uuid4()),
                timestamp=datetime.utcnow(),
                strategy=strategy,
                symbol=symbol,
                features=features,
                outcome=outcome,
                note=note,
            )

            self.db.add(decision_log)
            await self.db.commit()
            await self.db.refresh(decision_log)

            # Record telemetry
            metrics.decision_logs_total.labels(strategy=strategy).inc()

            logger.info(
                f"Recorded decision: strategy={strategy}, symbol={symbol}, "
                f"outcome={outcome.value}, id={decision_log.id}"
            )

            return decision_log

        except Exception as e:
            await self.db.rollback()
            logger.error(
                f"Failed to record decision: strategy={strategy}, symbol={symbol}, "
                f"outcome={outcome.value}, error={e}",
                exc_info=True,
            )
            raise

    async def get_by_id(self, decision_id: str) -> DecisionLog | None:
        """Retrieve decision log by ID.

        Args:
            decision_id: Decision log UUID

        Returns:
            DecisionLog or None if not found
        """
        result = await self.db.execute(
            select(DecisionLog).where(DecisionLog.id == decision_id)
        )
        return result.scalar_one_or_none()

    async def query_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        strategy: str | None = None,
        symbol: str | None = None,
        outcome: DecisionOutcome | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DecisionLog]:
        """Query decisions by date range with optional filters.

        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            strategy: Optional strategy name filter
            symbol: Optional symbol filter
            outcome: Optional outcome filter
            limit: Maximum results (default: 100)
            offset: Pagination offset (default: 0)

        Returns:
            List of DecisionLog instances
        """
        query = select(DecisionLog).where(
            DecisionLog.timestamp >= start_date, DecisionLog.timestamp <= end_date
        )

        if strategy:
            query = query.where(DecisionLog.strategy == strategy)
        if symbol:
            query = query.where(DecisionLog.symbol == symbol)
        if outcome:
            query = query.where(DecisionLog.outcome == outcome)

        query = query.order_by(DecisionLog.timestamp.desc()).limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_recent(
        self,
        strategy: str | None = None,
        symbol: str | None = None,
        limit: int = 10,
    ) -> list[DecisionLog]:
        """Get recent decisions.

        Args:
            strategy: Optional strategy filter
            symbol: Optional symbol filter
            limit: Maximum results (default: 10)

        Returns:
            List of recent DecisionLog instances
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)  # Last 30 days

        return await self.query_by_date_range(
            start_date=start_date,
            end_date=end_date,
            strategy=strategy,
            symbol=symbol,
            limit=limit,
        )

    async def count_by_strategy(
        self, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> dict[str, int]:
        """Count decisions per strategy.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary mapping strategy name to count
        """
        query = select(
            DecisionLog.strategy, func.count(DecisionLog.id).label("count")
        ).group_by(DecisionLog.strategy)

        if start_date:
            query = query.where(DecisionLog.timestamp >= start_date)
        if end_date:
            query = query.where(DecisionLog.timestamp <= end_date)

        result = await self.db.execute(query)
        return {row[0]: int(row[1]) for row in result}

    async def count_by_outcome(
        self,
        strategy: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, int]:
        """Count decisions by outcome.

        Args:
            strategy: Optional strategy filter
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary mapping outcome to count
        """
        query = select(
            DecisionLog.outcome, func.count(DecisionLog.id).label("count")
        ).group_by(DecisionLog.outcome)

        if strategy:
            query = query.where(DecisionLog.strategy == strategy)
        if start_date:
            query = query.where(DecisionLog.timestamp >= start_date)
        if end_date:
            query = query.where(DecisionLog.timestamp <= end_date)

        result = await self.db.execute(query)
        return {row[0].value: int(row[1]) for row in result}

    async def get_feature_payload_sizes(
        self, limit: int = 100
    ) -> list[tuple[str, int]]:
        """Get feature payload sizes for monitoring.

        Useful for identifying large payloads that might need optimization.

        Args:
            limit: Maximum results

        Returns:
            List of (decision_id, payload_size_bytes) tuples
        """
        # PostgreSQL function to get JSONB size
        query = select(
            DecisionLog.id,
            func.length(func.cast(DecisionLog.features, String)).label("size"),
        ).order_by(func.length(func.cast(DecisionLog.features, String)).desc())

        query = query.limit(limit)

        result = await self.db.execute(query)
        return [(row.id, row.size) for row in result]


# Convenience function for quick decision recording
async def record_decision(
    db: AsyncSession,
    strategy: str,
    symbol: str,
    features: dict[str, Any],
    outcome: DecisionOutcome,
    note: str | None = None,
    sanitize_pii: bool = True,
) -> DecisionLog:
    """Convenience function to record a decision.

    Args:
        db: Async database session
        strategy: Strategy name
        symbol: Trading symbol
        features: Feature dictionary
        outcome: Decision outcome
        note: Optional rationale
        sanitize_pii: Whether to redact PII

    Returns:
        Created DecisionLog instance

    Example:
        >>> log = await record_decision(
        ...     db=db,
        ...     strategy="ppo_gold",
        ...     symbol="GOLD",
        ...     features={"rsi": 65, "macd": 0.5},
        ...     outcome=DecisionOutcome.ENTERED
        ... )
    """
    service = DecisionLogService(db)
    return await service.record_decision(
        strategy=strategy,
        symbol=symbol,
        features=features,
        outcome=outcome,
        note=note,
        sanitize_pii=sanitize_pii,
    )
