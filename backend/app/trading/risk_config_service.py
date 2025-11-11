"""
PR-105: Risk Configuration Service - Owner-Controlled Global Fixed Risk %

Allows owner to change the global fixed risk percentage that applies to ALL users.
- Default: 3.0% (from environment variable DEFAULT_FIXED_RISK_PERCENT)
- Owner can change to any % between 0.1% and 50% via API
- Changes apply immediately to all position sizing calculations
- Stored in-memory (GLOBAL_RISK_CONFIG dict) and persisted to database

Business justification:
- Owner can reduce risk globally during high volatility (e.g., 1% during news events)
- Owner can increase risk when confidence is high (e.g., 5% during strong trends)
- All users treated equally - risk scales with account size naturally
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trading.mt5_models import RiskConfiguration
from backend.app.trading.position_sizing_service import GLOBAL_RISK_CONFIG

logger = logging.getLogger(__name__)


class RiskConfigService:
    """
    Service for managing global fixed risk configuration.

    Owner-only operations:
    - Get current global risk %
    - Update global risk % (applies to ALL users immediately)
    - Validate risk % is within safe bounds (0.1% - 50%)
    - Persist changes to database for restart recovery
    """

    MIN_RISK_PERCENT = 0.1  # Minimum 0.1% (very conservative)
    MAX_RISK_PERCENT = 50.0  # Maximum 50% (very aggressive, not recommended)
    DEFAULT_RISK_PERCENT = 3.0  # Default if no config exists

    @staticmethod
    async def get_global_risk_config(db: AsyncSession) -> dict:
        """
        Get current global risk configuration.

        Returns:
            {
                "fixed_risk_percent": 3.0,
                "entry_splits": {
                    "entry_1_percent": 0.50,
                    "entry_2_percent": 0.35,
                    "entry_3_percent": 0.15
                },
                "margin_buffer_percent": 20.0,
                "updated_at": "2025-11-11T12:00:00Z",
                "updated_by": "owner_user_id"
            }
        """
        stmt = select(RiskConfiguration).limit(1)  # Single row table
        result = await db.execute(stmt)
        config_row = result.scalar_one_or_none()

        if config_row:
            return {
                "fixed_risk_percent": config_row.fixed_risk_percent,
                "entry_splits": {
                    "entry_1_percent": config_row.entry_1_percent,
                    "entry_2_percent": config_row.entry_2_percent,
                    "entry_3_percent": config_row.entry_3_percent,
                },
                "margin_buffer_percent": config_row.margin_buffer_percent,
                "updated_at": (
                    config_row.updated_at.isoformat() if config_row.updated_at else None
                ),
                "updated_by": config_row.updated_by,
            }
        else:
            # Return current in-memory config if no DB row
            return {
                "fixed_risk_percent": GLOBAL_RISK_CONFIG["fixed_risk_percent"],
                "entry_splits": GLOBAL_RISK_CONFIG["entry_splits"],
                "margin_buffer_percent": GLOBAL_RISK_CONFIG["margin_buffer_percent"],
                "updated_at": None,
                "updated_by": None,
            }

    @staticmethod
    async def update_global_risk_percent(
        db: AsyncSession,
        new_risk_percent: float,
        updated_by_user_id: str,
    ) -> dict:
        """
        Update global fixed risk percentage (owner-only).

        Updates both in-memory (GLOBAL_RISK_CONFIG) and database (RiskConfiguration table).
        Changes apply immediately to all position sizing calculations.

        Args:
            db: Database session
            new_risk_percent: New risk % (0.1 - 50.0)
            updated_by_user_id: User ID making the change (must be owner)

        Returns:
            {
                "fixed_risk_percent": 5.0,
                "previous_risk_percent": 3.0,
                "updated_at": "2025-11-11T12:00:00Z",
                "updated_by": "owner_user_id"
            }

        Raises:
            ValueError: If risk % out of bounds (0.1 - 50%)
        """
        # Validate bounds
        if not (
            RiskConfigService.MIN_RISK_PERCENT
            <= new_risk_percent
            <= RiskConfigService.MAX_RISK_PERCENT
        ):
            raise ValueError(
                f"Risk percent must be between {RiskConfigService.MIN_RISK_PERCENT}% "
                f"and {RiskConfigService.MAX_RISK_PERCENT}%. Got: {new_risk_percent}%"
            )

        # Get previous value
        previous_risk_percent = GLOBAL_RISK_CONFIG["fixed_risk_percent"]

        # Update in-memory config (applies immediately)
        GLOBAL_RISK_CONFIG["fixed_risk_percent"] = new_risk_percent

        # Update database (for persistence across restarts)
        stmt = select(RiskConfiguration).limit(1)
        result = await db.execute(stmt)
        config_row = result.scalar_one_or_none()

        now = datetime.utcnow()

        if config_row:
            # Update existing row
            config_row.fixed_risk_percent = new_risk_percent
            config_row.updated_by = updated_by_user_id
            config_row.updated_at = now
        else:
            # Create new row
            config_row = RiskConfiguration(
                fixed_risk_percent=new_risk_percent,
                entry_1_percent=GLOBAL_RISK_CONFIG["entry_splits"]["entry_1_percent"],
                entry_2_percent=GLOBAL_RISK_CONFIG["entry_splits"]["entry_2_percent"],
                entry_3_percent=GLOBAL_RISK_CONFIG["entry_splits"]["entry_3_percent"],
                margin_buffer_percent=GLOBAL_RISK_CONFIG["margin_buffer_percent"],
                updated_by=updated_by_user_id,
                updated_at=now,
            )
            db.add(config_row)

        await db.commit()

        logger.info(
            f"Global risk % updated: {previous_risk_percent}% → {new_risk_percent}% by {updated_by_user_id}",
            extra={
                "previous_risk_percent": previous_risk_percent,
                "new_risk_percent": new_risk_percent,
                "updated_by": updated_by_user_id,
            },
        )

        return {
            "fixed_risk_percent": new_risk_percent,
            "previous_risk_percent": previous_risk_percent,
            "updated_at": now.isoformat(),
            "updated_by": updated_by_user_id,
        }

    @staticmethod
    async def load_config_from_database(db: AsyncSession) -> None:
        """
        Load risk configuration from database into in-memory GLOBAL_RISK_CONFIG.

        Called on application startup to restore persisted configuration.
        If no config exists in DB, uses default values.
        """
        stmt = select(RiskConfiguration).limit(1)
        result = await db.execute(stmt)
        config_row = result.scalar_one_or_none()

        if config_row:
            GLOBAL_RISK_CONFIG["fixed_risk_percent"] = config_row.fixed_risk_percent
            GLOBAL_RISK_CONFIG["entry_splits"][
                "entry_1_percent"
            ] = config_row.entry_1_percent
            GLOBAL_RISK_CONFIG["entry_splits"][
                "entry_2_percent"
            ] = config_row.entry_2_percent
            GLOBAL_RISK_CONFIG["entry_splits"][
                "entry_3_percent"
            ] = config_row.entry_3_percent
            GLOBAL_RISK_CONFIG["margin_buffer_percent"] = (
                config_row.margin_buffer_percent
            )

            logger.info(
                f"Loaded risk config from database: {config_row.fixed_risk_percent}% fixed risk",
                extra={
                    "fixed_risk_percent": config_row.fixed_risk_percent,
                    "updated_by": config_row.updated_by,
                    "updated_at": (
                        config_row.updated_at.isoformat()
                        if config_row.updated_at
                        else None
                    ),
                },
            )
        else:
            logger.info(
                f"No risk config in database, using defaults: {GLOBAL_RISK_CONFIG['fixed_risk_percent']}%"
            )
