"""Approval domain API routes."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.schemas import ApprovalListOut, ApprovalOut, ApprovalRequest
from backend.app.approvals.service import (
    create_approval,
    get_approval,
    get_signal_approvals,
    get_user_approvals,
)
from backend.app.core.db import get_db


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


@router.post("", status_code=201, response_model=ApprovalOut)
async def approve_signal(
    request: Request,
    approval_request: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
    x_user_id: Optional[str] = Header(None),
) -> ApprovalOut:
    """Approve or reject a signal.

    Creates an approval decision. Each user can only approve/reject each signal once.
    
    For now, X-User-Id header provides the user ID (JWT auth via PR-8).

    Args:
        request: HTTP request
        approval_request: Approval request with signal_id and decision
        db: Database session
        x_user_id: User ID from header

    Returns:
        ApprovalOut: Created approval details

    Raises:
        HTTPException: 400 if signal not found or already approved,
                      401 if unauthorized,
                      422 if validation fails,
                      500 on server error

    Example:
        POST /api/v1/approvals
        Headers: X-User-Id: user-123
        {
            "signal_id": "sig-abc123",
            "decision": 0,
            "consent_version": "2024-01-15",
            "ip": "192.168.1.1",
            "ua": "Mozilla/5.0..."
        }

        Response (201):
        {
            "id": "apr-xyz789",
            "signal_id": "sig-abc123",
            "user_id": "user-123",
            "decision": 0,
            "created_at": "2024-01-15T10:30:00Z"
        }
    """
    # Validate user_id header
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    
    try:
        logger.info(
            f"User approving signal",
            extra={
                "user_id": x_user_id,
                "signal_id": approval_request.signal_id,
                "decision": approval_request.decision,
            },
        )
        approval = await create_approval(db, x_user_id, approval_request)
        return approval
    except ValueError as e:
        logger.warning(
            f"Approval validation failed: {e}",
            extra={
                "user_id": x_user_id,
                "signal_id": approval_request.signal_id,
            },
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error creating approval: {e}",
            exc_info=True,
            extra={"user_id": x_user_id},
        )
        raise HTTPException(status_code=500, detail="Failed to create approval")


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_approval_endpoint(
    approval_id: str,
    db: AsyncSession = Depends(get_db),
    x_user_id: Optional[str] = Header(None),
) -> ApprovalOut:
    """Get an approval by ID.

    Args:
        approval_id: Approval ID
        db: Database session
        x_user_id: User ID from header

    Returns:
        ApprovalOut: Approval details

    Raises:
        HTTPException: 401 if unauthorized, 404 if not found, 500 on error

    Example:
        GET /api/v1/approvals/apr-xyz789
        Headers: X-User-Id: user-123

        Response (200):
        {
            "id": "apr-xyz789",
            "signal_id": "sig-abc123",
            "user_id": "user-123",
            "decision": 0,
            "created_at": "2024-01-15T10:30:00Z"
        }
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    
    try:
        approval = await get_approval(db, approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
        return approval
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving approval: {e}",
            exc_info=True,
            extra={"approval_id": approval_id},
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve approval")


@router.get("/user/me", response_model=ApprovalListOut)
async def get_my_approvals(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    x_user_id: Optional[str] = Header(None),
) -> ApprovalListOut:
    """Get current user's approvals.

    Returns paginated list of approvals made by the current user.

    Args:
        limit: Max results (1-1000, default 100)
        offset: Result offset (default 0)
        db: Database session
        x_user_id: User ID from header

    Returns:
        ApprovalListOut: List of approvals

    Raises:
        HTTPException: 401 if unauthorized, 500 on error

    Example:
        GET /api/v1/approvals/user/me?limit=50&offset=0
        Headers: X-User-Id: user-123

        Response (200):
        {
            "count": 2,
            "approvals": [
                {
                    "id": "apr-xyz789",
                    "signal_id": "sig-abc123",
                    "user_id": "user-123",
                    "decision": 0,
                    "created_at": "2024-01-15T10:30:00Z"
                },
                ...
            ]
        }
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    
    try:
        approvals = await get_user_approvals(db, x_user_id, limit, offset)
        return ApprovalListOut(count=len(approvals), approvals=approvals)
    except Exception as e:
        logger.error(
            f"Error retrieving user approvals: {e}",
            exc_info=True,
            extra={"user_id": x_user_id},
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve approvals")


@router.get("/signal/{signal_id}", response_model=ApprovalListOut)
async def get_signal_approvals_endpoint(
    signal_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    x_user_id: Optional[str] = Header(None),
) -> ApprovalListOut:
    """Get approvals for a signal.

    Returns paginated list of all approvals (approved/rejected) for a signal.

    Args:
        signal_id: Signal ID
        limit: Max results (1-1000, default 100)
        offset: Result offset (default 0)
        db: Database session
        x_user_id: User ID from header

    Returns:
        ApprovalListOut: List of approvals

    Raises:
        HTTPException: 401 if unauthorized, 500 on error

    Example:
        GET /api/v1/approvals/signal/sig-abc123?limit=50&offset=0
        Headers: X-User-Id: user-123

        Response (200):
        {
            "count": 1,
            "approvals": [
                {
                    "id": "apr-xyz789",
                    "signal_id": "sig-abc123",
                    "user_id": "user-123",
                    "decision": 0,
                    "created_at": "2024-01-15T10:30:00Z"
                }
            ]
        }
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    
    try:
        approvals = await get_signal_approvals(db, signal_id, limit, offset)
        return ApprovalListOut(count=len(approvals), approvals=approvals)
    except Exception as e:
        logger.error(
            f"Error retrieving signal approvals: {e}",
            exc_info=True,
            extra={"signal_id": signal_id},
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve approvals")
