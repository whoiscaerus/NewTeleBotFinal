"""Affiliate service - business logic."""

import logging
import secrets
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from backend.app.affiliates.schema import AffiliateStatsOut, CommissionOut, PayoutOut
from backend.app.core.errors import APIError

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
            APIError: If registration fails
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

        except APIError:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Affiliate registration failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="REGISTRATION_ERROR",
                message="Failed to register affiliate",
            ) from e

    async def record_referral(self, token: str, referred_user_id: str) -> None:
        """Record new referral signup.

        Args:
            token: Referral token from link
            referred_user_id: ID of user signing up

        Raises:
            APIError: If token invalid or user already referred
        """
        try:
            # Find affiliate by token
            result = await self.db.execute(
                select(Affiliate).where(Affiliate.referral_token == token)
            )
            affiliate = result.scalar()

            if not affiliate:
                raise APIError(
                    status_code=404,
                    code="INVALID_TOKEN",
                    message="Referral token not found",
                )

            # Check if already referred
            existing = await self.db.execute(
                select(Referral).where(Referral.referred_user_id == referred_user_id)
            )
            if existing.scalar():
                raise APIError(
                    status_code=409,
                    code="ALREADY_REFERRED",
                    message="User already has a referrer",
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

        except APIError:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Referral recording failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="REFERRAL_ERROR",
                message="Failed to record referral",
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
            raise APIError(
                status_code=500,
                code="ACTIVATION_ERROR",
                message="Failed to activate referral",
            ) from e

    async def record_commission(
        self,
        referrer_id: str,
        referred_user_id: str,
        amount: float,
        trade_id: str | None = None,
    ) -> None:
        """Record commission earned on referred user's trade.

        Args:
            referrer_id: User ID of referrer
            referred_user_id: User ID of referred user
            amount: Commission amount
            trade_id: Optional trade ID
        """
        try:
            # Get affiliate tier
            affiliate_result = await self.db.execute(
                select(Affiliate).where(Affiliate.user_id == referrer_id)
            )
            affiliate = affiliate_result.scalar()

            if not affiliate or not affiliate.is_active():
                logger.debug(
                    f"Affiliate not active: {referrer_id}, skipping commission"
                )
                return

            tier = affiliate.commission_tier

            # Create commission record
            commission = Commission(
                referrer_id=referrer_id,
                referred_user_id=referred_user_id,
                trade_id=trade_id,
                amount=amount,
                tier=tier,
                status=CommissionStatus.PENDING.value,
            )

            self.db.add(commission)

            # Update affiliate pending total
            affiliate.pending_commission += amount

            await self.db.commit()

            logger.info(
                f"Commission recorded: {referrer_id} +{amount}",
                extra={
                    "referrer_id": referrer_id,
                    "amount": amount,
                    "trade_id": trade_id,
                },
            )

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Commission recording failed: {e}", exc_info=True)
            # Don't raise - commission failure shouldn't block trade

    async def get_stats(self, user_id: str) -> AffiliateStatsOut:
        """Get affiliate earnings stats.

        Args:
            user_id: User ID

        Returns:
            Affiliate stats

        Raises:
            APIError: If not an affiliate
        """
        try:
            affiliate_result = await self.db.execute(
                select(Affiliate).where(Affiliate.user_id == user_id)
            )
            affiliate = affiliate_result.scalar()

            if not affiliate:
                raise APIError(
                    status_code=404,
                    code="NOT_AFFILIATE",
                    message="User is not an affiliate",
                )

            # Count activated referrals
            referral_result = await self.db.execute(
                select(func.count(Referral.id)).where(
                    and_(
                        Referral.referrer_id == user_id,
                        Referral.status == ReferralStatus.ACTIVATED.value,
                    )
                )
            )
            total_referrals = referral_result.scalar() or 0

            return AffiliateStatsOut(
                total_referrals=total_referrals,
                total_commission=affiliate.total_commission,
                pending_commission=affiliate.pending_commission,
                paid_commission=affiliate.paid_commission,
                commission_tier=affiliate.commission_tier,
            )

        except APIError:
            raise
        except Exception as e:
            logger.error(f"Stats retrieval failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="STATS_ERROR",
                message="Failed to retrieve stats",
            ) from e

    async def request_payout(self, user_id: str, amount: float) -> PayoutOut:
        """Request commission payout.

        Args:
            user_id: User ID
            amount: Payout amount

        Returns:
            Payout record

        Raises:
            APIError: If insufficient pending commission
        """
        try:
            # Get affiliate
            affiliate_result = await self.db.execute(
                select(Affiliate).where(Affiliate.user_id == user_id)
            )
            affiliate = affiliate_result.scalar()

            if not affiliate:
                raise APIError(
                    status_code=404,
                    code="NOT_AFFILIATE",
                    message="User is not an affiliate",
                )

            if amount > affiliate.pending_commission:
                raise APIError(
                    status_code=400,
                    code="INSUFFICIENT_BALANCE",
                    message=f"Insufficient pending commission (available: {affiliate.pending_commission})",
                )

            # Create payout record
            payout = Payout(
                referrer_id=user_id,
                amount=amount,
                status=PayoutStatus.PENDING.value,
            )

            self.db.add(payout)

            # Update affiliate (move from pending to paid when processed)
            affiliate.pending_commission -= amount

            await self.db.commit()
            await self.db.refresh(payout)

            logger.info(
                f"Payout requested: {user_id} {amount}",
                extra={"user_id": user_id, "amount": amount},
            )

            return PayoutOut.model_validate(payout)

        except APIError:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Payout request failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="PAYOUT_ERROR",
                message="Failed to request payout",
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
            raise APIError(
                status_code=500,
                code="HISTORY_ERROR",
                message="Failed to retrieve commission history",
            ) from e
