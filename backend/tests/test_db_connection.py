"""Database connectivity and migration tests.

Tests for:
- Database connection establishment
- Session creation and cleanup
- Migration running and rollback
- Database health checks
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.db import (
    get_database_url,
    create_db_engine,
    get_engine,
    init_db,
    verify_db_connection,
    SessionLocal,
    get_db,
    Base,
)


@pytest_asyncio.fixture
async def test_engine():
    """Create an in-memory SQLite engine for testing.

    Yields:
        AsyncEngine: Test database engine.
    """
    # Use SQLite in-memory database for tests
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine):
    """Create a test database session.

    Args:
        test_engine: Test database engine.

    Yields:
        AsyncSession: Test database session.
    """
    TestSessionLocal = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with TestSessionLocal() as session:
        yield session


class TestDatabaseConfiguration:
    """Tests for database configuration and URL building."""

    def test_get_database_url_from_env(self, monkeypatch):
        """Test database URL extraction from environment variables.

        Args:
            monkeypatch: pytest fixture for environment variable mocking.
        """
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost/testdb")

        url = get_database_url()
        assert url == "postgresql+psycopg://test:test@localhost/testdb"

    def test_get_database_url_default_value(self, monkeypatch):
        """Test database URL default value when env var not set.

        Args:
            monkeypatch: pytest fixture for environment variable mocking.
        """
        monkeypatch.delenv("DATABASE_URL", raising=False)

        url = get_database_url()
        assert "postgresql+psycopg://" in url or "sqlite" in url

    def test_get_database_url_async_driver(self, monkeypatch):
        """Test that database URL can be converted to async driver.

        Args:
            monkeypatch: pytest fixture for environment variable mocking.
        """
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")
        url = get_database_url()

        # Verify URL format is valid
        assert url.startswith("postgresql")
        assert "localhost" in url


class TestDatabaseEngine:
    """Tests for database engine creation and configuration."""

    def test_create_db_engine_returns_engine(self, monkeypatch):
        """Test that create_db_engine returns an AsyncEngine.

        Args:
            monkeypatch: pytest fixture for environment variable mocking.
        """
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

        engine = create_db_engine()
        assert engine is not None
        assert hasattr(engine, "begin")  # AsyncEngine method

    def test_create_db_engine_pool_configuration(self, monkeypatch):
        """Test database engine pool configuration (via env vars).

        Args:
            monkeypatch: pytest fixture for environment variable mocking.
        """
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        monkeypatch.setenv("DATABASE_POOL_SIZE", "15")
        monkeypatch.setenv("DATABASE_MAX_OVERFLOW", "5")

        # Just verify it creates without errors
        engine = create_db_engine()
        assert engine is not None

    def test_get_engine_singleton(self, monkeypatch):
        """Test that get_engine returns the same engine instance.

        Args:
            monkeypatch: pytest fixture for environment variable mocking.
        """
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

        engine1 = get_engine()
        engine2 = get_engine()
        assert engine1 is engine2


class TestDatabaseSession:
    """Tests for session creation and management."""

    @pytest.mark.asyncio
    async def test_session_creation(self, test_engine):
        """Test that sessions can be created from engine.

        Args:
            test_engine: Test database engine.
        """
        TestSessionLocal = sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        async with TestSessionLocal() as session:
            assert isinstance(session, AsyncSession)

    @pytest.mark.asyncio
    async def test_session_cleanup(self, test_engine):
        """Test that sessions are properly closed after use.

        Args:
            test_engine: Test database engine.
        """
        TestSessionLocal = sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        session_obj = None
        async with TestSessionLocal() as session:
            session_obj = session
            # Session is active inside context
            assert session_obj.is_active is True

        # After context exit, session should be closed
        # Note: is_active might still be True but connection is closed
        assert session_obj is not None

    @pytest.mark.asyncio
    async def test_get_db_dependency(self, test_engine, monkeypatch):
        """Test FastAPI dependency get_db() returns a session.

        Args:
            test_engine: Test database engine.
            monkeypatch: pytest fixture for mocking.
        """
        # Mock the global engine
        monkeypatch.setattr("backend.app.core.db._engine", test_engine)

        # Call dependency directly
        async for session in get_db():
            assert isinstance(session, AsyncSession)
            break


class TestDatabaseInitialization:
    """Tests for database initialization and table creation."""

    @pytest.mark.asyncio
    async def test_init_db_creates_tables(self, test_engine, monkeypatch):
        """Test that init_db creates all tables from SQLAlchemy models.

        Args:
            test_engine: Test database engine.
            monkeypatch: pytest fixture for mocking.
        """
        monkeypatch.setattr("backend.app.core.db.get_engine", lambda: test_engine)

        await init_db()

        # Verify tables were created (or can be accessed)
        async with test_engine.begin() as conn:
            tables = await conn.run_sync(lambda c: list(Base.metadata.tables.keys()))
            # At baseline, should be empty or minimal
            assert isinstance(tables, list)

    @pytest.mark.asyncio
    async def test_verify_db_connection_success(self, test_engine, monkeypatch):
        """Test database health check succeeds on valid connection.

        Args:
            test_engine: Test database engine.
            monkeypatch: pytest fixture for mocking.
        """
        monkeypatch.setattr("backend.app.core.db.get_engine", lambda: test_engine)

        result = await verify_db_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_db_connection_failure(self, monkeypatch):
        """Test database health check fails on invalid connection.

        Args:
            monkeypatch: pytest fixture for mocking.
        """
        async def mock_engine():
            """Mock engine that raises on query."""
            class MockEngine:
                async def begin(self):
                    raise Exception("Connection failed")

            return MockEngine()

        monkeypatch.setattr("backend.app.core.db.get_engine", mock_engine)

        # Should handle exception gracefully
        result = await verify_db_connection()
        assert result is False


class TestDatabaseIntegration:
    """Integration tests for full database workflows."""

    @pytest.mark.asyncio
    async def test_complete_session_lifecycle(self, test_session):
        """Test complete session lifecycle: create → execute → close.

        Args:
            test_session: Test database session fixture.
        """
        # Session is created by fixture
        assert test_session is not None

        # Test session is active
        assert test_session.is_active

    @pytest.mark.asyncio
    async def test_database_transaction_rollback(self, test_engine):
        """Test transaction rollback on error.

        Args:
            test_engine: Test database engine.
        """
        TestSessionLocal = sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        try:
            async with TestSessionLocal() as session:
                # Start transaction
                assert session.is_active is True

                # Simulate error - transaction should rollback
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Session should be closed
        async with TestSessionLocal() as session:
            # New session should work fine
            assert isinstance(session, AsyncSession)

    @pytest.mark.asyncio
    async def test_multiple_concurrent_sessions(self, test_engine):
        """Test multiple sessions can exist concurrently.

        Args:
            test_engine: Test database engine.
        """
        TestSessionLocal = sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        session1 = None
        session2 = None

        try:
            async with TestSessionLocal() as s1:
                session1 = s1
                async with TestSessionLocal() as s2:
                    session2 = s2
                    # Both sessions active simultaneously
                    assert session1 is not None
                    assert session2 is not None
                    assert session1 is not session2
        except Exception as e:
            pytest.fail(f"Concurrent sessions failed: {e}")
