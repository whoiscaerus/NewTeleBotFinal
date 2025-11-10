"""
Daily Outlook Scheduler (PR-091).

Cron job to generate and distribute daily AI-written market outlooks.

Respects owner toggle:
- If disabled: Skip generation
- If owner-only: Send to owner email only
- If public: Send to all users via email + Telegram

Schedule: Daily at 6:00 AM UTC
"""

import asyncio
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.analyst import (
    FeatureDisabledError,
    build_outlook,
    is_analyst_enabled,
    is_analyst_owner_only,
)
from backend.app.core.db import get_db_context
from backend.app.observability.metrics import MetricsCollector

logger = logging.getLogger(__name__)

# Initialize metrics collector
try:
    metrics = MetricsCollector()
except Exception as e:
    logger.warning(f"Failed to initialize metrics: {e}")
    metrics = None


async def generate_daily_outlook():
    """
    Generate daily market outlook and distribute via channels.

    Respects feature toggle:
    - Disabled: Skip generation
    - Owner-only: Send to owner email
    - Public: Send to all users

    Increments metrics: ai_outlook_published_total{channel}
    """
    logger.info("Daily outlook generation started")

    try:
        async with get_db_context() as db:
            # Check if feature is enabled
            if not await is_analyst_enabled(db):
                logger.info("AI Analyst disabled, skipping daily outlook generation")
                return

            # Generate outlook
            outlook = await build_outlook(db, target_date=date.today())

            logger.info(
                f"Outlook generated: {len(outlook.narrative)} chars, "
                f"{len(outlook.volatility_zones)} zones, "
                f"{len(outlook.correlations)} correlations"
            )

            # Check owner-only mode
            owner_only = await is_analyst_owner_only(db)

            if owner_only:
                logger.info("Owner-only mode: sending to owner email only")
                await _send_to_owner(db, outlook)

                # Increment metric
                if metrics:
                    metrics.ai_outlook_published_total.labels(
                        channel="email"
                    ).inc()
            else:
                logger.info("Public mode: sending to all users")
                email_count = await _send_to_all_users_email(db, outlook)
                telegram_count = await _send_to_all_users_telegram(db, outlook)

                logger.info(
                    f"Outlook distributed: {email_count} emails, {telegram_count} Telegram messages"
                )

                # Increment metrics
                if metrics:
                    metrics.ai_outlook_published_total.labels(
                        channel="email"
                    ).inc()
                    if telegram_count > 0:
                        metrics.ai_outlook_published_total.labels(
                            channel="telegram"
                        ).inc()

            logger.info("Daily outlook generation completed successfully")

    except FeatureDisabledError:
        logger.info("AI Analyst disabled during generation, skipping")
    except Exception as e:
        logger.error(f"Daily outlook generation failed: {e}", exc_info=True)
        raise


async def _send_to_owner(db: AsyncSession, outlook) -> None:
    """
    Send outlook to owner via email.

    Args:
        db: Database session
        outlook: OutlookReport object
    """
    # This would integrate with PR-060 messaging service
    # For now, log placeholder
    logger.info(
        "Sending outlook to owner email (integration with PR-060 messaging service)"
    )

    # TODO: Integrate with messaging service
    # from backend.app.messaging.service import send_email
    # await send_email(
    #     to=OWNER_EMAIL,
    #     subject=f"Daily Market Outlook - {outlook.generated_at.strftime('%B %d, %Y')}",
    #     template="daily_outlook_email",
    #     context={"outlook": outlook}
    # )


async def _send_to_all_users_email(db: AsyncSession, outlook) -> int:
    """
    Send outlook to all users via email.

    Args:
        db: Database session
        outlook: OutlookReport object

    Returns:
        int: Number of emails sent
    """
    logger.info("Sending outlook to all users via email")

    # TODO: Integrate with messaging service
    # from backend.app.messaging.service import send_bulk_email
    # count = await send_bulk_email(
    #     template="daily_outlook_email",
    #     context={"outlook": outlook}
    # )

    return 0  # Placeholder


async def _send_to_all_users_telegram(db: AsyncSession, outlook) -> int:
    """
    Send outlook to all users via Telegram.

    Args:
        db: Database session
        outlook: OutlookReport object

    Returns:
        int: Number of Telegram messages sent
    """
    logger.info("Sending outlook to all users via Telegram")

    # TODO: Integrate with messaging service
    # from backend.app.messaging.service import send_bulk_telegram
    # count = await send_bulk_telegram(
    #     template="daily_outlook_telegram",
    #     context={"outlook": outlook}
    # )

    return 0  # Placeholder


if __name__ == "__main__":
    # Manual execution for testing
    asyncio.run(generate_daily_outlook())
