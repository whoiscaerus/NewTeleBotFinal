"""Signals service - business logic for signal handling."""

import hashlib
import hmac
import logging
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import APIError
from backend.app.signals.models import Signal, SignalStatus
from backend.app.signals.schema import SignalCreate, SignalOut

logger = logging.getLogger(__name__)


class DuplicateSignalError(APIError):
    """Signal already exists (deduplication check)."""

    def __init__(self, external_id: str):
        super().__init__(
            status_code=409,
            code="DUPLICATE_SIGNAL",
            message=f"Signal {external_id} already exists",
            details={"external_id": external_id},
        )


class SignalNotFoundError(APIError):
    """Signal not found."""

    def __init__(self, signal_id: str):
        super().__init__(
            status_code=404,
            code="SIGNAL_NOT_FOUND",
            message=f"Signal {signal_id} not found",
            details={"signal_id": signal_id},
        )


class SignalService:
    """Service for signal ingestion, validation, and management.

    Responsibilities:
    - Validate incoming signal payloads
    - Deduplicate signals by external_id
    - Store signals in database
    - Query signals with filtering
    - Update signal status
    """

    def __init__(self, db: AsyncSession, hmac_key: str):
        """Initialize signal service.

        Args:
            db: Async database session
            hmac_key: Secret key for HMAC signature verification
        """
        self.db = db
        self.hmac_key = hmac_key.encode()

    async def create_signal(
        self,
        user_id: str,
        signal_create: SignalCreate,
        external_id: str | None = None,
    ) -> SignalOut:
        """Create new signal with deduplication.

        Args:
            user_id: User receiving the signal
            signal_create: Validated signal data
            external_id: External system ID for deduplication

        Returns:
            Created signal

        Raises:
            DuplicateSignalError: If external_id already exists
            APIError: If creation fails
        """
        try:
            # Check for duplicates if external_id provided
            if external_id:
                existing = await self.db.execute(
                    select(Signal).where(Signal.external_id == external_id)
                )
                if existing.scalar():
                    logger.warning(f"Duplicate signal attempt: {external_id}")
                    raise DuplicateSignalError(external_id)

            # Create signal
            signal = Signal(
                user_id=user_id,
                instrument=signal_create.instrument,
                side=0 if signal_create.side == "buy" else 1,
                price=signal_create.price,
                payload=signal_create.payload or {},
                external_id=external_id,
            )

            self.db.add(signal)
            await self.db.commit()
            await self.db.refresh(signal)

            logger.info(
                f"Signal created: {signal.id}",
                extra={
                    "user_id": user_id,
                    "instrument": signal.instrument,
                    "external_id": external_id,
                },
            )

            return SignalOut.model_validate(signal)

        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"Unique constraint violation: {e}")
            raise APIError(
                status_code=409,
                code="DUPLICATE_SIGNAL",
                message="Signal already exists",
            ) from e
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Signal creation failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="SIGNAL_CREATE_ERROR",
                message="Failed to create signal",
            ) from e

    async def get_signal(self, signal_id: str) -> SignalOut:
        """Retrieve signal by ID.

        Args:
            signal_id: Signal ID

        Returns:
            Signal data

        Raises:
            SignalNotFoundError: If signal not found
        """
        try:
            result = await self.db.execute(select(Signal).where(Signal.id == signal_id))
            signal = result.scalar()

            if not signal:
                raise SignalNotFoundError(signal_id)

            return SignalOut.model_validate(signal)

        except SignalNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Signal retrieval failed: {e}")
            raise APIError(
                status_code=500,
                code="SIGNAL_GET_ERROR",
                message="Failed to retrieve signal",
            ) from e

    async def list_signals(
        self,
        user_id: str,
        status: int | None = None,
        instrument: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SignalOut], int]:
        """List signals with filtering and pagination.

        Args:
            user_id: User ID
            status: Filter by status (optional)
            instrument: Filter by instrument (optional)
            page: Page number (1-indexed)
            page_size: Signals per page

        Returns:
            Tuple of (signals, total_count)
        """
        try:
            # Build query
            query = select(Signal).where(Signal.user_id == user_id)

            if status is not None:
                query = query.where(Signal.status == status)
            if instrument:
                query = query.where(Signal.instrument == instrument)

            # Get total count
            count_result = await self.db.execute(
                select(Signal).where(Signal.user_id == user_id)
            )
            total = len(count_result.fetchall())

            # Apply pagination
            offset = (page - 1) * page_size
            query = (
                query.order_by(desc(Signal.created_at)).offset(offset).limit(page_size)
            )

            result = await self.db.execute(query)
            signals = result.scalars().all()

            return (
                [SignalOut.model_validate(s) for s in signals],
                total,
            )

        except Exception as e:
            logger.error(f"Signal listing failed: {e}")
            raise APIError(
                status_code=500,
                code="SIGNAL_LIST_ERROR",
                message="Failed to list signals",
            ) from e

    async def update_signal_status(
        self, signal_id: str, new_status: SignalStatus
    ) -> SignalOut:
        """Update signal status.

        Args:
            signal_id: Signal ID
            new_status: New status

        Returns:
            Updated signal

        Raises:
            SignalNotFoundError: If signal not found
        """
        try:
            result = await self.db.execute(select(Signal).where(Signal.id == signal_id))
            signal = result.scalar()

            if not signal:
                raise SignalNotFoundError(signal_id)

            signal.status = new_status.value
            signal.updated_at = datetime.utcnow()

            await self.db.commit()
            await self.db.refresh(signal)

            logger.info(
                f"Signal status updated: {signal_id} → {new_status.name}",
                extra={"signal_id": signal_id, "status": new_status.name},
            )

            return SignalOut.model_validate(signal)

        except SignalNotFoundError:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Status update failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="SIGNAL_UPDATE_ERROR",
                message="Failed to update signal",
            ) from e

    def verify_hmac_signature(self, payload: str, signature: str) -> bool:
        """Verify HMAC signature of signal payload.

        Args:
            payload: Signal payload (JSON string)
            signature: Hex-encoded HMAC-SHA256 signature

        Returns:
            True if signature valid, False otherwise
        """
        try:
            expected_sig = hmac.new(
                self.hmac_key,
                payload.encode(),
                hashlib.sha256,
            ).hexdigest()

            is_valid = hmac.compare_digest(expected_sig, signature)

            if not is_valid:
                logger.warning(
                    "HMAC verification failed",
                    extra={
                        "expected": expected_sig[:16],
                        "got": signature[:16],
                    },
                )

            return is_valid

        except Exception as e:
            logger.error(f"HMAC verification error: {e}")
            return False
