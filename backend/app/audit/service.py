"""Audit event recording service."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.models import AUDIT_ACTIONS, AuditLog
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class AuditService:
    """Service for recording audit events.

    Events are immutable - only append operations allowed.
    """

    @staticmethod
    async def record(
        db: AsyncSession,
        action: str,
        target: str,
        actor_id: str | None = None,
        actor_role: str = "USER",
        target_id: str | None = None,
        meta: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        status: str = "success",
    ) -> AuditLog:
        """Record an audit event.

        Args:
            db: Database session
            action: Action name (e.g., 'auth.login')
            target: Resource type (e.g., 'user')
            actor_id: User ID performing action (None for system)
            actor_role: User role (OWNER, ADMIN, USER, SYSTEM)
            target_id: ID of affected resource
            meta: Structured metadata (no PII/secrets)
            ip_address: Client IP address
            user_agent: HTTP User-Agent header
            status: Result status ('success', 'failure', 'error')

        Returns:
            AuditLog: Recorded audit event

        Raises:
            ValueError: If action or target not recognized

        Example:
            await AuditService.record(
                db=db,
                action="auth.login",
                target="user",
                actor_id="user-123",
                actor_role="USER",
                ip_address="192.168.1.1",
                status="success"
            )
        """
        # Validate action
        if action not in AUDIT_ACTIONS:
            logger.warning(f"Unknown audit action: {action}", extra={"action": action})

        # Create event
        event = AuditLog(
            action=action,
            target=target,
            actor_id=actor_id,
            actor_role=actor_role,
            target_id=target_id,
            meta=meta or {},
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
        )

        # Persist
        db.add(event)
        await db.flush()  # Get ID without committing
        await db.refresh(event)

        # Log
        logger.info(
            f"Audit: {action}",
            extra={
                "audit_id": event.id,
                "action": action,
                "target": target,
                "actor_id": actor_id,
                "status": status,
            },
        )

        return event

    @staticmethod
    async def record_login(
        db: AsyncSession,
        user_id: str,
        success: bool,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        """Record login attempt.

        Args:
            db: Database session
            user_id: User ID
            success: Whether login succeeded
            ip_address: Client IP
            user_agent: HTTP User-Agent

        Returns:
            AuditLog: Recorded event
        """
        return await AuditService.record(
            db=db,
            action="auth.login",
            target="user",
            actor_id=user_id if success else None,
            actor_role="USER",
            target_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            status="success" if success else "failure",
        )

    @staticmethod
    async def record_register(
        db: AsyncSession,
        user_id: str,
        email: str,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Record user registration.

        Args:
            db: Database session
            user_id: New user ID
            email: User email (non-PII field for audit)
            ip_address: Client IP

        Returns:
            AuditLog: Recorded event
        """
        return await AuditService.record(
            db=db,
            action="auth.register",
            target="user",
            actor_id=user_id,
            actor_role="USER",
            target_id=user_id,
            meta={"email_domain": email.split("@")[1] if "@" in email else "unknown"},
            ip_address=ip_address,
            status="success",
        )

    @staticmethod
    async def record_role_change(
        db: AsyncSession,
        admin_id: str,
        target_user_id: str,
        old_role: str,
        new_role: str,
    ) -> AuditLog:
        """Record user role change.

        Args:
            db: Database session
            admin_id: Admin user ID making change
            target_user_id: User whose role changed
            old_role: Previous role
            new_role: New role

        Returns:
            AuditLog: Recorded event
        """
        return await AuditService.record(
            db=db,
            action="user.role_change",
            target="user",
            actor_id=admin_id,
            actor_role="ADMIN",
            target_id=target_user_id,
            meta={"old_role": old_role, "new_role": new_role},
            status="success",
        )

    @staticmethod
    async def record_error(
        db: AsyncSession,
        action: str,
        target: str,
        error: str,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Record failed operation.

        Args:
            db: Database session
            action: Action name
            target: Resource type
            error: Error message
            ip_address: Client IP

        Returns:
            AuditLog: Recorded event
        """
        return await AuditService.record(
            db=db,
            action=action,
            target=target,
            meta={"error": error},
            ip_address=ip_address,
            status="error",
        )
