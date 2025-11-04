"""Database models for marketing functionality.

This module defines models for tracking marketing interactions such as CTA clicks,
promo impressions, and conversion tracking.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.db import Base


class MarketingClick(Base):
    """Marketing CTA click tracking model.

    Represents a user interaction with a marketing call-to-action,
    enabling conversion tracking and campaign effectiveness analysis.

    Fields:
        id: Unique click identifier (UUID)
        user_id: User who clicked the CTA (Telegram user ID)
        promo_id: Associated promo campaign identifier
        cta_text: Call-to-action button text
        chat_id: Telegram chat ID (optional, for message context)
        message_id: Telegram message ID (optional, for message context)
        click_data: JSON metadata (conversion status, source, plan, etc.)
        clicked_at: Click timestamp (UTC)

    Example:
        >>> click = MarketingClick(
        ...     id=str(uuid4()),
        ...     user_id="123456789",
        ...     promo_id="promo_1",
        ...     cta_text="Upgrade to Premium",
        ...     clicked_at=datetime.utcnow()
        ... )
    """

    __tablename__ = "marketing_clicks"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Unique click identifier",
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        doc="Telegram user ID who clicked",
    )
    promo_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="Promo campaign identifier",
    )
    cta_text: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="CTA button text",
    )
    chat_id: Mapped[int | None] = mapped_column(
        nullable=True,
        doc="Telegram chat ID for message context",
    )
    message_id: Mapped[int | None] = mapped_column(
        nullable=True,
        doc="Telegram message ID for message context",
    )
    click_data: Mapped[dict] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        doc="JSON metadata (conversion, source, plan, etc.)",
    )
    clicked_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
        doc="Click timestamp (UTC)",
    )

    __table_args__ = (Index("ix_marketing_clicks_user_promo", "user_id", "promo_id"),)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<MarketingClick {self.id}: user={self.user_id} "
            f"promo={self.promo_id} at {self.clicked_at}>"
        )


class MarketingPromoLog(Base):
    """Marketing promo posting event log.

    Tracks when promos are posted to channels, recording success/failure
    counts for analytics and debugging.

    Fields:
        id: Unique log entry identifier (UUID)
        promo_id: ID of the promo that was posted
        posted_to: Number of successful posts
        failed: Number of failed posts
        details: JSON metadata (per-chat status, errors, etc.)
        created_at: Log timestamp (UTC)

    Example:
        >>> log = MarketingPromoLog(
        ...     id=str(uuid4()),
        ...     promo_id="promo_1",
        ...     posted_to=3,
        ...     failed=0,
        ...     created_at=datetime.utcnow()
        ... )
    """

    __tablename__ = "marketing_promo_logs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Unique log entry identifier",
    )
    promo_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="Promo campaign identifier",
    )
    posted_to: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        doc="Number of successful posts",
    )
    failed: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        doc="Number of failed posts",
    )
    details: Mapped[dict] = mapped_column(
        "details_json",
        JSON,
        nullable=False,
        default=dict,
        doc="JSON metadata (per-chat status, errors)",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
        index=True,
        doc="Log timestamp (UTC)",
    )

    __table_args__ = (Index("ix_marketing_logs_promo_time", "promo_id", "created_at"),)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<MarketingPromoLog {self.id}: promo={self.promo_id} "
            f"posted={self.posted_to} failed={self.failed} at {self.created_at}>"
        )

