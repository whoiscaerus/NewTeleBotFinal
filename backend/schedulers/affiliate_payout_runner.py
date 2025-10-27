"""
Affiliate payout scheduler.

Runs daily batch job to:
1. Aggregate affiliate earnings
2. Create Stripe payouts for earnings > MIN_PAYOUT_GBP
3. Poll payout status
4. Update payout records in DB

Scheduled via APScheduler/Celery Beat.
"""

import logging
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.affiliates.models import AffiliateEarnings, AffiliatePayout
from backend.app.core.db import get_async_session
from backend.app.core.settings import get_settings
from backend.app.users.models import User

logger = logging.getLogger(__name__)


class AffiliatePayoutService:
    """Service for processing affiliate payouts."""

    def __init__(self, db: AsyncSession, stripe_client):
        """
        Initialize payout service.

        Args:
            db: Database session
            stripe_client: Stripe API client instance
        """
        self.db = db
        self.stripe = stripe_client
        self.settings = get_settings()

    async def run_daily_payout_batch(self) -> dict:
        """
        Run daily payout batch job (typically at 00:00 UTC).

        Returns:
            Summary dict with statistics

        Example:
            >>> service = AffiliatePayoutService(db, stripe_client)
            >>> result = await service.run_daily_payout_batch()
            >>> print(f"Processed {result['count_processed']} affiliates")
        """
        logger.info("Starting daily affiliate payout batch")

        stats = {
            "timestamp": datetime.utcnow(),
            "count_processed": 0,
            "count_paid": 0,
            "total_amount_gbp": 0.0,
            "errors": [],
        }

        try:
            # Get all affiliates with pending earnings
            affiliates_with_earnings = (
                await self._get_affiliates_with_pending_earnings()
            )

            for affiliate_id, pending_amount in affiliates_with_earnings:
                try:
                    result = await self.trigger_payout(affiliate_id, pending_amount)

                    if result:
                        stats["count_paid"] += 1
                        stats["total_amount_gbp"] += pending_amount
                    stats["count_processed"] += 1

                except Exception as e:
                    logger.error(
                        f"Error processing payout for affiliate {affiliate_id}",
                        exc_info=True,
                    )
                    stats["errors"].append(
                        {
                            "affiliate_id": affiliate_id,
                            "error": str(e),
                        }
                    )

            logger.info(
                "Daily payout batch complete",
                extra={
                    "processed": stats["count_processed"],
                    "paid": stats["count_paid"],
                    "total_gbp": stats["total_amount_gbp"],
                },
            )

            return stats

        except Exception as e:
            logger.error("Daily payout batch failed", exc_info=True)
            stats["errors"].append({"batch": "batch_error", "error": str(e)})
            return stats

    async def trigger_payout(
        self,
        affiliate_id: str,
        amount_gbp: float,
    ) -> bool:
        """
        Trigger Stripe payout for affiliate.

        Args:
            affiliate_id: Affiliate user ID
            amount_gbp: Amount to pay in GBP

        Returns:
            True if payout created successfully, False otherwise

        Example:
            >>> success = await service.trigger_payout("affiliate_123", 150.50)
            >>> if success:
            ...     logger.info("Payout created")
        """
        # Get affiliate user and payment method
        stmt = select(User).where(User.id == affiliate_id)
        result = await self.db.execute(stmt)
        affiliate_user = result.scalar_one_or_none()

        if not affiliate_user:
            logger.error(f"Affiliate user not found: {affiliate_id}")
            return False

        # Check: minimum payout threshold
        min_payout = float(self.settings.get("AFFILIATE_MIN_PAYOUT_GBP", 50.0))
        if amount_gbp < min_payout:
            logger.info(
                "Payout below minimum threshold",
                extra={
                    "affiliate_id": affiliate_id,
                    "amount_gbp": amount_gbp,
                    "min_threshold": min_payout,
                },
            )
            return False

        try:
            # Create Stripe payout
            # Requires: affiliate has Stripe Connect account/bank details
            payout_response = self.stripe.Payout.create(
                amount=int(amount_gbp * 100),  # Convert to pence
                currency="gbp",
                destination=affiliate_user.stripe_connected_account_id,
                statement_descriptor="Trading platform affiliate commission",
                metadata={
                    "affiliate_id": affiliate_id,
                    "batch_date": datetime.utcnow().isoformat(),
                },
            )

            payout_id = payout_response.id
            payout_status = (
                payout_response.status
            )  # pending, in_transit, paid, failed, cancelled

            # Record payout in DB
            payout_record = AffiliatePayout(
                affiliate_id=affiliate_id,
                amount_gbp=amount_gbp,
                stripe_payout_id=payout_id,
                status=payout_status,
                requested_at=datetime.utcnow(),
                stripe_response=payout_response,
            )

            self.db.add(payout_record)

            # Clear pending earnings for this affiliate
            stmt_clear = select(AffiliateEarnings).where(
                and_(
                    AffiliateEarnings.affiliate_id == affiliate_id,
                    AffiliateEarnings.status == "pending",
                )
            )
            result_earnings = await self.db.execute(stmt_clear)
            pending_earnings = result_earnings.scalars().all()

            for earning in pending_earnings:
                earning.status = "paid"
                earning.payout_id = payout_record.id
                earning.paid_at = datetime.utcnow()

            await self.db.commit()

            logger.info(
                "Payout triggered successfully",
                extra={
                    "affiliate_id": affiliate_id,
                    "amount_gbp": amount_gbp,
                    "stripe_payout_id": payout_id,
                    "status": payout_status,
                },
            )

            return True

        except Exception:
            logger.error(
                "Failed to create Stripe payout",
                exc_info=True,
                extra={
                    "affiliate_id": affiliate_id,
                    "amount_gbp": amount_gbp,
                },
            )
            return False

    async def poll_payout_status(self) -> dict:
        """
        Poll Stripe for status of pending payouts.

        Returns:
            Summary of payout status updates

        Example:
            >>> result = await service.poll_payout_status()
            >>> print(f"Updated {result['count_updated']} payouts")
        """
        logger.info("Polling affiliate payout statuses")

        stats = {
            "count_polled": 0,
            "count_updated": 0,
            "count_completed": 0,
        }

        # Get all payouts not yet completed
        stmt = select(AffiliatePayout).where(
            AffiliatePayout.status.in_(["pending", "in_transit"])
        )
        result = await self.db.execute(stmt)
        payouts = result.scalars().all()

        for payout in payouts:
            try:
                # Fetch latest status from Stripe
                stripe_payout = self.stripe.Payout.retrieve(payout.stripe_payout_id)
                new_status = stripe_payout.status

                if new_status != payout.status:
                    logger.info(
                        "Payout status updated",
                        extra={
                            "payout_id": payout.id,
                            "old_status": payout.status,
                            "new_status": new_status,
                        },
                    )

                    payout.status = new_status

                    if new_status == "paid":
                        payout.paid_at = datetime.utcnow()
                        stats["count_completed"] += 1

                    stats["count_updated"] += 1

                stats["count_polled"] += 1

            except Exception:
                logger.error(
                    "Error polling payout status",
                    exc_info=True,
                    extra={"payout_id": payout.id},
                )

        await self.db.commit()

        logger.info(
            "Payout status polling complete",
            extra={
                "polled": stats["count_polled"],
                "updated": stats["count_updated"],
                "completed": stats["count_completed"],
            },
        )

        return stats

    async def _get_affiliates_with_pending_earnings(self) -> list[tuple[str, float]]:
        """
        Get list of (affiliate_id, pending_amount) tuples.

        Returns:
            List of tuples with affiliate IDs and their pending earnings
        """
        stmt = (
            select(
                AffiliateEarnings.affiliate_id,
                func.sum(AffiliateEarnings.amount_gbp).label("total_pending"),
            )
            .where(AffiliateEarnings.status == "pending")
            .group_by(AffiliateEarnings.affiliate_id)
        )

        result = await self.db.execute(stmt)
        earnings = result.all()

        return [(aff_id, float(amount)) for aff_id, amount in earnings]


# Scheduled task function (called by APScheduler/Celery)
async def run_affiliate_payouts_task():
    """
    Scheduled task: run daily payout batch.

    Called via APScheduler or Celery Beat at 00:00 UTC daily.

    Example (in scheduler setup):
        scheduler.add_job(
            run_affiliate_payouts_task,
            'cron',
            hour=0,
            minute=0,
            id='affiliate_payouts_daily'
        )
    """
    async for db in get_async_session():
        try:
            # Initialize Stripe (from settings/secrets)
            import stripe

            stripe.api_key = get_settings().stripe_secret_key

            service = AffiliatePayoutService(db, stripe)

            # Run batch
            result = await service.run_daily_payout_batch()

            # Poll status
            poll_result = await service.poll_payout_status()

            logger.info(
                "Affiliate payout task completed",
                extra={
                    "batch_result": result,
                    "poll_result": poll_result,
                },
            )

        except Exception:
            logger.error(
                "Affiliate payout task failed",
                exc_info=True,
            )
