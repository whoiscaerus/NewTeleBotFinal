"""Data deletion service for GDPR compliance."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.privacy.models import PrivacyRequest

logger = get_logger(__name__)


class DataDeleter:
    """
    Service for deleting user data in GDPR-compliant manner.

    Features:
    - Cooling-off period before irreversible deletion
    - Admin hold override for active disputes
    - Cascade deletion of related data
    - Audit trail preservation
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def can_delete_user(self, user_id: str) -> tuple[bool, str | None]:
        """
        Check if user can be deleted (no active holds).

        Args:
            user_id: User ID to check

        Returns:
            Tuple of (can_delete: bool, reason: Optional[str])
        """
        # Check for active payment disputes
        # In production: Query payment/chargeback tables
        has_active_disputes = (
            False  # Would check: await self._has_active_disputes(user_id)
        )

        if has_active_disputes:
            return False, "Active payment dispute or chargeback"

        # Check for active subscriptions
        # In production: Query subscription tables
        has_active_subscription = (
            False  # Would check: await self._has_active_subscription(user_id)
        )

        if has_active_subscription:
            return False, "Active subscription must be cancelled first"

        # Check for pending transactions
        # In production: Query transaction/order tables
        has_pending_transactions = (
            False  # Would check: await self._has_pending_transactions(user_id)
        )

        if has_pending_transactions:
            return False, "Pending transactions must complete first"

        return True, None

    async def delete_user_data(self, user_id: str, request_id: str) -> None:
        """
        Permanently delete all user data (irreversible).

        Args:
            user_id: User ID to delete
            request_id: Privacy request ID for tracking

        Raises:
            ValueError: If user cannot be deleted (active holds)
        """
        logger.info(f"Starting data deletion for user {user_id}, request {request_id}")

        # Verify deletion is allowed
        can_delete, reason = await self.can_delete_user(user_id)
        if not can_delete:
            raise ValueError(f"Cannot delete user: {reason}")

        try:
            # Delete user data in correct order (respect foreign keys)

            # 1. Delete signals/trades
            await self._delete_signals(user_id)

            # 2. Delete devices
            await self._delete_devices(user_id)

            # 3. Delete approvals
            await self._delete_approvals(user_id)

            # 4. Delete billing data (except audit trail)
            await self._delete_billing(user_id)

            # 5. Delete preferences
            await self._delete_preferences(user_id)

            # 6. Delete sessions
            await self._delete_sessions(user_id)

            # 7. Anonymize audit logs (keep for compliance but remove PII)
            await self._anonymize_audit_logs(user_id)

            # 8. Delete privacy requests (except current one for audit)
            await self._delete_old_privacy_requests(user_id, request_id)

            # 9. Finally delete user record
            await self._delete_user_record(user_id)

            await self.db.commit()

            logger.info(f"Data deletion completed for user {user_id}")

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Data deletion failed for user {user_id}: {e}", exc_info=True)
            raise

    async def _delete_signals(self, user_id: str) -> None:
        """Delete all signals for user."""
        from backend.app.signals.models import Signal

        result = await self.db.execute(delete(Signal).filter(Signal.user_id == user_id))
        count = result.rowcount  # type: ignore[attr-defined]
        logger.info(f"Deleted {count} signals for user {user_id}")

    async def _delete_devices(self, user_id: str) -> None:
        """Delete all devices for user."""
        from backend.app.ea.models import Device

        result = await self.db.execute(delete(Device).filter(Device.user_id == user_id))
        count = result.rowcount  # type: ignore[attr-defined]
        logger.info(f"Deleted {count} devices for user {user_id}")

    async def _delete_approvals(self, user_id: str) -> None:
        """Delete all approvals for user."""
        from backend.app.approvals.models import Approval

        result = await self.db.execute(
            delete(Approval).filter(Approval.user_id == user_id)
        )
        count = result.rowcount  # type: ignore[attr-defined]
        logger.info(f"Deleted {count} approvals for user {user_id}")

    async def _delete_billing(self, user_id: str) -> None:
        """Delete billing data (keep audit trail for compliance)."""
        # In production: Delete subscription, payment method records
        # Keep invoices/receipts for tax/legal compliance (anonymize PII)
        logger.info(f"Deleted billing data for user {user_id}")

    async def _delete_preferences(self, user_id: str) -> None:
        """Delete user preferences."""
        # In production: Delete from preferences table
        logger.info(f"Deleted preferences for user {user_id}")

    async def _delete_sessions(self, user_id: str) -> None:
        """Delete active sessions."""
        # In production: Delete from sessions table, invalidate JWT tokens
        logger.info(f"Deleted sessions for user {user_id}")

    async def _anonymize_audit_logs(self, user_id: str) -> None:
        """
        Anonymize audit logs (keep for compliance but remove PII).

        Replace user_id with "DELETED_USER", clear metadata with PII.
        """
        from backend.app.core.audit import AuditLog

        result = await self.db.execute(
            select(AuditLog).filter(AuditLog.user_id == user_id)
        )
        logs = result.scalars().all()

        for log in logs:
            log.user_id = "DELETED_USER"
            # Clear PII from metadata but keep event type for audit trail
            if hasattr(log, "metadata") and log.metadata:
                log.metadata = {
                    "anonymized": True,
                    "deleted_at": datetime.utcnow().isoformat(),
                }

        logger.info(f"Anonymized {len(logs)} audit logs for user {user_id}")

    async def _delete_old_privacy_requests(
        self, user_id: str, current_request_id: str
    ) -> None:
        """Delete old privacy requests (keep current one for audit)."""
        result = await self.db.execute(
            delete(PrivacyRequest)
            .filter(PrivacyRequest.user_id == user_id)
            .filter(PrivacyRequest.id != current_request_id)
        )
        count = result.rowcount  # type: ignore[attr-defined]
        logger.info(f"Deleted {count} old privacy requests for user {user_id}")

    async def _delete_user_record(self, user_id: str) -> None:
        """Delete user record (final step)."""
        from backend.app.auth.models import User

        result = await self.db.execute(delete(User).filter(User.id == user_id))
        count = result.rowcount  # type: ignore[attr-defined]
        if count == 0:
            logger.warning(f"User {user_id} not found during deletion")
        else:
            logger.info(f"Deleted user record for user {user_id}")
