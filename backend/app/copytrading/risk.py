"""
PR-046: Copy-Trading Risk & Compliance Controls - Risk evaluation and breach detection

This module implements risk parameter enforcement for copy-trading:
- Max leverage per trade
- Max per-trade risk (% of account)
- Total exposure (% across all positions)
- Daily stop loss (% accumulated losses today)

All evaluations trigger Telegram alerts on breach and force pause on violation.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.copytrading.service import CopyTradeSettings

try:
    from prometheus_client import Counter

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    Counter = None  # type: ignore

logger = logging.getLogger(__name__)

# Prometheus metrics
copy_risk_block_counter: Any
if PROMETHEUS_AVAILABLE:
    copy_risk_block_counter = Counter(
        "copy_risk_block_total",
        "Total number of trades blocked due to risk limit breaches",
        ["reason", "user_tier"],
    )
else:
    copy_risk_block_counter = None

# Risk breach reasons
BREACH_MAX_LEVERAGE = "max_leverage_exceeded"
BREACH_MAX_TRADE_RISK = "max_trade_risk_exceeded"
BREACH_TOTAL_EXPOSURE = "total_exposure_exceeded"
BREACH_DAILY_STOP = "daily_stop_exceeded"


class RiskEvaluator:
    """
    Evaluates copy-trading risk parameters and enforces guardrails.

    All breaches:
    - Are logged to audit trail (PR-008)
    - Trigger Telegram alerts to user
    - Force pause of copy-trading
    """

    def __init__(self, telegram_service=None, audit_service=None):
        """
        Initialize risk evaluator.

        Args:
            telegram_service: Service for Telegram alerts (can be None for testing)
            audit_service: Service for audit logging (PR-008)
        """
        self.telegram_service = telegram_service
        self.audit_service = audit_service

    async def evaluate_risk(
        self,
        db: AsyncSession,
        user_id: str,
        proposed_trade: dict,
        account_state: dict,
    ) -> tuple[bool, Optional[str]]:
        """
        Evaluate if proposed trade violates risk parameters.

        Args:
            db: Database session
            user_id: User identifier
            proposed_trade: Dict with: instrument, side, entry_price, volume, sl_price, tp_price
            account_state: Dict with: equity, open_positions_value, todays_loss

        Returns:
            Tuple of (can_execute: bool, breach_reason: str or None)
            If breach detected, also pauses copy-trading and alerts user.

        Example:
            >>> can_trade, reason = await evaluator.evaluate_risk(
            ...     db, user_id,
            ...     {"instrument": "GOLD", "side": "buy", "entry_price": 1950, "volume": 1.0, ...},
            ...     {"equity": 10000, "open_positions_value": 5000, "todays_loss": 150}
            ... )
            >>> if not can_trade:
            ...     print(f"Trade blocked: {reason}")
        """
        # Get user's copy-trading settings
        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        result = await db.execute(stmt)
        settings = result.scalar_one_or_none()

        if not settings or not settings.enabled:
            return False, "copy_trading_not_enabled"

        # If already paused, block all trades
        if settings.is_paused:
            return False, f"copy_trading_paused: {settings.pause_reason}"

        # Extract values
        equity = account_state.get("equity", 0)
        trade_volume = proposed_trade.get("volume", 0)
        entry_price = proposed_trade.get("entry_price", 0)
        sl_price = proposed_trade.get("sl_price", 0)
        todays_loss = account_state.get("todays_loss", 0)
        open_positions_value = account_state.get("open_positions_value", 0)

        # Check 1: Max Leverage per Trade
        if entry_price > 0 and equity > 0:
            trade_value = trade_volume * entry_price
            trade_leverage = trade_value / equity
            max_leverage = settings.max_leverage or 5.0

            if trade_leverage > max_leverage:
                breach_reason = BREACH_MAX_LEVERAGE
                await self._handle_breach(
                    db,
                    user_id,
                    settings,
                    breach_reason,
                    f"Max leverage {max_leverage}x exceeded: {trade_leverage:.2f}x",
                )
                return False, breach_reason

        # Check 2: Max Per-Trade Risk (as % of account)
        if equity > 0 and entry_price > 0 and sl_price > 0:
            risk_per_trade = abs(entry_price - sl_price) * trade_volume
            risk_percent = (risk_per_trade / equity) * 100
            max_trade_risk = settings.max_per_trade_risk_percent or 2.0

            if risk_percent > max_trade_risk:
                breach_reason = BREACH_MAX_TRADE_RISK
                await self._handle_breach(
                    db,
                    user_id,
                    settings,
                    breach_reason,
                    f"Max trade risk {max_trade_risk}% exceeded: {risk_percent:.2f}%",
                )
                return False, breach_reason

        # Check 3: Total Exposure (all positions combined)
        if equity > 0:
            new_position_value = trade_volume * entry_price
            total_exposure_value = open_positions_value + new_position_value
            total_exposure_percent = (total_exposure_value / equity) * 100
            max_exposure = settings.total_exposure_percent or 50.0

            if total_exposure_percent > max_exposure:
                breach_reason = BREACH_TOTAL_EXPOSURE
                await self._handle_breach(
                    db,
                    user_id,
                    settings,
                    breach_reason,
                    f"Max exposure {max_exposure}% exceeded: {total_exposure_percent:.2f}%",
                )
                return False, breach_reason

        # Check 4: Daily Stop Loss (accumulated losses today)
        if equity > 0:
            daily_loss_percent = (todays_loss / equity) * 100
            daily_stop = settings.daily_stop_percent or 10.0

            if daily_loss_percent > daily_stop:
                breach_reason = BREACH_DAILY_STOP
                await self._handle_breach(
                    db,
                    user_id,
                    settings,
                    breach_reason,
                    f"Daily stop {daily_stop}% exceeded: {daily_loss_percent:.2f}% loss",
                )
                return False, breach_reason

        return True, None

    async def _handle_breach(
        self,
        db: AsyncSession,
        user_id: str,
        settings: CopyTradeSettings,
        breach_reason: str,
        detailed_message: str,
    ) -> None:
        """
        Handle a risk breach: pause trading, alert user, log to audit.

        Args:
            db: Database session
            user_id: User identifier
            settings: Current copy-trading settings
            breach_reason: Type of breach (BREACH_MAX_LEVERAGE, etc.)
            detailed_message: Human-readable breach details
        """
        # Update settings: pause and record breach
        settings.is_paused = True
        settings.pause_reason = breach_reason
        settings.paused_at = datetime.utcnow()
        settings.last_breach_at = datetime.utcnow()
        settings.last_breach_reason = breach_reason

        db.add(settings)
        await db.commit()

        # Increment breach counter metric
        if copy_risk_block_counter:
            try:
                user_tier = getattr(
                    settings, "user_tier", "unknown"
                )  # Try to get tier, default to 'unknown'
                copy_risk_block_counter.labels(
                    reason=breach_reason, user_tier=user_tier
                ).inc()
            except Exception as e:
                logger.error(f"Failed to increment Prometheus metric: {e}")

        logger.warning(
            f"Copy-trading breach detected for user {user_id}: {breach_reason}",
            extra={
                "user_id": user_id,
                "breach_reason": breach_reason,
                "details": detailed_message,
            },
        )

        # Send Telegram alert
        if self.telegram_service:
            try:
                alert_text = (
                    f"🛑 **COPY-TRADING PAUSED** 🛑\n\n"
                    f"Reason: {breach_reason}\n"
                    f"Details: {detailed_message}\n\n"
                    f"Your copy-trading has been automatically paused to protect your account.\n"
                    f"Review your risk settings and resume when ready."
                )
                await self.telegram_service.send_user_alert(user_id, alert_text)
            except Exception as e:
                logger.error(f"Failed to send Telegram alert: {e}")

        # Log to audit trail
        if self.audit_service:
            try:
                await self.audit_service.log_event(
                    user_id=user_id,
                    action="copy_trading_paused",
                    details={
                        "reason": breach_reason,
                        "message": detailed_message,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
            except Exception as e:
                logger.error(f"Failed to log audit event: {e}")

    async def can_resume_trading(
        self,
        db: AsyncSession,
        user_id: str,
        manual_override: bool = False,
    ) -> tuple[bool, str]:
        """
        Check if user can resume trading after pause.

        Args:
            db: Database session
            user_id: User identifier
            manual_override: If True, allow resume even if conditions not met (admin only)

        Returns:
            Tuple of (can_resume: bool, reason: str)
        """
        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        result = await db.execute(stmt)
        settings = result.scalar_one_or_none()

        if not settings:
            return False, "No copy-trading settings found"

        if not settings.is_paused:
            return True, "Already trading"

        # Auto-resume after 24 hours if no override
        if not manual_override and settings.paused_at:
            if datetime.utcnow() - settings.paused_at > timedelta(hours=24):
                settings.is_paused = False
                settings.pause_reason = None
                db.add(settings)
                await db.commit()
                return True, "Auto-resumed after 24 hours"

        # Manual override (admin)
        if manual_override:
            settings.is_paused = False
            settings.pause_reason = None
            db.add(settings)
            await db.commit()
            return True, "Resumed by user"

        return (
            False,
            f"Paused until {(settings.paused_at + timedelta(hours=24)).isoformat()}",
        )

    async def get_user_risk_status(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> dict:
        """
        Get current risk status for user.

        Args:
            db: Database session
            user_id: User identifier

        Returns:
            Dict with risk status, parameters, and pause information
        """
        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        result = await db.execute(stmt)
        settings = result.scalar_one_or_none()

        if not settings:
            return {"error": "No settings found"}

        return {
            "user_id": user_id,
            "enabled": settings.enabled,
            "is_paused": settings.is_paused,
            "pause_reason": settings.pause_reason,
            "paused_at": settings.paused_at.isoformat() if settings.paused_at else None,
            "last_breach_at": (
                settings.last_breach_at.isoformat() if settings.last_breach_at else None
            ),
            "last_breach_reason": settings.last_breach_reason,
            "risk_parameters": {
                "max_leverage": settings.max_leverage,
                "max_per_trade_risk_percent": settings.max_per_trade_risk_percent,
                "total_exposure_percent": settings.total_exposure_percent,
                "daily_stop_percent": settings.daily_stop_percent,
            },
        }
