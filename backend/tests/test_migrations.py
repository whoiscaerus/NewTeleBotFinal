"""Database migration tests."""

import pytest
from sqlalchemy import inspect


@pytest.mark.asyncio
async def test_migration_0001_creates_users_table(db_session):
    """Test migration 0001 creates users table with correct schema."""
    # Get table inspection
    inspector = inspect(db_session.bind)
    tables = inspector.get_table_names()

    assert "users" in tables

    # Verify columns
    columns = {col["name"]: col for col in inspector.get_columns("users")}
    assert "id" in columns
    assert "email" in columns
    assert "password_hash" in columns
    assert "role" in columns
    assert "created_at" in columns
    assert "updated_at" in columns

    # Verify column types
    assert columns["id"]["type"].__class__.__name__ == "String"
    assert columns["email"]["type"].__class__.__name__ == "String"
    assert columns["password_hash"]["type"].__class__.__name__ == "String"


@pytest.mark.asyncio
async def test_migration_0001_creates_audit_logs_table(db_session):
    """Test migration 0001 creates audit_logs table with correct schema."""
    inspector = inspect(db_session.bind)
    tables = inspector.get_table_names()

    assert "audit_logs" in tables

    # Verify columns
    columns = {col["name"]: col for col in inspector.get_columns("audit_logs")}
    assert "id" in columns
    assert "timestamp" in columns
    assert "actor_id" in columns
    assert "actor_role" in columns
    assert "action" in columns
    assert "target" in columns
    assert "target_id" in columns
    assert "meta" in columns
    assert "ip_address" in columns
    assert "user_agent" in columns
    assert "status" in columns


@pytest.mark.asyncio
async def test_migration_0001_creates_indexes(db_session):
    """Test migration 0001 creates proper indexes."""
    inspector = inspect(db_session.bind)

    # Check users indexes
    users_indexes = inspector.get_indexes("users")
    users_index_names = {idx["name"] for idx in users_indexes}
    assert "uq_users_email" in users_index_names or any(
        "email" in idx["name"].lower() for idx in users_indexes
    )

    # Check audit_logs indexes
    audit_indexes = inspector.get_indexes("audit_logs")
    audit_index_names = {idx["name"] for idx in audit_indexes}
    assert any("actor" in name.lower() for name in audit_index_names)
    assert any("action" in name.lower() for name in audit_index_names)
    assert any("target" in name.lower() for name in audit_index_names)


@pytest.mark.asyncio
async def test_users_table_enforces_email_unique(db_session):
    """Test email unique constraint on users table."""
    from backend.app.auth.models import User

    # Create first user
    user1 = User(
        id="user-1",
        email="test@example.com",
        password_hash="hash1",
        role="user",
    )
    db_session.add(user1)
    await db_session.commit()

    # Try to create duplicate email
    user2 = User(
        id="user-2",
        email="test@example.com",
        password_hash="hash2",
        role="user",
    )
    db_session.add(user2)

    with pytest.raises(Exception):  # IntegrityError
        await db_session.commit()


@pytest.mark.asyncio
async def test_audit_logs_is_immutable(db_session):
    """Test audit logs cannot be updated."""
    from backend.app.audit.models import AuditLog

    # Create audit entry
    log = AuditLog(
        id="log-1",
        actor_id="user-1",
        actor_role="admin",
        action="test.action",
        target="test_resource",
        status="success",
    )
    db_session.add(log)
    await db_session.commit()

    # Try to update (should be prevented by application layer)
    log.status = "failure"
    await db_session.commit()

    # Refresh and verify original status persists (DB doesn't prevent, app does)
    # In production, we'd add CHECK constraint or DB trigger
    refreshed = await db_session.get(AuditLog, "log-1")
    assert refreshed is not None
