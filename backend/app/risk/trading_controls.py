"""Trading control models and service for pause/resume/sizing.

PR-075: Trading Controls in Mini App
Provides user-scoped trading pause/resume, position sizing, and notification toggles.
Integrates with PR-074 guards and PR-019 runtime loop.

Business Logic:
- When paused, signal generation stops (checked in strategy scheduler)
- Resume reactivates on next candle bar boundary
- Position size overrides default risk calculations
- Notifications toggle controls alert delivery
- All state changes are telemetry-tracked
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Column, DateTime, Float, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.core.db import Base
from backend.app.observability.metrics import MetricsCollector


class TradingControl(Base):
    """Trading control settings per user.

    Tracks:
    - Trading pause/resume state
    - Position sizing overrides
    - Notification preferences
    - Actor who made changes (user vs admin vs system)
    """

    __tablename__ = "trading_controls"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, unique=True, index=True)

    # Pause/Resume state
    is_paused = Column(Boolean, nullable=False, default=False)
    paused_at = Column(DateTime, nullable=True)
    paused_by = Column(String(50), nullable=True)  # user, admin, system
    pause_reason = Column(String(500), nullable=True)

    # Position sizing override (None = use default risk %)
    position_size_override = Column(Float, nullable=True)

    # Notification toggles
    notifications_enabled = Column(Boolean, nullable=False, default=True)

    # Audit fields
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        status = "PAUSED" if self.is_paused else "RUNNING"
        return f"<TradingControl {self.user_id}: {status}>"


class TradingControlService:
    """Service layer for trading control operations.

    Handles:
    - Pause/resume with telemetry tracking
    - Position size updates
    - Notification toggles
    - Integration with PR-074 guards and PR-019 runtime
    """

    @staticmethod
    async def get_or_create_control(user_id: str, db: AsyncSession) -> TradingControl:
        """Get existing control or create default.

        Args:
            user_id: User ID
            db: Database session

        Returns:
            TradingControl: User's trading control settings

        Example:
            >>> control = await TradingControlService.get_or_create_control("user-123", db)
            >>> assert control.is_paused is False  # Default running
        """
        stmt = select(TradingControl).where(TradingControl.user_id == user_id)
        result = await db.execute(stmt)
        control = result.scalar_one_or_none()

        if control is None:
            # Create default control (running, no overrides)
            from uuid import uuid4

            control = TradingControl(
                id=str(uuid4()),
                user_id=user_id,
                is_paused=False,
                notifications_enabled=True,
            )
            db.add(control)
            await db.commit()
            await db.refresh(control)

        return control

    @staticmethod
    async def pause_trading(
        user_id: str,
        db: AsyncSession,
        actor: str = "user",
        reason: str | None = None,
    ) -> TradingControl:
        """Pause trading for user.

        Business Logic:
        - Sets is_paused=True, records timestamp and actor
        - Increments trading_paused_total{actor} metric
        - Strategy scheduler checks this flag before emitting signals
        - Existing open positions are NOT closed (manual close required)

        Args:
            user_id: User ID to pause
            db: Database session
            actor: Who initiated pause (user/admin/system)
            reason: Optional reason for audit trail

        Returns:
            TradingControl: Updated control with paused state

        Raises:
            ValueError: If already paused

        Example:
            >>> control = await TradingControlService.pause_trading(
            ...     "user-123", db, actor="user", reason="Risk breach"
            ... )
            >>> assert control.is_paused is True
            >>> assert control.paused_by == "user"
        """
        control = await TradingControlService.get_or_create_control(user_id, db)

        if control.is_paused:
            raise ValueError(f"Trading already paused for user {user_id}")

        control.is_paused = True
        control.paused_at = datetime.utcnow()
        control.paused_by = actor
        control.pause_reason = reason

        db.add(control)
        await db.commit()
        await db.refresh(control)

        # Record telemetry
        metrics = MetricsCollector()
        metrics.trading_paused_total.labels(actor=actor).inc()

        return control

    @staticmethod
    async def resume_trading(
        user_id: str, db: AsyncSession, actor: str = "user"
    ) -> TradingControl:
        """Resume trading for user.

        Business Logic:
        - Sets is_paused=False, clears pause metadata
        - Increments trading_resumed_total{actor} metric
        - Signal generation resumes on NEXT candle bar boundary (not immediate)
        - No retroactive signal generation for missed bars

        Args:
            user_id: User ID to resume
            db: Database session
            actor: Who initiated resume (user/admin)

        Returns:
            TradingControl: Updated control with running state

        Raises:
            ValueError: If already running

        Example:
            >>> control = await TradingControlService.resume_trading("user-123", db)
            >>> assert control.is_paused is False
            >>> assert control.paused_at is not None  # History preserved
        """
        control = await TradingControlService.get_or_create_control(user_id, db)

        if not control.is_paused:
            raise ValueError(f"Trading already running for user {user_id}")

        control.is_paused = False
        # Keep paused_at/paused_by/pause_reason for audit history
        control.updated_at = datetime.utcnow()

        db.add(control)
        await db.commit()
        await db.refresh(control)

        # Record telemetry
        metrics = MetricsCollector()
        metrics.trading_resumed_total.labels(actor=actor).inc()

        return control

    @staticmethod
    async def update_position_size(
        user_id: str, db: AsyncSession, position_size: Decimal | None
    ) -> TradingControl:
        """Update position size override.

        Business Logic:
        - position_size=None → use default risk % calculations (PR-074)
        - position_size=X → force all trades to X lots (within broker constraints)
        - Increments trading_size_changed_total metric
        - Size validation happens in PR-074 position_size.py

        Args:
            user_id: User ID
            db: Database session
            position_size: Override size in lots (None = use default)

        Returns:
            TradingControl: Updated control with new size

        Raises:
            ValueError: If position_size invalid (negative, > 100 lots)

        Example:
            >>> control = await TradingControlService.update_position_size(
            ...     "user-123", db, Decimal("0.5")
            ... )
            >>> assert control.position_size_override == 0.5
        """
        if position_size is not None:
            if position_size < Decimal("0.01"):
                raise ValueError("Position size must be >= 0.01 lots")
            if position_size > Decimal("100"):
                raise ValueError("Position size must be <= 100 lots")

        control = await TradingControlService.get_or_create_control(user_id, db)

        old_size = control.position_size_override
        control.position_size_override = float(position_size) if position_size else None

        db.add(control)
        await db.commit()
        await db.refresh(control)

        # Record telemetry
        if old_size != control.position_size_override:
            metrics = MetricsCollector()
            metrics.trading_size_changed_total.inc()

        return control

    @staticmethod
    async def update_notifications(
        user_id: str, db: AsyncSession, enabled: bool
    ) -> TradingControl:
        """Toggle notification delivery.

        Business Logic:
        - enabled=False → no Telegram/email/push notifications sent
        - enabled=True → resume notification delivery
        - Does NOT affect critical system alerts (security, payment failures)

        Args:
            user_id: User ID
            db: Database session
            enabled: Whether to send notifications

        Returns:
            TradingControl: Updated control

        Example:
            >>> control = await TradingControlService.update_notifications(
            ...     "user-123", db, enabled=False
            ... )
            >>> assert control.notifications_enabled is False
        """
        control = await TradingControlService.get_or_create_control(user_id, db)

        control.notifications_enabled = enabled

        db.add(control)
        await db.commit()
        await db.refresh(control)

        return control

    @staticmethod
    async def get_trading_status(user_id: str, db: AsyncSession) -> dict:
        """Get comprehensive trading status.

        Returns:
            dict with:
            - is_paused: bool
            - paused_at: datetime or None
            - paused_by: str or None
            - pause_reason: str or None
            - position_size_override: float or None
            - notifications_enabled: bool

        Example:
            >>> status = await TradingControlService.get_trading_status("user-123", db)
            >>> print(f"Trading: {'PAUSED' if status['is_paused'] else 'RUNNING'}")
        """
        control = await TradingControlService.get_or_create_control(user_id, db)

        return {
            "is_paused": control.is_paused,
            "paused_at": control.paused_at.isoformat() if control.paused_at else None,
            "paused_by": control.paused_by,
            "pause_reason": control.pause_reason,
            "position_size_override": control.position_size_override,
            "notifications_enabled": control.notifications_enabled,
            "updated_at": control.updated_at.isoformat(),
        }
