"""
PR-045: Copy-Trading Integration & Pricing Uplift - Auto-execution with +30% markup
PR-046: Copy-Trading Risk & Compliance Controls - Guard rails, disclosures, pause mechanism

Copy-trading enables users to automatically execute trades without approval.
Pricing is marked up +30% on base plan price for copy-trading tier.
PR-046 adds risk parameters, disclosure versioning, forced pause on breach, and Telegram alerts.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Session

from backend.app.core.db import Base


class CopyTradeSettings(Base):
    """User copy-trading configuration with PR-046 risk parameters."""

    __tablename__ = "copy_trade_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    # PR-045 fields
    enabled = Column(Boolean, default=False)
    risk_multiplier = Column(Float, default=1.0)  # Scale trade sizes by factor
    max_drawdown_percent = Column(Float, default=20.0)  # Stop trading if DD > threshold
    max_position_size_lot = Column(Float, default=5.0)  # Cap per-trade size
    max_daily_trades = Column(Integer, default=50)  # Max trades per day
    trades_today = Column(Integer, default=0)  # Counter for current day
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    consent_version = Column(String(50), default="1.0")  # Versioned consent text
    consent_accepted_at = Column(DateTime)

    # PR-048/049: User tier for fixed risk allocation
    tier = Column(
        String(20), default="standard", index=True
    )  # standard (3%), premium (5%), elite (7%)

    # PR-046 Risk Control Fields
    max_leverage = Column(Float, default=5.0)  # Max leverage per trade (1x-10x)
    max_per_trade_risk_percent = Column(
        Float, default=2.0
    )  # Max risk per trade as % of account
    total_exposure_percent = Column(
        Float, default=50.0
    )  # Max total exposure % across all positions
    daily_stop_percent = Column(Float, default=10.0)  # Max daily loss % before pause
    is_paused = Column(Boolean, default=False)  # Paused due to breach
    pause_reason = Column(String(500))  # Reason for pause (breach type)
    paused_at = Column(DateTime)  # When pause triggered
    last_breach_at = Column(DateTime)  # Last time risk breach detected
    last_breach_reason = Column(
        String(500)
    )  # Type of breach (max_leverage, max_risk, exposure, daily_stop)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_copy_enabled_user", "enabled", "user_id"),
        Index("ix_copy_paused_user", "is_paused", "user_id"),
        Index("ix_copy_tier", "tier"),  # PR-048: Index on tier for risk allocation
    )


class Disclosure(Base):
    """Versioned disclosure/consent document for copy-trading (PR-046)."""

    __tablename__ = "disclosures"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version = Column(
        String(50), nullable=False, unique=True, index=True
    )  # "1.0", "1.1", "2.0"
    title = Column(
        String(500), nullable=False
    )  # e.g., "Copy-Trading Risk Disclosure v1.0"
    content = Column(Text, nullable=False)  # Full disclosure text (markdown)
    effective_date = Column(
        DateTime, nullable=False
    )  # When this version becomes active
    is_active = Column(Boolean, default=True)  # Current version for new signups
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_disclosure_version", "version"),
        Index("ix_disclosure_active", "is_active"),
    )


class UserConsent(Base):
    """User's acceptance of disclosure (PR-046) - immutable audit trail."""

    __tablename__ = "user_consents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    disclosure_version = Column(
        String(50), nullable=False
    )  # Version accepted (e.g., "1.0")
    accepted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ip_address = Column(String(45))  # IPv4 or IPv6
    user_agent = Column(String(500))  # Browser/client info
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_user_consent_user_version", "user_id", "disclosure_version"),
        Index("ix_user_consent_user_date", "user_id", "accepted_at"),
    )


class CopyTradeExecution(Base):
    """Record of copy-traded execution (auto-executed signal)."""

    __tablename__ = "copy_trade_executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    signal_id = Column(String(36), nullable=False)  # Reference to original signal
    original_volume = Column(Float, nullable=False)
    executed_volume = Column(Float, nullable=False)  # After risk_multiplier
    markup_percent = Column(Float, default=30.0)  # +30% markup billed
    status = Column(String(50), default="executed")  # executed, closed, cancelled
    executed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime)

    __table_args__ = (Index("ix_copy_exec_user_signal", "user_id", "signal_id"),)


class CopyTradingService:
    """
    Manages copy-trading operations with risk controls.
    Auto-executes trades, applies risk caps, logs markup.
    """

    MARKUP_PERCENT = 30.0  # +30% pricing markup

    def __init__(self):
        """Initialize copy-trading service."""
        pass

    async def enable_copy_trading(
        self,
        db,
        user_id: str,
        consent_version: str = "1.0",
        risk_multiplier: float = 1.0,
    ) -> dict:
        """
        Enable copy-trading for user.

        Args:
            db: Database session (async)
            user_id: User identifier
            consent_version: Consent document version (must be current)
            risk_multiplier: Trade size multiplier (1.0 = normal, 0.5 = half-size)

        Returns:
            Copy-trading settings
        """
        from sqlalchemy.future import select

        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        result = await db.execute(stmt)
        settings = result.scalar_one_or_none()

        if not settings:
            settings = CopyTradeSettings(
                id=str(uuid.uuid4()),
                user_id=user_id,
                enabled=True,
                risk_multiplier=risk_multiplier,
                consent_version=consent_version,
                consent_accepted_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
            )
            db.add(settings)
        else:
            settings.enabled = True
            settings.risk_multiplier = risk_multiplier
            settings.consent_version = consent_version
            settings.consent_accepted_at = datetime.utcnow()
            settings.started_at = datetime.utcnow()

        await db.commit()

        return {
            "user_id": user_id,
            "enabled": True,
            "risk_multiplier": risk_multiplier,
            "markup_percent": self.MARKUP_PERCENT,
        }

    async def disable_copy_trading(self, db, user_id: str) -> dict:
        """
        Disable copy-trading for user.

        Args:
            db: Database session (async)
            user_id: User identifier

        Returns:
            Confirmation
        """
        from sqlalchemy.future import select

        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        result = await db.execute(stmt)
        settings = result.scalar_one_or_none()

        if settings:
            settings.enabled = False
            settings.ended_at = datetime.utcnow()
            await db.commit()

        return {"user_id": user_id, "enabled": False}

    async def get_copy_settings(self, db, user_id: str) -> dict | None:
        """
        Get copy-trading settings for user.

        Args:
            db: Database session (async)
            user_id: User identifier

        Returns:
            Settings dict or None
        """
        from sqlalchemy.future import select

        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        result = await db.execute(stmt)
        settings = result.scalar_one_or_none()

        if not settings:
            return None

        return {
            "enabled": settings.enabled,
            "risk_multiplier": settings.risk_multiplier,
            "max_drawdown_percent": settings.max_drawdown_percent,
            "max_position_size_lot": settings.max_position_size_lot,
            "max_daily_trades": settings.max_daily_trades,
            "trades_today": settings.trades_today,
            "markup_percent": self.MARKUP_PERCENT,
        }

    async def can_copy_execute(self, db, user_id: str) -> tuple[bool, str]:
        """
        Check if user can copy-execute trade (risk checks).

        Args:
            db: Database session (async)
            user_id: User identifier

        Returns:
            Tuple of (can_execute: bool, reason: str)
        """
        from sqlalchemy.future import select

        stmt = select(CopyTradeSettings).where(
            (CopyTradeSettings.user_id == user_id) & (CopyTradeSettings.enabled.is_(True))
        )
        result = await db.execute(stmt)
        settings = result.scalar_one_or_none()

        if not settings:
            return False, "Copy-trading not enabled"

        # Check daily trade limit
        if settings.trades_today >= settings.max_daily_trades:
            return False, "Daily trade limit reached"

        # Check drawdown cap
        # In production, query account info for actual drawdown
        current_drawdown = 0.0  # Placeholder

        if current_drawdown >= settings.max_drawdown_percent:
            return False, "Max drawdown reached"

        return True, "OK"

    async def execute_copy_trade(
        self,
        db,
        user_id: str,
        signal_id: str,
        signal_volume: float,
        signal_data: dict,
    ) -> dict:
        """
        Execute trade in copy-trading mode (auto-approve).

        Args:
            db: Database session (async)
            user_id: User identifier
            signal_id: Signal identifier
            signal_volume: Original signal volume
            signal_data: Signal details (for order placement)

        Returns:
            Execution record
        """
        from sqlalchemy.future import select

        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        result = await db.execute(stmt)
        settings = result.scalar_one_or_none()

        if not settings or not settings.enabled:
            return {"error": "Copy-trading not enabled"}

        # Can execute?
        can_exec, reason = await self.can_copy_execute(db, user_id)
        if not can_exec:
            return {"error": reason}

        # Apply risk multiplier
        executed_volume = signal_volume * settings.risk_multiplier
        executed_volume = min(executed_volume, settings.max_position_size_lot)

        # Create execution record
        execution = CopyTradeExecution(
            id=str(uuid.uuid4()),
            user_id=user_id,
            signal_id=signal_id,
            original_volume=signal_volume,
            executed_volume=executed_volume,
            markup_percent=self.MARKUP_PERCENT,
            status="executed",
            executed_at=datetime.utcnow(),
        )

        db.add(execution)

        # Increment daily counter
        settings.trades_today += 1

        await db.commit()

        return {
            "execution_id": execution.id,
            "user_id": user_id,
            "signal_id": signal_id,
            "original_volume": signal_volume,
            "executed_volume": executed_volume,
            "markup_percent": self.MARKUP_PERCENT,
            "status": "executed",
        }

    def apply_copy_markup(self, base_price_usd: float) -> float:
        """
        Apply +30% markup to base plan price for copy-trading tier.

        Args:
            base_price_usd: Base plan price in USD

        Returns:
            Markup price (base_price * 1.30)
        """
        return base_price_usd * (1.0 + self.MARKUP_PERCENT / 100.0)

    def get_copy_pricing(
        self, db: Session, base_plans: dict[str, float]
    ) -> dict[str, float]:
        """
        Calculate copy-trading tier pricing (+30% markup).

        Args:
            db: Database session
            base_plans: Dict of plan_name -> base_price_usd

        Returns:
            Dict of plan_name -> copy_price_usd
        """
        copy_pricing = {}

        for plan_name, base_price in base_plans.items():
            copy_price = self.apply_copy_markup(base_price)
            copy_pricing[f"{plan_name}_copy"] = copy_price

        return copy_pricing


# Pydantic schemas
class CopyTradingEnable(BaseModel):
    """Request to enable copy-trading."""

    consent_version: str = Field(default="1.0", description="Consent document version")
    risk_multiplier: float = Field(
        default=1.0, ge=0.1, le=2.0, description="Trade size multiplier"
    )


class CopyTradingSettings(BaseModel):
    """Copy-trading settings response."""

    enabled: bool
    risk_multiplier: float
    max_drawdown_percent: float
    max_position_size_lot: float
    max_daily_trades: int
    trades_today: int
    markup_percent: float


class CopyTradeExecutionOut(BaseModel):
    """Copy trade execution response."""

    execution_id: str
    user_id: str
    signal_id: str
    original_volume: float
    executed_volume: float
    markup_percent: float
    status: str
