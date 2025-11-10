"""
PR-098: CRM Routes - Owner API for Playbook Management

Provides owner/admin endpoints to:
- View playbook definitions
- Get execution status
- Override/cancel executions
- View performance metrics
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import require_owner
from backend.app.core.db import get_db
from backend.app.crm.models import CRMDiscountCode, CRMPlaybookExecution
from backend.app.crm.playbooks import PLAYBOOKS, mark_converted

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/crm", tags=["crm"])


# ===== SCHEMAS =====


class PlaybookDefinitionOut(BaseModel):
    """Playbook definition response."""

    name: str
    trigger: str
    description: str
    steps: list[dict[str, Any]]


class PlaybookExecutionOut(BaseModel):
    """Playbook execution response."""

    id: str
    user_id: str
    playbook_name: str
    trigger_event: str
    status: str
    current_step: int
    total_steps: int
    next_action_at: str | None
    converted_at: str | None
    conversion_value: int | None
    created_at: str
    updated_at: str


class PlaybookStatsOut(BaseModel):
    """Playbook performance stats."""

    playbook_name: str
    total_executions: int
    active_count: int
    completed_count: int
    converted_count: int
    conversion_rate: float  # 0.0-1.0
    avg_conversion_value: float | None


class ConversionRequest(BaseModel):
    """Request to mark execution as converted."""

    conversion_value: int  # In GBP


# ===== ROUTES =====


@router.get("/playbooks", response_model=list[PlaybookDefinitionOut])
async def get_playbooks(
    _owner: dict = Depends(require_owner),
) -> list[PlaybookDefinitionOut]:
    """
    Get all playbook definitions.

    Owner-only endpoint to view configured playbooks.

    Returns:
        List of playbook definitions
    """
    return [
        PlaybookDefinitionOut(
            name=playbook["name"],
            trigger=playbook["trigger"],
            description=playbook["description"],
            steps=playbook["steps"],
        )
        for playbook in PLAYBOOKS.values()
    ]


@router.get("/executions", response_model=list[PlaybookExecutionOut])
async def get_executions(
    status: str | None = None,
    playbook_name: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _owner: dict = Depends(require_owner),
) -> list[PlaybookExecutionOut]:
    """
    Get playbook executions.

    Owner-only endpoint to monitor CRM automation activity.

    Args:
        status: Filter by status (active, completed, abandoned, failed)
        playbook_name: Filter by playbook name
        limit: Max results (default 100)

    Returns:
        List of executions
    """
    stmt = select(CRMPlaybookExecution).order_by(CRMPlaybookExecution.created_at.desc())

    if status:
        stmt = stmt.where(CRMPlaybookExecution.status == status)
    if playbook_name:
        stmt = stmt.where(CRMPlaybookExecution.playbook_name == playbook_name)

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    executions = result.scalars().all()

    return [
        PlaybookExecutionOut(
            id=ex.id,
            user_id=ex.user_id,
            playbook_name=ex.playbook_name,
            trigger_event=ex.trigger_event,
            status=ex.status,
            current_step=ex.current_step,
            total_steps=ex.total_steps,
            next_action_at=ex.next_action_at.isoformat() if ex.next_action_at else None,
            converted_at=ex.converted_at.isoformat() if ex.converted_at else None,
            conversion_value=ex.conversion_value,
            created_at=ex.created_at.isoformat(),
            updated_at=ex.updated_at.isoformat(),
        )
        for ex in executions
    ]


@router.get("/stats", response_model=list[PlaybookStatsOut])
async def get_playbook_stats(
    db: AsyncSession = Depends(get_db),
    _owner: dict = Depends(require_owner),
) -> list[PlaybookStatsOut]:
    """
    Get playbook performance statistics.

    Owner-only endpoint to measure CRM effectiveness.

    Returns:
        Stats for each playbook (conversion rates, values, etc.)
    """
    stats = []

    for playbook_name in PLAYBOOKS.keys():
        # Total executions
        total_result = await db.execute(
            select(func.count(CRMPlaybookExecution.id)).where(
                CRMPlaybookExecution.playbook_name == playbook_name
            )
        )
        total_count = total_result.scalar() or 0

        # Active count
        active_result = await db.execute(
            select(func.count(CRMPlaybookExecution.id))
            .where(CRMPlaybookExecution.playbook_name == playbook_name)
            .where(CRMPlaybookExecution.status == "active")
        )
        active_count = active_result.scalar() or 0

        # Completed count
        completed_result = await db.execute(
            select(func.count(CRMPlaybookExecution.id))
            .where(CRMPlaybookExecution.playbook_name == playbook_name)
            .where(CRMPlaybookExecution.status == "completed")
        )
        completed_count = completed_result.scalar() or 0

        # Converted count
        converted_result = await db.execute(
            select(func.count(CRMPlaybookExecution.id))
            .where(CRMPlaybookExecution.playbook_name == playbook_name)
            .where(CRMPlaybookExecution.converted_at.isnot(None))
        )
        converted_count = converted_result.scalar() or 0

        # Avg conversion value
        avg_value_result = await db.execute(
            select(func.avg(CRMPlaybookExecution.conversion_value))
            .where(CRMPlaybookExecution.playbook_name == playbook_name)
            .where(CRMPlaybookExecution.converted_at.isnot(None))
        )
        avg_conversion_value = avg_value_result.scalar()

        # Conversion rate
        conversion_rate = 0.0
        if total_count > 0:
            conversion_rate = converted_count / total_count

        stats.append(
            PlaybookStatsOut(
                playbook_name=playbook_name,
                total_executions=total_count,
                active_count=active_count,
                completed_count=completed_count,
                converted_count=converted_count,
                conversion_rate=conversion_rate,
                avg_conversion_value=(
                    float(avg_conversion_value) if avg_conversion_value else None
                ),
            )
        )

    return stats


@router.post("/executions/{execution_id}/convert")
async def mark_execution_converted(
    execution_id: str,
    request: ConversionRequest,
    db: AsyncSession = Depends(get_db),
    _owner: dict = Depends(require_owner),
) -> dict:
    """
    Mark a playbook execution as converted.

    Owner-only endpoint to manually record conversion (e.g., user called and renewed).

    Args:
        execution_id: Execution ID
        request: Conversion value

    Returns:
        Success message
    """
    await mark_converted(db, execution_id, request.conversion_value)
    return {"status": "success", "execution_id": execution_id}


@router.delete("/executions/{execution_id}")
async def cancel_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
    _owner: dict = Depends(require_owner),
) -> dict:
    """
    Cancel an active playbook execution.

    Owner-only endpoint to stop a playbook (e.g., user complained).

    Args:
        execution_id: Execution ID

    Returns:
        Success message
    """
    result = await db.execute(
        select(CRMPlaybookExecution).where(CRMPlaybookExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    execution.status = "abandoned"
    execution.updated_at = datetime.utcnow()  # type: ignore
    await db.commit()

    logger.info(
        f"Cancelled execution {execution_id}",
        extra={"execution_id": execution_id, "user_id": execution.user_id},
    )

    return {"status": "cancelled", "execution_id": execution_id}


@router.get("/discount-codes", response_model=list[dict])
async def get_discount_codes(
    user_id: str | None = None,
    active_only: bool = True,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _owner: dict = Depends(require_owner),
) -> list[dict]:
    """
    Get discount codes issued by CRM.

    Owner-only endpoint to view issued codes and usage.

    Args:
        user_id: Filter by user ID
        active_only: Only show unused/unexpired codes
        limit: Max results

    Returns:
        List of discount codes
    """
    from datetime import datetime

    stmt = select(CRMDiscountCode).order_by(CRMDiscountCode.created_at.desc())

    if user_id:
        stmt = stmt.where(CRMDiscountCode.user_id == user_id)

    if active_only:
        now = datetime.utcnow()
        stmt = stmt.where(CRMDiscountCode.expires_at > now).where(
            CRMDiscountCode.used_count < CRMDiscountCode.max_uses
        )

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    codes = result.scalars().all()

    return [
        {
            "id": code.id,
            "code": code.code,
            "user_id": code.user_id,
            "percent_off": code.percent_off,
            "max_uses": code.max_uses,
            "used_count": code.used_count,
            "expires_at": code.expires_at.isoformat(),
            "used_at": code.used_at.isoformat() if code.used_at else None,
            "created_at": code.created_at.isoformat(),
        }
        for code in codes
    ]
