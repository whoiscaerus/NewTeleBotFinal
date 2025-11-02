"""
Live Positions Service - Query and Cache MT5 Positions

Implements:
- Fetch live positions from MT5
- Account info caching with TTL
- P&L calculations
- Error handling and fallback caching
"""

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship

from backend.app.accounts.service import AccountLinkingService
from backend.app.core.db import Base
from backend.app.core.errors import NotFoundError, ValidationError
from backend.app.trading.mt5.session import MT5SessionManager

logger = logging.getLogger(__name__)


# ============================================================================
# DATABASE MODELS
# ============================================================================


class LivePosition(Base):
    """
    Live position snapshot for portfolio tracking.

    Represents open MT5 positions cached from EA polls.
    Linked to accounts (not users) for multi-account tracking.
    Different from reconciliation.PositionSnapshot which tracks account-level metrics.
    """

    __tablename__ = "live_positions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_link_id = Column(String(36), ForeignKey("account_links.id"), nullable=False)
    ticket = Column(String(255), nullable=False)  # MT5 ticket number
    instrument = Column(String(20), nullable=False)
    side = Column(Integer, nullable=False)  # 0=buy, 1=sell
    volume = Column(Numeric(12, 2), nullable=False)
    entry_price = Column(Numeric(20, 6), nullable=False)
    current_price = Column(Numeric(20, 6), nullable=False)
    stop_loss = Column(Numeric(20, 6), nullable=True)
    take_profit = Column(Numeric(20, 6), nullable=True)
    pnl_points = Column(Numeric(10, 2), nullable=False)  # Points profit/loss
    pnl_usd = Column(Numeric(12, 2), nullable=False)  # USD profit/loss
    pnl_percent = Column(Numeric(8, 4), nullable=False)  # % profit/loss
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    opened_at = Column(DateTime, nullable=True)  # MT5 open time
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    account_link = relationship("AccountLink")

    # Indexes
    __table_args__ = (
        Index("ix_live_positions_account_time", "account_link_id", "created_at"),
        Index("ix_live_positions_instrument", "instrument"),
    )

    def __repr__(self):
        return f"<LivePosition {self.id}: {self.instrument} {self.side} PnL={self.pnl_usd}>"


# ============================================================================
# PYDANTIC SCHEMAS (No DB Models - Using shared PositionSnapshot from reconciliation)
# ============================================================================


class PositionOut(BaseModel):
    """Live position snapshot response."""

    id: str
    ticket: str
    instrument: str
    side: int  # 0=buy, 1=sell
    volume: float
    entry_price: float
    current_price: float
    stop_loss: float | None
    take_profit: float | None
    pnl_points: float
    pnl_usd: float
    pnl_percent: float
    opened_at: datetime | None

    class Config:
        from_attributes = True


class PortfolioOut(BaseModel):
    """Full portfolio snapshot."""

    account_id: str
    balance: float
    equity: float
    free_margin: float
    margin_level: float | None
    drawdown_percent: float | None
    open_positions_count: int
    total_pnl_usd: float
    total_pnl_percent: float
    positions: list[PositionOut]
    last_updated: datetime


# ============================================================================
# SERVICE
# ============================================================================


class PositionsService:
    """
    Manages live position tracking.

    Provides:
    - Position fetching from MT5
    - P&L calculations
    - Portfolio aggregation
    - Caching with TTL
    """

    def __init__(
        self,
        db_session: AsyncSession,
        account_service: AccountLinkingService,
        mt5_manager: MT5SessionManager,
        cache_ttl_seconds: int = 30,
    ):
        """
        Initialize service.

        Args:
            db_session: AsyncSession for database
            account_service: AccountLinkingService for account lookup
            mt5_manager: MT5SessionManager for data fetch
            cache_ttl_seconds: Cache time-to-live (default 30s)
        """
        self.db = db_session
        self.accounts = account_service
        self.mt5 = mt5_manager
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)

    async def get_positions(
        self,
        account_link_id: str,
        force_refresh: bool = False,
    ) -> PortfolioOut:
        """
        Get live positions for account.

        Uses cached positions if fresh, otherwise fetches from MT5.

        Args:
            account_link_id: Account link ID
            force_refresh: Skip cache and fetch fresh

        Returns:
            Portfolio with positions list

        Raises:
            NotFoundError: If account not found
            ValidationError: If MT5 fetch fails
        """
        try:
            # Get account link (validates account exists)
            await self.accounts.get_account(account_link_id)

            # Get account info (balance, equity, drawdown)
            account_info = await self.accounts.get_account_info(
                account_link_id, force_refresh=force_refresh
            )

            # Get positions
            positions = await self._fetch_positions(
                account_link_id, force_refresh=force_refresh
            )

            # Calculate portfolio totals
            total_pnl_usd = sum(float(p.pnl_usd) for p in positions)
            total_pnl_percent = 0
            if account_info.equity and account_info.balance:
                total_pnl_percent = (total_pnl_usd / float(account_info.balance)) * 100

            logger.info(
                "Portfolio fetched",
                extra={
                    "account_id": account_link_id,
                    "positions_count": len(positions),
                    "total_pnl_usd": total_pnl_usd,
                    "equity": account_info.equity,
                },
            )

            return PortfolioOut(
                account_id=account_link_id,
                balance=float(account_info.balance or 0),
                equity=float(account_info.equity or 0),
                free_margin=float(account_info.free_margin or 0),
                margin_level=(
                    float(account_info.margin_level or 0)
                    if account_info.margin_level
                    else None
                ),
                drawdown_percent=float(account_info.drawdown_percent or 0),
                open_positions_count=len(positions),
                total_pnl_usd=total_pnl_usd,
                total_pnl_percent=total_pnl_percent,
                positions=[PositionOut.model_validate(p) for p in positions],
                last_updated=account_info.last_updated,
            )

        except Exception as e:
            logger.error(f"Error getting portfolio: {e}", exc_info=True)
            raise

    async def get_user_positions(
        self,
        user_id: str,
        force_refresh: bool = False,
    ) -> PortfolioOut:
        """
        Get positions for user's primary account.

        Args:
            user_id: User ID
            force_refresh: Skip cache

        Returns:
            Portfolio with positions

        Raises:
            NotFoundError: If user has no primary account
        """
        primary = await self.accounts.get_primary_account(user_id)
        if not primary:
            raise NotFoundError(f"No primary account for user: {user_id}")

        return await self.get_positions(primary.id, force_refresh=force_refresh)

    async def _fetch_positions(
        self,
        account_link_id: str,
        force_refresh: bool = False,
    ) -> list[LivePosition]:
        """
        Fetch positions from MT5 or cache.

        Args:
            account_link_id: Account link ID
            force_refresh: Skip cache

        Returns:
            List of LivePosition objects

        Raises:
            ValidationError: If MT5 fetch fails
        """
        try:
            # Get account link
            link = await self.accounts.get_account(account_link_id)

            # Check cache
            if not force_refresh:
                result = await self.db.execute(
                    select(LivePosition)
                    .where(LivePosition.account_link_id == account_link_id)
                    .order_by(LivePosition.updated_at.desc())
                    .limit(1)
                )
                latest = result.scalar()
                if latest:
                    age = datetime.utcnow() - latest.updated_at
                    if age < self.cache_ttl:
                        # Fetch all recent positions
                        result = await self.db.execute(
                            select(LivePosition)
                            .where(LivePosition.account_link_id == account_link_id)
                            .order_by(LivePosition.instrument)
                        )
                        logger.info(
                            f"Positions from cache (age: {age.total_seconds():.1f}s)",
                            extra={"account_id": account_link_id},
                        )
                        return result.scalars().all()

            # Fetch fresh from MT5
            logger.info(
                "Fetching positions from MT5", extra={"account_id": account_link_id}
            )
            mt5_positions = await self.mt5.get_positions(link.mt5_login)

            if not mt5_positions:
                logger.info(
                    "No positions returned from MT5",
                    extra={"account_id": account_link_id},
                )
                # Clear old positions and return empty
                await self.db.execute(
                    select(LivePosition).where(
                        LivePosition.account_link_id == account_link_id
                    )
                )
                return []

            # Store positions
            stored = []
            for mt5_pos in mt5_positions:
                pos = LivePosition(
                    id=str(uuid4()),
                    account_link_id=account_link_id,
                    ticket=str(mt5_pos.get("ticket", "")),
                    instrument=mt5_pos.get("symbol", ""),
                    side=0 if mt5_pos.get("type") == "buy" else 1,
                    volume=float(mt5_pos.get("volume", 0)),
                    entry_price=float(mt5_pos.get("open_price", 0)),
                    current_price=float(mt5_pos.get("current_price", 0)),
                    stop_loss=(
                        float(mt5_pos.get("sl", 0)) if mt5_pos.get("sl") else None
                    ),
                    take_profit=(
                        float(mt5_pos.get("tp", 0)) if mt5_pos.get("tp") else None
                    ),
                    pnl_points=float(mt5_pos.get("pnl_points", 0)),
                    pnl_usd=float(mt5_pos.get("pnl", 0)),
                    pnl_percent=float(mt5_pos.get("pnl_percent", 0)),
                    opened_at=mt5_pos.get("open_time"),
                )
                self.db.add(pos)
                stored.append(pos)

            await self.db.commit()

            logger.info(
                "Positions fetched and stored",
                extra={
                    "account_id": account_link_id,
                    "count": len(stored),
                },
            )

            return stored

        except Exception as e:
            logger.error(f"Error fetching positions: {e}", exc_info=True)
            raise ValidationError(f"Failed to fetch positions: {str(e)}")
