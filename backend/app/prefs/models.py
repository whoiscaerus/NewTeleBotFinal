"""
User Preferences Model - PR-059

Manages user notification preferences, instrument filters, alert settings,
quiet hours, and digest frequency.

Integrates with:
- PR-044 (Price Alerts)
- PR-033/034 (Billing reminders)
- PR-032 (Marketing nudges)
- PR-104 (Position Tracking - execution failure alerts)
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
)
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class UserPreferences(Base):
    """
    User notification and alert preferences.

    Controls:
    - Which instruments to monitor (gold, sp500, crypto, etc.)
    - Alert types enabled (price, drawdown, copy-risk, execution failures)
    - Notification channels (telegram, email, web push)
    - Quiet hours (do not disturb periods in user's local timezone)
    - Digest frequency (immediate, hourly, daily)
    - Execution failure alerts (entry/exit failures from PR-104)

    Business Rules:
    - Default instruments: all enabled
    - Default alert types: all enabled
    - Default channels: telegram=true, email=true, push=false
    - Default execution failure alerts: ON (safety-first)
    - Quiet hours: None (24/7 notifications unless user sets)
    - Digest frequency: immediate
    - Timezone: UTC (until user updates)

    Security:
    - User can only access their own preferences (tenant isolation)
    - All updates logged via audit trail (PR-008)
    - JWT required for all operations

    Note: Using JSON for array storage (SQLite-compatible, also works with PostgreSQL)
    """

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Instrument filters (trading assets to monitor)
    # Stored as JSON array for SQLite compatibility
    # Examples: ["gold", "sp500", "crypto", "forex", "indices"]
    instruments_enabled = Column(
        JSON,
        nullable=False,
        default=["gold", "sp500", "crypto", "forex", "indices"],
    )

    # Alert types (what events to notify about)
    # Stored as JSON array for SQLite compatibility
    # Examples: ["price", "drawdown", "copy_risk", "execution_failure"]
    alert_types_enabled = Column(
        JSON,
        nullable=False,
        default=["price", "drawdown", "copy_risk", "execution_failure"],
    )

    # Notification channels (where to send alerts)
    notify_via_telegram = Column(Boolean, nullable=False, default=True)
    notify_via_email = Column(Boolean, nullable=False, default=True)
    notify_via_push = Column(Boolean, nullable=False, default=False)

    # Quiet hours (do not disturb periods in user's timezone)
    # Example: quiet_hours_start="22:00", quiet_hours_end="08:00", timezone="Europe/London"
    quiet_hours_enabled = Column(Boolean, nullable=False, default=False)
    quiet_hours_start = Column(Time, nullable=True)  # Local time in user's timezone
    quiet_hours_end = Column(Time, nullable=True)  # Local time in user's timezone
    timezone = Column(String(50), nullable=False, default="UTC")

    # Digest frequency (how often to batch notifications)
    # Values: "immediate", "hourly", "daily"
    digest_frequency = Column(String(20), nullable=False, default="immediate")

    # Execution failure alerts (PR-104 integration - default ON for safety)
    # When EA cannot execute entry order
    notify_entry_failure = Column(Boolean, nullable=False, default=True)
    # When position monitor cannot close at SL/TP
    notify_exit_failure = Column(Boolean, nullable=False, default=True)

    # Alert frequency throttling (max alerts per hour per type)
    # Example: max_alerts_per_hour=10 (prevents spam)
    max_alerts_per_hour = Column(Integer, nullable=False, default=10)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    user = relationship("User", back_populates="preferences")

    def __repr__(self) -> str:
        return (
            f"<UserPreferences(user_id={self.user_id}, "
            f"instruments={len(self.instruments_enabled or [])}, "
            f"telegram={self.notify_via_telegram}, "
            f"email={self.notify_via_email}, "
            f"push={self.notify_via_push}, "
            f"quiet_hours={self.quiet_hours_enabled})>"
        )

    def to_dict(self) -> dict:
        """Convert preferences to dictionary for API responses."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "instruments_enabled": self.instruments_enabled or [],
            "alert_types_enabled": self.alert_types_enabled or [],
            "notify_via_telegram": self.notify_via_telegram,
            "notify_via_email": self.notify_via_email,
            "notify_via_push": self.notify_via_push,
            "quiet_hours_enabled": self.quiet_hours_enabled,
            "quiet_hours_start": (
                self.quiet_hours_start.isoformat() if self.quiet_hours_start else None
            ),
            "quiet_hours_end": (
                self.quiet_hours_end.isoformat() if self.quiet_hours_end else None
            ),
            "timezone": self.timezone,
            "digest_frequency": self.digest_frequency,
            "notify_entry_failure": self.notify_entry_failure,
            "notify_exit_failure": self.notify_exit_failure,
            "max_alerts_per_hour": self.max_alerts_per_hour,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
