"""Device registry models."""

import secrets
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.db import Base


class Device(Base):
    """Client device registration.

    Tracks connected trading terminals/EAs with unique HMAC keys
    for secure signal polling.
    """

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Device ID",
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        doc="User ID who owns this device",
    )
    device_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Device name (e.g., 'Trading PC', 'VPS-1')",
    )
    hmac_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        doc="HMAC key for signal polling authentication",
    )
    last_poll: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Last time device polled for signals",
    )
    last_ack: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Last time device sent ACK",
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        index=True,
        doc="Whether device is active",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_devices_user", "user_id", "is_active"),
        Index("ix_devices_user_created", "user_id", "created_at"),
    )

    @staticmethod
    def generate_hmac_key() -> str:
        """Generate unique HMAC key for device.

        Returns:
            Random 64-character hex string
        """
        return secrets.token_hex(32)

    def is_online(self) -> bool:
        """Check if device is active and recently polled.

        Returns:
            True if active and polled in last 5 minutes
        """
        if not self.is_active or not self.last_poll:
            return False

        delta = datetime.utcnow() - self.last_poll
        return delta.total_seconds() < 300  # 5 minutes
