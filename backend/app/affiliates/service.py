"""Affiliate service - business logic."""

import logging
import secrets
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.affiliates.models import (
    Affiliate,
    AffiliateEarnings,
    AffiliateStatus,
    Commission,
    CommissionTier,
    Payout,
    PayoutStatus,
    Referral,
    ReferralEvent,
    ReferralStatus,
)
from backend.app.affiliates.schema import CommissionOut, PayoutOut
from backend.app.core.errors import APIException

logger = logging.getLogger(__name__)


class AffiliateService:
    """Service for affiliate program management.

    Responsibilities:
    - Generate and track referral links
    - Record referrals and track activation
    - Calculate commissions on referred user trades
    - Process payout requests
    """

    def __init__(self, db: AsyncSession):
        """Initialize service.

        Args:
            db: Database session
        """
        self.db = db

    async def register_affiliate(self, user_id: str) -> Affiliate:
        """Register user for affiliate program.

        Args:
            user_id: User ID

        Returns:
            Affiliate object

        Raises:
            APIException: If registration fails
        """
        try:
            # Check if already registered
            existing = await self.db.execute(
                select(Affiliate).where(Affiliate.user_id == user_id)
            )
            existing_affiliate = existing.scalar_one_or_none()
            if existing_affiliate:
                logger.info(
                    f"Affiliate already registered: {user_id}",
                    extra={"user_id": user_id},
                )
                return existing_affiliate

            # Generate unique token
            token = secrets.token_urlsafe(24)

            # Create affiliate record
            affiliate = Affiliate(
                user_id=user_id,
                referral_token=token,
                commission_tier=CommissionTier.TIER0.value,
                status=AffiliateStatus.ACTIVE.value,
            )

            self.db.add(affiliate)
            await self.db.commit()
            await self.db.refresh(affiliate)

            logger.info(
                f"Affiliate registered: {user_id}",
                extra={"user_id": user_id, "token": token[:10]},
            )

            return affiliate

        except APIException:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Affiliate registration failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="server_error",
                title="Registration Error",
                detail="Failed to register affiliate",
            ) from e

    async def record_referral(self, token: str, referred_user_id: str) -> None:
        """Record new referral signup.

        Args:
            token: Referral token from link
            referred_user_id: ID of user signing up

        Raises:
            APIException: If token invalid or user already referred
        """
        try:
            # Find affiliate by token
            result = await self.db.execute(
                select(Affiliate).where(Affiliate.referral_token == token)
            )
            affiliate = result.scalar()

            if not affiliate:
                raise APIException(
                    status_code=404,
                    error_type="INVALID_TOKEN",
                    title="Error",
                    detail="Referral token not found",
                )

            # Check if already referred
            existing = await self.db.execute(
                select(Referral).where(Referral.referred_user_id == referred_user_id)
            )
            if existing.scalar():
                raise APIException(
                    status_code=409,
                    error_type="referral_conflict",
                    title="User Already Referred",
                    detail="User already has a referrer",
                )

            # Create referral record
            referral = Referral(
                referrer_id=affiliate.user_id,
                referred_user_id=referred_user_id,
                status=ReferralStatus.PENDING.value,
            )

            self.db.add(referral)
            await self.db.commit()
            await self.db.refresh(referral)

            logger.info(
                f"Referral recorded: {referred_user_id} → {affiliate.user_id}",
                extra={
                    "referrer_id": affiliate.user_id,
                    "referred_user_id": referred_user_id,
                },
            )

        except APIException:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Referral recording failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="REFERRAL_ERROR",
                title="Error",
                detail="Failed to record referral",
            ) from e

    async def activate_referral(self, referred_user_id: str) -> None:
        """Activate referral (user first login).

        Args:
            referred_user_id: User ID
        """
        try:
            result = await self.db.execute(
                select(Referral).where(
                    and_(
                        Referral.referred_user_id == referred_user_id,
                        Referral.status == ReferralStatus.PENDING.value,
                    )
                )
            )
            referral = result.scalar()

            if referral:
                referral.status = ReferralStatus.ACTIVATED.value
                referral.activated_at = datetime.utcnow()
                await self.db.commit()

                logger.info(
                    f"Referral activated: {referred_user_id}",
                    extra={"referred_user_id": referred_user_id},
                )

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Referral activation failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="ACTIVATION_ERROR",
                title="Error",
                detail="Failed to activate referral",
            ) from e

    async def record_commission(
        self,
        affiliate_id: str,
        referee_id: str,
        amount_gbp: float,
        tier: str,
    ) -> "AffiliateEarnings":
        """Record commission earned on referred user's subscription.

        Args:
            affiliate_id: Affiliate user ID
            referee_id: Referred user ID
            amount_gbp: Commission amount in GBP
            tier: Commission tier

        Returns:
            AffiliateEarnings: Created earnings record

        Raises:
            APIException: If recording fails
        """
        try:
            from backend.app.affiliates.models import AffiliateEarnings

            # Affiliate MUST already exist (should register first)
            affiliate_result = await self.db.execute(
                select(Affiliate).where(Affiliate.user_id == affiliate_id)
            )
            affiliate = affiliate_result.scalar()

            if not affiliate:
                raise APIException(
                    status_code=404,
                    error_type="not_found",
                    title="Affiliate Not Found",
                    detail=f"User {affiliate_id} is not registered as an affiliate. Register first before recording commissions.",
                )

            # Update affiliate totals
            affiliate.total_commission += amount_gbp
            affiliate.pending_commission += amount_gbp

            # Create earnings record
            earning = AffiliateEarnings(
                affiliate_id=affiliate_id,
                user_id=affiliate_id,
                amount=amount_gbp,
                commission_type=tier,
                period=datetime.utcnow().strftime("%Y-%m"),
                paid=False,
            )

            self.db.add(earning)
            await self.db.commit()
            await self.db.refresh(earning)

            logger.info(
                f"Commission recorded: {affiliate_id} earned {amount_gbp} GBP",
                extra={
                    "affiliate_id": affiliate_id,
                    "referee_id": referee_id,
                    "amount": amount_gbp,
                },
            )

            return earning

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Commission recording failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="server_error",
                title="Commission Error",
                detail="Failed to record commission",
            ) from e

    async def get_stats(self, affiliate_id: str) -> dict:
        """Get affiliate statistics.

        Args:
            affiliate_id: Affiliate ID

        Returns:
            Dict with affiliate statistics (clicks, signups, subscriptions, conversion_rate)

        Raises:
            APIException: If affiliate not found
        """
        try:
            affiliate_result = await self.db.execute(
                select(Affiliate).where(Affiliate.id == affiliate_id)
            )
            affiliate = affiliate_result.scalar()

            if not affiliate:
                raise APIException(
                    status_code=404,
                    error_type="not_found",
                    title="Affiliate Not Found",
                    detail="Affiliate not found",
                )

            # Count signup events (each click/signup)
            signups_result = await self.db.execute(
                select(func.count(ReferralEvent.id)).where(
                    and_(
                        ReferralEvent.referral_code == affiliate.referral_code,
                        ReferralEvent.event_type == "signup",
                    )
                )
            )
            total_clicks = signups_result.scalar() or 0

            # Count unique users who signed up
            unique_signups_result = await self.db.execute(
                select(func.count(func.distinct(ReferralEvent.user_id))).where(
                    and_(
                        ReferralEvent.referral_code == affiliate.referral_code,
                        ReferralEvent.event_type == "signup",
                    )
                )
            )
            total_signups = unique_signups_result.scalar() or 0

            # Count subscriptions
            subscriptions_result = await self.db.execute(
                select(func.count(ReferralEvent.id)).where(
                    and_(
                        ReferralEvent.referral_code == affiliate.referral_code,
                        ReferralEvent.event_type == "subscription_created",
                    )
                )
            )
            total_subscriptions = subscriptions_result.scalar() or 0

            # Calculate conversion rate
            conversion_rate = (
                total_subscriptions / total_signups if total_signups > 0 else 0.0
            )

            return {
                "total_clicks": total_clicks,
                "total_signups": total_signups,
                "total_subscriptions": total_subscriptions,
                "conversion_rate": conversion_rate,
                "total_commission": affiliate.total_commission,
                "pending_commission": affiliate.pending_commission,
                "paid_commission": affiliate.paid_commission,
            }

        except APIException:
            raise
        except Exception as e:
            logger.error(f"Stats retrieval failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="server_error",
                title="Stats Error",
                detail="Failed to retrieve stats",
            ) from e

    async def get_earnings_summary(self, user_id: str) -> dict:
        """Get affiliate earnings summary.

        Args:
            user_id: User ID

        Returns:
            Dict with earnings summary (total, pending, paid)
        """
        try:
            # Get affiliate - if not exists, return zero earnings
            affiliate_result = await self.db.execute(
                select(Affiliate).where(Affiliate.user_id == user_id)
            )
            affiliate = affiliate_result.scalar()

            if not affiliate:
                # User must be registered as affiliate to get earnings
                raise APIException(
                    status_code=404,
                    error_type="not_found",
                    title="Not an Affiliate",
                    detail="User has not registered as an affiliate",
                )

            return {
                "total_earnings": affiliate.total_commission,
                "pending_earnings": affiliate.pending_commission,
                "paid_earnings": affiliate.paid_commission,
            }

        except Exception as e:
            logger.error(f"Earnings summary failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="server_error",
                title="Summary Error",
                detail="Failed to retrieve earnings summary",
            ) from e

    async def request_payout(self, affiliate_id: str) -> PayoutOut:
        """Request commission payout of all pending earnings.

        Idempotent: Multiple calls return the same payout if one already exists with PENDING status.

        Args:
            affiliate_id: User ID (affiliate)

        Returns:
            Payout record

        Raises:
            ValueError: If pending commission < £50 minimum
            APIException: If affiliate not found
        """
        try:
            # FIRST: Check for existing pending payout (IDEMPOTENCY - must check before balance check)
            # This query will always hit the database (not cache) due to AsyncSession behavior
            existing_payout_result = await self.db.execute(
                select(Payout).where(
                    (Payout.referrer_id == affiliate_id)
                    & (Payout.status == PayoutStatus.PENDING.value)
                )
            )
            existing_payout = existing_payout_result.scalar()

            if existing_payout:
                logger.info(
                    f"Idempotency: returning existing payout {existing_payout.id}",
                    extra={
                        "affiliate_id": affiliate_id,
                        "payout_id": existing_payout.id,
                    },
                )
                return PayoutOut.model_validate(existing_payout)

            # SECOND: Get affiliate (only if creating new payout)
            affiliate_result = await self.db.execute(
                select(Affiliate).where(Affiliate.user_id == affiliate_id)
            )
            affiliate = affiliate_result.scalar()

            if not affiliate:
                raise APIException(
                    status_code=404,
                    error_type="not_found",
                    title="Not an Affiliate",
                    detail="User is not registered as an affiliate",
                )

            # THIRD: Check minimum payout threshold (£50 - only for new payouts)
            MIN_PAYOUT_GBP = 50.0
            if affiliate.pending_commission < MIN_PAYOUT_GBP:
                raise ValueError(
                    f"Insufficient pending commission for payout (minimum: £{MIN_PAYOUT_GBP}, available: £{affiliate.pending_commission})"
                )

            # FOURTH: Create payout record with all pending commission
            payout = Payout(
                referrer_id=affiliate_id,
                amount=affiliate.pending_commission,
                status=PayoutStatus.PENDING.value,
            )

            self.db.add(payout)

            # FIFTH: Clear pending commission (it's now locked in this payout)
            affiliate.pending_commission = 0.0
            self.db.add(affiliate)

            await self.db.commit()
            await self.db.refresh(payout)
            await self.db.refresh(affiliate)

            logger.info(
                f"Payout created: {payout.id} for £{payout.amount}",
                extra={
                    "affiliate_id": affiliate_id,
                    "payout_id": payout.id,
                    "amount": payout.amount,
                },
            )

            return PayoutOut.model_validate(payout)

        except ValueError:
            raise
        except APIException:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Payout request failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="server_error",
                title="Payout Error",
                detail="Failed to request payout",
            ) from e

    async def get_commission_history(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CommissionOut]:
        """Get commission history for affiliate.

        Args:
            user_id: User ID
            limit: Results limit
            offset: Results offset

        Returns:
            List of commissions
        """
        try:
            result = await self.db.execute(
                select(Commission)
                .where(Commission.referrer_id == user_id)
                .order_by(Commission.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            commissions = result.scalars().all()

            return [CommissionOut.model_validate(c) for c in commissions]

        except Exception as e:
            logger.error(f"History retrieval failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="HISTORY_ERROR",
                title="Error",
                detail="Failed to retrieve commission history",
            ) from e

    async def generate_referral_link(self, affiliate_id: str) -> str:
        """Generate shareable referral link for affiliate.

        Args:
            affiliate_id: Affiliate ID

        Returns:
            Referral link URL

        Raises:
            APIException: If affiliate not found
        """
        try:
            result = await self.db.execute(
                select(Affiliate).where(Affiliate.id == affiliate_id)
            )
            affiliate = result.scalar()

            if not affiliate:
                raise APIException(
                    status_code=404,
                    error_type="AFFILIATE_NOT_FOUND",
                    title="Error",
                    detail="Affiliate not found",
                )

            # Generate link with referral code
            base_url = "https://yourdomain.com"  # TODO: Move to config
            link = f"{base_url}/?ref={affiliate.referral_code}"

            logger.info(
                f"Referral link generated: {affiliate_id}",
                extra={"affiliate_id": affiliate_id},
            )

            return link

        except APIException:
            raise
        except Exception as e:
            logger.error(f"Link generation failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="LINK_ERROR",
                title="Error",
                detail="Failed to generate referral link",
            ) from e

    async def track_signup(
        self, referral_code: str, new_user_id: str
    ) -> "ReferralEvent":
        """Track user signup via referral link.

        Args:
            referral_code: Referral code from link
            new_user_id: User ID signing up

        Returns:
            ReferralEvent: Created signup event

        Raises:
            APIException: If referral code invalid
        """
        try:
            # Find affiliate by referral code
            affiliate_result = await self.db.execute(
                select(Affiliate).where(Affiliate.referral_token == referral_code)
            )
            affiliate = affiliate_result.scalar()

            if not affiliate:
                raise APIException(
                    status_code=400,
                    error_type="invalid_referral",
                    title="Invalid Referral Code",
                    detail=f"Referral code '{referral_code}' not found",
                )

            # Record the referral
            await self.record_referral(referral_code, new_user_id)

            # Create signup event
            event = ReferralEvent(
                referral_code=referral_code,
                event_type="signup",
                user_id=new_user_id,
            )
            self.db.add(event)
            await self.db.commit()
            await self.db.refresh(event)

            logger.info(
                f"Signup tracked: {new_user_id} via {referral_code}",
                extra={
                    "user_id": new_user_id,
                    "referral_code": referral_code,
                },
            )

            return event

        except APIException:
            raise
        except Exception as e:
            logger.error(f"Signup tracking failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="signup_track_error",
                title="Signup Tracking Failed",
                detail=str(e),
            )

    async def track_subscription(
        self, referral_code: str, user_id: str, subscription_price: float
    ) -> "ReferralEvent":
        """Track user subscription.

        Args:
            referral_code: Referral code
            user_id: User ID who subscribed
            subscription_price: Subscription price

        Returns:
            ReferralEvent: Created subscription event

        Raises:
            APIException: If tracking fails
        """
        try:
            # Create subscription event with meta data
            event = ReferralEvent(
                referral_code=referral_code,
                event_type="subscription_created",
                user_id=user_id,
                meta={"subscription_price": subscription_price},
            )
            self.db.add(event)
            await self.db.commit()
            await self.db.refresh(event)

            logger.info(
                f"Subscription tracked: {user_id}",
                extra={
                    "user_id": user_id,
                    "subscription_price": subscription_price,
                },
            )

            return event

        except Exception as e:
            logger.error(f"Subscription tracking failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="SUBSCRIPTION_TRACK_ERROR",
                title="Error",
                detail="Failed to track subscription",
            ) from e

    async def track_first_trade(
        self, referral_code: str, user_id: str
    ) -> "ReferralEvent":
        """Track user's first trade.

        Args:
            referral_code: Referral code
            user_id: User ID who placed trade

        Returns:
            ReferralEvent: Created trade event

        Raises:
            APIException: If tracking fails
        """
        try:
            # Create first trade event
            event = ReferralEvent(
                referral_code=referral_code,
                event_type="first_trade",
                user_id=user_id,
            )
            self.db.add(event)
            await self.db.commit()
            await self.db.refresh(event)

            logger.info(
                f"First trade tracked: {user_id}",
                extra={"user_id": user_id},
            )

            return event

        except Exception as e:
            logger.error(f"First trade tracking failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="TRADE_TRACK_ERROR",
                title="Error",
                detail="Failed to track trade",
            ) from e

    async def calculate_commission(
        self,
        subscription_price: float,
        month: int,
        performance_bonus: bool = False,
    ) -> float:
        """Calculate commission based on month and subscription price.

        Commission tiers:
        - Month 1: 30% of subscription price
        - Months 2+: 15% of subscription price
        - Performance bonus (3+ months): +5%

        Args:
            subscription_price: Monthly subscription price
            month: Month number (1, 2, 3+)
            performance_bonus: Apply 5% bonus if eligible

        Returns:
            Commission amount
        """
        try:
            base_commission = 0.0

            # Tier 1: First month = 30%
            if month == 1:
                base_commission = subscription_price * 0.30
            # Tier 2: Months 2+ = 15%
            else:
                base_commission = subscription_price * 0.15

            # Performance bonus: 5% if 3+ months
            if performance_bonus and month >= 3:
                base_commission += subscription_price * 0.05

            return base_commission

        except Exception as e:
            logger.error(f"Commission calculation failed: {e}", exc_info=True)
            return 0.0

    async def check_self_referral(
        self, referrer_id: str, referred_user_id: str
    ) -> bool:
        """Check if referral is self-referral (fraud).

        Args:
            referrer_id: Affiliate user ID
            referred_user_id: User being referred

        Returns:
            True if self-referral, False otherwise
        """
        return referrer_id == referred_user_id

    async def detect_wash_trade(self, user_id: str, hours_window: int = 24) -> bool:
        """Detect wash trading (buy/sell same day for commission abuse).

        Args:
            user_id: User ID to check
            hours_window: Time window in hours

        Returns:
            True if suspicious pattern detected
        """
        # TODO: Implement with trade history
        # For now, return False (not implemented)
        return False
