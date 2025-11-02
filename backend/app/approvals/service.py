"""Approval service."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.models import Approval
from backend.app.core.errors import APIError
from backend.app.risk.service import RiskService
from backend.app.signals.models import Signal, SignalStatus

logger = logging.getLogger(__name__)


class ApprovalService:
    """Service for signal approvals."""

    def __init__(self, db: AsyncSession):
        """Initialize service."""
        self.db = db

    async def approve_signal(
        self,
        signal_id: str,
        user_id: str,
        decision: str,
        reason: str | None = None,
        ip: str | None = None,
        ua: str | None = None,
        consent_version: int = 1,
    ) -> Approval:
        """Create approval record.

        Args:
            signal_id: Signal ID
            user_id: User making decision
            decision: "approved" or "rejected"
            reason: Optional rejection reason

        Returns:
            Created approval
        """
        try:
            # Get signal
            result = await self.db.execute(select(Signal).where(Signal.id == signal_id))
            signal = result.scalar()
            if not signal:
                raise ValueError(f"Signal {signal_id} not found")

            # Create approval
            approval = Approval(
                signal_id=signal_id,
                user_id=user_id,
                decision=1 if decision == "approved" else 0,
                reason=reason,
                ip=ip,
                ua=ua,
                consent_version=consent_version,
            )

            # Update signal status
            if decision == "approved":
                signal.status = SignalStatus.APPROVED.value
            else:
                signal.status = SignalStatus.REJECTED.value

            self.db.add(approval)
            self.db.add(signal)
            await self.db.commit()
            await self.db.refresh(approval)

            # ===== NEW: Update exposure snapshot (PR-048 Integration) =====
            # After approval, recalculate exposure for risk monitoring
            if decision == "approved":
                try:
                    await RiskService.calculate_current_exposure(user_id, self.db)
                    logger.debug(
                        "Exposure snapshot updated after approval",
                        extra={"signal_id": signal_id, "user_id": user_id},
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to update exposure snapshot: {e}",
                        extra={"signal_id": signal_id, "user_id": user_id},
                    )
            # ===== END: Update exposure snapshot =====

            logger.info(
                f"Signal {decision}: {signal_id}",
                extra={
                    "signal_id": signal_id,
                    "user_id": user_id,
                    "decision": decision,
                },
            )

            return approval

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Approval creation failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                error_type="server_error",
                title="Approval Error",
                detail="Failed to create approval",
            ) from e
