"""Pytest configuration and shared fixtures."""

import json
import os
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine, pool, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Set test environment variables BEFORE importing app
os.environ["APP_ENV"] = "development"
os.environ["DB_DSN"] = "postgresql+psycopg://user:pass@localhost:5432/test_app"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["HMAC_PRODUCER_ENABLED"] = "false"


@pytest.fixture(autouse=True)
def reset_context():
    """Reset logging context before each test."""
    from backend.app.core.logging import _request_id_context

    _request_id_context.set("unknown")
    yield
    _request_id_context.set("unknown")


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
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session factory
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Create test FastAPI client."""
    from httpx import ASGITransport
    from backend.app.orchestrator.main import app
    from backend.app.core.db import get_db
    
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
        "time": datetime.now(timezone.utc).isoformat(),
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
