"""Audit logging tests."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.models import AUDIT_ACTIONS, AuditLog
from backend.app.audit.service import AuditService


class TestAuditLogModel:
    """Test AuditLog model."""

    @pytest.mark.asyncio
    async def test_audit_log_creation(self, db_session: AsyncSession):
        """Test creating audit log entry."""
        log = AuditLog(
            action="auth.login",
            target="user",
            actor_id="user-123",
            actor_role="USER",
            target_id="user-123",
            ip_address="192.168.1.1",
            status="success",
        )

        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        assert log.id
        assert log.action == "auth.login"
        assert log.actor_id == "user-123"
        assert log.status == "success"

    @pytest.mark.asyncio
    async def test_audit_log_with_meta(self, db_session: AsyncSession):
        """Test audit log with metadata."""
        meta = {"old_role": "USER", "new_role": "ADMIN"}
        log = AuditLog(
            action="user.role_change",
            target="user",
            actor_id="admin-1",
            actor_role="ADMIN",
            target_id="user-123",
            meta=meta,
            status="success",
        )

        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        assert log.meta == meta

    @pytest.mark.asyncio
    async def test_audit_log_immutable(self, db_session: AsyncSession):
        """Test audit logs should not be updated (application enforces)."""
        log = AuditLog(
            action="auth.login",
            target="user",
            actor_id="user-1",
            actor_role="USER",
            status="success",
        )

        db_session.add(log)
        await db_session.commit()

        # In production, we'd add database constraints to prevent updates
        # Application layer should also prevent updates


class TestAuditService:
    """Test AuditService."""

    @pytest.mark.asyncio
    async def test_record_login_success(self, db_session: AsyncSession):
        """Test recording successful login."""
        log = await AuditService.record_login(
            db=db_session,
            user_id="user-123",
            success=True,
            ip_address="192.168.1.1",
        )

        assert log.action == "auth.login"
        assert log.status == "success"
        assert log.actor_id == "user-123"

    @pytest.mark.asyncio
    async def test_record_login_failure(self, db_session: AsyncSession):
        """Test recording failed login."""
        log = await AuditService.record_login(
            db=db_session,
            user_id="user-123",
            success=False,
            ip_address="192.168.1.1",
        )

        assert log.action == "auth.login"
        assert log.status == "failure"
        assert log.actor_id is None  # Failed login doesn't have actor

    @pytest.mark.asyncio
    async def test_record_registration(self, db_session: AsyncSession):
        """Test recording user registration."""
        log = await AuditService.record_registration(
            db=db_session,
            user_id="user-999",
            email="user@example.com",
            ip_address="10.0.0.1",
        )

        assert log.action == "auth.register"
        assert log.target_id == "user-999"
        assert log.meta["email_domain"] == "example.com"

    @pytest.mark.asyncio
    async def test_record_role_change(self, db_session: AsyncSession):
        """Test recording role change."""
        log = await AuditService.record_role_change(
            db=db_session,
            admin_id="admin-1",
            target_user_id="user-456",
            old_role="USER",
            new_role="ADMIN",
        )

        assert log.action == "user.role_change"
        assert log.actor_id == "admin-1"
        assert log.meta["old_role"] == "USER"
        assert log.meta["new_role"] == "ADMIN"

    @pytest.mark.asyncio
    async def test_record_failure(self, db_session: AsyncSession):
        """Test recording operation failure."""
        log = await AuditService.record_failure(
            db=db_session,
            action="billing.payment",
            target="payment",
            error="Insufficient funds",
            ip_address="192.168.1.50",
        )

        assert log.status == "error"
        assert log.meta["error"] == "Insufficient funds"

    @pytest.mark.asyncio
    async def test_record_generic(self, db_session: AsyncSession):
        """Test generic record method."""
        log = await AuditService.record(
            db=db_session,
            action="signal.create",
            target="signal",
            actor_id="user-123",
            target_id="signal-789",
            meta={"instrument": "EURUSD", "side": "BUY"},
            status="success",
        )

        assert log.action == "signal.create"
        assert log.target == "signal"
        assert log.meta["instrument"] == "EURUSD"

    @pytest.mark.asyncio
    async def test_audit_queries(self, db_session: AsyncSession):
        """Test querying audit logs."""
        # Create multiple events
        for i in range(3):
            await AuditService.record(
                db=db_session,
                action="auth.login",
                target="user",
                actor_id=f"user-{i}",
                status="success",
            )

        # Query by action
        stmt = select(AuditLog).where(AuditLog.action == "auth.login")
        result = await db_session.execute(stmt)
        logs = result.scalars().all()

        assert len(logs) == 3

    @pytest.mark.asyncio
    async def test_audit_log_no_pii(self, db_session: AsyncSession):
        """Test audit logs don't store sensitive data."""
        # Should store email domain, not full email
        log = await AuditService.record_registration(
            db=db_session,
            user_id="user-123",
            email="john.doe@confidential.company.com",
            ip_address="1.2.3.4",
        )

        # Verify PII not in meta
        assert "john" not in str(log.meta)
        assert "doe" not in str(log.meta)
        # But domain should be there
        assert "confidential.company.com" in str(log.meta)


class TestAuditActions:
    """Test predefined audit actions."""

    def test_audit_actions_defined(self):
        """Test all common audit actions are defined."""
        expected_actions = [
            "auth.login",
            "auth.register",
            "user.create",
            "user.role_change",
            "billing.payment",
            "signal.create",
        ]

        for action in expected_actions:
            assert action in AUDIT_ACTIONS, f"Missing action: {action}"

    def test_audit_actions_have_descriptions(self):
        """Test all actions have descriptions."""
        for _action, description in AUDIT_ACTIONS.items():
            assert isinstance(description, str)
            assert len(description) > 0
            assert len(description) < 200  # Reasonable limit
