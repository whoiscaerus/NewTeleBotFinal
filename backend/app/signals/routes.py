"""FastAPI routes for signals domain."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.core.settings import settings
from backend.app.signals.schemas import SignalCreate, SignalOut
from backend.app.signals.service import (
    create_signal,
    validate_hmac_signature,
    validate_signal_payload,
    validate_timestamp_freshness,
)

# Get logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1", tags=["signals"])


@router.post(
    "/signals",
    status_code=201,
    response_model=SignalOut,
    summary="Create a new trading signal",
    description="Ingest a new trading signal with optional HMAC validation",
)
async def post_signal(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_producer_id: Optional[str] = Header(None),
    x_timestamp: Optional[str] = Header(None),
    x_signature: Optional[str] = Header(None),
) -> SignalOut:
    """
    Create a new trading signal.

    **Request Body:**
    ```json
    {
      "instrument": "XAUUSD",
      "side": 0,
      "time": "2024-01-15T10:30:45Z",
      "payload": {"rsi": 75},
      "version": 1
    }
    ```

    **Response (201 Created):**
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "status": 0,
      "created_at": "2024-01-15T10:30:45.123456Z"
    }
    ```

    **Authentication (if HMAC_PRODUCER_ENABLED=true):**
    - `X-Producer-Id`: Producer identifier
    - `X-Timestamp`: ISO8601 timestamp
    - `X-Signature`: Base64 HMAC-SHA256(body+timestamp+producer_id)

    **Error Responses:**
    - 400: Invalid request format or missing HMAC header
    - 401: Invalid HMAC signature or clock skew
    - 413: Payload too large (>32KB)
    - 422: Validation error (invalid instrument, side, etc.)
    - 500: Internal server error

    Args:
        request: FastAPI request object
        db: Database session
        x_producer_id: Producer ID header (required if HMAC enabled)
        x_timestamp: Timestamp header (required if HMAC enabled)
        x_signature: Signature header (required if HMAC enabled)

    Returns:
        SignalOut: Created signal details

    Raises:
        HTTPException: Various HTTP errors for validation/auth failures

    Example:
        ```python
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": 0,
                "time": "2024-01-15T10:30:45Z",
                "payload": {"rsi": 75}
            }
        )
        assert response.status_code == 201
        ```
    """
    try:
        # Read and validate raw body size first (before Pydantic parsing)
        body = await request.body()
        
        # Max 32KB per acceptance criteria
        MAX_PAYLOAD_SIZE = 32 * 1024  # 32KB
        if len(body) > MAX_PAYLOAD_SIZE:
            logger.warning(
                "Request body exceeds maximum size",
                extra={
                    "size": len(body),
                    "max": MAX_PAYLOAD_SIZE,
                    "producer_id": x_producer_id,
                },
            )
            raise HTTPException(
                status_code=413,
                detail=f"Request body too large (max {MAX_PAYLOAD_SIZE} bytes)",
            )
        
        # Parse body as JSON
        try:
            body_str = body.decode("utf-8")
            body_dict = json.loads(body_str)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning(f"JSON parse error: {e}")
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON in request body",
            )
        
        # Parse into Pydantic model
        try:
            signal = SignalCreate(**body_dict)
        except ValidationError as e:
            logger.warning(f"Pydantic validation error: {e}")
            # Return FastAPI-compatible validation error format
            details = []
            for error in e.errors():
                details.append({
                    "loc": error.get("loc", ()),
                    "msg": error.get("msg", "Validation error"),
                    "type": error.get("type", "unknown"),
                })
            raise HTTPException(
                status_code=422,
                detail=details,
            )

        # Validate payload structure
        if not validate_signal_payload(signal.payload):
            logger.warning(
                "Payload validation failed",
                extra={
                    "instrument": signal.instrument,
                    "producer_id": x_producer_id,
                },
            )
            raise HTTPException(
                status_code=413,
                detail="Payload too large (max 32KB)",
            )

        # Handle HMAC validation (if enabled)
        if settings.HMAC_PRODUCER_ENABLED:
            # Check all headers present
            if x_producer_id is None:
                logger.warning("Missing X-Producer-Id header")
                raise HTTPException(
                    status_code=401,
                    detail="Missing X-Producer-Id header",
                )

            if x_timestamp is None:
                logger.warning("Missing X-Timestamp header")
                raise HTTPException(
                    status_code=401,
                    detail="Missing X-Timestamp header",
                )

            if x_signature is None:
                logger.warning("Missing X-Signature header")
                raise HTTPException(
                    status_code=401,
                    detail="Missing X-Signature header",
                )

            # Validate producer ID not empty
            if not x_producer_id.strip():
                raise HTTPException(
                    status_code=400,
                    detail="X-Producer-Id cannot be empty",
                )

            # Validate timestamp freshness
            is_fresh, reason = validate_timestamp_freshness(
                x_timestamp,
                tolerance_seconds=300,  # 5 minutes
            )
            if not is_fresh:
                logger.warning(
                    f"Timestamp validation failed: {reason}",
                    extra={"producer_id": x_producer_id},
                )
                raise HTTPException(
                    status_code=401,
                    detail=f"Invalid timestamp: {reason}",
                )

            # Validate HMAC signature
            is_valid = validate_hmac_signature(
                body=body_str,
                timestamp=x_timestamp,
                producer_id=x_producer_id,
                signature=x_signature,
                secret=settings.HMAC_PRODUCER_SECRET,
            )

            if not is_valid:
                logger.warning(
                    "HMAC signature invalid",
                    extra={"producer_id": x_producer_id},
                )
                raise HTTPException(
                    status_code=401,
                    detail="Invalid HMAC signature",
                )

        # Create signal in database
        try:
            db_signal = await create_signal(
                db=db,
                signal_data=signal,
                producer_id=x_producer_id,
            )

            await db.commit()
            await db.refresh(db_signal)

            logger.info(
                "Signal ingested successfully",
                extra={
                    "signal_id": db_signal.id,
                    "instrument": db_signal.instrument,
                    "side": db_signal.side,
                    "producer_id": x_producer_id,
                },
            )

            return SignalOut(
                id=db_signal.id,
                status=db_signal.status,
                created_at=db_signal.created_at,
            )

        except Exception as e:
            await db.rollback()
            logger.error(
                f"Database error creating signal: {e}",
                extra={"producer_id": x_producer_id},
                exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail="Internal server error",
            )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise

    except Exception as e:
        logger.error(
            f"Unexpected error in POST /signals: {e}",
            extra={"producer_id": x_producer_id},
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )
