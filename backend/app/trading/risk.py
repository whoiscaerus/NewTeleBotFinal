"""
Risk Management Engine.
Enforces pre-trade risk limits (Daily Loss, Leverage, Position Size).
"""

from datetime import datetime
from typing import Optional

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.core.redis_cache import _redis_client

logger = get_logger(__name__)


class RiskCheckException(Exception):
    """Raised when a risk check fails."""

    pass


class RiskEngine:
    """
    Pre-trade risk checks.
    Uses Redis for real-time P&L tracking and configuration.
    """

    def __init__(self, redis: Optional[Redis] = None):
        self.redis = redis or _redis_client

    async def check_risk(
        self,
        user_id: str,
        account_id: str,
        symbol: str,
        side: str,
        volume: float,
        price: float,
        equity: float,
        db: AsyncSession,
    ) -> bool:
        """
        Perform all risk checks before order placement.

        Args:
            user_id: User ID
            account_id: Trading account ID
            symbol: Instrument symbol
            side: 'buy' or 'sell'
            volume: Order volume (lots)
            price: Current price
            equity: Account equity
            db: Database session

        Returns:
            True if all checks pass

        Raises:
            RiskCheckException: If any check fails
        """
        if not self.redis:
            logger.warning("Redis not available for risk checks - skipping")
            return True

        # 1. Check Kill Switch
        if await self._is_kill_switch_active(user_id):
            raise RiskCheckException("Trading is disabled (Kill Switch active)")

        # 2. Check Max Daily Loss
        if await self._check_daily_loss_limit(user_id, account_id, equity):
            raise RiskCheckException("Daily loss limit reached")

        # 3. Check Max Position Size
        if not await self._check_position_size(volume, equity, price):
            raise RiskCheckException("Position size exceeds limit")

        return True

    async def _is_kill_switch_active(self, user_id: str) -> bool:
        """Check if global or user kill switch is active."""
        # Global kill switch
        if await self.redis.get("risk:kill_switch:global"):
            return True

        # User kill switch
        if await self.redis.get(f"risk:kill_switch:user:{user_id}"):
            return True

        return False

    async def _check_daily_loss_limit(
        self, user_id: str, account_id: str, equity: float
    ) -> bool:
        """
        Check if daily loss limit is hit.
        Returns True if limit is hit (STOP TRADING).
        """
        # Get daily starting equity (snapshot at 00:00 UTC)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        start_equity_key = f"risk:equity:{account_id}:{today}:start"

        start_equity = await self.redis.get(start_equity_key)
        if not start_equity:
            # First trade of day, set start equity
            await self.redis.set(start_equity_key, equity, ex=86400)
            return False

        start_equity = float(start_equity)
        current_pl_pct = (equity - start_equity) / start_equity * 100

        # Get limit (default -5%)
        limit_pct = float(
            await self.redis.get(f"risk:limit:daily_loss:{user_id}") or -5.0
        )

        if current_pl_pct <= limit_pct:
            logger.warning(
                f"Daily loss limit hit for {user_id}: {current_pl_pct}% <= {limit_pct}%"
            )
            return True

        return False

    async def _check_position_size(
        self, volume: float, equity: float, price: float
    ) -> bool:
        """
        Check if position size is within limits.
        Simple check: Notional value < X% of equity * leverage.
        For now, we'll just check max lots per trade.
        """
        # Default max lots: 10.0
        max_lots = float(await self.redis.get("risk:limit:max_lots") or 10.0)

        if volume > max_lots:
            return False

        return True

    async def update_daily_pnl(self, account_id: str, equity: float):
        """Update P&L tracking (call this on every equity update)."""
        if not self.redis:
            return

        today = datetime.utcnow().strftime("%Y-%m-%d")
        start_equity_key = f"risk:equity:{account_id}:{today}:start"

        # Ensure start equity exists
        if not await self.redis.exists(start_equity_key):
            await self.redis.set(start_equity_key, equity, ex=86400)


# Global instance
risk_engine = RiskEngine()
