"""
Aggregate execution status queries for PR-025.

Provides functions to query execution outcomes per approval and aggregate
placement/failure statistics across multiple devices.
"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ea.models import Execution, ExecutionStatus
from backend.app.ea.schemas import AggregateExecutionStatus, ExecutionOut

logger = logging.getLogger(__name__)


async def get_approval_execution_status(
    db: AsyncSession,
    approval_id: UUID,
) -> AggregateExecutionStatus:
    """
    Get aggregated execution status for an approval.

    Counts executions by status (placed, failed) and returns detailed
    list of all executions for this approval.

    Args:
        db: Database session
        approval_id: Approval ID to query

    Returns:
        AggregateExecutionStatus with counts and full execution list

    Example:
        >>> status = await get_approval_execution_status(db, approval_id)
        >>> assert status.placed_count == 2
        >>> assert status.failed_count == 0
    """
    # Query all executions for this approval
    stmt = select(Execution).where(Execution.approval_id == approval_id)
    result = await db.execute(stmt)
    executions = result.scalars().all()

    # Count by status
    placed_count = sum(1 for e in executions if e.status == ExecutionStatus.PLACED)
    failed_count = sum(1 for e in executions if e.status == ExecutionStatus.FAILED)
    total_count = len(executions)

    # Get latest update
    last_update = max((e.updated_at for e in executions), default=datetime.utcnow())

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
        "Approval execution status queried",
        extra={
            "approval_id": approval_id,
            "placed_count": placed_count,
            "failed_count": failed_count,
            "total_count": total_count,
        },
    )

    return AggregateExecutionStatus(
        approval_id=approval_id,
        placed_count=placed_count,
        failed_count=failed_count,
        total_count=total_count,
        last_update=last_update,
        executions=execution_outs,
    )


async def get_executions_by_device(
    db: AsyncSession,
    device_id: UUID,
    status_filter: ExecutionStatus = None,
    limit: int = 100,
) -> list[Execution]:
    """
    Get executions for a specific device.

    Args:
        db: Database session
        device_id: Device ID to query
        status_filter: Optional status filter
        limit: Max results to return

    Returns:
        List of Execution records
    """
    stmt = select(Execution).where(Execution.device_id == device_id)

    if status_filter:
        stmt = stmt.where(Execution.status == status_filter)

    stmt = stmt.order_by(Execution.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    return result.scalars().all()


async def get_executions_by_approval(
    db: AsyncSession,
    approval_id: UUID,
) -> list[Execution]:
    """
    Get all executions for an approval across all devices.

    Args:
        db: Database session
        approval_id: Approval ID to query

    Returns:
        List of Execution records
    """
    stmt = (
        select(Execution)
        .where(Execution.approval_id == approval_id)
        .order_by(Execution.created_at.desc())
    )

    result = await db.execute(stmt)
    return result.scalars().all()


async def get_execution_success_rate(
    db: AsyncSession,
    device_id: UUID,
    hours: int = 24,
) -> dict[str, float]:
    """
    Calculate execution success rate for device.

    Args:
        db: Database session
        device_id: Device ID
        hours: Look back window

    Returns:
        Dict with success_rate, placement_count, failure_count
    """
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(hours=hours)

    stmt = select(Execution).where(
        and_(
            Execution.device_id == device_id,
            Execution.created_at >= cutoff,
        )
    )

    result = await db.execute(stmt)
    executions = result.scalars().all()

    if not executions:
        return {
            "success_rate": 0.0,
            "placement_count": 0,
            "failure_count": 0,
            "total_count": 0,
        }

    placed = sum(1 for e in executions if e.status == ExecutionStatus.PLACED)
    failed = sum(1 for e in executions if e.status == ExecutionStatus.FAILED)
    total = len(executions)

    success_rate = (placed / total * 100) if total > 0 else 0.0

    return {
        "success_rate": success_rate,
        "placement_count": placed,
        "failure_count": failed,
        "total_count": total,
    }


async def get_failed_executions(
    db: AsyncSession,
    approval_id: UUID = None,
    device_id: UUID = None,
    limit: int = 50,
) -> list[Execution]:
    """
    Get failed executions.

    Args:
        db: Database session
        approval_id: Filter by approval (optional)
        device_id: Filter by device (optional)
        limit: Max results

    Returns:
        List of failed Execution records
    """
    stmt = select(Execution).where(Execution.status == ExecutionStatus.FAILED)

    if approval_id:
        stmt = stmt.where(Execution.approval_id == approval_id)

    if device_id:
        stmt = stmt.where(Execution.device_id == device_id)

    stmt = stmt.order_by(Execution.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    return result.scalars().all()
