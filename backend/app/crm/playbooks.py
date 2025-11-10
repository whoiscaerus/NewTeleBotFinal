"""
PR-098: CRM Playbooks - Predefined Journey Definitions

Playbooks are JSON-serializable journey definitions triggered by lifecycle events.

Architecture:
    Event → triggers.py → playbooks.py → execute_playbook() → steps → messaging

Playbook Structure:
    {
        "name": "payment_failed_rescue",
        "trigger": "payment_failed",
        "steps": [
            {"type": "send_message", "channel": "email", "template": "rescue_step1", "delay_hours": 0},
            {"type": "send_message", "channel": "telegram", "template": "rescue_step2", "delay_hours": 24, "discount_percent": 20},
            {"type": "owner_dm", "message": "User {{user_id}} payment failed 48h ago", "delay_hours": 48}
        ]
    }
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.crm.models import (
    CRMDiscountCode,
    CRMPlaybookExecution,
    CRMStepExecution,
)
from backend.app.messaging.bus import MessagingBus
from backend.app.prefs.service import get_user_preferences, is_quiet_hours_active

logger = logging.getLogger(__name__)

# Playbook type definitions
PlaybookName = Literal[
    "payment_failed_rescue",
    "trial_ending",
    "inactivity_nudge",
    "winback",
    "milestone_congrats",
    "churn_risk",
]

StepType = Literal["send_message", "discount_code", "owner_dm", "wait"]
ChannelType = Literal["email", "telegram", "push"]


# ===== PLAYBOOK DEFINITIONS =====

PLAYBOOKS: dict[PlaybookName, dict[str, Any]] = {
    "payment_failed_rescue": {
        "name": "payment_failed_rescue",
        "trigger": "payment_failed",
        "description": "3-step rescue sequence when payment fails",
        "steps": [
            {
                "type": "send_message",
                "channel": "email",
                "template": "payment_failed_rescue_step1",
                "delay_hours": 0,  # Immediate
                "subject": "Payment Update Required",
            },
            {
                "type": "send_message",
                "channel": "telegram",
                "template": "payment_failed_rescue_step2",
                "delay_hours": 24,
                "discount_percent": 20,  # Issue 20% discount code
            },
            {
                "type": "owner_dm",
                "message": "🚨 User {{user_id}} ({{email}}) payment failed 48h ago. Subscription: £{{amount}}/month. Consider personal outreach.",
                "delay_hours": 48,
            },
        ],
    },
    "trial_ending": {
        "name": "trial_ending",
        "trigger": "trial_expiring_soon",
        "description": "Nudge users before trial expires",
        "steps": [
            {
                "type": "send_message",
                "channel": "email",
                "template": "trial_ending_reminder",
                "delay_hours": 0,  # 3 days before expiry
                "subject": "Your Trial Ends Soon - Don't Lose Access",
            },
            {
                "type": "send_message",
                "channel": "telegram",
                "template": "trial_ending_telegram",
                "delay_hours": 48,  # 1 day before expiry
                "discount_percent": 15,  # First-time subscriber discount
            },
        ],
    },
    "inactivity_nudge": {
        "name": "inactivity_nudge",
        "trigger": "inactivity_14d",
        "description": "Re-engage inactive users (no approvals for 14 days)",
        "steps": [
            {
                "type": "send_message",
                "channel": "telegram",
                "template": "inactivity_nudge",
                "delay_hours": 0,
                "subject": "We Miss You! Check Out New Signals",
            },
            {
                "type": "send_message",
                "channel": "email",
                "template": "inactivity_reactivation",
                "delay_hours": 72,  # 3 days later if still inactive
                "discount_percent": 10,  # Small incentive
            },
        ],
    },
    "winback": {
        "name": "winback",
        "trigger": "subscription_cancelled",
        "description": "Win back churned users",
        "steps": [
            {
                "type": "send_message",
                "channel": "email",
                "template": "winback_feedback",
                "delay_hours": 24,
                "subject": "We're Sorry to See You Go - Quick Feedback?",
            },
            {
                "type": "send_message",
                "channel": "telegram",
                "template": "winback_offer",
                "delay_hours": 168,  # 1 week later
                "discount_percent": 30,  # Aggressive winback offer
                "subject": "Come Back - 30% Off for 3 Months",
            },
        ],
    },
    "milestone_congrats": {
        "name": "milestone_congrats",
        "trigger": "new_high_watermark",
        "description": "Celebrate user milestones (new profit high)",
        "steps": [
            {
                "type": "send_message",
                "channel": "telegram",
                "template": "milestone_congrats",
                "delay_hours": 0,
                "subject": "🎉 New Profit Milestone Achieved!",
            },
            {
                "type": "send_message",
                "channel": "email",
                "template": "milestone_share",
                "delay_hours": 24,
                "subject": "Share Your Success - Refer a Friend",
            },
        ],
    },
    "churn_risk": {
        "name": "churn_risk",
        "trigger": "churn_risk_detected",
        "description": "Proactive outreach when churn risk detected (declining usage + negative PnL)",
        "steps": [
            {
                "type": "send_message",
                "channel": "email",
                "template": "churn_risk_support",
                "delay_hours": 0,
                "subject": "Need Help? Let's Optimize Your Strategy",
            },
            {
                "type": "owner_dm",
                "message": "⚠️ Churn risk: User {{user_id}} ({{email}}) - Declining usage + negative PnL. Consider proactive call.",
                "delay_hours": 48,
            },
        ],
    },
}


# ===== PLAYBOOK EXECUTION ENGINE =====


async def start_playbook(
    db: AsyncSession,
    user_id: str,
    playbook_name: PlaybookName,
    context: dict[str, Any],
) -> CRMPlaybookExecution:
    """
    Start a CRM playbook for a user.

    Args:
        db: Database session
        user_id: User to execute playbook for
        playbook_name: Name of playbook to execute
        context: Event context data (e.g., {"amount": 20, "subscription_id": "sub_123"})

    Returns:
        CRMPlaybookExecution: Created execution record

    Business Logic:
        - Checks for existing active execution (prevents duplicates)
        - Creates execution record with status=active
        - Schedules first step based on delay_hours
        - Returns execution ID for tracking
    """
    if playbook_name not in PLAYBOOKS:
        raise ValueError(f"Unknown playbook: {playbook_name}")

    playbook = PLAYBOOKS[playbook_name]

    # Check for existing active execution
    existing_result = await db.execute(
        select(CRMPlaybookExecution)
        .where(CRMPlaybookExecution.user_id == user_id)
        .where(CRMPlaybookExecution.playbook_name == playbook_name)
        .where(CRMPlaybookExecution.status == "active")
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        logger.warning(
            f"User {user_id} already has active playbook {playbook_name}",
            extra={"user_id": user_id, "execution_id": existing.id},
        )
        return existing

    # Create execution
    execution = CRMPlaybookExecution(
        id=str(uuid4()),
        user_id=user_id,
        playbook_name=playbook_name,
        trigger_event=playbook["trigger"],
        context=context,
        status="active",
        current_step=0,
        total_steps=len(playbook["steps"]),
        next_action_at=datetime.utcnow(),  # First step runs immediately (or after delay)
    )

    # Calculate next_action_at based on first step delay
    first_step = playbook["steps"][0]
    if first_step.get("delay_hours", 0) > 0:
        execution.next_action_at = datetime.utcnow() + timedelta(
            hours=first_step["delay_hours"]
        )

    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    logger.info(
        f"Started playbook {playbook_name} for user {user_id}",
        extra={"user_id": user_id, "execution_id": execution.id, "context": context},
    )

    return execution


async def execute_pending_steps(db: AsyncSession, messaging_bus: MessagingBus) -> int:
    """
    Execute all pending playbook steps that are due.

    This function should be called periodically (e.g., every 5 minutes) to process pending steps.

    Args:
        db: Database session
        messaging_bus: Messaging bus for sending messages

    Returns:
        Number of steps executed

    Business Logic:
        - Query executions where next_action_at <= now
        - Execute current step
        - Advance to next step or mark completed
        - Respect quiet hours (skip send_message if in quiet hours)
    """
    now = datetime.utcnow()

    # Find executions with pending actions
    result = await db.execute(
        select(CRMPlaybookExecution)
        .where(CRMPlaybookExecution.status == "active")
        .where(CRMPlaybookExecution.next_action_at <= now)
        .order_by(CRMPlaybookExecution.next_action_at)
    )
    pending_executions = result.scalars().all()

    steps_executed = 0

    for execution in pending_executions:
        try:
            await _execute_step(db, messaging_bus, execution)
            steps_executed += 1
        except Exception as e:
            logger.error(
                f"Error executing step for execution {execution.id}: {e}",
                exc_info=True,
                extra={"execution_id": execution.id, "user_id": execution.user_id},
            )
            # Mark step as failed but don't stop execution
            step_record = CRMStepExecution(
                id=str(uuid4()),
                execution_id=execution.id,
                step_number=execution.current_step,
                step_type="unknown",
                config={},
                status="failed",
                executed_at=datetime.utcnow(),
                error_message=str(e),
            )
            db.add(step_record)

            # Move to next step anyway (don't block entire playbook)
            await _advance_to_next_step(db, execution)

    if steps_executed > 0:
        await db.commit()
        logger.info(f"Executed {steps_executed} CRM playbook steps")

    return steps_executed


async def _execute_step(
    db: AsyncSession,
    messaging_bus: MessagingBus,
    execution: CRMPlaybookExecution,
) -> None:
    """Execute a single playbook step."""
    playbook = PLAYBOOKS.get(execution.playbook_name)  # type: ignore
    if not playbook:
        raise ValueError(f"Playbook {execution.playbook_name} not found")

    if execution.current_step >= len(playbook["steps"]):
        # All steps completed
        execution.status = "completed"
        execution.completed_at = datetime.utcnow()
        execution.next_action_at = None
        logger.info(
            f"Completed playbook {execution.playbook_name} for user {execution.user_id}",
            extra={"execution_id": execution.id},
        )
        return

    step = playbook["steps"][execution.current_step]
    step_type = step["type"]

    # Create step execution record
    step_record = CRMStepExecution(
        id=str(uuid4()),
        execution_id=execution.id,
        step_number=execution.current_step,
        step_type=step_type,
        config=step,
        status="pending",
    )
    db.add(step_record)

    try:
        if step_type == "send_message":
            await _execute_send_message(db, messaging_bus, execution, step, step_record)
        elif step_type == "discount_code":
            await _execute_discount_code(db, execution, step, step_record)
        elif step_type == "owner_dm":
            await _execute_owner_dm(db, messaging_bus, execution, step, step_record)
        elif step_type == "wait":
            # Just mark as completed (delay handled by next_action_at)
            step_record.status = "completed"
            step_record.executed_at = datetime.utcnow()
        else:
            raise ValueError(f"Unknown step type: {step_type}")

        # Advance to next step
        await _advance_to_next_step(db, execution)

    except Exception as e:
        step_record.status = "failed"
        step_record.error_message = str(e)
        step_record.executed_at = datetime.utcnow()
        raise


async def _execute_send_message(
    db: AsyncSession,
    messaging_bus: MessagingBus,
    execution: CRMPlaybookExecution,
    step: dict[str, Any],
    step_record: CRMStepExecution,
) -> None:
    """Execute send_message step."""
    # Check quiet hours
    prefs = await get_user_preferences(db, execution.user_id)
    if is_quiet_hours_active(prefs):
        logger.info(
            f"Skipping message send for user {execution.user_id} - quiet hours",
            extra={"execution_id": execution.id},
        )
        step_record.status = "skipped"
        step_record.executed_at = datetime.utcnow()
        step_record.error_message = "quiet_hours"
        return

    channel = step["channel"]
    template = step["template"]

    # Issue discount code if specified
    discount_code = None
    if step.get("discount_percent"):
        discount_code = await _create_discount_code(
            db, execution.user_id, execution.id, step["discount_percent"]
        )

    # Build template vars
    template_vars = {
        **execution.context,
        "user_id": execution.user_id,
        "discount_code": discount_code.code if discount_code else None,
        "discount_percent": step.get("discount_percent"),
    }

    # Send message
    message_id = await messaging_bus.enqueue_message(
        user_id=execution.user_id,
        channel=channel,  # type: ignore
        template_name=template,
        template_vars=template_vars,
        priority="campaign",
    )

    step_record.message_id = message_id
    step_record.status = "completed"
    step_record.executed_at = datetime.utcnow()

    logger.info(
        f"Sent {channel} message to user {execution.user_id}",
        extra={
            "execution_id": execution.id,
            "template": template,
            "message_id": message_id,
        },
    )


async def _execute_discount_code(
    db: AsyncSession,
    execution: CRMPlaybookExecution,
    step: dict[str, Any],
    step_record: CRMStepExecution,
) -> None:
    """Execute discount_code step (create code without sending message)."""
    percent_off = step.get("discount_percent", 10)
    discount_code = await _create_discount_code(
        db, execution.user_id, execution.id, percent_off
    )

    step_record.status = "completed"
    step_record.executed_at = datetime.utcnow()
    step_record.config["discount_code"] = discount_code.code

    logger.info(
        f"Created discount code {discount_code.code} for user {execution.user_id}",
        extra={"execution_id": execution.id},
    )


async def _execute_owner_dm(
    db: AsyncSession,
    messaging_bus: MessagingBus,
    execution: CRMPlaybookExecution,
    step: dict[str, Any],
    step_record: CRMStepExecution,
) -> None:
    """Execute owner_dm step (send notification to owner)."""
    # Replace template vars in message
    message = step["message"]
    for key, value in execution.context.items():
        message = message.replace(f"{{{{{key}}}}}", str(value))
    message = message.replace("{{user_id}}", execution.user_id)

    # Send to owner (hardcoded Telegram channel or env var)
    # TODO: Get owner Telegram ID from settings
    message_id = await messaging_bus.enqueue_message(
        user_id="owner",  # Special user_id for owner notifications
        channel="telegram",
        template_name="owner_notification",
        template_vars={"message": message},
        priority="transactional",
    )

    step_record.message_id = message_id
    step_record.status = "completed"
    step_record.executed_at = datetime.utcnow()

    logger.info(
        f"Sent owner DM for execution {execution.id}",
        extra={"execution_id": execution.id, "message_id": message_id},
    )


async def _create_discount_code(
    db: AsyncSession,
    user_id: str,
    execution_id: str,
    percent_off: int,
) -> CRMDiscountCode:
    """Create a discount code for CRM playbook."""
    code = f"CRM{percent_off}-{str(uuid4())[:8].upper()}"
    expires_at = datetime.utcnow() + timedelta(days=7)  # Valid for 7 days

    discount = CRMDiscountCode(
        id=str(uuid4()),
        code=code,
        user_id=user_id,
        execution_id=execution_id,
        percent_off=percent_off,
        max_uses=1,
        used_count=0,
        expires_at=expires_at,
    )

    db.add(discount)
    await db.flush()  # Get ID without committing
    return discount


async def _advance_to_next_step(
    db: AsyncSession, execution: CRMPlaybookExecution
) -> None:
    """Advance execution to next step or mark completed."""
    playbook = PLAYBOOKS.get(execution.playbook_name)  # type: ignore
    if not playbook:
        return

    execution.current_step += 1

    if execution.current_step >= len(playbook["steps"]):
        # All steps completed
        execution.status = "completed"
        execution.completed_at = datetime.utcnow()
        execution.next_action_at = None
    else:
        # Schedule next step
        next_step = playbook["steps"][execution.current_step]
        delay_hours = next_step.get("delay_hours", 0)
        execution.next_action_at = datetime.utcnow() + timedelta(hours=delay_hours)

    execution.updated_at = datetime.utcnow()


async def mark_converted(
    db: AsyncSession, execution_id: str, conversion_value: int
) -> None:
    """
    Mark a playbook execution as converted (user took desired action).

    Args:
        db: Database session
        execution_id: Execution ID
        conversion_value: Value of conversion (e.g., £20 if subscription renewed)

    Business Logic:
        - Sets status=abandoned (user took action, no need to continue)
        - Records conversion time and value
        - Used for measuring playbook effectiveness
    """
    result = await db.execute(
        select(CRMPlaybookExecution).where(CRMPlaybookExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        logger.warning(f"Execution {execution_id} not found")
        return

    execution.status = "abandoned"  # User converted, stop playbook
    execution.converted_at = datetime.utcnow()
    execution.conversion_value = conversion_value
    execution.updated_at = datetime.utcnow()

    await db.commit()

    logger.info(
        f"Marked execution {execution_id} as converted: £{conversion_value}",
        extra={"execution_id": execution_id, "value": conversion_value},
    )
