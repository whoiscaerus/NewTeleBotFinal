"""Pytest configuration and shared fixtures."""

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Set test environment variables BEFORE importing app
os.environ["APP_ENV"] = "development"
os.environ["DB_DSN"] = "postgresql+psycopg://user:pass@localhost:5432/test_app"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["HMAC_PRODUCER_ENABLED"] = "false"

from backend.app.audit.models import AuditLog  # noqa: F401, E402

# Import all models so they're registered with Base.metadata
from backend.app.auth.models import User  # noqa: F401, E402


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """Run alembic migrations once before test session starts."""
    try:
        from alembic import command
        from alembic.config import Config

        # Get path to alembic.ini (one level up from backend/tests)
        alembic_ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")

        if os.path.exists(alembic_ini_path):
            alembic_cfg = Config(alembic_ini_path)
            # Run migrations
            command.upgrade(alembic_cfg, "head")
    except Exception as e:
        # Log but don't fail - migrations may not be needed for in-memory SQLite tests
        import logging

        logging.warning(f"Could not run migrations: {e}")
    yield


@pytest.fixture(autouse=True)
def reset_context():
    """Reset logging context before each test."""
    from backend.app.core.logging import _request_id_var

    token = _request_id_var.set("unknown")
    yield
    _request_id_var.reset(token)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session with fresh schema each test."""
    from backend.app.core.db import Base

    # Create fresh engine for this test
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=pool.StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Create all tables from Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    # Cleanup - drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Create test FastAPI client."""
    from httpx import ASGITransport

    from backend.app.core.db import get_db
    from backend.app.orchestrator.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def valid_signal_data() -> dict:
    """Create valid signal data for testing."""
    return {
        "instrument": "XAUUSD",
        "side": 0,
        "time": datetime.now(UTC).isoformat(),
        "payload": {"rsi": 75, "macd": -0.5},
    }


@pytest.fixture
def producer_id() -> str:
    """Return test producer ID."""
    return "test-producer-001"


@pytest.fixture
def hmac_secret() -> str:
    """Return test HMAC secret."""
    return "test-hmac-secret-key-12345678"
