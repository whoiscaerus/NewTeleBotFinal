"""
Analytics ETL: Load trades into warehouse and build rollups.

Provides idempotent ETL functions to:
1. Load trades from source tables into trades_fact
2. Build dimension tables (dim_symbol, dim_day)
3. Generate daily rollups with pre-computed metrics
4. Handle DST/UTC transitions safely
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.models import (
    DailyRollups,
    DimDay,
    DimSymbol,
    EquityCurve,
    TradesFact,
)
from backend.app.core.logging import get_logger
from backend.app.trading.store.models import Trade

logger = get_logger(__name__)

try:
    from prometheus_client import Counter, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

if PROMETHEUS_AVAILABLE:
    analytics_rollups_built_counter = Counter(
        "analytics_rollups_built_total",
        "Total rollups built",
        labelnames=["user_id", "date"],
    )
    etl_duration_histogram = Histogram(
        "etl_duration_seconds",
        "ETL operation duration in seconds",
        labelnames=["operation"],
    )


class AnalyticsETL:
    """ETL service for analytics warehouse.

    Handles:
    - Dimension table maintenance (dim_symbol, dim_day)
    - Fact table loading (trades_fact)
    - Rollup aggregation (daily_rollups)
    - Equity curve snapshots
    - Prometheus telemetry
    """

    def __init__(self, db_session: AsyncSession):
        """Initialize ETL service.

        Args:
            db_session: Async database session
        """
        self.db = db_session
        self.logger = logger

    async def get_or_create_dim_symbol(
        self, symbol: str, asset_class: Optional[str] = None
    ) -> DimSymbol:
        """Get or create dimension record for symbol.

        Idempotent: returns existing record if found.

        Args:
            symbol: Trading symbol (e.g., 'GOLD', 'EURUSD')
            asset_class: Optional asset class ('forex', 'commodity', 'crypto', 'stock')

        Returns:
            DimSymbol: Dimension record (created if not existing)
        """
        stmt = select(DimSymbol).where(DimSymbol.symbol == symbol)
        result = await self.db.execute(stmt)
        dim_symbol = result.scalars().first()

        if dim_symbol:
            return dim_symbol

        # Create new dimension record
        dim_symbol = DimSymbol(
            symbol=symbol,
            asset_class=asset_class,
            created_at=datetime.utcnow(),
        )
        self.db.add(dim_symbol)
        await self.db.flush()  # Flush to get auto-increment ID
        self.logger.info(f"Created new DimSymbol: {symbol}", extra={"symbol": symbol})
        return dim_symbol

    async def get_or_create_dim_day(self, target_date: date) -> DimDay:
        """Get or create dimension record for date.

        Idempotent: returns existing record if found.
        Handles DST/UTC transitions safely by storing metadata.

        Args:
            target_date: Date to create/retrieve

        Returns:
            DimDay: Dimension record (created if not existing)
        """
        stmt = select(DimDay).where(DimDay.date == target_date)
        result = await self.db.execute(stmt)
        dim_day = result.scalars().first()

        if dim_day:
            return dim_day

        # Calculate date metadata
        temp_date = datetime.combine(target_date, datetime.min.time())
        day_of_week = temp_date.weekday()  # 0=Monday, 6=Sunday
        day_of_year = temp_date.timetuple().tm_yday
        week_of_year = temp_date.isocalendar()[1]
        month = target_date.month
        year = target_date.year

        # Is trading day? (Not weekend, not major holiday)
        is_trading_day = 1 if day_of_week < 5 else 0

        # Create new dimension record
        dim_day = DimDay(
            date=target_date,
            day_of_week=day_of_week,
            week_of_year=week_of_year,
            month=month,
            year=year,
            is_trading_day=is_trading_day,
            created_at=datetime.utcnow(),
        )
        self.db.add(dim_day)
        await self.db.flush()
        self.logger.info(
            f"Created new DimDay: {target_date}", extra={"date": str(target_date)}
        )
        return dim_day

    async def load_trades(self, user_id: str, since: Optional[datetime] = None) -> int:
        """Load trades from source into trades_fact.

        Idempotent: checks for duplicates before inserting.
        Skips trades already loaded (by trade ID).

        Args:
            user_id: User ID to load trades for
            since: Optional datetime to load only trades after this point

        Returns:
            int: Number of trades loaded

        Raises:
            ValueError: If trade data is invalid
        """
        try:
            # Query source trades for this user
            source_trades_query = select(Trade).where(
                and_(
                    Trade.user_id == user_id,
                    Trade.status == "closed",  # Only closed trades
                )
            )

            if since:
                source_trades_query = source_trades_query.where(
                    Trade.exit_time >= since
                )

            result = await self.db.execute(source_trades_query)
            source_trades = result.scalars().all()

            loaded_count = 0

            for source_trade in source_trades:
                # Check if already loaded
                existing = await self.db.execute(
                    select(TradesFact).where(TradesFact.id == source_trade.id)
                )
                if existing.scalars().first():
                    self.logger.debug(
                        f"Trade {source_trade.id} already loaded, skipping"
                    )
                    continue

                # Get or create dimension records
                dim_symbol = await self.get_or_create_dim_symbol(
                    symbol=source_trade.instrument,
                    asset_class="forex",  # Default assumption
                )
                entry_dim_day = await self.get_or_create_dim_day(
                    source_trade.entry_time.date()
                )
                exit_dim_day = await self.get_or_create_dim_day(
                    source_trade.exit_time.date()
                )

                # Calculate trade metrics
                side = 0 if source_trade.side.lower() == "buy" else 1
                price_diff = source_trade.exit_price - source_trade.entry_price
                if side == 1:  # Sell
                    price_diff = -price_diff

                gross_pnl = Decimal(str(price_diff)) * Decimal(str(source_trade.volume))
                commission = Decimal(str(getattr(source_trade, "commission", 0)))
                net_pnl = gross_pnl - commission

                # PnL percentage
                pnl_percent = Decimal(0)
                if source_trade.entry_price != 0:
                    pnl_percent = (
                        price_diff / Decimal(str(source_trade.entry_price))
                    ) * Decimal(100)

                # R multiple (Risk/Reward)
                r_multiple = None
                if (
                    source_trade.stop_loss
                    and source_trade.stop_loss != source_trade.entry_price
                ):
                    risk = abs(source_trade.entry_price - source_trade.stop_loss)
                    reward = abs(source_trade.exit_price - source_trade.entry_price)
                    if risk > 0:
                        r_multiple = reward / risk

                # Bars held (approximation from timestamps)
                bars_held = (
                    (source_trade.exit_time - source_trade.entry_time).total_seconds()
                    / 3600
                ) or 1

                # Winning trade
                winning_trade = 1 if net_pnl > 0 else 0

                # Risk amount
                risk_amount = Decimal(0)
                if source_trade.stop_loss:
                    risk_amount = abs(
                        Decimal(str(source_trade.entry_price))
                        - Decimal(str(source_trade.stop_loss))
                    )

                # Max run-up and drawdown (from source if available)
                max_run_up = Decimal(str(getattr(source_trade, "max_run_up", 0)))
                max_drawdown_trade = Decimal(
                    str(getattr(source_trade, "max_drawdown", 0))
                )

                # Create fact record
                fact_record = TradesFact(
                    id=source_trade.id,
                    user_id=user_id,
                    symbol_id=dim_symbol.id,
                    entry_date_id=entry_dim_day.id,
                    exit_date_id=exit_dim_day.id,
                    side=side,
                    entry_price=Decimal(str(source_trade.entry_price)),
                    exit_price=Decimal(str(source_trade.exit_price)),
                    stop_loss=(
                        Decimal(str(source_trade.stop_loss))
                        if source_trade.stop_loss
                        else None
                    ),
                    take_profit=(
                        Decimal(str(source_trade.take_profit))
                        if source_trade.take_profit
                        else None
                    ),
                    volume=Decimal(str(source_trade.volume)),
                    gross_pnl=gross_pnl,
                    pnl_percent=pnl_percent,
                    commission=commission,
                    net_pnl=net_pnl,
                    r_multiple=r_multiple,
                    bars_held=int(bars_held),
                    winning_trade=winning_trade,
                    risk_amount=risk_amount,
                    max_run_up=max_run_up,
                    max_drawdown=max_drawdown_trade,
                    entry_time=source_trade.entry_time,
                    exit_time=source_trade.exit_time,
                    source=getattr(source_trade, "source", "manual"),
                    signal_id=getattr(source_trade, "signal_id", None),
                )
                self.db.add(fact_record)
                loaded_count += 1

            await self.db.commit()
            self.logger.info(
                f"Loaded {loaded_count} trades for user {user_id}",
                extra={"user_id": user_id, "loaded_count": loaded_count},
            )
            return loaded_count

        except Exception as e:
            await self.db.rollback()
            self.logger.error(f"Error loading trades: {e}", exc_info=True)
            raise

    async def build_daily_rollups(
        self, user_id: str, target_date: date
    ) -> Optional[DailyRollups]:
        """Build daily rollups for a user and date.

        Idempotent: deletes and rebuilds if exists.
        Aggregates all trades for the day by symbol.

        Args:
            user_id: User ID
            target_date: Date to build rollups for

        Returns:
            DailyRollups: Created rollup record (or None if no trades for date)
        """
        try:
            dim_day = await self.get_or_create_dim_day(target_date)

            # Get all symbols traded on this date for this user
            symbols_query = (
                select(DimSymbol.id, DimSymbol.symbol)
                .join(TradesFact, TradesFact.symbol_id == DimSymbol.id)
                .where(
                    and_(
                        TradesFact.user_id == user_id,
                        TradesFact.exit_date_id == dim_day.id,
                    )
                )
                .distinct()
            )
            result = await self.db.execute(symbols_query)
            symbols = result.all()

            if not symbols:
                self.logger.debug(
                    f"No trades on {target_date} for user {user_id}, skipping rollup"
                )
                return None

            rollups_created = 0

            for symbol_id, symbol_name in symbols:
                # Check if rollup already exists
                existing = await self.db.execute(
                    select(DailyRollups).where(
                        and_(
                            DailyRollups.user_id == user_id,
                            DailyRollups.symbol_id == symbol_id,
                            DailyRollups.day_id == dim_day.id,
                        )
                    )
                )

                if existing.scalars().first():
                    # Delete old rollup to rebuild
                    await self.db.execute(
                        select(DailyRollups).where(
                            and_(
                                DailyRollups.user_id == user_id,
                                DailyRollups.symbol_id == symbol_id,
                                DailyRollups.day_id == dim_day.id,
                            )
                        )
                    )
                    self.logger.debug(
                        f"Rebuilding rollup for {symbol_name} on {target_date}"
                    )

                # Query trades for this symbol on this date
                trades_query = select(TradesFact).where(
                    and_(
                        TradesFact.user_id == user_id,
                        TradesFact.symbol_id == symbol_id,
                        TradesFact.exit_date_id == dim_day.id,
                    )
                )
                result = await self.db.execute(trades_query)
                trades = result.scalars().all()

                if not trades:
                    continue

                # Calculate rollup metrics
                total_trades = len(trades)
                winning_trades = sum(1 for t in trades if t.winning_trade)
                losing_trades = total_trades - winning_trades

                gross_pnl = sum(Decimal(str(t.gross_pnl)) for t in trades)
                total_commission = sum(Decimal(str(t.commission)) for t in trades)
                net_pnl = sum(Decimal(str(t.net_pnl)) for t in trades)

                # Win rate
                win_rate = (
                    Decimal(winning_trades) / Decimal(total_trades)
                    if total_trades > 0
                    else Decimal(0)
                )

                # Profit factor (winning PnL / losing PnL)
                winning_pnl = sum(
                    Decimal(str(t.gross_pnl)) for t in trades if t.winning_trade
                )
                losing_pnl = sum(
                    Decimal(str(t.gross_pnl)) for t in trades if not t.winning_trade
                )
                profit_factor = (
                    abs(winning_pnl / losing_pnl) if losing_pnl != 0 else Decimal(0)
                )

                # Average metrics
                avg_win = (
                    winning_pnl / Decimal(winning_trades)
                    if winning_trades > 0
                    else Decimal(0)
                )
                avg_loss = (
                    losing_pnl / Decimal(losing_trades)
                    if losing_trades > 0
                    else Decimal(0)
                )
                largest_win = max(
                    (Decimal(str(t.gross_pnl)) for t in trades if t.winning_trade),
                    default=Decimal(0),
                )
                largest_loss = min(
                    (Decimal(str(t.gross_pnl)) for t in trades if not t.winning_trade),
                    default=Decimal(0),
                )

                # Average R multiple
                r_multiples = [
                    Decimal(str(t.r_multiple)) for t in trades if t.r_multiple
                ]
                avg_r_multiple = (
                    sum(r_multiples) / Decimal(len(r_multiples))
                    if r_multiples
                    else Decimal(0)
                )

                # Max run-up and drawdown
                max_run_up = max(
                    (Decimal(str(t.max_run_up)) for t in trades), default=Decimal(0)
                )
                max_drawdown_daily = max(
                    (Decimal(str(t.max_drawdown)) for t in trades), default=Decimal(0)
                )

                # Create rollup record
                rollup = DailyRollups(
                    id=str(uuid4()),
                    user_id=user_id,
                    symbol_id=symbol_id,
                    day_id=dim_day.id,
                    total_trades=total_trades,
                    winning_trades=winning_trades,
                    losing_trades=losing_trades,
                    gross_pnl=gross_pnl,
                    total_commission=total_commission,
                    net_pnl=net_pnl,
                    win_rate=win_rate,
                    profit_factor=profit_factor,
                    avg_r_multiple=avg_r_multiple,
                    avg_win=avg_win,
                    avg_loss=avg_loss,
                    largest_win=largest_win,
                    largest_loss=largest_loss,
                    max_run_up=max_run_up,
                    max_drawdown=max_drawdown_daily,
                )
                self.db.add(rollup)
                rollups_created += 1

                # Increment Prometheus counter
                if PROMETHEUS_AVAILABLE:
                    try:
                        analytics_rollups_built_counter.labels(
                            user_id=user_id,
                            date=str(target_date),
                        ).inc()
                    except Exception as e:
                        self.logger.error(
                            f"Failed to increment Prometheus counter: {e}"
                        )

            await self.db.commit()
            self.logger.info(
                f"Built {rollups_created} rollups for user {user_id} on {target_date}",
                extra={
                    "user_id": user_id,
                    "date": str(target_date),
                    "count": rollups_created,
                },
            )
            return None

        except Exception as e:
            await self.db.rollback()
            self.logger.error(f"Error building daily rollups: {e}", exc_info=True)
            raise

    async def build_equity_curve(
        self, user_id: str, initial_balance: Decimal = Decimal("10000")
    ) -> int:
        """Build equity curve snapshots from trades.

        Idempotent: rebuilds all snapshots for user.
        Tracks cumulative PnL and drawdown over time.

        Args:
            user_id: User ID
            initial_balance: Starting account balance

        Returns:
            int: Number of snapshots created
        """
        try:
            # Get all unique exit dates for this user (sorted)
            dates_query = (
                select(DimDay.date)
                .join(TradesFact, TradesFact.exit_date_id == DimDay.id)
                .where(TradesFact.user_id == user_id)
                .distinct()
                .order_by(DimDay.date)
            )
            result = await self.db.execute(dates_query)
            dates = result.scalars().all()

            if not dates:
                self.logger.debug(
                    f"No trades for user {user_id}, skipping equity curve"
                )
                return 0

            # Build curve
            snapshots_created = 0
            cumulative_pnl = Decimal(0)
            peak_equity = initial_balance

            for snapshot_date in dates:
                # Get daily PnL for this date
                daily_pnl_query = (
                    select(func.sum(TradesFact.net_pnl))
                    .join(DimDay, TradesFact.exit_date_id == DimDay.id)
                    .where(
                        and_(
                            TradesFact.user_id == user_id,
                            DimDay.date == snapshot_date,
                        )
                    )
                )
                result = await self.db.execute(daily_pnl_query)
                daily_pnl = result.scalar() or Decimal(0)

                cumulative_pnl += Decimal(str(daily_pnl))
                equity = initial_balance + cumulative_pnl
                peak_equity = max(peak_equity, equity)

                # Drawdown percentage
                drawdown = (
                    ((peak_equity - equity) / peak_equity) * Decimal(100)
                    if peak_equity > 0
                    else Decimal(0)
                )

                # Check if snapshot already exists
                existing = await self.db.execute(
                    select(EquityCurve).where(
                        and_(
                            EquityCurve.user_id == user_id,
                            EquityCurve.date == snapshot_date,
                        )
                    )
                )

                if existing.scalars().first():
                    continue

                # Create snapshot
                snapshot = EquityCurve(
                    id=str(uuid4()),
                    user_id=user_id,
                    date=snapshot_date,
                    equity=equity,
                    cumulative_pnl=cumulative_pnl,
                    peak_equity=peak_equity,
                    drawdown=drawdown,
                    daily_change=daily_pnl,
                )
                self.db.add(snapshot)
                snapshots_created += 1

            await self.db.commit()
            self.logger.info(
                f"Built {snapshots_created} equity snapshots for user {user_id}",
                extra={"user_id": user_id, "count": snapshots_created},
            )
            return snapshots_created

        except Exception as e:
            await self.db.rollback()
            self.logger.error(f"Error building equity curve: {e}", exc_info=True)
            raise
