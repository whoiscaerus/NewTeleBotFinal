"""
PR-049: Position Sizing Service with Fixed Risk Management

Calculates incremental position sizes for trade setups respecting:
- Fixed risk budget per user tier (3%, 5%, 7%)
- Incremental entry splits (50%/35%/15%)
- Total stop loss ≤ allocated risk
- Margin availability validation
- Owner-controlled risk parameters
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trading.mt5_models import TradeSetupRiskLog, UserMT5Account
from backend.app.trading.mt5_sync_service import MT5AccountSyncService

logger = logging.getLogger(__name__)


# Owner-controlled global risk parameters
# Owner can change these values via API - changes apply to ALL clients immediately
GLOBAL_RISK_CONFIG = {
    "fixed_risk_percent": 3.0,  # Default 3% - Owner can change to any % (applies to ALL users)
    "entry_splits": {
        "entry_1_percent": 0.50,  # 50% of risk budget (Entry 1)
        "entry_2_percent": 0.35,  # 35% of risk budget (Entry 2)
        "entry_3_percent": 0.15,  # 15% of risk budget (Entry 3)
    },
    "margin_buffer_percent": 20.0,  # Reserve 20% margin buffer
}


class PositionSizingService:
    """
    Calculate position sizes for multi-entry trade setups.

    Enforces fixed risk management:
    - Global fixed risk percentage (default 3%, owner can change)
    - Applies to ALL users equally
    - Owner can update risk % via API, applies immediately
    - Incremental position sizing (3 entries per setup)
    - Total stop loss validation
    - Margin requirement validation
    """

    @staticmethod
    async def calculate_setup_position_sizes(
        db: AsyncSession,
        user_id: str,
        setup: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Calculate position sizes for a trade setup with 3 entries.

        Args:
            db: Database session
            user_id: User identifier
            setup: Trade setup specification:
                {
                    "setup_id": "setup-001",
                    "instrument": "GOLD",
                    "side": "buy",
                    "entries": [
                        {"entry_price": 1950.0, "sl_price": 1945.0, "tp_price": 1965.0},
                        {"entry_price": 1960.0, "sl_price": 1955.0, "tp_price": 1975.0},
                        {"entry_price": 1970.0, "sl_price": 1965.0, "tp_price": 1985.0},
                    ]
                }

        Returns:
            {
                "setup_id": "setup-001",
                "validation_status": "approved" | "rejected_risk" | "rejected_margin",
                "rejection_reason": str | None,
                "positions": [
                    {
                        "entry_number": 1,
                        "instrument": "GOLD",
                        "entry_price": 1950.0,
                        "sl_price": 1945.0,
                        "tp_price": 1965.0,
                        "volume_lots": 0.75,
                        "sl_distance": 5.0,
                        "sl_amount": 375.0,
                        "margin_required": 1462.5
                    },
                    {...},  # entry 2
                    {...},  # entry 3
                ],
                "summary": {
                    "total_volume_lots": 1.5,
                    "total_sl_amount": 750.0,
                    "total_sl_percent": 1.5,
                    "total_margin_required": 2925.0,
                    "margin_available": 43500.0,
                    "margin_after": 40575.0,
                    "user_tier": "standard",
                    "allocated_risk_percent": 3.0,
                    "account_balance": 50000.0
                }
            }

        Raises:
            ValueError: If MT5 account not synced or missing data
        """
        # Step 1: Get MT5 account state
        account_state = await MT5AccountSyncService.get_account_state(
            db, user_id, require_fresh=True
        )
        if not account_state:
            raise ValueError(
                f"MT5 account not found for user {user_id}. Please link MT5 account."
            )

        # Step 2: Get global fixed risk percentage (applies to ALL users)
        # Owner can change this value via API - applies immediately to all clients
        allocated_risk_percent = GLOBAL_RISK_CONFIG["fixed_risk_percent"]
        allocated_risk_amount = account_state.balance * allocated_risk_percent / 100.0

        # Step 3: Calculate position sizes for each entry
        positions = []
        total_sl_amount = 0.0
        total_volume = 0.0

        entry_splits = GLOBAL_RISK_CONFIG["entry_splits"]
        entry_percentages = [
            entry_splits["entry_1_percent"],
            entry_splits["entry_2_percent"],
            entry_splits["entry_3_percent"],
        ]

        for idx, entry_spec in enumerate(setup["entries"]):
            entry_num = idx + 1
            entry_risk_percent = entry_percentages[idx]
            entry_risk_amount = allocated_risk_amount * entry_risk_percent

            # Calculate SL distance
            entry_price = float(entry_spec["entry_price"])
            sl_price = float(entry_spec["sl_price"])
            sl_distance = abs(entry_price - sl_price)

            # Calculate position size
            # volume = risk_amount / (sl_distance × contract_size × price_per_unit)
            # For GOLD: contract_size = 100 oz
            # Simplified: volume = risk_amount / sl_distance (assuming GOLD standard lot)
            contract_size = 100.0  # GOLD standard
            pip_value = contract_size  # £100 per pip for GOLD

            volume_lots = entry_risk_amount / (sl_distance * pip_value)

            # Round to 2 decimals (standard lot precision)
            volume_lots = round(volume_lots, 2)

            # Actual SL amount with rounded volume
            actual_sl_amount = volume_lots * sl_distance * pip_value

            # Calculate margin required
            margin_required = (
                await MT5AccountSyncService.calculate_position_margin_requirement(
                    account_state=account_state,
                    instrument=setup["instrument"],
                    volume_lots=volume_lots,
                    entry_price=entry_price,
                )
            )

            positions.append(
                {
                    "entry_number": entry_num,
                    "instrument": setup["instrument"],
                    "side": setup["side"],
                    "entry_price": entry_price,
                    "sl_price": sl_price,
                    "tp_price": float(entry_spec.get("tp_price", 0.0)),
                    "volume_lots": volume_lots,
                    "sl_distance": sl_distance,
                    "sl_amount": actual_sl_amount,
                    "margin_required": margin_required,
                }
            )

            total_sl_amount += actual_sl_amount
            total_volume += volume_lots

        # Step 5: Calculate total margin requirement
        margin_result = await MT5AccountSyncService.calculate_multi_position_margin(
            account_state=account_state,
            positions=[
                {
                    "instrument": p["instrument"],
                    "volume": p["volume_lots"],
                    "entry_price": p["entry_price"],
                }
                for p in positions
            ],
        )

        # Step 6: Validate risk budget
        # Handle zero balance edge case
        if account_state.balance <= 0:
            validation_status = "rejected_risk"
            rejection_reason = "Account balance is zero or negative"
            await PositionSizingService._log_risk_validation(
                db=db,
                user_id=user_id,
                setup_id=setup["setup_id"],
                account_state=account_state,
                allocated_risk_percent=allocated_risk_percent,
                allocated_risk_amount=allocated_risk_amount,
                positions=positions,
                total_sl_amount=total_sl_amount,
                total_sl_percent=0.0,  # Zero balance, so percent is 0
                total_margin_required=margin_result["total_margin_required"],
                validation_status=validation_status,
                rejection_reason=rejection_reason,
            )
            return {
                "setup_id": setup["setup_id"],
                "validation_status": validation_status,
                "rejection_reason": rejection_reason,
                "positions": positions,
                "summary": {
                    "total_volume_lots": total_volume,
                    "total_sl_amount": total_sl_amount,
                    "total_sl_percent": 0.0,
                    "total_margin_required": margin_result["total_margin_required"],
                    "margin_available": margin_result["margin_available"],
                    "margin_after": margin_result["margin_after_execution"],
                    "allocated_risk_percent": allocated_risk_percent,
                    "allocated_risk_amount": allocated_risk_amount,
                    "account_balance": account_state.balance,
                },
            }

        total_sl_percent = (total_sl_amount / account_state.balance) * 100

        validation_status = "approved"
        rejection_reason = None

        if total_sl_percent > allocated_risk_percent:
            validation_status = "rejected_risk"
            rejection_reason = (
                f"Total SL {total_sl_percent:.2f}% exceeds allocated risk budget "
                f"{allocated_risk_percent}% for global risk"
            )

        # Step 7: Validate margin availability
        elif not margin_result["is_sufficient"]:
            validation_status = "rejected_margin"
            rejection_reason = (
                f"Insufficient margin: Required {margin_result['total_margin_required']:.2f}, "
                f"Available {margin_result['margin_available']:.2f}"
            )

        # Step 8: Check margin buffer
        elif margin_result["margin_after_execution"] < (
            account_state.balance * GLOBAL_RISK_CONFIG["margin_buffer_percent"] / 100
        ):
            validation_status = "rejected_margin"
            rejection_reason = (
                f"Margin buffer violated: Would leave {margin_result['margin_after_execution']:.2f}, "
                f"Required {account_state.balance * 0.20:.2f} (20% buffer)"
            )

        # Step 9: Log validation
        await PositionSizingService._log_risk_validation(
            db=db,
            user_id=user_id,
            setup_id=setup["setup_id"],
            account_state=account_state,
            allocated_risk_percent=allocated_risk_percent,
            allocated_risk_amount=allocated_risk_amount,
            positions=positions,
            total_sl_amount=total_sl_amount,
            total_sl_percent=total_sl_percent,
            total_margin_required=margin_result["total_margin_required"],
            validation_status=validation_status,
            rejection_reason=rejection_reason,
        )

        # Step 10: Return result
        return {
            "setup_id": setup["setup_id"],
            "validation_status": validation_status,
            "rejection_reason": rejection_reason,
            "positions": positions,
            "summary": {
                "total_volume_lots": total_volume,
                "total_sl_amount": total_sl_amount,
                "total_sl_percent": total_sl_percent,
                "total_margin_required": margin_result["total_margin_required"],
                "margin_available": margin_result["margin_available"],
                "margin_after": margin_result["margin_after_execution"],
                "global_risk_percent": allocated_risk_percent,  # Same for all users
                "allocated_risk_amount": allocated_risk_amount,
                "account_balance": account_state.balance,
            },
        }

    @staticmethod
    async def _log_risk_validation(
        db: AsyncSession,
        user_id: str,
        setup_id: str,
        account_state: UserMT5Account,
        allocated_risk_percent: float,
        allocated_risk_amount: float,
        positions: list[dict[str, Any]],
        total_sl_amount: float,
        total_sl_percent: float,
        total_margin_required: float,
        validation_status: str,
        rejection_reason: str | None,
    ) -> None:
        """Log risk validation result."""
        log_entry = TradeSetupRiskLog(
            user_id=user_id,
            setup_id=setup_id,
            account_balance=account_state.balance,
            account_equity=account_state.equity,
            margin_available=account_state.margin_free,
            account_leverage=account_state.account_leverage,
            user_tier="global",  # All users use same global risk %
            allocated_risk_percent=allocated_risk_percent,
            allocated_risk_amount=allocated_risk_amount,
            total_positions_count=len(positions),
            entry_1_size_lots=(
                positions[0]["volume_lots"] if len(positions) > 0 else None
            ),
            entry_2_size_lots=(
                positions[1]["volume_lots"] if len(positions) > 1 else None
            ),
            entry_3_size_lots=(
                positions[2]["volume_lots"] if len(positions) > 2 else None
            ),
            total_stop_loss_amount=total_sl_amount,
            total_stop_loss_percent=total_sl_percent,
            total_margin_required=total_margin_required,
            validation_status=validation_status,
            rejection_reason=rejection_reason,
        )
        db.add(log_entry)
        await db.commit()

        logger.info(
            f"Risk validation logged for setup {setup_id}: "
            f"status={validation_status}, "
            f"sl_amount={total_sl_amount:.2f}, "
            f"sl_percent={total_sl_percent:.2f}%, "
            f"margin_required={total_margin_required:.2f}"
        )
