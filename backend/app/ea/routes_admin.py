"""
Admin execution query endpoints for PR-025.

Endpoints:
- GET /api/v1/executions/{approval_id}: Get aggregate execution status for approval
- GET /api/v1/executions/device/{device_id}: Get execution history for device (admin only)
- GET /api/v1/executions/device/{device_id}/success-rate: Get device success metrics (admin only)
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.models import Approval
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.auth.rbac import require_roles
from backend.app.core.db import get_db
from backend.app.ea.aggregate import (
    get_approval_execution_status,
    get_execution_success_rate,
    get_executions_by_device,
)
from backend.app.ea.schemas import AggregateExecutionStatus, ExecutionOut

router = APIRouter(prefix="/api/v1/executions", tags=["executions"])
logger = logging.getLogger(__name__)


@router.get("/{approval_id}", response_model=AggregateExecutionStatus)
@require_roles("admin", "owner")
async def query_approval_executions(
    approval_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> AggregateExecutionStatus:
    """
    Get aggregated execution status for an approval.

    Returns aggregate counts (placed, failed) and full list of executions
    across all devices for this approval.

    Requires: admin or owner role

    Args:
        approval_id: Approval ID to query (as UUID string)
        current_user: Authenticated user (admin/owner)
        db: Database session

    Returns:
        AggregateExecutionStatus with counts and execution details

    Raises:
        HTTPException: 404 if approval not found
        HTTPException: 403 if user is not admin/owner

    Example:
        GET /api/v1/executions/550e8400-e29b-41d4-a716-446655440000
        Authorization: Bearer <JWT_TOKEN>
    """
    logger.info(
        "Querying approval execution status",
        extra={
            "approval_id": approval_id,
            "user_id": current_user.id,
            "user_role": current_user.role,
        },
    )

    # Verify approval exists
    from sqlalchemy import select

    stmt = select(Approval).where(Approval.id == approval_id)
    result = await db.execute(stmt)
    approval = result.scalar_one_or_none()

    if not approval:
        logger.warning("Approval not found", extra={"approval_id": approval_id})
        raise HTTPException(status_code=404, detail="Approval not found")

    # Get aggregate status
    status = await get_approval_execution_status(db, approval_id)

    logger.info(
        "Approval execution status retrieved",
        extra={
            "approval_id": approval_id,
            "placed_count": status.placed_count,
            "failed_count": status.failed_count,
        },
    )

    return status


@router.get("/device/{device_id}/executions", response_model=list[ExecutionOut])
@require_roles("admin", "owner")
async def query_device_executions(
    device_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),  # noqa: B008
    limit: int = 100,
) -> list[ExecutionOut]:
    """
    Get execution history for a device (admin only).

    Returns recent executions from this device with full details
    including approval, status, and broker outcomes.

    Requires: admin or owner role

    Args:
        device_id: Device ID to query (as UUID string)
        db: Database session
        current_user: Authenticated user (admin/owner)
        limit: Max results to return (default 100, max 1000)

    Returns:
        List of ExecutionOut records

    Example:
        GET /api/v1/executions/device/dev_123/executions?limit=50
        Authorization: Bearer <JWT_TOKEN>
    """
    # Validate limit
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")

    logger.info(
        "Querying device executions",
        extra={"device_id": device_id, "user_id": current_user.id, "limit": limit},
    )

    # Get executions
    executions = await get_executions_by_device(db, device_id, limit=limit)

    # Convert to schemas
    execution_outs = [
        ExecutionOut(
            id=e.id,
            approval_id=e.approval_id,
            device_id=e.device_id,
            status=e.status.value,
            broker_ticket=e.broker_ticket,
            error=e.error,
            created_at=e.created_at,
            updated_at=e.updated_at,
        )
        for e in executions
    ]

    logger.info(
        "Device executions retrieved",
        extra={"device_id": device_id, "execution_count": len(execution_outs)},
    )

    return execution_outs


@router.get("/device/{device_id}/success-rate", response_model=dict)
@require_roles("admin", "owner")
async def query_device_success_rate(
    device_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),  # noqa: B008
    hours: int = 24,
) -> dict:
    """
    Get device execution success metrics (admin only).

    Calculates success rate as: placed_count / total_count * 100

    Requires: admin or owner role

    Args:
        device_id: Device ID to query
        db: Database session
        current_user: Authenticated user
        hours: Look-back window (default 24, max 720)

    Returns:
        Dict with success_rate, placement_count, failure_count

    Example:
        GET /api/v1/executions/device/dev_123/success-rate?hours=48
        Authorization: Bearer <JWT_TOKEN>
    """
    # Validate hours
    if hours < 1 or hours > 720:
        raise HTTPException(status_code=400, detail="hours must be between 1 and 720")

    logger.info(
        "Querying device success rate",
        extra={"device_id": device_id, "user_id": current_user.id, "hours": hours},
    )

    # Get metrics
    metrics = await get_execution_success_rate(db, device_id, hours)

    logger.info(
        "Device success rate retrieved",
        extra={
            "device_id": device_id,
            "success_rate": metrics["success_rate"],
            "placement_count": metrics["placement_count"],
        },
    )

    return metrics
