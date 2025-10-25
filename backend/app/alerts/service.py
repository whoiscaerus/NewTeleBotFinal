"""
PR-044: Price Alerts & Notifications - User-specific price alerts

Alert system for price levels with Telegram + Mini App notifications.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Session

from backend.app.core.db import Base


class PriceAlert(Base):
    """User price alert rule."""

    __tablename__ = "price_alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(50), nullable=False)
    operator = Column(String(20), nullable=False)  # "above" or "below"
    price_level = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_alerts_user_symbol", "user_id", "symbol"),
        Index("ix_alerts_active", "is_active", "symbol"),
    )


class AlertNotification(Base):
    """Sent notifications (for deduplication)."""

    __tablename__ = "alert_notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id = Column(
        String(36), ForeignKey("price_alerts.id"), nullable=False, index=True
    )
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    price_triggered = Column(Float, nullable=False)
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    channel = Column(String(50))  # "telegram" or "miniapp"

    __table_args__ = (Index("ix_notif_alert_user", "alert_id", "user_id"),)


class PriceAlertService:
    """
    Manages price alerts and alert evaluation.
    Runs periodically to check if alerts should trigger.
    """

    def __init__(self):
        """Initialize alert service."""
        self.throttle_minutes = 5  # Min time between alerts for same alert

    def create_alert(
        self, db: Session, user_id: str, symbol: str, operator: str, price_level: float
    ) -> dict:
        """
        Create price alert.

        Args:
            db: Database session
            user_id: User identifier
            symbol: Trading symbol (e.g., "XAUUSD")
            operator: "above" or "below"
            price_level: Price to trigger at

        Returns:
            Alert details
        """
        if operator not in ["above", "below"]:
            raise ValueError("Operator must be 'above' or 'below'")

        if price_level <= 0:
            raise ValueError("Price level must be positive")

        alert = PriceAlert(
            id=str(uuid.uuid4()),
            user_id=user_id,
            symbol=symbol,
            operator=operator,
            price_level=price_level,
            is_active=True,
            created_at=datetime.utcnow(),
        )

        db.add(alert)
        db.commit()

        return {
            "alert_id": alert.id,
            "symbol": alert.symbol,
            "operator": alert.operator,
            "price_level": alert.price_level,
            "is_active": True,
        }

    def list_user_alerts(self, db: Session, user_id: str) -> list[dict]:
        """
        List all alerts for user.

        Args:
            db: Database session
            user_id: User identifier

        Returns:
            List of alert details
        """
        alerts = db.query(PriceAlert).filter_by(user_id=user_id).all()

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
            }
            for alert in alerts
        ]

    def delete_alert(self, db: Session, alert_id: str, user_id: str) -> bool:
        """
        Delete alert.

        Args:
            db: Database session
            alert_id: Alert identifier
            user_id: User identifier (for ownership check)

        Returns:
            True if deleted
        """
        alert = db.query(PriceAlert).filter_by(id=alert_id, user_id=user_id).first()

        if not alert:
            return False

        db.delete(alert)
        db.commit()
        return True

    def evaluate_alerts(
        self, db: Session, current_prices: dict[str, float]
    ) -> list[dict]:
        """
        Evaluate all active alerts against current prices.

        Args:
            db: Database session
            current_prices: Dict of symbol -> current price

        Returns:
            List of triggered alerts
        """
        triggered = []

        # Get all active alerts for symbols we have prices for
        alerts = (
            db.query(PriceAlert)
            .filter(
                PriceAlert.is_active,
                PriceAlert.symbol.in_(list(current_prices.keys())),
            )
            .all()
        )

        for alert in alerts:
            current_price = current_prices.get(alert.symbol)
            if current_price is None:
                continue

            should_trigger = False

            if alert.operator == "above" and current_price >= alert.price_level:
                should_trigger = True
            elif alert.operator == "below" and current_price <= alert.price_level:
                should_trigger = True

            if should_trigger:
                # Check throttle
                if self._should_notify(db, alert.id):
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
                    db.commit()

        return triggered

    def _should_notify(self, db: Session, alert_id: str) -> bool:
        """
        Check if enough time has passed since last notification.

        Args:
            db: Database session
            alert_id: Alert identifier

        Returns:
            True if should notify
        """
        from datetime import timedelta

        last_notif = (
            db.query(AlertNotification)
            .filter_by(alert_id=alert_id)
            .order_by(AlertNotification.sent_at.desc())
            .first()
        )

        if not last_notif:
            return True

        time_since = datetime.utcnow() - last_notif.sent_at
        return time_since >= timedelta(minutes=self.throttle_minutes)

    def record_notification(
        self,
        db: Session,
        alert_id: str,
        user_id: str,
        channel: str,
        current_price: float,
    ):
        """
        Record that notification was sent.

        Args:
            db: Database session
            alert_id: Alert identifier
            user_id: User identifier
            channel: Notification channel ("telegram" or "miniapp")
            current_price: Price when triggered
        """
        notif = AlertNotification(
            id=str(uuid.uuid4()),
            alert_id=alert_id,
            user_id=user_id,
            price_triggered=current_price,
            channel=channel,
            sent_at=datetime.utcnow(),
        )

        db.add(notif)
        db.commit()


# Pydantic schemas
class AlertCreate(BaseModel):
    """Request to create alert."""

    symbol: str = Field(..., min_length=2, max_length=50, description="Trading symbol")
    operator: str = Field(..., pattern="^(above|below)$", description="above or below")
    price_level: float = Field(..., gt=0, lt=1000000, description="Price trigger level")


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
