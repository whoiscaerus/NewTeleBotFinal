"""Execution store API routes."""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.clients.exec.schema import (
    ExecutionAckRequest,
    ExecutionErrorRequest,
    ExecutionFillRequest,
    ExecutionRecordOut,
)
from backend.app.clients.exec.service import ExecutionService
from backend.app.core.db import get_db
from backend.app.core.errors import APIError

router = APIRouter(prefix="/api/v1", tags=["executions"])


@router.post("/exec/ack", status_code=201, response_model=ExecutionRecordOut)
async def record_ack(
    request: ExecutionAckRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ExecutionRecordOut:
    """Record device ACK of signal.

    Device confirms receipt and processing of a signal.

    Args:
        request: ACK request
        db: Database session
        current_user: Authenticated user

    Returns:
        Execution record

    Raises:
        HTTPException: 400 for invalid input, 401 for unauthorized,
                      500 for server errors
    """
    try:
        service = ExecutionService(db)
        return await service.record_ack(
            device_id=request.device_id,
            signal_id=request.signal_id,
        )

    except APIError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to record ACK",
        ) from e


@router.post("/exec/fill", status_code=201, response_model=ExecutionRecordOut)
async def record_fill(
    request: ExecutionFillRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ExecutionRecordOut:
    """Record device execution fill.

    Device reports that an order filled with specified price/size.

    Args:
        request: Fill request
        db: Database session
        current_user: Authenticated user

    Returns:
        Execution record

    Raises:
        HTTPException: 400 for invalid input, 401 for unauthorized,
                      500 for server errors
    """
    try:
        service = ExecutionService(db)
        return await service.record_fill(
            device_id=request.device_id,
            signal_id=request.signal_id,
            trade_id=request.trade_id,
            fill_price=request.fill_price,
            fill_size=request.fill_size,
        )

    except APIError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to record fill",
        ) from e


@router.post(
    "/exec/error",
    status_code=201,
    response_model=ExecutionRecordOut,
)
async def record_error(
    request: ExecutionErrorRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ExecutionRecordOut:
    """Record device execution error.

    Device reports an error during signal processing.

    Args:
        request: Error request
        db: Database session
        current_user: Authenticated user

    Returns:
        Execution record

    Raises:
        HTTPException: 400 for invalid input, 401 for unauthorized,
                      500 for server errors
    """
    try:
        service = ExecutionService(db)
        return await service.record_error(
            device_id=request.device_id,
            signal_id=request.signal_id,
            status_code=request.status_code,
            error_message=request.error_message,
        )

    except APIError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to record error",
        ) from e


@router.get(
    "/exec/status/{signal_id}",
    response_model=list[ExecutionRecordOut],
)
async def get_execution_status(
    signal_id: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> list[ExecutionRecordOut]:
    """Get execution status for signal.

    Retrieve all execution records (ACKs, fills, errors) for a given signal.

    Args:
        signal_id: Signal ID
        db: Database session
        current_user: Authenticated user

    Returns:
        List of execution records

    Raises:
        HTTPException: 500 for server errors
    """
    try:
        service = ExecutionService(db)
        result = await service.get_execution_status(signal_id=signal_id)
        return cast(list[ExecutionRecordOut], result)

    except APIError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to get execution status",
        ) from e
