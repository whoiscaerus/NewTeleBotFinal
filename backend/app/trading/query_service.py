"""
Phase 6 Database Query Service - Real Data Retrieval

This service replaces the simulated hardcoded data in routes.py with
actual database queries. Provides methods to fetch:

- Reconciliation logs and status
- Open positions
- Guard conditions (drawdown, market alerts)

Used by Phase 5 endpoints to return production data.

Author: Trading System
Date: 2024-10-26
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trading.reconciliation.models import ReconciliationLog
from backend.app.trading.schemas import (
    AlertType,
    ConditionType,
    DrawdownAlertOut,
    EventType,
    MarketConditionAlertOut,
    PositionOut,
    PositionStatus,
    ReconciliationEventOut,
    ReconciliationStatusOut,
)

logger = logging.getLogger(__name__)


class ReconciliationQueryService:
    """Service for querying reconciliation data from database."""

    @staticmethod
    async def get_reconciliation_status(
        db: AsyncSession,
        user_id: UUID,
        limit_events: int = 5,
    ) -> ReconciliationStatusOut:
        """
        Get reconciliation status for user including sync health and recent events.

        Args:
            db: Database session
            user_id: User ID
            limit_events: Number of recent events to include

        Returns:
            ReconciliationStatusOut with current reconciliation status

        Raises:
            Exception: On database error
        """
        try:
            logger.info(
                "Querying reconciliation status from database",
                extra={"user_id": str(user_id)},
            )

            # Count total syncs
            total_syncs_query = select(func.count(ReconciliationLog.id)).where(
                and_(
                    ReconciliationLog.user_id == user_id,
                    ReconciliationLog.event_type == "sync",
                )
            )
            total_syncs = (await db.execute(total_syncs_query)).scalar() or 0

            # Get last sync
            last_sync_query = (
                select(ReconciliationLog)
                .where(
                    and_(
                        ReconciliationLog.user_id == user_id,
                        ReconciliationLog.event_type == "sync",
                    )
                )
                .order_by(desc(ReconciliationLog.created_at))
                .limit(1)
            )
            last_sync_result = await db.execute(last_sync_query)
            last_sync = last_sync_result.scalars().first()

            # Calculate sync metrics
            last_sync_at = last_sync.created_at if last_sync else datetime.utcnow()
            last_sync_duration_ms = (
                int(
                    (last_sync.updated_at - last_sync.created_at).total_seconds() * 1000
                )
                if last_sync and last_sync.updated_at
                else 0
            )

            # Count open positions
            open_positions_query = select(func.count(ReconciliationLog.id)).where(
                and_(
                    ReconciliationLog.user_id == user_id,
                    ReconciliationLog.matched == 1,  # Matched positions
                )
            )
            open_positions_count = (
                await db.execute(open_positions_query)
            ).scalar() or 0

            # Count matched positions
            matched_query = select(func.count(ReconciliationLog.id)).where(
                and_(
                    ReconciliationLog.user_id == user_id,
                    ReconciliationLog.matched == 1,  # 1 = matched
                )
            )
            matched_positions = (await db.execute(matched_query)).scalar() or 0

            # Count divergences
            divergences_query = select(func.count(ReconciliationLog.id)).where(
                and_(
                    ReconciliationLog.user_id == user_id,
                    ReconciliationLog.matched == 2,  # 2 = divergence
                )
            )
            divergences_detected = (await db.execute(divergences_query)).scalar() or 0

            # Determine overall status
            if divergences_detected > 0:
                status = "warning"
            elif open_positions_count == 0:
                status = "idle"
            else:
                status = "healthy"

            # Get recent events
            recent_events_query = (
                select(ReconciliationLog)
                .where(ReconciliationLog.user_id == user_id)
                .order_by(desc(ReconciliationLog.created_at))
                .limit(limit_events)
            )
            recent_logs = (await db.execute(recent_events_query)).scalars().all()

            # Convert to schema objects
            events = []
            for log in recent_logs:
                event_type_map = {
                    "sync": EventType.POSITION_MATCHED,
                    "close": EventType.POSITION_CLOSED,
                    "guard_trigger": EventType.GUARD_TRIGGERED,
                    "warning": EventType.DIVERGENCE_DETECTED,
                }
                event_type = event_type_map.get(
                    log.event_type, EventType.POSITION_MATCHED
                )

                description = f"{log.symbol} {log.direction}"
                if log.close_reason:
                    description += f" (closed: {log.close_reason})"
                if log.divergence_reason:
                    description += f" (divergence: {log.divergence_reason})"

                events.append(
                    ReconciliationEventOut(
                        event_id=str(log.id),
                        event_type=event_type,
                        user_id=user_id,
                        created_at=log.created_at,
                        description=description,
                        metadata={
                            "symbol": log.symbol,
                            "mt5_ticket": log.mt5_position_id,
                            "matched": log.matched,
                            "pnl_gbp": log.pnl_gbp,
                        },
                    )
                )

            error_message = None
            if divergences_detected > 0:
                error_message = (
                    f"{divergences_detected} divergence(s) detected - review positions"
                )

            return ReconciliationStatusOut(
                user_id=user_id,
                status=status,
                last_sync_at=last_sync_at,
                total_syncs=total_syncs,
                last_sync_duration_ms=last_sync_duration_ms,
                open_positions_count=open_positions_count,
                matched_positions=matched_positions,
                divergences_detected=divergences_detected,
                recent_events=events,
                error_message=error_message,
            )

        except Exception as e:
            logger.error(
                f"Error querying reconciliation status: {e}",
                extra={"user_id": str(user_id)},
                exc_info=True,
            )
            raise

    @staticmethod
    async def get_recent_reconciliation_logs(
        db: AsyncSession,
        user_id: UUID,
        limit: int = 10,
        hours: int = 24,
    ) -> list[ReconciliationLog]:
        """
        Get recent reconciliation logs for user.

        Args:
            db: Database session
            user_id: User ID
            limit: Maximum logs to return
            hours: Only logs from last N hours

        Returns:
            List of ReconciliationLog records
        """
        try:
            time_threshold = datetime.utcnow() - timedelta(hours=hours)

            query = (
                select(ReconciliationLog)
                .where(
                    and_(
                        ReconciliationLog.user_id == user_id,
                        ReconciliationLog.created_at >= time_threshold,
                    )
                )
                .order_by(desc(ReconciliationLog.created_at))
                .limit(limit)
            )

            result = await db.execute(query)
            return result.scalars().all()

        except Exception as e:
            logger.error(
                f"Error querying recent reconciliation logs: {e}",
                extra={"user_id": str(user_id)},
                exc_info=True,
            )
            raise


class PositionQueryService:
    """Service for querying open positions from database."""

    @staticmethod
    async def get_open_positions(
        db: AsyncSession,
        user_id: UUID,
        symbol: Optional[str] = None,
    ) -> tuple[list[PositionOut], float, float]:
        """
        Get open positions for user.

        Args:
            db: Database session
            user_id: User ID
            symbol: Optional symbol filter

        Returns:
            Tuple of (positions list, total_pnl, total_pnl_pct)

        Raises:
            Exception: On database error
        """
        try:
            logger.info(
                "Querying open positions from database",
                extra={"user_id": str(user_id), "symbol_filter": symbol},
            )

            # Get matched reconciliation logs that represent open positions
            # These are positions that have been matched between MT5 and bot
            query = (
                select(ReconciliationLog)
                .where(
                    and_(
                        ReconciliationLog.user_id == user_id,
                        ReconciliationLog.matched == 1,  # Matched
                        ReconciliationLog.close_reason == None,  # Still open
                    )
                )
                .order_by(desc(ReconciliationLog.created_at))
            )

            if symbol:
                query = query.where(ReconciliationLog.symbol == symbol)

            result = await db.execute(query)
            logs = result.scalars().all()

            positions = []
            total_pnl = 0.0

            for i, log in enumerate(logs):
                # Calculate unrealized PnL
                if log.current_price and log.entry_price:
                    price_diff = log.current_price - log.entry_price
                    if log.direction.lower() == "sell":
                        price_diff = -price_diff
                    unrealized_pnl = (
                        price_diff * log.volume * 100
                    )  # Simplified: assume 1 lot = £100
                else:
                    unrealized_pnl = 0.0

                unrealized_pnl_pct = (
                    ((unrealized_pnl / (log.entry_price * log.volume * 100)) * 100)
                    if log.entry_price and log.volume
                    else 0.0
                )

                total_pnl += unrealized_pnl

                position = PositionOut(
                    position_id=str(log.id),
                    ticket=log.mt5_position_id,
                    symbol=log.symbol,
                    direction=log.direction.lower(),
                    volume=log.volume,
                    entry_price=log.entry_price,
                    entry_time=log.created_at,
                    current_price=log.current_price or log.entry_price,
                    unrealized_pnl=round(unrealized_pnl, 2),
                    unrealized_pnl_pct=round(unrealized_pnl_pct, 2),
                    take_profit=log.take_profit,
                    stop_loss=log.stop_loss,
                    status=PositionStatus.OPEN,
                    matched_with_bot=log.matched == 1,
                    last_updated_at=log.updated_at,
                )
                positions.append(position)

            # Calculate total PnL %
            # Assume 20000 GBP account equity for now
            account_equity = 20000.0
            total_pnl_pct = (
                (total_pnl / account_equity * 100) if account_equity > 0 else 0.0
            )

            logger.info(
                "Open positions retrieved from database",
                extra={
                    "user_id": str(user_id),
                    "position_count": len(positions),
                    "total_pnl": round(total_pnl, 2),
                },
            )

            return positions, round(total_pnl, 2), round(total_pnl_pct, 2)

        except Exception as e:
            logger.error(
                f"Error querying open positions: {e}",
                extra={"user_id": str(user_id)},
                exc_info=True,
            )
            raise

    @staticmethod
    async def get_position_by_id(
        db: AsyncSession,
        user_id: UUID,
        position_id: UUID,
    ) -> Optional[PositionOut]:
        """
        Get a specific position by ID.

        Args:
            db: Database session
            user_id: User ID (for security)
            position_id: Position ID

        Returns:
            PositionOut or None if not found
        """
        try:
            query = (
                select(ReconciliationLog)
                .where(
                    and_(
                        ReconciliationLog.id == position_id,
                        ReconciliationLog.user_id == user_id,
                    )
                )
                .limit(1)
            )

            result = await db.execute(query)
            log = result.scalars().first()

            if not log:
                return None

            # Convert to PositionOut
            if log.current_price and log.entry_price:
                price_diff = log.current_price - log.entry_price
                if log.direction.lower() == "sell":
                    price_diff = -price_diff
                unrealized_pnl = price_diff * log.volume * 100
            else:
                unrealized_pnl = 0.0

            unrealized_pnl_pct = (
                ((unrealized_pnl / (log.entry_price * log.volume * 100)) * 100)
                if log.entry_price and log.volume
                else 0.0
            )

            return PositionOut(
                position_id=str(log.id),
                ticket=log.mt5_position_id,
                symbol=log.symbol,
                direction=log.direction.lower(),
                volume=log.volume,
                entry_price=log.entry_price,
                entry_time=log.created_at,
                current_price=log.current_price or log.entry_price,
                unrealized_pnl=round(unrealized_pnl, 2),
                unrealized_pnl_pct=round(unrealized_pnl_pct, 2),
                take_profit=log.take_profit,
                stop_loss=log.stop_loss,
                status=PositionStatus.OPEN,
                matched_with_bot=log.matched == 1,
                last_updated_at=log.updated_at,
            )

        except Exception as e:
            logger.error(
                f"Error querying position {position_id}: {e}",
                extra={"user_id": str(user_id)},
                exc_info=True,
            )
            raise


class GuardQueryService:
    """Service for querying guard conditions from database."""

    @staticmethod
    async def get_drawdown_alert(
        db: AsyncSession,
        user_id: UUID,
        current_equity: float = 8000.0,
        peak_equity: float = 10000.0,
        alert_threshold_pct: float = 20.0,
    ) -> DrawdownAlertOut:
        """
        Get drawdown guard alert status.

        In production, this would query real equity tracking tables.
        For now, it accepts current/peak equity as parameters.

        Args:
            db: Database session (for extensibility)
            user_id: User ID
            current_equity: Current account equity
            peak_equity: Peak account equity
            alert_threshold_pct: Threshold % for alert

        Returns:
            DrawdownAlertOut with current drawdown status
        """
        try:
            logger.info(
                "Querying drawdown alert status",
                extra={"user_id": str(user_id)},
            )

            # Calculate drawdown
            drawdown_pct = (
                ((peak_equity - current_equity) / peak_equity * 100)
                if peak_equity > 0
                else 0.0
            )

            # Determine alert type
            if drawdown_pct >= alert_threshold_pct:
                alert_type = AlertType.CRITICAL
                should_close = True
                time_to_liquidation = 60  # Seconds before forced liquidation
            elif drawdown_pct >= (alert_threshold_pct * 0.75):
                alert_type = AlertType.WARNING
                should_close = False
                time_to_liquidation = None
            else:
                alert_type = AlertType.NORMAL
                should_close = False
                time_to_liquidation = None

            return DrawdownAlertOut(
                user_id=user_id,
                current_equity=current_equity,
                peak_equity=peak_equity,
                current_drawdown_pct=round(drawdown_pct, 2),
                alert_type=alert_type,
                alert_threshold_pct=alert_threshold_pct,
                should_close_all=should_close,
                time_to_liquidation_seconds=time_to_liquidation,
                last_checked_at=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(
                f"Error querying drawdown alert: {e}",
                extra={"user_id": str(user_id)},
                exc_info=True,
            )
            raise

    @staticmethod
    async def get_market_condition_alerts(
        db: AsyncSession,
        user_id: UUID,
    ) -> list[MarketConditionAlertOut]:
        """
        Get market condition alerts for user's open positions.

        Queries for recent price gaps, spread warnings, etc.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            List of MarketConditionAlertOut
        """
        try:
            logger.info(
                "Querying market condition alerts",
                extra={"user_id": str(user_id)},
            )

            # Get recent market guard alerts from reconciliation logs
            query = (
                select(ReconciliationLog)
                .where(
                    and_(
                        ReconciliationLog.user_id == user_id,
                        ReconciliationLog.event_type == "guard_trigger",
                    )
                )
                .order_by(desc(ReconciliationLog.created_at))
                .limit(5)
            )

            result = await db.execute(query)
            logs = result.scalars().all()

            alerts = []
            for log in logs:
                # Determine condition type from divergence reason
                condition_type_map = {
                    "gap": ConditionType.PRICE_GAP,
                    "spread": ConditionType.BID_ASK_SPREAD,
                    "liquidity": ConditionType.LOW_LIQUIDITY,
                    "volatility": ConditionType.HIGH_VOLATILITY,
                }
                condition_type = condition_type_map.get(
                    log.divergence_reason or "",
                    ConditionType.PRICE_GAP,
                )

                # Determine alert type
                alert_type = (
                    AlertType.CRITICAL
                    if log.divergence_reason == "gap"
                    else AlertType.WARNING
                )

                alert = MarketConditionAlertOut(
                    symbol=log.symbol,
                    condition_type=condition_type,
                    alert_type=alert_type,
                    price_gap_pct=abs(log.slippage_pips) if log.slippage_pips else None,
                    bid_ask_spread_pct=None,  # Would come from live feed
                    open_price=None,
                    close_price=log.entry_price,
                    bid=None,
                    ask=None,
                    should_close_positions=alert_type == AlertType.CRITICAL,
                    detected_at=log.created_at,
                )
                alerts.append(alert)

            logger.info(
                "Market condition alerts retrieved",
                extra={"user_id": str(user_id), "alert_count": len(alerts)},
            )

            return alerts

        except Exception as e:
            logger.error(
                f"Error querying market condition alerts: {e}",
                extra={"user_id": str(user_id)},
                exc_info=True,
            )
            raise
