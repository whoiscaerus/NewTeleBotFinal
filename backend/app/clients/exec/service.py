"""Execution store service."""

import logging
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.exec.models import ExecutionRecord, ExecutionType
from backend.app.clients.exec.schema import ExecutionRecordOut
from backend.app.core.errors import APIError

logger = logging.getLogger(__name__)


class ExecutionService:
    """Service for managing execution records.

    Responsibilities:
    - Record device ACKs
    - Record device fills
    - Record device errors
    - Provide execution history
    """

    def __init__(self, db: AsyncSession):
        """Initialize service.

        Args:
            db: Database session
        """
        self.db = db

    async def record_ack(
        self,
        device_id: str,
        signal_id: str,
    ) -> ExecutionRecordOut:
        """Record device ACK of signal.

        Args:
            device_id: Device ID
            signal_id: Signal ID

        Returns:
            Execution record

        Raises:
            APIError: If recording fails
        """
        try:
            record = ExecutionRecord(
                device_id=device_id,
                signal_id=signal_id,
                execution_type=ExecutionType.ACK.value,
                status_code=200,
            )

            self.db.add(record)
            await self.db.commit()
            await self.db.refresh(record)

            logger.info(
                f"Execution ACK recorded: {device_id} → {signal_id}",
                extra={"device_id": device_id, "signal_id": signal_id},
            )

            return ExecutionRecordOut.model_validate(record)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"ACK recording failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="ACK_ERROR",
                message="Failed to record ACK",
            ) from e

    async def record_fill(
        self,
        device_id: str,
        signal_id: str,
        trade_id: str,
        fill_price: float,
        fill_size: float,
    ) -> ExecutionRecordOut:
        """Record device fill report.

        Args:
            device_id: Device ID
            signal_id: Signal ID
            trade_id: Trade ID
            fill_price: Fill price
            fill_size: Fill size

        Returns:
            Execution record

        Raises:
            APIError: If recording fails
        """
        try:
            record = ExecutionRecord(
                device_id=device_id,
                signal_id=signal_id,
                trade_id=trade_id,
                execution_type=ExecutionType.FILL.value,
                status_code=200,
                fill_price=fill_price,
                fill_size=fill_size,
            )

            self.db.add(record)
            await self.db.commit()
            await self.db.refresh(record)

            logger.info(
                f"Execution FILL recorded: {device_id} → {signal_id} @ {fill_price}",
                extra={
                    "device_id": device_id,
                    "signal_id": signal_id,
                    "fill_price": fill_price,
                },
            )

            return ExecutionRecordOut.model_validate(record)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"FILL recording failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="FILL_ERROR",
                message="Failed to record fill",
            ) from e

    async def record_error(
        self,
        device_id: str,
        signal_id: str,
        status_code: int | None = None,
        error_message: str = "",
    ) -> ExecutionRecordOut:
        """Record device execution error.

        Args:
            device_id: Device ID
            signal_id: Signal ID
            status_code: HTTP status code from device
            error_message: Error message

        Returns:
            Execution record

        Raises:
            APIError: If recording fails
        """
        try:
            record = ExecutionRecord(
                device_id=device_id,
                signal_id=signal_id,
                execution_type=ExecutionType.ERROR.value,
                status_code=status_code or 500,
                error_message=error_message,
            )

            self.db.add(record)
            await self.db.commit()
            await self.db.refresh(record)

            logger.warning(
                f"Execution ERROR recorded: {device_id} → {signal_id}: {error_message}",
                extra={
                    "device_id": device_id,
                    "signal_id": signal_id,
                    "error": error_message,
                },
            )

            return ExecutionRecordOut.model_validate(record)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"ERROR recording failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="ERROR_RECORD_FAILED",
                message="Failed to record error",
            ) from e

    async def get_execution_status(
        self,
        signal_id: str,
    ) -> list[ExecutionRecordOut]:
        """Get execution history for signal.

        Args:
            signal_id: Signal ID

        Returns:
            List of execution records
        """
        try:
            result = await self.db.execute(
                select(ExecutionRecord)
                .where(ExecutionRecord.signal_id == signal_id)
                .order_by(ExecutionRecord.created_at.desc())
            )
            records = cast(list[ExecutionRecord], result.scalars().all())

            return [ExecutionRecordOut.model_validate(r) for r in records]

        except Exception as e:
            logger.error(f"Status retrieval failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="STATUS_ERROR",
                message="Failed to get execution status",
            ) from e
