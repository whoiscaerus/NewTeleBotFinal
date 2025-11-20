"""
Journey Engine

Evaluates triggers, executes journey steps, and manages user journey state.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.journeys.models import (
    ActionType,
    Journey,
    JourneyStep,
    StepExecution,
    TriggerType,
    UserJourney,
)

try:
    from prometheus_client import Counter

    JOURNEY_STARTED_COUNTER = Counter(
        "journey_started_total", "Total journeys started", ["name"]
    )
    JOURNEY_STEP_FIRED_COUNTER = Counter(
        "journey_step_fired_total", "Total journey steps fired", ["name", "step"]
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = logging.getLogger(__name__)


class JourneyEngine:
    """
    Journey automation engine.

    Handles trigger evaluation, step execution, and progress tracking.
    """

    async def evaluate_trigger(
        self,
        db: AsyncSession,
        trigger_type: TriggerType,
        user_id: str,
        context: dict[str, Any],
    ) -> list[str]:
        """
        Evaluate if any journeys should start for a trigger event.

        Args:
            db: Database session
            trigger_type: Type of trigger event
            user_id: User who triggered the event
            context: Additional context data

        Returns:
            List of started journey IDs
        """
        # Find active journeys for this trigger type
        result = await db.execute(
            select(Journey)
            .where(Journey.trigger_type == trigger_type.value)
            .where(Journey.is_active == True)  # noqa: E712
            .order_by(Journey.priority.desc())
        )
        journeys = result.scalars().all()

        started_journey_ids = []

        for journey in journeys:
            # Check if user already has an active journey for this definition
            existing_result = await db.execute(
                select(UserJourney)
                .where(UserJourney.user_id == user_id)
                .where(UserJourney.journey_id == journey.id)
                .where(UserJourney.status == "active")
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                logger.info(
                    f"User {user_id} already has active journey {journey.name}",
                    extra={"user_id": user_id, "journey_id": journey.id},
                )
                continue

            # Check trigger condition if specified
            if journey.trigger_config:
                if not self._evaluate_condition(journey.trigger_config, context):
                    logger.debug(
                        f"Journey {journey.name} condition not met for user {user_id}",
                        extra={
                            "user_id": user_id,
                            "journey_id": journey.id,
                            "context": context,
                        },
                    )
                    continue

            # Start journey for user
            user_journey = UserJourney(
                id=str(__import__("uuid").uuid4()),
                user_id=user_id,
                journey_id=journey.id,
                status="active",
                started_at=datetime.utcnow(),
                metadata=context,
            )
            db.add(user_journey)

            # Increment metric
            if PROMETHEUS_AVAILABLE:
                JOURNEY_STARTED_COUNTER.labels(name=journey.name).inc()

            logger.info(
                f"Started journey {journey.name} for user {user_id}",
                extra={
                    "user_id": user_id,
                    "journey_id": journey.id,
                    "trigger": trigger_type.value,
                },
            )

            started_journey_ids.append(journey.id)

        await db.commit()
        return started_journey_ids

    async def execute_steps(
        self, db: AsyncSession, user_journey_id: str
    ) -> dict[str, Any]:
        """
        Execute pending steps for a user journey.

        Args:
            db: Database session
            user_journey_id: User journey ID

        Returns:
            Execution result summary
        """
        # Load user journey with relationships
        result = await db.execute(
            select(UserJourney).where(UserJourney.id == user_journey_id)
        )
        user_journey = result.scalar_one_or_none()

        if not user_journey or user_journey.status != "active":
            return {"status": "skipped", "reason": "journey not active"}

        # Load journey and steps
        journey_result = await db.execute(
            select(Journey).where(Journey.id == user_journey.journey_id)
        )
        journey = journey_result.scalar_one()

        steps_result = await db.execute(
            select(JourneyStep)
            .where(JourneyStep.journey_id == journey.id)
            .where(JourneyStep.is_active == True)  # noqa: E712
            .order_by(JourneyStep.order)
        )
        steps = steps_result.scalars().all()

        executed_count = 0
        skipped_count = 0
        failed_count = 0

        for step in steps:
            # Check if step already executed
            existing_exec_result = await db.execute(
                select(StepExecution)
                .where(StepExecution.user_journey_id == user_journey_id)
                .where(StepExecution.step_id == step.id)
                .where(StepExecution.status == "success")
            )
            existing_exec = existing_exec_result.scalar_one_or_none()

            if existing_exec:
                logger.debug(
                    f"Step {step.name} already executed", extra={"step_id": step.id}
                )
                continue

            # Check delay
            if step.delay_minutes > 0:
                scheduled_time = user_journey.started_at + timedelta(
                    minutes=step.delay_minutes
                )
                if datetime.utcnow() < scheduled_time:
                    logger.debug(
                        f"Step {step.name} scheduled for {scheduled_time}",
                        extra={"step_id": step.id, "scheduled_time": scheduled_time},
                    )
                    skipped_count += 1
                    continue

            # Check condition
            if step.condition:
                if not self._evaluate_condition(
                    step.condition, user_journey.journey_metadata
                ):
                    logger.debug(
                        f"Step {step.name} condition not met",
                        extra={"step_id": step.id, "condition": step.condition},
                    )
                    # Mark as skipped
                    execution = StepExecution(
                        id=str(__import__("uuid").uuid4()),
                        user_journey_id=user_journey_id,
                        step_id=step.id,
                        status="skipped",
                        executed_at=datetime.utcnow(),
                        completed_at=datetime.utcnow(),
                    )
                    db.add(execution)
                    skipped_count += 1
                    continue

            # Execute step
            execution_result = await self._execute_step(db, user_journey, step)

            if execution_result["status"] == "success":
                executed_count += 1
                # Increment metric
                if PROMETHEUS_AVAILABLE:
                    JOURNEY_STEP_FIRED_COUNTER.labels(
                        name=journey.name, step=step.name
                    ).inc()
            else:
                failed_count += 1

            # Update user journey current step
            user_journey.current_step_id = step.id
            user_journey.updated_at = datetime.utcnow()

        # Check if journey completed
        if executed_count + skipped_count >= len(steps):
            user_journey.status = "completed"
            user_journey.completed_at = datetime.utcnow()
            logger.info(
                f"Journey {journey.name} completed for user {user_journey.user_id}",
                extra={"user_journey_id": user_journey_id, "journey_id": journey.id},
            )

        await db.commit()

        return {
            "status": "executed",
            "executed": executed_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "total_steps": len(steps),
        }

    async def _execute_step(
        self, db: AsyncSession, user_journey: UserJourney, step: JourneyStep
    ) -> dict[str, Any]:
        """
        Execute a single journey step.

        Args:
            db: Database session
            user_journey: User journey instance
            step: Step to execute

        Returns:
            Execution result
        """
        execution = StepExecution(
            id=str(__import__("uuid").uuid4()),
            user_journey_id=user_journey.id,
            step_id=step.id,
            status="pending",
            executed_at=datetime.utcnow(),
            retry_count=0,
        )
        db.add(execution)

        try:
            action_type = ActionType(step.action_type)
            action_config = step.action_config or {}

            if action_type == ActionType.SEND_EMAIL:
                result = await self._send_email(user_journey.user_id, action_config)
            elif action_type == ActionType.SEND_TELEGRAM:
                result = await self._send_telegram(user_journey.user_id, action_config)
            elif action_type == ActionType.SEND_PUSH:
                result = await self._send_push(user_journey.user_id, action_config)
            elif action_type == ActionType.APPLY_TAG:
                result = await self._apply_tag(db, user_journey.user_id, action_config)
            elif action_type == ActionType.REMOVE_TAG:
                result = await self._remove_tag(db, user_journey.user_id, action_config)
            elif action_type == ActionType.GRANT_REWARD:
                result = await self._grant_reward(
                    db, user_journey.user_id, action_config
                )
            elif action_type == ActionType.SCHEDULE_NEXT:
                result = {"status": "success", "message": "Next step scheduled"}
            elif action_type == ActionType.TRIGGER_WEBHOOK:
                result = await self._trigger_webhook(
                    user_journey.user_id, action_config
                )
            else:
                raise ValueError(f"Unknown action type: {action_type}")

            execution.status = "success"
            execution.completed_at = datetime.utcnow()
            execution.result = result

            logger.info(
                f"Step {step.name} executed successfully",
                extra={
                    "step_id": step.id,
                    "action_type": action_type.value,
                    "result": result,
                },
            )

            return {"status": "success", "result": result}

        except Exception as e:
            execution.status = "failed"
            execution.completed_at = datetime.utcnow()
            execution.error_message = str(e)

            logger.error(
                f"Step {step.name} execution failed: {e}",
                extra={"step_id": step.id, "error": str(e)},
                exc_info=True,
            )

            return {"status": "failed", "error": str(e)}

    def _evaluate_condition(
        self, condition: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """
        Evaluate a conditional expression.

        Args:
            condition: Condition to evaluate (e.g., {"field": "plan", "op": "eq", "value": "gold"})
            context: Context data

        Returns:
            True if condition passes, False otherwise
        """
        if not condition:
            return True

        field = condition.get("field")
        op = condition.get("op")
        expected = condition.get("value")

        if not field or not op:
            return True

        actual = context.get(field)

        if op == "eq":
            return actual == expected
        elif op == "ne":
            return actual != expected
        elif op == "gt":
            return actual > expected if actual is not None else False
        elif op == "gte":
            return actual >= expected if actual is not None else False
        elif op == "lt":
            return actual < expected if actual is not None else False
        elif op == "lte":
            return actual <= expected if actual is not None else False
        elif op == "in":
            return (
                actual in expected
                if actual is not None and expected is not None
                else False
            )
        elif op == "contains":
            return expected in actual if actual is not None else False
        else:
            logger.warning(f"Unknown condition operator: {op}")
            return True

    async def _send_email(self, user_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Send email notification."""
        # Placeholder - integrate with messaging bus (PR-060)
        logger.info(f"Sending email to user {user_id}", extra={"config": config})
        return {"status": "sent", "channel": "email", "user_id": user_id}

    async def _send_telegram(
        self, user_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Send Telegram notification."""
        # Placeholder - integrate with Telegram bot
        logger.info(
            f"Sending Telegram message to user {user_id}", extra={"config": config}
        )
        return {"status": "sent", "channel": "telegram", "user_id": user_id}

    async def _send_push(self, user_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Send push notification."""
        # Placeholder - integrate with push service
        logger.info(
            f"Sending push notification to user {user_id}", extra={"config": config}
        )
        return {"status": "sent", "channel": "push", "user_id": user_id}

    async def _apply_tag(
        self, db: AsyncSession, user_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply tag to user."""
        tag = config.get("tag")
        if not tag:
            raise ValueError("Tag not specified in config")

        logger.info(
            f"Applying tag {tag} to user {user_id}",
            extra={"tag": tag, "user_id": user_id},
        )
        # Placeholder - implement tag system if needed
        return {"status": "applied", "tag": tag, "user_id": user_id}

    async def _remove_tag(
        self, db: AsyncSession, user_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Remove tag from user."""
        tag = config.get("tag")
        if not tag:
            raise ValueError("Tag not specified in config")

        logger.info(
            f"Removing tag {tag} from user {user_id}",
            extra={"tag": tag, "user_id": user_id},
        )
        # Placeholder - implement tag system if needed
        return {"status": "removed", "tag": tag, "user_id": user_id}

    async def _grant_reward(
        self, db: AsyncSession, user_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Grant reward to user."""
        reward_type = config.get("type")
        reward_value = config.get("value")

        if not reward_type or not reward_value:
            raise ValueError("Reward type/value not specified in config")

        logger.info(
            f"Granting reward {reward_type}={reward_value} to user {user_id}",
            extra={
                "reward_type": reward_type,
                "reward_value": reward_value,
                "user_id": user_id,
            },
        )
        # Placeholder - integrate with education/billing rewards (PR-064/PR-033)
        return {
            "status": "granted",
            "type": reward_type,
            "value": reward_value,
            "user_id": user_id,
        }

    async def _trigger_webhook(
        self, user_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Trigger external webhook."""
        url = config.get("url")
        if not url:
            raise ValueError("Webhook URL not specified in config")

        logger.info(
            f"Triggering webhook {url} for user {user_id}",
            extra={"url": url, "user_id": user_id},
        )
        # Placeholder - implement HTTP POST to webhook
        return {"status": "triggered", "url": url, "user_id": user_id}
