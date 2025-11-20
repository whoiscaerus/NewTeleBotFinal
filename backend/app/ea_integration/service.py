"""
Service for EA (Expert Advisor) device integration.

Handles:
1. Device authentication via HMAC signatures
2. Signal polling from EA devices
3. Execution acknowledgment from EA
4. Nonce/timestamp verification for request freshness
5. Signal delivery to connected devices
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.signals.models import Signal


class EAPollService:
    """Service for EA device polling and signal acknowledgment."""

    NONCE_WINDOW_SECONDS = 300  # 5 minute validity
    TIMESTAMP_SKEW_TOLERANCE = 5  # 5 second clock skew tolerance

    @staticmethod
    async def verify_device_signature(
        device_id: str,
        request_data: str,
        signature: str,
        db: AsyncSession,
    ) -> bool:
        """
        Verify HMAC signature for device request.

        Args:
            device_id: Device identifier
            request_data: Request data to verify
            signature: HMAC signature from device
            db: Database session

        Returns:
            bool: True if signature valid, False otherwise

        Raises:
            ValueError: If device not found or revoked
        """
        # Stub implementation
        if not device_id or not request_data or not signature:
            raise ValueError("Missing required signature data")

        # In real implementation: fetch device secret, compute HMAC, compare
        return True

    @staticmethod
    async def verify_request_freshness(
        timestamp: int,
        nonce: str,
        db: AsyncSession,
    ) -> bool:
        """
        Verify request timestamp is fresh and nonce not replayed.

        Args:
            timestamp: Request timestamp (unix seconds)
            nonce: Unique request nonce
            db: Database session

        Returns:
            bool: True if timestamp fresh and nonce valid

        Raises:
            ValueError: If timestamp stale or nonce replayed
        """
        # Stub implementation
        now = datetime.utcnow().timestamp()

        # Check timestamp freshness
        age = now - timestamp
        if abs(age) > EAPollService.NONCE_WINDOW_SECONDS:
            raise ValueError(f"Request timestamp too old: {age}s")

        # Check nonce hasn't been used
        # In real implementation: query cache/db for nonce
        return True

    @staticmethod
    async def get_approved_signals_for_poll(
        device_id: str,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """
        Get all approved signals for device polling.

        Returns only signals with status "approved", ready for execution.

        Args:
            device_id: Device identifier
            db: Database session

        Returns:
            list: Approved signal details for execution

        Example:
            [
                {
                    "signal_id": "sig-001",
                    "instrument": "EURUSD",
                    "side": "buy",
                    "entry_price": 1.0850,
                    "stop_loss": 1.0800,
                    "take_profit": 1.0900,
                    "volume": 1.0
                },
                ...
            ]
        """
        # Stub implementation
        stmt = select(Signal).where(Signal.status == 1)  # 1 = approved
        result = await db.execute(stmt)
        signals = result.scalars().all()

        return [
            {
                "signal_id": s.id,
                "instrument": s.instrument,
                "side": "buy" if s.side == 0 else "sell",
                "entry_price": float(s.price),
            }
            for s in signals
        ]

    @staticmethod
    async def acknowledge_signal_execution(
        signal_id: str,
        order_id: str | None = None,
        execution_status: str = "executed",
        rejection_reason: str | None = None,
        db: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """
        Process acknowledgment from EA device for signal execution.

        Args:
            signal_id: Signal identifier being acknowledged
            order_id: Order ID from EA (if executed)
            execution_status: Status of execution ("executed", "rejected", "pending")
            rejection_reason: Reason if rejected (e.g., "insufficient margin")
            db: Database session

        Returns:
            dict: Acknowledgment result with status and timestamp

        Raises:
            ValueError: If signal not found or invalid status
        """
        # Stub implementation
        if not signal_id:
            raise ValueError("signal_id required")

        if execution_status not in ("executed", "rejected", "pending"):
            raise ValueError(f"Invalid execution_status: {execution_status}")

        return {
            "acknowledged": True,
            "signal_id": signal_id,
            "order_id": order_id,
            "status": execution_status,
            "timestamp": datetime.utcnow().isoformat(),
        }

    @staticmethod
    async def filter_signals_by_device_config(
        signals: list[dict],
        device_config: dict,
    ) -> list[dict]:
        """
        Filter signals based on device configuration.

        Removes signals that don't match device allowed instruments, max volume, etc.

        Args:
            signals: List of signals to filter
            device_config: Device configuration with filters

        Returns:
            list: Filtered signals matching device config
        """
        # Stub implementation
        return signals

    @staticmethod
    async def rate_limit_check(
        device_id: str,
        db: AsyncSession,
        max_requests_per_minute: int = 60,
    ) -> bool:
        """
        Check if device is within rate limits.

        Args:
            device_id: Device identifier
            db: Database session
            max_requests_per_minute: Maximum allowed requests

        Returns:
            bool: True if within limit, False if exceeded

        Raises:
            ValueError: If rate limit exceeded
        """
        # Stub implementation
        return True
