"""Affiliate system - referrals and commission tracking."""

from backend.app.affiliates.models import (
    Affiliate,
    AffiliateStatus,
    Commission,
    CommissionStatus,
    CommissionTier,
    Payout,
    PayoutStatus,
    Referral,
    ReferralStatus,
)
from backend.app.affiliates.schema import (
    AffiliateOut,
    CommissionOut,
    PayoutCreate,
    PayoutOut,
    ReferralOut,
)
from backend.app.affiliates.service import AffiliateService

__all__ = [
    "Affiliate",
    "AffiliateStatus",
    "Referral",
    "ReferralStatus",
    "Commission",
    "CommissionStatus",
    "CommissionTier",
    "Payout",
    "PayoutStatus",
    "AffiliateOut",
    "ReferralOut",
    "CommissionOut",
    "PayoutCreate",
    "PayoutOut",
    "AffiliateService",
]
