"""Pydantic schemas for affiliate API."""

from datetime import datetime

from pydantic import BaseModel, Field


class AffiliateOut(BaseModel):
    """Affiliate program status."""

    id: str
    user_id: str
    referral_token: str
    commission_tier: int
    total_commission: float
    paid_commission: float
    pending_commission: float
    status: int
    created_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class ReferralOut(BaseModel):
    """Referral record."""

    id: str
    referrer_id: str
    referred_user_id: str
    status: int
    created_at: datetime
    activated_at: datetime | None

    class Config:
        """Pydantic config."""

        from_attributes = True


class CommissionOut(BaseModel):
    """Commission earned."""

    id: str
    referrer_id: str
    referred_user_id: str
    trade_id: str | None
    amount: float
    tier: int
    status: int
    created_at: datetime
    paid_at: datetime | None

    class Config:
        """Pydantic config."""

        from_attributes = True


class PayoutCreate(BaseModel):
    """Payout request."""

    amount: float = Field(..., gt=0, description="Payout amount")
    bank_account: str | None = Field(None, max_length=50, description="Bank account")


class PayoutOut(BaseModel):
    """Payout record."""

    id: str
    referrer_id: str
    amount: float
    status: int
    bank_account: str | None
    reference: str | None
    created_at: datetime
    paid_at: datetime | None

    class Config:
        """Pydantic config."""

        from_attributes = True


class AffiliateStatsOut(BaseModel):
    """Affiliate earnings stats."""

    total_referrals: int = Field(description="Total referrals (activated)")
    total_commission: float = Field(description="Total commission earned")
    pending_commission: float = Field(description="Pending payout")
    paid_commission: float = Field(description="Already paid out")
    commission_tier: int = Field(description="Current tier percentage")


class ReferralStatsOut(BaseModel):
    """Referral statistics."""

    total_referrals: int
    activated_referrals: int
    total_commission: float
    pending_commission: float


class AffiliateCreate(BaseModel):
    """Request to create/join affiliate program."""

    referral_code: str | None = Field(None, max_length=50)
