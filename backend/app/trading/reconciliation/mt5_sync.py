"""MT5 Position Synchronization Service.

Fetches live positions from MT5 terminal, compares against bot's expected trades,
detects divergences (slippage, partial fills, broker closes), and records audit trail.

This service runs every 10 seconds to ensure real-time account reconciliation.
"""

from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.service import AuditService
from backend.app.auth.models import User
from backend.app.core.logging import get_logger
from backend.app.trading.reconciliation.models import (
    PositionSnapshot,
    ReconciliationLog,
)
from backend.app.trading.store.models import Trade

logger = get_logger(__name__)


class MT5Position:
    """Immutable representation of a single MT5 position."""

    def __init__(
        self,
        ticket: int,
        symbol: str,
        direction: int,  # 0=buy, 1=sell
        volume: float,
        entry_price: float,
        current_price: float,
        tp: float | None = None,
        sl: float | None = None,
        commission: float = 0.0,
        swap: float = 0.0,
        profit: float = 0.0,
    ):
        """Initialize MT5 position snapshot."""
        self.ticket = ticket
        self.symbol = symbol
        self.direction = direction
        self.volume = volume
        self.entry_price = entry_price
        self.current_price = current_price
        self.tp = tp
        self.sl = sl
        self.commission = commission
        self.swap = swap
        self.profit = profit

    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized P&L in account currency (GBP)."""
        return self.profit - self.commission - self.swap

    def __repr__(self) -> str:
        return (
            f"<MT5Position {self.symbol} {self.volume}L {self.direction} "
            f"@ {self.entry_price}>"
        )


class MT5AccountSnapshot:
    """Account state snapshot from MT5."""

    def __init__(
        self,
        balance: float,
        equity: float,
        positions: list[MT5Position],
        timestamp: datetime,
    ):
        """Initialize account snapshot."""
        self.balance = balance
        self.equity = equity
        self.positions = positions
        self.timestamp = timestamp
        self.margin_used = 0.0  # Will be populated from MT5
        self.margin_free = 0.0

    @property
    def total_open_volume(self) -> float:
        """Sum of all position volumes."""
        return sum(p.volume for p in self.positions)

    @property
    def unrealized_pnl(self) -> float:
        """Sum of unrealized P&L across all positions."""
        return sum(p.unrealized_pnl for p in self.positions)

    @property
    def drawdown_percent(self) -> float:
        """Calculate drawdown as percentage. (Requires peak_equity from DB)"""
        # This will be computed in main sync method
        return 0.0

    def __repr__(self) -> str:
        return f"<MT5Account balance={self.balance} equity={self.equity} positions={len(self.positions)}>"


class MT5SyncService:
    """Service to sync MT5 positions and reconcile with bot's trade store."""

    def __init__(self, mt5_session, db: AsyncSession):
        """Initialize sync service.

        Args:
            mt5_session: Connected MT5SessionManager instance
            db: AsyncSession for database operations
        """
        self.mt5 = mt5_session
        self.db = db

    async def fetch_account_snapshot(self) -> MT5AccountSnapshot | None:
        """Fetch live account state from MT5 terminal.

        Returns account balance, equity, and open positions. Handles reconnection
        if MT5 session is stale.

        Returns:
            MT5AccountSnapshot if successful, None if MT5 unavailable
        """
        try:
            # Ensure MT5 connection is alive
            self.mt5.ensure_connected()

            # Get account info (balance, equity, margin, etc.)
            account_info = self.mt5.mt5.account_info()
            if not account_info:
                logger.error("MT5 AccountInfo() returned None")
                return None

            balance = account_info.balance
            equity = account_info.equity
            margin_used = account_info.margin

            # Get all open positions
            positions_data = self.mt5.mt5.positions_get()
            if positions_data is None:
                logger.error("MT5 Positions() returned None")
                return None

            positions = []
            for pos in positions_data:
                mt5_pos = MT5Position(
                    ticket=pos.ticket,
                    symbol=pos.symbol,
                    direction=pos.type,  # 0=buy, 1=sell
                    volume=pos.volume,
                    entry_price=pos.price_open,
                    current_price=pos.price_current,
                    tp=pos.tp if pos.tp > 0 else None,
                    sl=pos.sl if pos.sl > 0 else None,
                    commission=pos.commission,
                    swap=pos.swap,
                    profit=pos.profit,
                )
                positions.append(mt5_pos)

            snapshot = MT5AccountSnapshot(
                balance=balance,
                equity=equity,
                positions=positions,
                timestamp=datetime.now(UTC),
            )
            snapshot.margin_used = margin_used

            logger.info(
                "MT5 snapshot fetched",
                extra={
                    "balance": balance,
                    "equity": equity,
                    "positions_count": len(positions),
                    "timestamp": snapshot.timestamp.isoformat(),
                },
            )

            return snapshot

        except Exception as e:
            logger.error(
                f"Failed to fetch MT5 snapshot: {e}",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return None

    async def sync_positions_for_user(self, user_id: str, user: User) -> dict:
        """Sync all positions for a specific user.

        Compares MT5 positions to bot's expected trades, records divergences,
        and updates PositionSnapshot.

        Args:
            user_id: User UUID
            user: User ORM object (for relationships)

        Returns:
            Dict with sync results: {
                'matched_count': int,
                'divergences_count': int,
                'new_positions_count': int,
                'closed_positions_count': int,
                'errors': list[str],
            }
        """
        result = {
            "matched_count": 0,
            "divergences_count": 0,
            "new_positions_count": 0,
            "closed_positions_count": 0,
            "errors": [],
        }

        try:
            # 1. Fetch MT5 account snapshot
            snapshot = await self.fetch_account_snapshot()
            if not snapshot:
                result["errors"].append("Failed to fetch MT5 snapshot")
                return result

            # 2. Load all open bot trades for this user
            stmt = select(Trade).where(
                and_(
                    Trade.user_id == user_id,
                    Trade.status == 1,  # 1 = open
                )
            )
            result_trades = await self.db.execute(stmt)
            bot_trades = result_trades.scalars().all()

            logger.info(
                "Loaded bot trades for sync",
                extra={
                    "user_id": user_id,
                    "bot_trades_count": len(bot_trades),
                    "mt5_positions_count": len(snapshot.positions),
                },
            )

            # 3. Create tracking sets
            matched_bot_trades = set()

            # 4. Match MT5 positions to bot trades
            for mt5_pos in snapshot.positions:
                match = self._find_matching_trade(
                    mt5_pos, bot_trades, matched_bot_trades
                )

                if match:
                    matched_bot_trades.add(match.id)
                    divergence = self._detect_divergence(mt5_pos, match)

                    if divergence:
                        # Record divergence
                        await self._record_divergence(
                            user_id, mt5_pos, match, divergence
                        )
                        result["divergences_count"] += 1
                    else:
                        result["matched_count"] += 1
                else:
                    # MT5 position not in bot trades (manual trade or fill issue)
                    await self._record_unmatched_position(user_id, mt5_pos)
                    result["new_positions_count"] += 1

            # 5. Detect bot trades with no MT5 counterpart (closed by broker)
            for trade in bot_trades:
                if trade.id not in matched_bot_trades:
                    await self._record_closed_position(user_id, trade, snapshot)
                    result["closed_positions_count"] += 1

            # 6. Update account snapshot
            await self._update_position_snapshot(user_id, snapshot, user)

            logger.info(
                "Position sync completed",
                extra={
                    "user_id": user_id,
                    "matched": result["matched_count"],
                    "divergences": result["divergences_count"],
                    "new_positions": result["new_positions_count"],
                    "closed_positions": result["closed_positions_count"],
                },
            )

            # 7. Record sync event
            await AuditService.record(
                db=self.db,
                action="reconciliation.sync_complete",
                target="account",
                actor_id=None,
                actor_role="system",
                target_id=user_id,
                meta={
                    "matched_count": result["matched_count"],
                    "divergences_count": result["divergences_count"],
                    "new_positions_count": result["new_positions_count"],
                    "closed_positions_count": result["closed_positions_count"],
                },
                status="success",
            )

            return result

        except Exception as e:
            logger.error(
                f"Exception during position sync for {user_id}: {e}",
                exc_info=True,
            )
            result["errors"].append(str(e))
            return result

    def _find_matching_trade(
        self,
        mt5_pos: MT5Position,
        bot_trades: list,
        matched_trades: set,
    ) -> Trade | None:
        """Find a bot trade matching the MT5 position.

        Matching criteria:
        1. Same symbol
        2. Same direction (buy/sell)
        3. Volume within 5% tolerance
        4. Entry price within 2 pips
        5. Not already matched

        Args:
            mt5_pos: MT5Position to match
            bot_trades: List of open bot trades
            matched_trades: Set of already-matched trade IDs

        Returns:
            Matching Trade or None
        """
        for trade in bot_trades:
            if trade.id in matched_trades:
                continue

            # Check symbol
            if trade.symbol.upper() != mt5_pos.symbol.upper():
                continue

            # Check direction
            if trade.direction != mt5_pos.direction:
                continue

            # Check volume (within 5%)
            volume_tolerance = trade.volume * 0.05
            if abs(trade.volume - mt5_pos.volume) > volume_tolerance:
                continue

            # Check entry price (within 2 pips for most pairs)
            price_tolerance = 0.0002
            if abs(trade.entry_price - mt5_pos.entry_price) > price_tolerance:
                continue

            # Match found
            return trade

        return None

    def _detect_divergence(self, mt5_pos: MT5Position, bot_trade: Trade) -> str | None:
        """Detect if MT5 position diverges from bot trade expectations.

        Returns divergence reason if detected, None if all good.

        Checks:
        - Entry price slippage (>2 pips)
        - Volume mismatch (>5%)
        - TP/SL mismatch

        Args:
            mt5_pos: MT5 position
            bot_trade: Expected bot trade

        Returns:
            Divergence reason string or None
        """
        # Check entry price slippage
        slippage = abs(mt5_pos.entry_price - bot_trade.entry_price)
        if slippage > 0.0005:  # 5 pips
            return f"slippage_entry: {slippage:.6f}"

        # Check volume mismatch (possible partial fill)
        volume_diff_pct = abs(
            (mt5_pos.volume - bot_trade.volume) / bot_trade.volume * 100
        )
        if volume_diff_pct > 10:  # >10% mismatch
            return f"volume_mismatch: bot={bot_trade.volume} mt5={mt5_pos.volume}"

        # Check TP (if set)
        if bot_trade.tp and mt5_pos.tp:
            tp_diff = abs(mt5_pos.tp - bot_trade.tp)
            if tp_diff > 0.001:  # 10 pips
                return f"tp_mismatch: bot={bot_trade.tp} mt5={mt5_pos.tp}"

        # Check SL (if set)
        if bot_trade.sl and mt5_pos.sl:
            sl_diff = abs(mt5_pos.sl - bot_trade.sl)
            if sl_diff > 0.001:  # 10 pips
                return f"sl_mismatch: bot={bot_trade.sl} mt5={mt5_pos.sl}"

        return None

    async def _record_divergence(
        self,
        user_id: str,
        mt5_pos: MT5Position,
        bot_trade: Trade,
        divergence_reason: str,
    ) -> None:
        """Record a position divergence to ReconciliationLog.

        Args:
            user_id: User UUID
            mt5_pos: MT5 position
            bot_trade: Expected bot trade
            divergence_reason: Description of divergence
        """
        try:
            log_entry = ReconciliationLog(
                user_id=user_id,
                signal_id=bot_trade.setup_id,
                approval_id=None,  # Link if available from Signal
                mt5_position_id=str(mt5_pos.ticket),
                symbol=mt5_pos.symbol,
                direction=mt5_pos.direction,
                volume=mt5_pos.volume,
                entry_price=float(mt5_pos.entry_price),
                current_price=float(mt5_pos.current_price),
                tp=float(mt5_pos.tp) if mt5_pos.tp else None,
                sl=float(mt5_pos.sl) if mt5_pos.sl else None,
                matched=1,  # 1 = divergence
                divergence_reason=divergence_reason,
                event_type="divergence",
                status=0,
            )
            self.db.add(log_entry)
            await self.db.flush()

            logger.warning(
                f"Position divergence recorded: {divergence_reason}",
                extra={
                    "user_id": user_id,
                    "symbol": mt5_pos.symbol,
                    "ticket": mt5_pos.ticket,
                    "reason": divergence_reason,
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to record divergence: {e}",
                exc_info=True,
            )

    async def _record_unmatched_position(
        self,
        user_id: str,
        mt5_pos: MT5Position,
    ) -> None:
        """Record a position that exists in MT5 but not in bot trades (manual or fill issue).

        Args:
            user_id: User UUID
            mt5_pos: MT5 position
        """
        try:
            log_entry = ReconciliationLog(
                user_id=user_id,
                signal_id=None,
                approval_id=None,
                mt5_position_id=str(mt5_pos.ticket),
                symbol=mt5_pos.symbol,
                direction=mt5_pos.direction,
                volume=mt5_pos.volume,
                entry_price=float(mt5_pos.entry_price),
                current_price=float(mt5_pos.current_price),
                tp=float(mt5_pos.tp) if mt5_pos.tp else None,
                sl=float(mt5_pos.sl) if mt5_pos.sl else None,
                matched=2,  # 2 = unmatched (manual or missing bot trade)
                divergence_reason="manual_trade_or_missing_signal",
                event_type="unmatched_position",
                status=0,
            )
            self.db.add(log_entry)
            await self.db.flush()

            logger.info(
                f"Unmatched position recorded: {mt5_pos}",
                extra={
                    "user_id": user_id,
                    "symbol": mt5_pos.symbol,
                    "ticket": mt5_pos.ticket,
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to record unmatched position: {e}",
                exc_info=True,
            )

    async def _record_closed_position(
        self,
        user_id: str,
        bot_trade: Trade,
        snapshot: MT5AccountSnapshot,
    ) -> None:
        """Record a position that was closed by broker but expected to be open.

        Args:
            user_id: User UUID
            bot_trade: Trade that should be open but isn't
            snapshot: Current MT5 account snapshot
        """
        try:
            log_entry = ReconciliationLog(
                user_id=user_id,
                signal_id=bot_trade.setup_id,
                approval_id=None,
                mt5_position_id=None,
                symbol=bot_trade.symbol,
                direction=bot_trade.direction,
                volume=bot_trade.volume,
                entry_price=float(bot_trade.entry_price),
                current_price=None,
                tp=float(bot_trade.tp) if bot_trade.tp else None,
                sl=float(bot_trade.sl) if bot_trade.sl else None,
                matched=0,  # 0 = no match
                divergence_reason="broker_closed_position",
                event_type="close",
                close_reason="broker_liquidated",
                status=1,
            )
            self.db.add(log_entry)
            await self.db.flush()

            logger.warning(
                f"Closed position detected: {bot_trade.symbol}",
                extra={
                    "user_id": user_id,
                    "symbol": bot_trade.symbol,
                    "setup_id": bot_trade.setup_id,
                    "reason": "broker_closed",
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to record closed position: {e}",
                exc_info=True,
            )

    async def _update_position_snapshot(
        self,
        user_id: str,
        snapshot: MT5AccountSnapshot,
        user: User,
    ) -> None:
        """Update PositionSnapshot table with current account state.

        Args:
            user_id: User UUID
            snapshot: MT5 account snapshot
            user: User ORM object
        """
        try:
            snapshot_entry = PositionSnapshot(
                user_id=user_id,
                equity_gbp=float(snapshot.equity),
                balance_gbp=float(snapshot.balance),
                open_positions_count=len(snapshot.positions),
                total_volume_lots=float(snapshot.total_open_volume),
                margin_used_percent=(
                    (snapshot.margin_used / snapshot.equity * 100)
                    if snapshot.equity > 0
                    else 0.0
                ),
                last_sync_at=snapshot.timestamp,
            )
            self.db.add(snapshot_entry)

            # Calculate peak_equity if not already set
            # (This would be done by guard service, but we record it here for reference)
            if not hasattr(user, "peak_equity_gbp") or not user.peak_equity_gbp:
                user.peak_equity_gbp = float(snapshot.equity)

            await self.db.flush()

            logger.info(
                "Position snapshot updated",
                extra={
                    "user_id": user_id,
                    "equity": snapshot.equity,
                    "balance": snapshot.balance,
                    "positions_count": len(snapshot.positions),
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to update position snapshot: {e}",
                exc_info=True,
            )


async def run_reconciliation_sync(db: AsyncSession, mt5_session, user: User) -> dict:
    """Entry point for reconciliation sync job.

    Called every 10 seconds per active user.

    Args:
        db: AsyncSession
        mt5_session: MT5SessionManager
        user: User to sync

    Returns:
        Sync result dict
    """
    service = MT5SyncService(mt5_session, db)
    result = await service.sync_positions_for_user(str(user.id), user)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to commit reconciliation: {e}", exc_info=True)
        result["errors"].append("Database commit failed")

    return result
