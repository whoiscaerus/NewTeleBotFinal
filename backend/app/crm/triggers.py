"""
PR-098: CRM Triggers - Event Listeners

Listens for lifecycle events and starts appropriate CRM playbooks.

Architecture:
    Event source (billing, analytics, user activity) → trigger_*() → start_playbook()

Integration points:
    - PR-033/034 (Billing): payment_failed webhook → trigger_payment_failed()
    - PR-056 (Revenue): trial_expiring check → trigger_trial_ending()
    - PR-052/053 (Analytics): high watermark detection → trigger_milestone()
    - User activity monitoring → trigger_inactivity()
"""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.crm.playbooks import start_playbook
from backend.app.observability.metrics import crm_playbook_fired_total

logger = logging.getLogger(__name__)


async def trigger_payment_failed(
    db: AsyncSession,
    user_id: str,
    subscription_id: str,
    amount: float,
    currency: str = "GBP",
) -> None:
    """
    Trigger payment failed rescue playbook.

    Called by: PR-033/034 billing webhook handler when payment fails

    Args:
        db: Database session
        user_id: User whose payment failed
        subscription_id: Subscription ID
        amount: Subscription amount
        currency: Currency code

    Business Logic:
        - Starts 3-step rescue sequence:
          1. Immediate email with payment update link
          2. 24h: Telegram DM with 20% discount
          3. 48h: Owner personal outreach
    """
    context = {
        "subscription_id": subscription_id,
        "amount": amount,
        "currency": currency,
        "failed_at": datetime.utcnow().isoformat(),
    }

    try:
        execution = await start_playbook(db, user_id, "payment_failed_rescue", context)

        crm_playbook_fired_total.labels(name="payment_failed_rescue").inc()

        logger.info(
            f"Triggered payment_failed_rescue for user {user_id}",
            extra={
                "user_id": user_id,
                "execution_id": execution.id,
                "context": context,
            },
        )

    except Exception as e:
        logger.error(
            f"Failed to trigger payment_failed_rescue for user {user_id}: {e}",
            exc_info=True,
        )


async def trigger_trial_ending(
    db: AsyncSession,
    user_id: str,
    trial_end_date: datetime,
) -> None:
    """
    Trigger trial ending nudge playbook.

    Called by: Scheduled job that checks trials expiring in 3 days

    Args:
        db: Database session
        user_id: User whose trial is ending
        trial_end_date: When trial expires

    Business Logic:
        - Sends reminder 3 days before expiry
        - Sends final reminder 1 day before with 15% discount
    """
    context = {
        "trial_end_date": trial_end_date.isoformat(),
        "days_remaining": (trial_end_date - datetime.utcnow()).days,
    }

    try:
        execution = await start_playbook(db, user_id, "trial_ending", context)

        crm_playbook_fired_total.labels(name="trial_ending").inc()

        logger.info(
            f"Triggered trial_ending for user {user_id}",
            extra={"user_id": user_id, "execution_id": execution.id},
        )

    except Exception as e:
        logger.error(
            f"Failed to trigger trial_ending for user {user_id}: {e}", exc_info=True
        )


async def trigger_inactivity(
    db: AsyncSession,
    user_id: str,
    last_activity_date: datetime,
) -> None:
    """
    Trigger inactivity nudge playbook.

    Called by: Scheduled job that detects users with no approvals for 14+ days

    Args:
        db: Database session
        user_id: Inactive user
        last_activity_date: Last time user approved a signal

    Business Logic:
        - Sends re-engagement message via Telegram
        - 3 days later: Email with 10% incentive if still inactive
    """
    days_inactive = (datetime.utcnow() - last_activity_date).days

    context = {
        "last_activity_date": last_activity_date.isoformat(),
        "days_inactive": days_inactive,
    }

    try:
        execution = await start_playbook(db, user_id, "inactivity_nudge", context)

        crm_playbook_fired_total.labels(name="inactivity_nudge").inc()

        logger.info(
            f"Triggered inactivity_nudge for user {user_id} ({days_inactive} days)",
            extra={"user_id": user_id, "execution_id": execution.id},
        )

    except Exception as e:
        logger.error(
            f"Failed to trigger inactivity_nudge for user {user_id}: {e}", exc_info=True
        )


async def trigger_churn_risk(
    db: AsyncSession,
    user_id: str,
    risk_score: float,
    risk_factors: list[str],
) -> None:
    """
    Trigger churn risk playbook.

    Called by: Analytics service when churn risk detected (declining usage + negative PnL)

    Args:
        db: Database session
        user_id: User at risk
        risk_score: Churn probability (0.0-1.0)
        risk_factors: List of risk indicators (e.g., ["declining_usage", "negative_pnl"])

    Business Logic:
        - Sends proactive support email
        - 48h: Owner DM to consider personal call
    """
    context = {
        "risk_score": risk_score,
        "risk_factors": risk_factors,
        "detected_at": datetime.utcnow().isoformat(),
    }

    try:
        execution = await start_playbook(db, user_id, "churn_risk", context)

        crm_playbook_fired_total.labels(name="churn_risk").inc()

        logger.info(
            f"Triggered churn_risk for user {user_id} (score: {risk_score:.2f})",
            extra={
                "user_id": user_id,
                "execution_id": execution.id,
                "risk_factors": risk_factors,
            },
        )

    except Exception as e:
        logger.error(
            f"Failed to trigger churn_risk for user {user_id}: {e}", exc_info=True
        )


async def trigger_milestone(
    db: AsyncSession,
    user_id: str,
    milestone_type: str,
    value: float,
) -> None:
    """
    Trigger milestone congratulations playbook.

    Called by: Analytics service when new high watermark detected

    Args:
        db: Database session
        user_id: User who achieved milestone
        milestone_type: Type of milestone (e.g., "new_profit_high")
        value: Milestone value (e.g., £1000 profit)

    Business Logic:
        - Immediate Telegram congrats
        - 24h: Email encouraging sharing/referral
    """
    context = {
        "milestone_type": milestone_type,
        "value": value,
        "achieved_at": datetime.utcnow().isoformat(),
    }

    try:
        execution = await start_playbook(db, user_id, "milestone_congrats", context)

        crm_playbook_fired_total.labels(name="milestone_congrats").inc()

        logger.info(
            f"Triggered milestone_congrats for user {user_id} ({milestone_type}: £{value})",
            extra={"user_id": user_id, "execution_id": execution.id},
        )

    except Exception as e:
        logger.error(
            f"Failed to trigger milestone_congrats for user {user_id}: {e}",
            exc_info=True,
        )


async def trigger_winback(
    db: AsyncSession,
    user_id: str,
    cancelled_at: datetime,
    subscription_tier: str,
) -> None:
    """
    Trigger winback playbook.

    Called by: Billing service when subscription is cancelled

    Args:
        db: Database session
        user_id: User who cancelled
        cancelled_at: When subscription was cancelled
        subscription_tier: What tier they had (for targeted messaging)

    Business Logic:
        - 24h: Feedback request email
        - 1 week: 30% discount offer to return
    """
    context = {
        "cancelled_at": cancelled_at.isoformat(),
        "subscription_tier": subscription_tier,
        "days_since_cancel": (datetime.utcnow() - cancelled_at).days,
    }

    try:
        execution = await start_playbook(db, user_id, "winback", context)

        crm_playbook_fired_total.labels(name="winback").inc()

        logger.info(
            f"Triggered winback for user {user_id}",
            extra={"user_id": user_id, "execution_id": execution.id},
        )

    except Exception as e:
        logger.error(
            f"Failed to trigger winback for user {user_id}: {e}", exc_info=True
        )
