"""Feature Store service.

Provides put/get operations for feature snapshots with efficient querying.

Examples:
    Store features:
        store = FeatureStore(session)
        await store.put_features(
            symbol="GOLD",
            timestamp=datetime.now(UTC),
            features={"rsi_14": 65.3, "roc_10": 0.012},
            quality_score=0.95
        )

    Get latest features:
        snapshot = await store.get_latest("GOLD")
        rsi = snapshot.features["rsi_14"]

    Query time range:
        snapshots = await store.get_features(
            symbol="GOLD",
            start_time=yesterday,
            end_time=now
        )
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.features.models import FeatureSnapshot

logger = logging.getLogger(__name__)


class FeatureStore:
    """Feature Store service.

    Manages feature snapshot persistence and retrieval.
    """

    def __init__(self, session: AsyncSession):
        """Initialize feature store.

        Args:
            session: Database session
        """
        self.session = session

    async def put_features(
        self,
        symbol: str,
        timestamp: datetime,
        features: dict[str, Any],
        quality_score: float = 1.0,
    ) -> FeatureSnapshot:
        """Store a feature snapshot.

        Args:
            symbol: Trading instrument
            timestamp: Feature computation timestamp (UTC)
            features: Dict of feature name -> value
            quality_score: Overall quality (0.0-1.0)

        Returns:
            Created FeatureSnapshot

        Raises:
            ValueError: If quality_score not in [0, 1]

        Examples:
            >>> snapshot = await store.put_features(
            ...     symbol="GOLD",
            ...     timestamp=datetime(2025, 11, 9, 12, 0, tzinfo=UTC),
            ...     features={"rsi_14": 65.3, "roc_10": 0.012, "atr_14": 12.5},
            ...     quality_score=0.95
            ... )
            >>> snapshot.id
            1
        """
        if not (0.0 <= quality_score <= 1.0):
            raise ValueError(
                f"quality_score must be in [0.0, 1.0], got {quality_score}"
            )

        snapshot = FeatureSnapshot(
            symbol=symbol,
            timestamp=timestamp,
            features=features,
            quality_score=quality_score,
        )

        self.session.add(snapshot)
        await self.session.commit()
        await self.session.refresh(snapshot)

        logger.info(
            f"Stored feature snapshot for {symbol}",
            extra={
                "symbol": symbol,
                "timestamp": timestamp.isoformat(),
                "feature_count": len(features),
                "quality_score": quality_score,
            },
        )

        return snapshot

    async def get_latest(self, symbol: str) -> FeatureSnapshot | None:
        """Get the latest feature snapshot for a symbol.

        Args:
            symbol: Trading instrument

        Returns:
            Latest FeatureSnapshot or None

        Examples:
            >>> snapshot = await store.get_latest("GOLD")
            >>> snapshot.features["rsi_14"]
            65.3
        """
        stmt = (
            select(FeatureSnapshot)
            .where(FeatureSnapshot.symbol == symbol)
            .order_by(desc(FeatureSnapshot.timestamp))
            .limit(1)
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_features(
        self,
        symbol: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[FeatureSnapshot]:
        """Get feature snapshots for a symbol in a time range.

        Args:
            symbol: Trading instrument
            start_time: Start of time range (inclusive, optional)
            end_time: End of time range (inclusive, optional)
            limit: Maximum number of results (optional)

        Returns:
            List of FeatureSnapshot ordered by timestamp descending

        Examples:
            >>> snapshots = await store.get_features(
            ...     symbol="GOLD",
            ...     start_time=datetime(2025, 11, 9, 0, 0, tzinfo=UTC),
            ...     end_time=datetime(2025, 11, 9, 23, 59, tzinfo=UTC),
            ...     limit=100
            ... )
            >>> len(snapshots)
            96  # 15-min bars in a day
        """
        stmt = select(FeatureSnapshot).where(FeatureSnapshot.symbol == symbol)

        if start_time:
            stmt = stmt.where(FeatureSnapshot.timestamp >= start_time)

        if end_time:
            stmt = stmt.where(FeatureSnapshot.timestamp <= end_time)

        stmt = stmt.order_by(desc(FeatureSnapshot.timestamp))

        if limit:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, snapshot_id: int) -> FeatureSnapshot | None:
        """Get a feature snapshot by ID.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            FeatureSnapshot or None

        Examples:
            >>> snapshot = await store.get_by_id(1)
            >>> snapshot.symbol
            'GOLD'
        """
        stmt = select(FeatureSnapshot).where(FeatureSnapshot.id == snapshot_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_snapshots(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """Count feature snapshots matching criteria.

        Args:
            symbol: Trading instrument (optional)
            start_time: Start of time range (optional)
            end_time: End of time range (optional)

        Returns:
            Count of matching snapshots

        Examples:
            >>> count = await store.count_snapshots(symbol="GOLD")
            >>> count
            2400  # 10 days of 15-min bars
        """
        from sqlalchemy import func

        stmt = select(func.count(FeatureSnapshot.id))

        if symbol:
            stmt = stmt.where(FeatureSnapshot.symbol == symbol)

        if start_time:
            stmt = stmt.where(FeatureSnapshot.timestamp >= start_time)

        if end_time:
            stmt = stmt.where(FeatureSnapshot.timestamp <= end_time)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def delete_old_snapshots(self, symbol: str, older_than: datetime) -> int:
        """Delete old snapshots for cleanup.

        Args:
            symbol: Trading instrument
            older_than: Delete snapshots older than this datetime

        Returns:
            Number of snapshots deleted

        Examples:
            >>> # Delete snapshots older than 30 days
            >>> deleted = await store.delete_old_snapshots(
            ...     symbol="GOLD",
            ...     older_than=datetime.now(UTC) - timedelta(days=30)
            ... )
            >>> deleted
            1200
        """
        from sqlalchemy import delete as sql_delete

        stmt = (
            sql_delete(FeatureSnapshot)
            .where(FeatureSnapshot.symbol == symbol)
            .where(FeatureSnapshot.timestamp < older_than)
        )

        result = await self.session.execute(stmt)
        await self.session.commit()

        deleted_count = result.rowcount

        logger.info(
            f"Deleted {deleted_count} old snapshots for {symbol}",
            extra={
                "symbol": symbol,
                "older_than": older_than.isoformat(),
                "deleted_count": deleted_count,
            },
        )

        return deleted_count
