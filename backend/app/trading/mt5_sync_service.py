"""
PR-048: MT5 Account Sync Service

Synchronizes live account data from MT5 via EA integration.
Critical for:
- Position sizing based on real balance/leverage
- Margin validation before trade execution
- Risk budget calculation
- Preventing over-leveraging
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trading.mt5_models import UserMT5Account, UserMT5SyncLog

logger = logging.getLogger(__name__)


class MT5AccountSyncService:
    """
    Service for syncing MT5 account state.

    Integrates with EA device to pull live account data:
    - Balance, equity, margin
    - Leverage configuration
    - Open positions count

    Validates data freshness and handles sync errors.
    """

    STALE_THRESHOLD_MINUTES = 5  # Mark account as stale after 5 minutes

    @staticmethod
    async def sync_account_from_mt5(
        db: AsyncSession,
        user_id: str,
        mt5_data: dict[str, Any],
    ) -> UserMT5Account:
        """
        Update user's MT5 account state from EA data.

        Args:
            db: Database session
            user_id: User identifier
            mt5_data: Account data from MT5/EA:
                {
                    "account_id": 123456,
                    "server": "FxPro-MT5 Demo",
                    "broker": "FxPro",
                    "balance": 50000.0,
                    "equity": 48500.0,
                    "margin_used": 5000.0,
                    "margin_free": 43500.0,
                    "leverage": 100,
                    "open_positions_count": 3,
                    "total_volume": 2.5,
                    "currency": "GBP",
                    "is_demo": True
                }

        Returns:
            UserMT5Account: Updated account state

        Raises:
            ValueError: If mt5_data missing required fields
        """
        start_time = datetime.utcnow()

        # Validate required fields
        required_fields = [
            "account_id",
            "balance",
            "equity",
            "margin_free",
            "leverage",
        ]
        missing = [f for f in required_fields if f not in mt5_data]
        if missing:
            raise ValueError(f"Missing required MT5 data fields: {missing}")

        # Get existing account or create new
        stmt = select(UserMT5Account).where(UserMT5Account.user_id == user_id)
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        balance_before = account.balance if account else None

        if not account:
            # Create new account
            account = UserMT5Account(
                user_id=user_id,
                mt5_account_id=mt5_data["account_id"],
                mt5_server=mt5_data.get("server", "Unknown"),
                broker_name=mt5_data.get("broker", "Unknown"),
            )
            db.add(account)

        # Update account state
        account.balance = float(mt5_data["balance"])
        account.equity = float(mt5_data["equity"])
        account.margin_used = float(mt5_data.get("margin_used", 0.0))
        account.margin_free = float(mt5_data["margin_free"])
        account.account_leverage = int(mt5_data["leverage"])
        account.open_positions_count = int(mt5_data.get("open_positions_count", 0))
        account.total_positions_volume = float(mt5_data.get("total_volume", 0.0))
        account.account_currency = mt5_data.get("currency", "GBP")
        account.is_demo = mt5_data.get("is_demo", True)

        # Calculate margin level (if positions open)
        if account.margin_used > 0:
            account.margin_level_percent = (account.equity / account.margin_used) * 100
        else:
            account.margin_level_percent = None

        # Update sync status
        account.last_synced_at = datetime.utcnow()
        account.sync_status = "active"
        account.sync_error_message = None
        account.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(account)

        # Log sync
        sync_duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        await MT5AccountSyncService._log_sync(
            db=db,
            user_id=user_id,
            mt5_account_id=mt5_data["account_id"],
            status="success",
            duration_ms=int(sync_duration),
            balance_before=balance_before,
            balance_after=account.balance,
            equity_after=account.equity,
            margin_free_after=account.margin_free,
            leverage_after=account.account_leverage,
        )

        logger.info(
            f"MT5 account synced for user {user_id}: "
            f"balance={account.balance}, equity={account.equity}, "
            f"margin_free={account.margin_free}, leverage={account.account_leverage}"
        )

        return account

    @staticmethod
    async def get_account_state(
        db: AsyncSession,
        user_id: str,
        require_fresh: bool = True,
    ) -> UserMT5Account | None:
        """
        Get user's MT5 account state.

        Args:
            db: Database session
            user_id: User identifier
            require_fresh: If True, raise error if account data is stale

        Returns:
            UserMT5Account or None if not found

        Raises:
            ValueError: If account is stale and require_fresh=True
        """
        stmt = select(UserMT5Account).where(UserMT5Account.user_id == user_id)
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        if not account:
            return None

        # Check if data is stale
        if require_fresh:
            age = datetime.utcnow() - account.last_synced_at
            if age > timedelta(minutes=MT5AccountSyncService.STALE_THRESHOLD_MINUTES):
                raise ValueError(
                    f"MT5 account data is stale (last sync: {age.total_seconds():.0f}s ago). "
                    f"Please sync account before trading."
                )

        return account

    @staticmethod
    async def calculate_position_margin_requirement(
        account_state: UserMT5Account,
        instrument: str,
        volume_lots: float,
        entry_price: float,
    ) -> float:
        """
        Calculate margin required for a position.

        Formula: margin = (volume × contract_size × price) / leverage

        Args:
            account_state: User's MT5 account state
            instrument: Trading instrument (e.g., "GOLD", "EURUSD")
            volume_lots: Position size in lots
            entry_price: Entry price

        Returns:
            Margin required in account currency

        Example:
            GOLD @ £1950, 1.0 lot, 100:1 leverage
            contract_size = 100 oz
            margin = (1.0 × 100 × 1950) / 100 = £1,950
        """
        # Contract sizes (standard)
        contract_sizes = {
            "GOLD": 100.0,  # 100 troy ounces
            "XAUUSD": 100.0,
            "EURUSD": 100000.0,  # 100k units
            "GBPUSD": 100000.0,
            "USDJPY": 100000.0,
            "BTCUSD": 1.0,  # 1 BTC
        }

        # Get contract size
        contract_size = contract_sizes.get(instrument.upper(), 100000.0)

        # Calculate margin
        position_value = volume_lots * contract_size * entry_price
        margin_required = position_value / account_state.account_leverage

        return float(margin_required)

    @staticmethod
    async def calculate_multi_position_margin(
        account_state: UserMT5Account,
        positions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Calculate total margin required for multiple positions.

        Args:
            account_state: User's MT5 account state
            positions: List of proposed positions:
                [
                    {"instrument": "GOLD", "volume": 0.5, "entry_price": 1950.0},
                    {"instrument": "GOLD", "volume": 0.3, "entry_price": 1960.0},
                    {"instrument": "GOLD", "volume": 0.2, "entry_price": 1970.0},
                ]

        Returns:
            {
                "total_margin_required": 3000.0,
                "margin_available": 43500.0,
                "margin_after_execution": 40500.0,
                "margin_level_after": 123.5,  # (equity / total_margin) * 100
                "is_sufficient": True
            }
        """
        total_margin = 0.0

        for pos in positions:
            margin = await MT5AccountSyncService.calculate_position_margin_requirement(
                account_state=account_state,
                instrument=pos["instrument"],
                volume_lots=pos["volume"],
                entry_price=pos["entry_price"],
            )
            total_margin += margin

        margin_after = account_state.margin_free - total_margin
        is_sufficient = margin_after >= 0

        # Calculate new margin level
        total_margin_used = account_state.margin_used + total_margin
        margin_level_after = (
            (account_state.equity / total_margin_used) * 100
            if total_margin_used > 0
            else None
        )

        return {
            "total_margin_required": total_margin,
            "margin_available": account_state.margin_free,
            "margin_after_execution": margin_after,
            "margin_level_after": margin_level_after,
            "is_sufficient": is_sufficient,
        }

    @staticmethod
    async def _log_sync(
        db: AsyncSession,
        user_id: str,
        mt5_account_id: int,
        status: str,
        duration_ms: int,
        balance_before: float | None,
        balance_after: float,
        equity_after: float,
        margin_free_after: float,
        leverage_after: int,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Log MT5 sync operation."""
        log_entry = UserMT5SyncLog(
            user_id=user_id,
            mt5_account_id=mt5_account_id,
            sync_status=status,
            sync_duration_ms=duration_ms,
            balance_before=balance_before,
            balance_after=balance_after,
            equity_after=equity_after,
            margin_free_after=margin_free_after,
            leverage_after=leverage_after,
            error_code=error_code,
            error_message=error_message,
        )
        db.add(log_entry)
        await db.commit()
