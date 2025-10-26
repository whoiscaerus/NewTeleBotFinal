"""Database models for affiliate system."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.db import Base


class AffiliateStatus(Enum):
    """Affiliate program participation status."""

    INACTIVE = 0
    ACTIVE = 1
    SUSPENDED = 2


class ReferralStatus(Enum):
    """Referral signup status."""

    PENDING = 0
    ACTIVATED = 1
    CANCELLED = 2


class CommissionStatus(Enum):
    """Commission payment status."""

    PENDING = 0
    PAID = 1
    REFUNDED = 2


class CommissionTier(Enum):
    """Commission percentage tiers."""

    TIER0 = 0.10  # 10%
    TIER1 = 0.15  # 15%
    TIER2 = 0.20  # 20%
    TIER3 = 0.25  # 25%


class PayoutStatus(Enum):
    """Payout processing status."""

    PENDING = 0
    PROCESSING = 1
    COMPLETED = 2
    FAILED = 3


class Affiliate(Base):
    """Affiliate program participant.

    Tracks referrer earnings, commission accumulation, and payout requests.
    """

    __tablename__ = "affiliates"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Affiliate ID",
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
        doc="User ID of referrer",
    )
    referral_token: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True,
        doc="Unique token for referral link",
    )
    commission_tier: Mapped[int] = mapped_column(
        nullable=False,
        default=CommissionTier.TIER0.value,
        doc="Commission percentage tier",
    )
    total_commission: Mapped[float] = mapped_column(
        nullable=False,
        default=0.0,
        doc="Total commission earned (all time)",
    )
    paid_commission: Mapped[float] = mapped_column(
        nullable=False,
        default=0.0,
        doc="Commission already paid out",
    )
    pending_commission: Mapped[float] = mapped_column(
        nullable=False,
        default=0.0,
        doc="Commission pending payout",
    )
    status: Mapped[int] = mapped_column(
        nullable=False,
        default=AffiliateStatus.ACTIVE.value,
        doc="Affiliate status (active, suspended)",
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

    __table_args__ = (Index("ix_affiliates_user_created", "user_id", "created_at"),)

    def is_active(self) -> bool:
        """Check if affiliate is active."""
        return self.status == AffiliateStatus.ACTIVE.value


class Referral(Base):
    """Referral signup tracking.

    Records when a user signs up via referral link.
    """

    __tablename__ = "referrals"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Referral ID",
    )
    referrer_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        doc="User ID of referrer",
    )
    referred_user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
        doc="User ID of referred user",
    )
    status: Mapped[int] = mapped_column(
        nullable=False,
        default=ReferralStatus.PENDING.value,
        doc="Referral status (pending, activated, cancelled)",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="When referral was activated (user logged in first time)",
    )

    __table_args__ = (
        Index("ix_referrals_referrer", "referrer_id", "created_at"),
        Index("ix_referrals_referred", "referred_user_id"),
    )


class Commission(Base):
    """Commission earned on referred user's trades.

    Created when referred user places a trade.
    """

    __tablename__ = "commissions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Commission ID",
    )
    referrer_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        doc="User ID of referrer earning commission",
    )
    referred_user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        doc="User ID of referred user",
    )
    trade_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        doc="Trade ID that generated commission (if applicable)",
    )
    amount: Mapped[float] = mapped_column(
        nullable=False,
        doc="Commission amount in account currency",
    )
    tier: Mapped[int] = mapped_column(
        nullable=False,
        doc="Commission tier (percentage)",
    )
    status: Mapped[int] = mapped_column(
        nullable=False,
        default=CommissionStatus.PENDING.value,
        doc="Commission status (pending, paid, refunded)",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="When commission was paid out",
    )

    __table_args__ = (
        Index("ix_commissions_referrer", "referrer_id", "created_at"),
        Index("ix_commissions_referred", "referred_user_id"),
        Index("ix_commissions_status", "status"),
    )


class Payout(Base):
    """Payout request from affiliate.

    Aggregates pending commissions and tracks payout processing.
    """

    __tablename__ = "commission_payouts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Payout ID",
    )
    referrer_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        doc="User ID requesting payout",
    )
    amount: Mapped[float] = mapped_column(
        nullable=False,
        doc="Payout amount",
    )
    status: Mapped[int] = mapped_column(
        nullable=False,
        default=PayoutStatus.PENDING.value,
        index=True,
        doc="Payout status (pending, processing, completed, failed)",
    )
    bank_account: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="Bank account for payout",
    )
    reference: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="External reference (e.g., transaction ID)",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="When payout was completed",
    )

    __table_args__ = (
        Index("ix_payouts_referrer", "referrer_id", "created_at"),
        Index("ix_payouts_status", "status"),
    )
