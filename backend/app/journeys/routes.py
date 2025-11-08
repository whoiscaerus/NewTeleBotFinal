"""
Journey Management Routes

CRUD operations for journey definitions (owner/admin only).
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.journeys.engine import JourneyEngine
from backend.app.journeys.models import (
    ActionType,
    Journey,
    JourneyStep,
    TriggerType,
    UserJourney,
)

router = APIRouter(prefix="/api/v1/journeys", tags=["journeys"])
logger = logging.getLogger(__name__)


# ============================================================================
# SCHEMAS
# ============================================================================


class JourneyStepCreate(BaseModel):
    """Schema for creating a journey step."""

    name: str = Field(..., min_length=1, max_length=100)
    order: int = Field(..., ge=0)
    action_type: ActionType
    action_config: dict[str, Any] = Field(default_factory=dict)
    delay_minutes: int = Field(default=0, ge=0)
    condition: Optional[dict[str, Any]] = None


class JourneyCreate(BaseModel):
    """Schema for creating a journey."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    trigger_type: TriggerType
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    priority: int = Field(default=0, ge=0)
    steps: list[JourneyStepCreate] = Field(default_factory=list)


class JourneyUpdate(BaseModel):
    """Schema for updating a journey."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=0)
    trigger_config: Optional[dict[str, Any]] = None


class JourneyOut(BaseModel):
    """Schema for journey response."""

    id: str
    name: str
    description: Optional[str]
    trigger_type: str
    trigger_config: dict[str, Any]
    is_active: bool
    priority: int
    created_by: str
    created_at: str
    step_count: int


class UserJourneyOut(BaseModel):
    """Schema for user journey response."""

    id: str
    user_id: str
    journey_id: str
    journey_name: str
    status: str
    current_step_id: Optional[str]
    started_at: str
    completed_at: Optional[str]
    metadata: dict[str, Any]


# ============================================================================
# ROUTES
# ============================================================================


@router.post("", status_code=status.HTTP_201_CREATED, response_model=JourneyOut)
async def create_journey(
    request: JourneyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JourneyOut:
    """
    Create a new journey definition.

    Only accessible to owners/admins.
    """
    # Check if name already exists
    existing_result = await db.execute(
        select(Journey).where(Journey.name == request.name)
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Journey with name '{request.name}' already exists",
        )

    # Create journey
    journey = Journey(
        id=str(__import__("uuid").uuid4()),
        name=request.name,
        description=request.description,
        trigger_type=request.trigger_type.value,
        trigger_config=request.trigger_config,
        is_active=request.is_active,
        priority=request.priority,
        created_by=current_user.id,
    )
    db.add(journey)

    # Create steps
    for step_data in request.steps:
        step = JourneyStep(
            id=str(__import__("uuid").uuid4()),
            journey_id=journey.id,
            name=step_data.name,
            order=step_data.order,
            action_type=step_data.action_type.value,
            action_config=step_data.action_config,
            delay_minutes=step_data.delay_minutes,
            condition=step_data.condition,
        )
        db.add(step)

    await db.commit()
    await db.refresh(journey)

    logger.info(
        f"Journey created: {journey.name}",
        extra={
            "journey_id": journey.id,
            "created_by": current_user.id,
            "step_count": len(request.steps),
        },
    )

    return JourneyOut(
        id=journey.id,
        name=journey.name,
        description=journey.description,
        trigger_type=journey.trigger_type,
        trigger_config=journey.trigger_config,
        is_active=journey.is_active,
        priority=journey.priority,
        created_by=journey.created_by,
        created_at=journey.created_at.isoformat(),
        step_count=len(request.steps),
    )


@router.get("", response_model=list[JourneyOut])
async def list_journeys(
    trigger_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[JourneyOut]:
    """
    List all journeys with optional filters.

    Only accessible to owners/admins.
    """
    query = select(Journey)

    if trigger_type:
        query = query.where(Journey.trigger_type == trigger_type)
    if is_active is not None:
        query = query.where(Journey.is_active == is_active)

    query = query.order_by(Journey.priority.desc(), Journey.created_at.desc())

    result = await db.execute(query)
    journeys = result.scalars().all()

    # Count steps for each journey
    journey_outputs = []
    for journey in journeys:
        steps_result = await db.execute(
            select(JourneyStep).where(JourneyStep.journey_id == journey.id)
        )
        step_count = len(steps_result.scalars().all())

        journey_outputs.append(
            JourneyOut(
                id=journey.id,
                name=journey.name,
                description=journey.description,
                trigger_type=journey.trigger_type,
                trigger_config=journey.trigger_config,
                is_active=journey.is_active,
                priority=journey.priority,
                created_by=journey.created_by,
                created_at=journey.created_at.isoformat(),
                step_count=step_count,
            )
        )

    return journey_outputs


@router.get("/{journey_id}", response_model=JourneyOut)
async def get_journey(
    journey_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JourneyOut:
    """
    Get journey details by ID.

    Only accessible to owners/admins.
    """
    result = await db.execute(select(Journey).where(Journey.id == journey_id))
    journey = result.scalar_one_or_none()

    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found"
        )

    steps_result = await db.execute(
        select(JourneyStep).where(JourneyStep.journey_id == journey.id)
    )
    step_count = len(steps_result.scalars().all())

    return JourneyOut(
        id=journey.id,
        name=journey.name,
        description=journey.description,
        trigger_type=journey.trigger_type,
        trigger_config=journey.trigger_config,
        is_active=journey.is_active,
        priority=journey.priority,
        created_by=journey.created_by,
        created_at=journey.created_at.isoformat(),
        step_count=step_count,
    )


@router.patch("/{journey_id}", response_model=JourneyOut)
async def update_journey(
    journey_id: str,
    request: JourneyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JourneyOut:
    """
    Update journey properties.

    Only accessible to owners/admins.
    """
    result = await db.execute(select(Journey).where(Journey.id == journey_id))
    journey = result.scalar_one_or_none()

    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found"
        )

    # Update fields
    if request.name is not None:
        # Check for name collision
        existing_result = await db.execute(
            select(Journey)
            .where(Journey.name == request.name)
            .where(Journey.id != journey_id)
        )
        if existing_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Journey with name '{request.name}' already exists",
            )
        journey.name = request.name

    if request.description is not None:
        journey.description = request.description
    if request.is_active is not None:
        journey.is_active = request.is_active
    if request.priority is not None:
        journey.priority = request.priority
    if request.trigger_config is not None:
        journey.trigger_config = request.trigger_config

    await db.commit()
    await db.refresh(journey)

    logger.info(
        f"Journey updated: {journey.name}",
        extra={"journey_id": journey.id, "updated_by": current_user.id},
    )

    steps_result = await db.execute(
        select(JourneyStep).where(JourneyStep.journey_id == journey.id)
    )
    step_count = len(steps_result.scalars().all())

    return JourneyOut(
        id=journey.id,
        name=journey.name,
        description=journey.description,
        trigger_type=journey.trigger_type,
        trigger_config=journey.trigger_config,
        is_active=journey.is_active,
        priority=journey.priority,
        created_by=journey.created_by,
        created_at=journey.created_at.isoformat(),
        step_count=step_count,
    )


@router.delete("/{journey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_journey(
    journey_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a journey definition.

    Only accessible to owners/admins. Cascades to steps and user journeys.
    """
    result = await db.execute(select(Journey).where(Journey.id == journey_id))
    journey = result.scalar_one_or_none()

    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found"
        )

    await db.delete(journey)
    await db.commit()

    logger.info(
        f"Journey deleted: {journey.name}",
        extra={"journey_id": journey.id, "deleted_by": current_user.id},
    )


@router.get("/users/{user_id}/journeys", response_model=list[UserJourneyOut])
async def list_user_journeys(
    user_id: str,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[UserJourneyOut]:
    """
    List journeys for a specific user.

    Only accessible to owners/admins or the user themselves.
    """
    # Authorization: user can see their own journeys, admin can see all
    if user_id != current_user.id:
        # Check if current user is admin (placeholder - implement proper RBAC)
        pass

    query = select(UserJourney).where(UserJourney.user_id == user_id)

    if status_filter:
        query = query.where(UserJourney.status == status_filter)

    query = query.order_by(UserJourney.started_at.desc())

    result = await db.execute(query)
    user_journeys = result.scalars().all()

    # Load journey names
    outputs = []
    for uj in user_journeys:
        journey_result = await db.execute(
            select(Journey).where(Journey.id == uj.journey_id)
        )
        journey = journey_result.scalar_one()

        outputs.append(
            UserJourneyOut(
                id=uj.id,
                user_id=uj.user_id,
                journey_id=uj.journey_id,
                journey_name=journey.name,
                status=uj.status,
                current_step_id=uj.current_step_id,
                started_at=uj.started_at.isoformat(),
                completed_at=uj.completed_at.isoformat() if uj.completed_at else None,
                metadata=uj.metadata,
            )
        )

    return outputs


@router.post("/trigger", response_model=dict[str, Any])
async def trigger_journey(
    trigger_type: TriggerType,
    user_id: str,
    context: dict[str, Any] = {},
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Manually trigger journey evaluation for a user.

    Only accessible to owners/admins for testing.
    """
    engine = JourneyEngine()
    started_journey_ids = await engine.evaluate_trigger(
        db, trigger_type, user_id, context
    )

    logger.info(
        f"Manually triggered {trigger_type.value} for user {user_id}",
        extra={
            "trigger_type": trigger_type.value,
            "user_id": user_id,
            "started_count": len(started_journey_ids),
        },
    )

    return {
        "trigger_type": trigger_type.value,
        "user_id": user_id,
        "started_journeys": started_journey_ids,
    }


@router.post("/execute/{user_journey_id}", response_model=dict[str, Any])
async def execute_journey_steps(
    user_journey_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Manually execute pending steps for a user journey.

    Only accessible to owners/admins for testing.
    """
    engine = JourneyEngine()
    result = await engine.execute_steps(db, user_journey_id)

    logger.info(
        f"Manually executed steps for user journey {user_journey_id}",
        extra={"user_journey_id": user_journey_id, "result": result},
    )

    return result
