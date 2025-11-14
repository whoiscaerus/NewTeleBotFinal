"""API routes for signal ingestion and management."""

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.core.db import get_db
from backend.app.core.errors import APIError
from backend.app.core.settings import get_settings
from backend.app.signals.schema import SignalCreate, SignalListOut, SignalOut, SignalUpdate
from backend.app.signals.service import SignalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


@router.post("", status_code=201, response_model=SignalOut)
async def create_signal(
    request: SignalCreate,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
    x_signature: str | None = Header(None),
    x_producer_id: str | None = Header(None),
) -> SignalOut:
    """Ingest new trading signal.

    Validates HMAC signature, deduplicates by external_id, stores signal.

    Args:
        request: Signal data
        x_signature: HMAC-SHA256 signature of request body
        x_producer_id: External producer ID for deduplication

    Returns:
        Created signal

    Raises:
        400: Invalid payload
        401: Unauthorized / invalid signature
        409: Duplicate signal
        413: Payload too large
        422: Validation error
        500: Server error
    """
    try:
        settings = get_settings()
        service = SignalService(
            db,
            hmac_key=settings.signals.hmac_key,
            dedup_window_seconds=settings.signals.dedup_window_seconds,
        )

        # Validate payload size
        if (
            request.payload
            and len(json.dumps(request.payload).encode())
            > settings.signals.max_payload_bytes
        ):
            logger.warning(
                f"Signal payload too large for user {current_user.id}: "
                f"{len(json.dumps(request.payload).encode())} bytes"
            )
            raise HTTPException(
                status_code=413,
                detail=f"Payload exceeds {settings.signals.max_payload_bytes} bytes",
            )

        # Verify HMAC if signature provided and enabled
        if x_signature and settings.signals.hmac_enabled:
            payload_json = json.dumps(request.model_dump())
            if not service.verify_hmac_signature(payload_json, x_signature):
                logger.warning(f"HMAC verification failed for user {current_user.id}")
                raise HTTPException(status_code=401, detail="Invalid HMAC signature")

        signal = await service.create_signal(
            user_id=current_user.id,
            signal_create=request,
            external_id=x_producer_id,
        )

        return signal

    except HTTPException:
        raise
    except APIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    except Exception as e:
        logger.error(f"Signal creation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{signal_id}", response_model=SignalOut)
async def get_signal(
    signal_id: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
) -> SignalOut:
    """Retrieve signal by ID."""
    try:
        service = SignalService(db, hmac_key="your-secret-key")
        signal = await service.get_signal(signal_id)

        # Verify ownership
        if signal.id and current_user.id != signal.user_id:  # Add user_id to SignalOut
            raise HTTPException(status_code=403, detail="Unauthorized")

        return signal
    except APIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.patch("/{signal_id}", response_model=SignalOut)
async def update_signal(
    signal_id: str,
    request: SignalUpdate,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
) -> SignalOut:
    """Update signal status."""
    try:
        from sqlalchemy import select
        from backend.app.signals.models import Signal

        # Query signal directly from database
        result = await db.execute(select(Signal).where(Signal.id == signal_id))
        signal = result.scalar_one_or_none()

        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found")

        # Verify ownership
        if current_user.id != signal.user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")

        # Update signal status in database
        signal.status = request.status
        db.add(signal)
        await db.commit()
        await db.refresh(signal)

        logger.info(f"Signal {signal_id} status updated to {request.status}")
        return signal

    except HTTPException:
        raise
    except APIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    except Exception as e:
        logger.error(f"Signal update failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("", response_model=SignalListOut)
async def list_signals(
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
    status: int | None = None,
    instrument: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> SignalListOut:
    """List user's signals with filtering."""
    try:
        service = SignalService(db, hmac_key="your-secret-key")
        signals, total = await service.list_signals(
            user_id=current_user.id,
            status=status,
            instrument=instrument,
            page=page,
            page_size=page_size,
        )

        return SignalListOut(
            items=signals,
            total=total,
            page=page,
            page_size=page_size,
        )
    except APIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
