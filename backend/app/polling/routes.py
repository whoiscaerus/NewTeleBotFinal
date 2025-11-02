"""
Poll API V2 Routes (PR-49): Enhanced polling with compression, ETags, and adaptive backoff.

Endpoints:
- GET /api/v2/client/poll - Poll for pending approvals with compression/ETags support
- GET /api/v2/client/poll/status - Poll status endpoint

Features:
- Response compression (gzip, brotli, zstd negotiation)
- ETag support for conditional requests (304 Not Modified)
- Adaptive backoff intervals based on approval frequency
- Batch size limiting for performance
- Backward compatible with v1 API
"""

import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.models import Approval
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.core.logging import get_logger
from backend.app.polling.adaptive_backoff import AdaptiveBackoffManager
from backend.app.polling.protocol_v2 import (
    calculate_compression_ratio,
    check_if_modified,
    compress_response,
    generate_etag,
)
from backend.app.signals.models import EncryptedSignalEnvelope

router = APIRouter(prefix="/api/v2", tags=["polling-v2"])


class ApprovalOut(BaseModel):
    """Approval data for poll response."""

    id: str = Field(..., description="Approval ID")
    instrument: str = Field(..., description="Instrument symbol")
    side: str = Field(..., pattern="^(buy|sell)$", description="Trade direction")
    entry_price: float = Field(..., gt=0, description="Entry price")
    volume: float = Field(..., gt=0, description="Trade volume")
    ttl_minutes: int = Field(..., ge=1, description="Time-to-live in minutes")
    approved_at: str = Field(..., description="Approval timestamp (ISO 8601)")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")


class PollResponseV2(BaseModel):
    """Poll response with V2 features (compression, ETag, backoff)."""

    version: int = Field(2, description="API version")
    approvals: list[ApprovalOut] = Field(
        default_factory=list, description="Pending approvals"
    )
    count: int = Field(..., ge=0, description="Number of approvals returned")
    compression_ratio: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Compression ratio achieved (0=perfect, 1=none)",
    )
    etag: str = Field(..., description="ETag for conditional requests")
    next_poll_seconds: int = Field(
        ..., ge=10, le=60, description="Recommended poll interval"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "version": 2,
                "approvals": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "instrument": "XAUUSD",
                        "side": "buy",
                        "entry_price": 1950.50,
                        "volume": 0.5,
                        "ttl_minutes": 240,
                        "approved_at": "2025-10-26T10:30:45Z",
                        "created_at": "2025-10-26T10:30:00Z",
                    }
                ],
                "count": 1,
                "compression_ratio": 0.35,
                "etag": "sha256:a1b2c3d4e5f6...",
                "next_poll_seconds": 10,
            }
        }


def get_backoff_manager() -> AdaptiveBackoffManager:
    """Get AdaptiveBackoffManager for poll history tracking.

    Returns:
        AdaptiveBackoffManager: Initialized manager with Redis client

    Example:
        >>> manager = get_backoff_manager()
        >>> manager.record_poll(device_id, has_approvals=True)
    """
    try:
        from redis import Redis

        redis = Redis(host="localhost", port=6379, db=0, decode_responses=True)
        return AdaptiveBackoffManager(redis)
    except Exception:
        # Fallback: return manager with None (will log warnings on usage)
        return AdaptiveBackoffManager(None)


@router.get(
    "/client/poll",
    response_model=PollResponseV2,
    status_code=status.HTTP_200_OK,
    responses={
        304: {"description": "Not Modified - no new approvals since If-Modified-Since"},
        400: {"description": "Invalid request parameters"},
        401: {"description": "Unauthorized - invalid device auth"},
        500: {"description": "Internal server error"},
    },
)
async def poll_v2(
    # Request headers
    device_auth: str = Header(
        ...,
        alias="X-Device-Auth",
        description="HMAC-256 device authentication token",
    ),
    accept_encoding: str = Header(
        "gzip", alias="Accept-Encoding", description="Supported compression algorithms"
    ),
    if_modified_since: Optional[str] = Header(
        None,
        alias="If-Modified-Since",
        description="ISO 8601 timestamp for conditional requests",
    ),
    poll_version: str = Header(
        "2", alias="X-Poll-Version", description="Poll API version"
    ),
    # Query parameters
    batch_size: int = Query(100, ge=1, le=500, description="Max approvals to return"),
    compress: bool = Query(True, description="Enable response compression"),
    # Dependencies
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    manager: AdaptiveBackoffManager = Depends(get_backoff_manager),
    logger=Depends(get_logger),
):
    """
    Poll for pending trading signal approvals with V2 features.

    Supports:
    - Response compression (gzip/brotli/zstd)
    - ETags for conditional requests (304 Not Modified)
    - Adaptive backoff intervals
    - Batch size limiting

    Args:
        device_auth: Device HMAC authentication header
        accept_encoding: Accepted compression algorithms
        if_modified_since: ISO 8601 timestamp for conditional requests
        poll_version: Expected API version (v2)
        batch_size: Max approvals to return (1-500)
        compress: Enable compression
        db: Database session
        current_user: Authenticated user
        manager: AdaptiveBackoffManager for backoff tracking
        logger: Structured logger

    Returns:
        PollResponseV2: Approvals with compression_ratio, etag, next_poll_seconds

    Raises:
        HTTPException: 400 if invalid params, 401 if auth fails, 500 on error

    Response Status:
        200: New data returned (with compression applied if requested)
        304: Not Modified (no approvals since If-Modified-Since timestamp)
        400: Invalid request
        401: Authentication failed
        500: Internal server error

    Example:
        >>> response = await client.get(
        ...     "/api/v2/client/poll",
        ...     headers={
        ...         "X-Device-Auth": "hmac-token",
        ...         "Accept-Encoding": "gzip, br",
        ...         "If-Modified-Since": "2025-01-01T12:00:00Z",
        ...         "X-Poll-Version": "2"
        ...     },
        ...     params={"batch_size": 50, "compress": True}
        ... )
        >>> assert response.status_code in (200, 304)
        >>> if response.status_code == 200:
        ...     data = response.json()
        ...     assert data["version"] == 2
        ...     assert data["compression_ratio"] > 0
        ...     assert data["etag"].startswith("sha256:")
    """
    try:
        logger.info(
            "Poll V2 request received",
            extra={
                "user_id": current_user.id,
                "batch_size": batch_size,
                "compress": compress,
                "poll_version": poll_version,
            },
        )

        # Validate poll version
        if poll_version != "2":
            logger.warning(f"Unsupported poll version: {poll_version}")
            raise HTTPException(
                status_code=400, detail=f"Unsupported poll version: {poll_version}"
            )

        # Validate batch size
        if not (1 <= batch_size <= 500):
            logger.warning(f"Invalid batch size: {batch_size}")
            raise HTTPException(status_code=400, detail="Batch size must be 1-500")

        # Parse If-Modified-Since timestamp
        since = None
        if if_modified_since:
            try:
                since = datetime.fromisoformat(if_modified_since.replace("Z", "+00:00"))
                logger.debug(f"If-Modified-Since: {since}")
            except ValueError:
                logger.warning(f"Invalid If-Modified-Since format: {if_modified_since}")
                raise HTTPException(
                    status_code=400,
                    detail="If-Modified-Since must be ISO 8601 format",
                )

        # Query pending approvals for user
        stmt = (
            select(Approval)
            .where(
                and_(
                    Approval.user_id == current_user.id,
                    Approval.status == 0,  # 0 = pending
                )
            )
            .order_by(desc(Approval.created_at))
            .limit(batch_size)
        )

        result = await db.execute(stmt)
        approvals = result.scalars().all()

        logger.debug(
            f"Found {len(approvals)} pending approvals",
            extra={"user_id": current_user.id},
        )

        # Check if modified (conditional request)
        if not check_if_modified(approvals, since):
            logger.debug(
                "No modifications since If-Modified-Since",
                extra={"user_id": current_user.id, "since": since},
            )

            # Record poll with no approvals
            device_id = (
                UUID(device_auth.split(":")[0]) if ":" in device_auth else UUID(int=0)
            )
            manager.record_poll(device_id, has_approvals=False)

            # Return 304 Not Modified
            return Response(status_code=status.HTTP_304_NOT_MODIFIED)

        # Record poll with approvals found
        device_id = (
            UUID(device_auth.split(":")[0]) if ":" in device_auth else UUID(int=0)
        )
        manager.record_poll(device_id, has_approvals=len(approvals) > 0)

        # Fetch encrypted signal envelopes for approvals
        approval_ids = [a.id for a in approvals]
        if approval_ids:
            stmt = select(EncryptedSignalEnvelope).where(
                EncryptedSignalEnvelope.approval_id.in_(approval_ids)
            )
            result = await db.execute(stmt)
            envelopes = result.scalars().all()
        else:
            envelopes = []

        # Build response data
        response_data = {
            "version": 2,
            "approvals": [
                {
                    "id": str(a.id),
                    "instrument": a.signal.instrument if a.signal else "UNKNOWN",
                    "side": (
                        "buy" if (a.signal.side if a.signal else 0) == 0 else "sell"
                    ),
                    "entry_price": float(a.signal.entry_price if a.signal else 0),
                    "volume": float(a.signal.volume if a.signal else 0),
                    "ttl_minutes": a.ttl_minutes,
                    "approved_at": a.created_at.isoformat(),
                    "created_at": a.created_at.isoformat(),
                }
                for a in approvals
            ],
            "count": len(approvals),
        }

        # Generate ETag from response data
        etag = generate_etag(response_data)
        logger.debug(f"Generated ETag: {etag}", extra={"user_id": current_user.id})

        # Compress response if requested
        if compress and accept_encoding and accept_encoding.lower() != "identity":
            response_json = json.dumps(response_data)
            compressed_data, algo = compress_response(response_data, accept_encoding)
            compression_ratio = calculate_compression_ratio(
                len(response_json), len(compressed_data)
            )

            logger.info(
                f"Response compressed with {algo}: {len(response_json)}→{len(compressed_data)} bytes",
                extra={
                    "user_id": current_user.id,
                    "algorithm": algo,
                    "compression_ratio": compression_ratio,
                },
            )
        else:
            compressed_data = json.dumps(response_data).encode("utf-8")
            compression_ratio = 1.0
            algo = "identity"

        # Calculate adaptive backoff interval
        next_poll_interval = manager.get_backoff_interval(device_id)
        logger.debug(
            f"Next poll interval: {next_poll_interval}s",
            extra={"user_id": current_user.id},
        )

        # Build response
        response_obj = PollResponseV2(
            version=2,
            approvals=response_data["approvals"],
            count=len(approvals),
            compression_ratio=compression_ratio,
            etag=etag,
            next_poll_seconds=next_poll_interval,
        )

        logger.info(
            "Poll V2 response sent",
            extra={
                "user_id": current_user.id,
                "approval_count": len(approvals),
                "compression_ratio": compression_ratio,
                "algorithm": algo,
            },
        )

        # Create response with compression header
        response_json = response_obj.model_dump_json()

        if compress and algo != "identity":
            compressed_response = json.loads(response_json).copy()
            compressed_response_json = json.dumps(compressed_response)
            compressed_bytes, _ = compress_response(
                compressed_response, accept_encoding
            )

            return Response(
                content=compressed_bytes,
                status_code=200,
                media_type="application/json",
                headers={
                    "Content-Encoding": algo,
                    "ETag": f'"{etag}"',
                    "X-Compression-Ratio": str(compression_ratio),
                    "X-Poll-Version": "2",
                },
            )
        else:
            return Response(
                content=response_json,
                status_code=200,
                media_type="application/json",
                headers={
                    "ETag": f'"{etag}"',
                    "X-Compression-Ratio": str(compression_ratio),
                    "X-Poll-Version": "2",
                },
            )

    except ValueError as e:
        logger.error(f"Poll V2 validation error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Poll V2 unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/client/poll/status", tags=["polling-v2"])
async def poll_status(
    device_auth: str = Header(..., alias="X-Device-Auth"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    manager: AdaptiveBackoffManager = Depends(get_backoff_manager),
    logger=Depends(get_logger),
):
    """
    Get poll status and history for a device.

    Args:
        device_auth: Device HMAC authentication header
        db: Database session
        current_user: Authenticated user
        manager: AdaptiveBackoffManager
        logger: Structured logger

    Returns:
        dict: Poll status with history and current backoff

    Example:
        >>> response = await client.get(
        ...     "/api/v2/client/poll/status",
        ...     headers={"X-Device-Auth": "hmac-token"}
        ... )
        >>> assert response.status_code == 200
        >>> data = response.json()
        >>> assert "history" in data
        >>> assert "current_backoff" in data
    """
    try:
        device_id = (
            UUID(device_auth.split(":")[0]) if ":" in device_auth else UUID(int=0)
        )

        history = manager.get_history(device_id)
        backoff = manager.get_backoff_interval(device_id)

        logger.info(
            "Poll status requested",
            extra={
                "user_id": current_user.id,
                "history_length": len(history),
                "current_backoff": backoff,
            },
        )

        return {
            "device_id": str(device_id),
            "history": history,
            "current_backoff": backoff,
            "version": 2,
        }

    except Exception as e:
        logger.error(f"Poll status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
