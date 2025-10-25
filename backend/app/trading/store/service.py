"""Trade store service for CRUD operations and querying."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trading.store.models import EquityPoint, Position, Trade, ValidationLog


class TradeService:
    """Service for managing trades and related operations.

    Provides CRUD operations, filtering, analytics queries, and reconciliation.

    Example:
        >>> service = TradeService(db_session)
        >>> trade = await service.create_trade(
        ...     symbol="GOLD",
        ...     trade_type="BUY",
        ...     entry_price=Decimal("1950.50"),
        ...     stop_loss=Decimal("1945.00"),
        ...     take_profit=Decimal("1960.00"),
        ...     volume=Decimal("0.1"),
        ... )
        >>> closed = await service.close_trade(
        ...     trade_id=trade.trade_id,
        ...     exit_price=Decimal("1955.50"),
        ...     exit_reason="TP_HIT"
        ... )
    """

    def __init__(self, db: AsyncSession):
        """Initialize trade service.

        Args:
            db: Async SQLAlchemy session
        """
        self.db = db

    async def create_trade(
        self,
        symbol: str,
        trade_type: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
        volume: Decimal,
        entry_time: datetime | None = None,
        strategy: str = "manual",
        timeframe: str = "H1",
        signal_id: str | None = None,
        device_id: str | None = None,
        setup_id: str | None = None,
        entry_comment: str | None = None,
    ) -> Trade:
        """Create a new trade record.

        Args:
            symbol: Trading symbol (GOLD, EURUSD, etc.)
            trade_type: BUY or SELL
            entry_price: Entry level
            stop_loss: Stop loss level
            take_profit: Take profit level
            volume: Position size in lots
            entry_time: Entry timestamp (defaults to now)
            strategy: Strategy name
            timeframe: Candle timeframe
            signal_id: Reference to signal
            device_id: Reference to device
            setup_id: Setup identifier
            entry_comment: Comment for entry

        Returns:
            Created Trade object

        Raises:
            ValueError: If prices violate constraints
        """
        entry_time = entry_time or datetime.utcnow()

        # Validate price relationships
        if trade_type == "BUY":
            if not (stop_loss < entry_price < take_profit):
                raise ValueError(
                    f"BUY: SL({stop_loss}) < Entry({entry_price}) < TP({take_profit}) violated"
                )
        elif trade_type == "SELL":
            if not (take_profit < entry_price < stop_loss):
                raise ValueError(
                    f"SELL: TP({take_profit}) < Entry({entry_price}) < SL({stop_loss}) violated"
                )
        else:
            raise ValueError(f"Invalid trade type: {trade_type}")

        # Validate volume
        if not (Decimal("0.01") <= volume <= Decimal("100.0")):
            raise ValueError(f"Volume must be 0.01-100.0, got {volume}")

        # Create trade
        trade = Trade(
            symbol=symbol,
            trade_type=trade_type,
            direction=0 if trade_type == "BUY" else 1,
            entry_price=entry_price,
            entry_time=entry_time,
            entry_comment=entry_comment,
            stop_loss=stop_loss,
            take_profit=take_profit,
            volume=volume,
            strategy=strategy,
            timeframe=timeframe,
            signal_id=signal_id,
            device_id=device_id,
            setup_id=setup_id,
            status="OPEN",
        )

        self.db.add(trade)
        await self.db.flush()

        # Log creation
        await self._log_validation(
            trade.trade_id,
            "CREATED",
            f"Trade created: {trade_type} {symbol} @ {entry_price}",
        )

        return trade

    async def close_trade(
        self,
        trade_id: str,
        exit_price: Decimal,
        exit_reason: str = "MANUAL_CLOSE",
        exit_time: datetime | None = None,
    ) -> Trade:
        """Close an open trade.

        Calculates P&L, pips, duration, and updates status.

        Args:
            trade_id: Trade ID to close
            exit_price: Exit level
            exit_reason: Reason for exit
            exit_time: Exit timestamp (defaults to now)

        Returns:
            Updated Trade object

        Raises:
            ValueError: If trade not found or not OPEN
        """
        exit_time = exit_time or datetime.utcnow()

        # Fetch trade
        stmt = select(Trade).where(Trade.trade_id == trade_id)
        result = await self.db.execute(stmt)
        trade = result.scalar_one_or_none()

        if not trade:
            raise ValueError(f"Trade not found: {trade_id}")

        if trade.status != "OPEN":
            raise ValueError(f"Trade not OPEN, current status: {trade.status}")

        # Update exit details
        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.exit_reason = exit_reason
        trade.status = "CLOSED"

        # Calculate duration
        duration = exit_time - trade.entry_time
        trade.duration_hours = duration.total_seconds() / 3600

        # Calculate P&L
        if trade.trade_type == "BUY":
            trade.profit = (exit_price - trade.entry_price) * trade.volume
            trade.pips = (exit_price - trade.entry_price) * Decimal("10000")  # For GOLD
        else:  # SELL
            trade.profit = (trade.entry_price - exit_price) * trade.volume
            trade.pips = (trade.entry_price - exit_price) * Decimal("10000")

        # Calculate R:R
        risk = abs(trade.entry_price - trade.stop_loss)
        reward = abs(trade.take_profit - trade.entry_price)
        if risk > 0:
            trade.risk_reward_ratio = reward / risk

        self.db.add(trade)
        await self.db.flush()

        # Log closure
        await self._log_validation(
            trade.trade_id,
            "CLOSED",
            f"Trade closed: Exit @ {exit_price}, P&L: £{trade.profit}",
        )

        return trade

    async def get_trade(self, trade_id: str) -> Trade | None:
        """Fetch a single trade by ID.

        Args:
            trade_id: Trade ID to fetch

        Returns:
            Trade object or None if not found
        """
        stmt = select(Trade).where(Trade.trade_id == trade_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_trades(
        self,
        symbol: str | None = None,
        status: str | None = None,
        strategy: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Trade]:
        """List trades with filtering.

        Args:
            symbol: Filter by symbol (GOLD, EURUSD, etc.)
            status: Filter by status (OPEN, CLOSED, CANCELLED)
            strategy: Filter by strategy name
            start_date: Filter trades after this date
            end_date: Filter trades before this date
            limit: Max results (default 100)
            offset: Pagination offset

        Returns:
            List of Trade objects

        Example:
            >>> trades = await service.list_trades(
            ...     symbol="GOLD",
            ...     status="CLOSED",
            ...     limit=50
            ... )
        """
        stmt = select(Trade)

        # Apply filters
        if symbol:
            stmt = stmt.where(Trade.symbol == symbol)
        if status:
            stmt = stmt.where(Trade.status == status)
        if strategy:
            stmt = stmt.where(Trade.strategy == strategy)
        if start_date:
            stmt = stmt.where(Trade.entry_time >= start_date)
        if end_date:
            stmt = stmt.where(Trade.entry_time <= end_date)

        # Sort and paginate
        stmt = stmt.order_by(desc(Trade.entry_time)).limit(limit).offset(offset)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_trade_stats(self, symbol: str | None = None) -> dict:
        """Calculate overall trade statistics.

        Args:
            symbol: Filter by symbol (None = all)

        Returns:
            Dictionary with statistics including win_rate, profit_factor, etc.

        Example:
            >>> stats = await service.get_trade_stats("GOLD")
            >>> print(f"Win rate: {stats['win_rate']:.1%}")
        """
        stmt = select(Trade).where(Trade.status == "CLOSED")

        if symbol:
            stmt = stmt.where(Trade.symbol == symbol)

        result = await self.db.execute(stmt)
        closed_trades = result.scalars().all()

        if not closed_trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "avg_profit": Decimal("0"),
                "avg_loss": Decimal("0"),
                "largest_win": Decimal("0"),
                "largest_loss": Decimal("0"),
                "total_profit": Decimal("0"),
            }

        # Calculate stats
        winning_trades = [t for t in closed_trades if t.profit > 0]
        losing_trades = [t for t in closed_trades if t.profit < 0]

        total_profit = sum((t.profit or Decimal("0")) for t in closed_trades)
        total_loss = sum((t.profit or Decimal("0")) for t in losing_trades)
        total_win = sum((t.profit or Decimal("0")) for t in winning_trades)

        win_rate = len(winning_trades) / len(closed_trades) if closed_trades else 0.0
        profit_factor = abs(total_win / total_loss) if total_loss != 0 else 0.0

        largest_win = max((t.profit for t in winning_trades), default=Decimal("0"))
        largest_loss = min((t.profit for t in losing_trades), default=Decimal("0"))

        return {
            "total_trades": len(closed_trades),
            "win_rate": win_rate,
            "profit_factor": float(profit_factor),
            "avg_profit": (
                total_win / len(winning_trades) if winning_trades else Decimal("0")
            ),
            "avg_loss": (
                total_loss / len(losing_trades) if losing_trades else Decimal("0")
            ),
            "largest_win": largest_win,
            "largest_loss": largest_loss,
            "total_profit": total_profit,
        }

    async def get_drawdown_peaks(self) -> list[dict]:
        """Get equity peaks and corresponding drawdowns.

        Returns:
            List of peak/trough periods with drawdown calculations
        """
        stmt = select(EquityPoint).order_by(EquityPoint.timestamp)
        result = await self.db.execute(stmt)
        equity_points = result.scalars().all()

        if not equity_points:
            return []

        peaks = []
        current_peak = equity_points[0]

        for point in equity_points[1:]:
            if point.equity > current_peak.equity:
                current_peak = point
            else:
                drawdown_pct = (
                    (current_peak.equity - point.equity) / current_peak.equity * 100
                    if current_peak.equity > 0
                    else 0
                )
                if drawdown_pct > 0:
                    peaks.append(
                        {
                            "peak_time": current_peak.timestamp,
                            "peak_equity": current_peak.equity,
                            "trough_time": point.timestamp,
                            "trough_equity": point.equity,
                            "drawdown_pct": drawdown_pct,
                            "recovery_time": None,  # Calculate if recovered
                        }
                    )

        return peaks

    async def get_position_summary(self) -> dict:
        """Get summary of current open positions.

        Returns:
            Dictionary with position summary
        """
        stmt = select(Position)
        result = await self.db.execute(stmt)
        positions = result.scalars().all()

        total_volume = sum((p.volume for p in positions), Decimal("0"))
        total_profit = sum((p.unrealized_profit or Decimal("0")) for p in positions)

        by_symbol = {}
        for pos in positions:
            if pos.symbol not in by_symbol:
                by_symbol[pos.symbol] = {
                    "count": 0,
                    "volume": Decimal("0"),
                    "profit": Decimal("0"),
                }
            by_symbol[pos.symbol]["count"] += 1
            by_symbol[pos.symbol]["volume"] += pos.volume
            by_symbol[pos.symbol]["profit"] += pos.unrealized_profit or Decimal("0")

        return {
            "total_positions": len(positions),
            "total_volume": total_volume,
            "total_unrealized_profit": total_profit,
            "by_symbol": by_symbol,
        }

    async def find_orphaned_trades(self, mt5_positions: list[dict]) -> list[Trade]:
        """Find trades not in MT5 (manually closed or deleted).

        Args:
            mt5_positions: List of current MT5 positions

        Returns:
            List of trades not in MT5

        Example:
            >>> orphaned = await service.find_orphaned_trades([
            ...     {"ticket": 123, "symbol": "GOLD", "volume": 0.1}
            ... ])
        """
        # Get all open trades
        stmt = select(Trade).where(Trade.status == "OPEN")
        result = await self.db.execute(stmt)
        open_trades = result.scalars().all()

        # Find trades not in MT5 positions
        mt5_tickets = {str(p.get("ticket")) for p in mt5_positions}
        orphaned = [t for t in open_trades if str(t.trade_id) not in mt5_tickets]

        return orphaned

    async def sync_with_mt5(self, mt5_positions: list[dict]) -> dict:
        """Reconcile MT5 positions with our trade store.

        Args:
            mt5_positions: List of current MT5 positions

        Returns:
            Dictionary with sync results and any mismatches

        Example:
            >>> result = await service.sync_with_mt5(mt5_positions)
            >>> print(f"Synced: {result['synced']}, Mismatches: {result['mismatches']}")
        """
        synced = 0
        mismatches = []
        actions = []

        for mt5_pos in mt5_positions:
            # Try to find corresponding trade
            stmt = select(Trade).where(
                and_(
                    Trade.symbol == mt5_pos.get("symbol"),
                    Trade.status == "OPEN",
                )
            )
            result = await self.db.execute(stmt)
            trade = result.scalar_one_or_none()

            if trade:
                # Check for volume mismatch
                if abs(trade.volume - Decimal(str(mt5_pos.get("volume", 0)))) > Decimal(
                    "0.01"
                ):
                    mismatches.append(
                        {
                            "trade_id": trade.trade_id,
                            "issue": "volume_mismatch",
                            "our_volume": trade.volume,
                            "mt5_volume": mt5_pos.get("volume"),
                        }
                    )
                else:
                    synced += 1
            else:
                actions.append(
                    {
                        "action": "create",
                        "symbol": mt5_pos.get("symbol"),
                        "volume": mt5_pos.get("volume"),
                        "reason": "position_in_mt5_not_in_our_store",
                    }
                )

        orphaned = await self.find_orphaned_trades(mt5_positions)
        if orphaned:
            actions.append(
                {
                    "action": "investigate",
                    "reason": "trades_open_locally_but_not_in_mt5",
                    "count": len(orphaned),
                }
            )

        return {
            "synced": synced,
            "mismatches": len(mismatches),
            "orphaned": len(orphaned),
            "mismatch_details": mismatches,
            "actions": actions,
        }

    async def _log_validation(
        self,
        trade_id: str,
        event_type: str,
        message: str,
        details: str | None = None,
    ) -> ValidationLog:
        """Internal method to log validation events.

        Args:
            trade_id: Trade ID
            event_type: Type of event
            message: Event message
            details: Optional JSON details

        Returns:
            Created ValidationLog
        """
        log = ValidationLog(
            trade_id=trade_id,
            event_type=event_type,
            message=message,
            details=details,
            timestamp=datetime.utcnow(),
        )
        self.db.add(log)
        await self.db.flush()
        return log
