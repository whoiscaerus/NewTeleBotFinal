"""Signals service - business logic for signal handling."""

import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import and_, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import APIException, ConflictError, NotFoundError
from backend.app.observability import get_metrics
from backend.app.signals.models import Signal, SignalStatus
from backend.app.signals.schema import SignalCreate, SignalOut

logger = logging.getLogger(__name__)
_metrics = None  # Lazy load on first use


def _get_metrics():
    """Get metrics instance (lazy loaded)."""
    global _metrics
    if _metrics is None:
        _metrics = get_metrics()
    return _metrics


class DuplicateSignalError(ConflictError):
    """Signal already exists (deduplication check)."""

    def __init__(self, external_id: str):
        super().__init__(detail=f"Signal {external_id} already exists")


class SignalNotFoundError(NotFoundError):
    """Signal not found."""

    def __init__(self, signal_id: str):
        super().__init__(resource="Signal", resource_id=signal_id)


class SignalService:
    """Service for signal ingestion, validation, and management.

    Responsibilities:
    - Validate incoming signal payloads
    - Deduplicate signals by external_id
    - Store signals in database
    - Query signals with filtering
    - Update signal status
    """

    def __init__(
        self, db: AsyncSession, hmac_key: str, dedup_window_seconds: int = 300
    ):
        """Initialize signal service.

        Args:
            db: Async database session
            hmac_key: Secret key for HMAC signature verification
            dedup_window_seconds: Deduplication window in seconds (default: 5 minutes)
        """
        self.db = db
        self.hmac_key = hmac_key.encode()
        self.dedup_window_seconds = dedup_window_seconds

    async def create_signal(
        self,
        user_id: str,
        signal_create: SignalCreate,
        external_id: str | None = None,
    ) -> SignalOut:
        """Create new signal with deduplication and time-window check.

        Args:
            user_id: User receiving the signal
            signal_create: Validated signal data
            external_id: External system ID for deduplication

        Returns:
            Created signal

        Raises:
            DuplicateSignalError: If external_id already exists or duplicate within window
            APIError: If creation fails
        """
        start_time = time.time()
        try:
            # Check for duplicates if external_id provided
            if external_id:
                existing = await self.db.execute(
                    select(Signal).where(Signal.external_id == external_id)
                )
                if existing.scalar():
                    logger.warning(f"Duplicate signal attempt: {external_id}")
                    raise DuplicateSignalError(external_id)

            # Check for duplicate (instrument, time, version) within dedup_window
            cutoff_time = datetime.utcnow() - timedelta(
                seconds=self.dedup_window_seconds
            )
            window_query = select(Signal).where(
                and_(
                    Signal.instrument == signal_create.instrument,
                    Signal.created_at >= cutoff_time,
                    Signal.version == signal_create.version,
                )
            )
            existing_in_window = await self.db.execute(window_query)
            if existing_in_window.scalar():
                logger.warning(
                    f"Duplicate signal in dedup window: "
                    f"{signal_create.instrument} v{signal_create.version}"
                )
                raise DuplicateSignalError(external_id or "unknown")

            # Create signal
            signal = Signal(
                user_id=user_id,
                instrument=signal_create.instrument,
                side=0 if signal_create.side == "buy" else 1,
                price=signal_create.price,
                payload=signal_create.payload or {},
                external_id=external_id,
                version=signal_create.version,
            )

            self.db.add(signal)
            await self.db.commit()
            await self.db.refresh(signal)

            # Emit telemetry
            try:
                metrics = _get_metrics()
                side_label = "buy" if signal_create.side == "buy" else "sell"
                metrics.signals_ingested_total.labels(
                    instrument=signal_create.instrument, side=side_label
                ).inc()
                elapsed = time.time() - start_time
                metrics.signals_create_seconds.observe(elapsed)
            except Exception:
                # metrics best-effort
                pass

            logger.info(
                f"Signal created: {signal.id}",
                extra={
                    "user_id": user_id,
                    "instrument": signal.instrument,
                    "external_id": external_id,
                },
            )

            return SignalOut.model_validate(signal)

        except (DuplicateSignalError, ConflictError) as e:
            await self.db.rollback()
            logger.error(f"Signal duplication check failed: {e}")
            raise
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"Unique constraint violation: {e}")
            raise ConflictError(detail="Signal already exists") from e
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Signal creation failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                error_type="server_error",
                title="Signal Creation Error",
                detail="Failed to create signal",
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
            raise APIException(
                status_code=500,
                error_type="server_error",
                title="Signal Retrieval Error",
                detail="Failed to retrieve signal",
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
            raise APIException(
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
            raise APIException(
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
