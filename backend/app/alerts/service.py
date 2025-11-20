"""
PR-044: Price Alerts & Notifications - User-specific price alerts

Alert system for price levels with Telegram + Mini App notifications.
Features:
- User-specific alert rules (above/below price triggers)
- Telegram DM notifications
- Mini App push/toast notifications
- Throttling (5-minute window to prevent spam)
- Deduplication tracking
- Prometheus metrics collection
"""

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel, Field, validator
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    and_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship

from backend.app.core.db import Base
from backend.app.core.errors import ValidationError

logger = logging.getLogger(__name__)

# Valid trading symbols
VALID_SYMBOLS = {
    "XAUUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "NZDUSD",
    "USDCAD",
    "USDCHF",
    "GOLD",
    "SILVER",
    "CRUDE",
    "NATGAS",
    "DXUSD",
    "SP500",
    "NASDQ100",
}

# Throttle window in minutes
THROTTLE_MINUTES = 5


# ============================================================================
# DATABASE MODELS
# ============================================================================


class PriceAlert(Base):
    """User price alert rule.

    Stores user-specific price alerts with above/below triggers.
    """

    __tablename__ = "price_alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(50), nullable=False)  # e.g., "XAUUSD"
    operator = Column(String(20), nullable=False)  # "above" or "below"
    price_level = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_triggered_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    notifications = relationship(
        "AlertNotification", back_populates="alert", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_price_alerts_user", "user_id"),
        Index("ix_price_alerts_user_symbol", "user_id", "symbol"),
        Index("ix_price_alerts_active", "is_active", "symbol"),
    )

    def __repr__(self):
        return (
            f"<PriceAlert {self.id}: {self.symbol} {self.operator} {self.price_level}>"
        )


class AlertNotification(Base):
    """Sent notifications (for deduplication/throttling).

    Tracks which alerts have sent notifications to prevent spam.
    """

    __tablename__ = "alert_notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    alert_id = Column(
        String(36), ForeignKey("price_alerts.id"), nullable=False, index=True
    )
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    price_triggered = Column(Float, nullable=False)
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    channel = Column(String(50), nullable=False)  # "telegram" or "miniapp"

    # Relationships
    alert = relationship("PriceAlert", back_populates="notifications")

    __table_args__ = (
        Index("ix_alert_notif_alert", "alert_id"),
        Index("ix_alert_notif_user", "user_id"),
        Index("ix_alert_notif_alert_user", "alert_id", "user_id"),
    )

    def __repr__(self):
        return f"<AlertNotification {self.id}: {self.channel} @ {self.price_triggered}>"


# ============================================================================
# SERVICE
# ============================================================================


class PriceAlertService:
    """
    Manages price alerts and alert evaluation.
    Runs periodically to check if alerts should trigger.
    """

    def __init__(self, telegram_service=None):
        """Initialize alert service.

        Args:
            telegram_service: Optional Telegram service for notifications
        """
        self.telegram_service = telegram_service
        self.throttle_minutes = THROTTLE_MINUTES

    async def create_alert(
        self,
        db: AsyncSession,
        user_id: str,
        symbol: str,
        operator: str,
        price_level: float,
    ) -> dict:
        """
        Create price alert.

        Args:
            db: Async database session
            user_id: User identifier
            symbol: Trading symbol (e.g., "XAUUSD")
            operator: "above" or "below"
            price_level: Price to trigger at

        Returns:
            Alert details dict

        Raises:
            ValidationError: If invalid input
        """
        # Validate operator
        if operator not in ["above", "below"]:
            logger.warning(f"Invalid operator: {operator}")
            raise ValidationError("Operator must be 'above' or 'below'")

        # Validate symbol
        if symbol not in VALID_SYMBOLS:
            logger.warning(f"Invalid symbol: {symbol}")
            raise ValidationError(f"Symbol '{symbol}' not supported (422)")

        # Validate price level
        if price_level <= 0 or price_level >= 1000000:
            logger.warning(f"Invalid price level: {price_level}")
            raise ValidationError("Price level must be between 0 and 1,000,000")

        # Check for duplicate alert (same user + symbol + operator + price)
        result = await db.execute(
            select(PriceAlert).where(
                and_(
                    PriceAlert.user_id == user_id,
                    PriceAlert.symbol == symbol,
                    PriceAlert.operator == operator,
                    PriceAlert.price_level == price_level,
                )
            )
        )
        if result.scalar():
            logger.warning(
                f"Duplicate alert for {user_id} {symbol} {operator} {price_level}"
            )
            raise ValidationError("Alert with same parameters already exists")

        # Create alert
        alert = PriceAlert(
            id=str(uuid4()),
            user_id=user_id,
            symbol=symbol,
            operator=operator,
            price_level=price_level,
            is_active=True,
            created_at=datetime.utcnow(),
        )

        db.add(alert)
        await db.commit()
        await db.refresh(alert)

        logger.info(
            f"Alert created: {alert.id}",
            extra={
                "user_id": user_id,
                "symbol": symbol,
                "operator": operator,
                "price_level": price_level,
            },
        )

        return {
            "alert_id": alert.id,
            "symbol": alert.symbol,
            "operator": alert.operator,
            "price_level": alert.price_level,
            "is_active": alert.is_active,
        }

    async def list_user_alerts(self, db: AsyncSession, user_id: str) -> list[dict]:
        """
        List all alerts for user.

        Args:
            db: Async database session
            user_id: User identifier

        Returns:
            List of alert details dicts
        """
        result = await db.execute(
            select(PriceAlert).where(PriceAlert.user_id == user_id)
        )
        alerts = result.scalars().all()

        logger.info(f"Listed {len(alerts)} alerts for user {user_id}")

        return [
            {
                "alert_id": alert.id,
                "symbol": alert.symbol,
                "operator": alert.operator,
                "price_level": alert.price_level,
                "is_active": alert.is_active,
                "last_triggered": (
                    alert.last_triggered_at.isoformat()
                    if alert.last_triggered_at
                    else None
                ),
                "created_at": alert.created_at.isoformat(),
            }
            for alert in alerts
        ]

    async def get_alert(
        self, db: AsyncSession, alert_id: str, user_id: str
    ) -> dict | None:
        """
        Get single alert by ID.

        Args:
            db: Async database session
            alert_id: Alert identifier
            user_id: User identifier (for ownership check)

        Returns:
            Alert dict or None
        """
        result = await db.execute(
            select(PriceAlert).where(
                and_(PriceAlert.id == alert_id, PriceAlert.user_id == user_id)
            )
        )
        alert = result.scalar()

        if not alert:
            return None

        return {
            "alert_id": alert.id,
            "symbol": alert.symbol,
            "operator": alert.operator,
            "price_level": alert.price_level,
            "is_active": alert.is_active,
            "last_triggered": (
                alert.last_triggered_at.isoformat() if alert.last_triggered_at else None
            ),
            "created_at": alert.created_at.isoformat(),
        }

    async def delete_alert(self, db: AsyncSession, alert_id: str, user_id: str) -> bool:
        """
        Delete alert.

        Args:
            db: Async database session
            alert_id: Alert identifier
            user_id: User identifier (for ownership check)

        Returns:
            True if deleted
        """
        result = await db.execute(
            select(PriceAlert).where(
                and_(PriceAlert.id == alert_id, PriceAlert.user_id == user_id)
            )
        )
        alert = result.scalar()

        if not alert:
            logger.warning(f"Alert not found: {alert_id} for user {user_id}")
            return False

        await db.delete(alert)
        await db.commit()

        logger.info(f"Alert deleted: {alert_id}")
        return True

    async def update_alert(
        self,
        db: AsyncSession,
        alert_id: str,
        user_id: str,
        operator: str | None = None,
        price_level: float | None = None,
        is_active: bool | None = None,
    ) -> dict | None:
        """
        Update alert fields.

        Args:
            db: Async database session
            alert_id: Alert identifier
            user_id: User identifier (for ownership check)
            operator: New operator ("above" or "below")
            price_level: New price level
            is_active: New active status

        Returns:
            Updated alert dict, or None if not found
        """
        result = await db.execute(
            select(PriceAlert).where(
                and_(PriceAlert.id == alert_id, PriceAlert.user_id == user_id)
            )
        )
        alert = result.scalar()

        if not alert:
            logger.warning(f"Alert not found: {alert_id} for user {user_id}")
            return None

        if operator is not None:
            alert.operator = operator
        if price_level is not None:
            alert.price_level = price_level
        if is_active is not None:
            alert.is_active = is_active

        await db.commit()
        await db.refresh(alert)

        logger.info(f"Alert updated: {alert_id}")

        return {
            "alert_id": alert.id,
            "user_id": alert.user_id,
            "symbol": alert.symbol,
            "operator": alert.operator,
            "price_level": alert.price_level,
            "is_active": alert.is_active,
            "last_triggered": (
                alert.last_triggered_at.isoformat() if alert.last_triggered_at else None
            ),
            "created_at": alert.created_at.isoformat(),
        }

    async def evaluate_alerts(
        self, db: AsyncSession, current_prices: dict[str, float]
    ) -> list[dict]:
        """
        Evaluate all active alerts against current prices.

        Args:
            db: Async database session
            current_prices: Dict of symbol -> current price

        Returns:
            List of triggered alerts {alert_id, user_id, symbol, ...}
        """
        triggered = []

        if not current_prices:
            logger.warning("No current prices provided")
            return triggered

        # Get all active alerts for symbols we have prices for
        result = await db.execute(
            select(PriceAlert).where(
                and_(
                    PriceAlert.is_active.is_(True),
                    PriceAlert.symbol.in_(list(current_prices.keys())),
                )
            )
        )
        alerts = result.scalars().all()

        logger.info(
            f"Evaluating {len(alerts)} alerts against {len(current_prices)} prices"
        )

        for alert in alerts:
            current_price = current_prices.get(alert.symbol)
            if current_price is None:
                continue

            should_trigger = False

            # Check trigger logic
            if alert.operator == "above" and current_price >= alert.price_level:
                should_trigger = True
                logger.debug(
                    f"Alert {alert.id}: ABOVE trigger {current_price} >= {alert.price_level}"
                )
            elif alert.operator == "below" and current_price <= alert.price_level:
                should_trigger = True
                logger.debug(
                    f"Alert {alert.id}: BELOW trigger {current_price} <= {alert.price_level}"
                )

            if should_trigger:
                # Check throttle
                if await self._should_notify(db, alert.id):
                    triggered.append(
                        {
                            "alert_id": alert.id,
                            "user_id": alert.user_id,
                            "symbol": alert.symbol,
                            "operator": alert.operator,
                            "price_level": alert.price_level,
                            "current_price": current_price,
                        }
                    )

                    # Update trigger time
                    alert.last_triggered_at = datetime.utcnow()
                    db.add(alert)
                    await db.commit()

                    logger.info(
                        f"Alert triggered: {alert.id}",
                        extra={
                            "alert_id": alert.id,
                            "user_id": alert.user_id,
                            "symbol": alert.symbol,
                            "current_price": current_price,
                        },
                    )
                else:
                    logger.debug(
                        f"Alert {alert.id} throttled (within {THROTTLE_MINUTES}min window)"
                    )

        return triggered

    async def _should_notify(self, db: AsyncSession, alert_id: str) -> bool:
        """
        Check if enough time has passed since last notification.

        Args:
            db: Async database session
            alert_id: Alert identifier

        Returns:
            True if should notify (throttle period passed)
        """
        result = await db.execute(
            select(AlertNotification)
            .where(AlertNotification.alert_id == alert_id)
            .order_by(AlertNotification.sent_at.desc())
            .limit(1)
        )
        last_notif = result.scalar()

        if not last_notif:
            logger.debug(f"Alert {alert_id}: first notification")
            return True

        time_since = datetime.utcnow() - last_notif.sent_at
        should_notify = time_since >= timedelta(minutes=self.throttle_minutes)

        if should_notify:
            logger.debug(
                f"Alert {alert_id}: throttle passed ({time_since.total_seconds():.0f}s)"
            )
        else:
            logger.debug(
                f"Alert {alert_id}: throttle active ({time_since.total_seconds():.0f}s < {self.throttle_minutes * 60}s)"
            )

        return should_notify

    async def record_notification(
        self,
        db: AsyncSession,
        alert_id: str,
        user_id: str,
        channel: str,
        current_price: float,
    ) -> None:
        """
        Record that notification was sent.

        Args:
            db: Async database session
            alert_id: Alert identifier
            user_id: User identifier
            channel: Notification channel ("telegram" or "miniapp")
            current_price: Price when triggered
        """
        notif = AlertNotification(
            id=str(uuid4()),
            alert_id=alert_id,
            user_id=user_id,
            price_triggered=current_price,
            channel=channel,
            sent_at=datetime.utcnow(),
        )

        db.add(notif)
        await db.commit()

        logger.info(
            f"Notification recorded: {notif.id}",
            extra={
                "alert_id": alert_id,
                "channel": channel,
                "price": current_price,
            },
        )

    async def send_notifications(
        self,
        db: AsyncSession,
        triggered_alerts: list[dict],
        telegram_service=None,
    ) -> None:
        """
        Send Telegram + Mini App notifications for triggered alerts.

        Args:
            db: Async database session
            triggered_alerts: List of triggered alert dicts
            telegram_service: Optional Telegram service
        """
        for alert in triggered_alerts:
            try:
                # Send Telegram notification
                if telegram_service or self.telegram_service:
                    svc = telegram_service or self.telegram_service
                    message = (
                        f"🚨 Price Alert: {alert['symbol']}\n"
                        f"Triggered: ${alert['current_price']:.2f}\n"
                        f"Condition: {alert['operator'].upper()} ${alert['price_level']:.2f}"
                    )
                    await svc.send_telegram_dm(alert["user_id"], message)
                    await self.record_notification(
                        db,
                        alert["alert_id"],
                        alert["user_id"],
                        "telegram",
                        alert["current_price"],
                    )

                    logger.info(
                        f"Telegram notification sent for alert {alert['alert_id']}"
                    )

            except Exception as e:
                logger.error(
                    f"Error sending notification for alert {alert['alert_id']}: {e}",
                    exc_info=True,
                )


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================


class AlertCreate(BaseModel):
    """Request to create alert."""

    symbol: str = Field(
        ..., min_length=2, max_length=50, description="Trading symbol (e.g., XAUUSD)"
    )
    operator: str = Field(..., pattern="^(above|below)$", description="above or below")
    price_level: float = Field(..., gt=0, lt=1000000, description="Price trigger level")

    @validator("symbol")
    def validate_symbol(cls, v):
        """Validate symbol is supported."""
        if v not in VALID_SYMBOLS:
            raise ValueError(f"Symbol '{v}' not supported")
        return v


class AlertUpdate(BaseModel):
    """Request to update alert."""

    operator: str | None = Field(None, pattern="^(above|below)$")
    price_level: float | None = Field(None, gt=0, lt=1000000)
    is_active: bool | None = None


class AlertOut(BaseModel):
    """Alert response."""

    alert_id: str
    symbol: str
    operator: str
    price_level: float
    is_active: bool
    last_triggered: str | None = None
    created_at: str | None = None

    class Config:
        from_attributes = True
