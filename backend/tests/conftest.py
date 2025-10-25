"""Pytest configuration and shared fixtures."""

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
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
from backend.app.trading.store.models import (  # noqa: F401, E402
    EquityPoint,
    Position,
    Trade,
    ValidationLog,
)


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """Skip migrations for in-memory SQLite tests - tables created directly."""
    # For in-memory SQLite, we use Base.metadata.create_all() instead of migrations
    # This is faster and cleaner for unit/integration tests
    pass


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
        connect_args={"check_same_thread": False},
    )

    # Drop any existing tables first (in case metadata is cached)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c))

    # Create all tables from Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c))

    # Create session factory
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    # Cleanup: drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c))
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_session: AsyncSession) -> AsyncSession:
    """Alias for db_session for backward compatibility."""
    return db_session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, monkeypatch):
    """Create test FastAPI client with disabled rate limiting."""
    from httpx import ASGITransport

    from backend.app.core.db import get_db
    from backend.app.orchestrator.main import app

    async def override_get_db():
        yield db_session

    # Mock the rate limiter to always allow requests in tests
    class NoOpRateLimiter:
        """Rate limiter that allows all requests in tests."""

        def __init__(self):
            """Initialize with no Redis client (signals Redis unavailable)."""
            self._initialized = False
            self.redis_client = None

        async def is_allowed(self, key: str, **kwargs) -> bool:
            """Always allow requests in tests."""
            return True

        async def get_remaining(self, key: str, max_tokens: int, **kwargs) -> int:
            """Return max tokens as always available in tests."""
            return max_tokens

    async def mock_get_rate_limiter():
        """Return no-op rate limiter for tests."""
        return NoOpRateLimiter()

    app.dependency_overrides[get_db] = override_get_db

    # Monkeypatch get_rate_limiter to return our no-op version
    monkeypatch.setattr(
        "backend.app.core.decorators.get_rate_limiter", mock_get_rate_limiter
    )

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


@pytest.fixture
def mock_mt5_client():
    """Create mock MT5 client for testing."""
    from unittest.mock import AsyncMock

    mock = AsyncMock()
    mock.get_account.return_value = {
        "equity": 10000.0,
        "balance": 10000.0,
        "margin": 5000.0,
        "free_margin": 5000.0,
    }
    mock.get_open_positions.return_value = []
    mock.place_order.return_value = {"order_id": "test_order_123", "status": "placed"}
    return mock


@pytest.fixture
def mock_approvals_service():
    """Create mock approvals service for testing."""
    from unittest.mock import AsyncMock

    mock = AsyncMock()
    mock.get_pending.return_value = []
    return mock


@pytest.fixture
def mock_order_service():
    """Create mock order service for testing."""
    from unittest.mock import AsyncMock

    mock = AsyncMock()
    mock.get_open_positions.return_value = []
    mock.close_all_positions.return_value = {"closed": 0}
    mock.place_order.return_value = {"order_id": "test_order_123"}
    return mock


@pytest.fixture
def mock_alert_service():
    """Create mock alert service for testing."""
    from unittest.mock import AsyncMock

    mock = AsyncMock()
    mock.send_owner_alert.return_value = True
    return mock


@pytest_asyncio.fixture
async def trading_loop(
    mock_mt5_client, mock_approvals_service, mock_order_service, mock_alert_service
):
    """Create TradingLoop with mocked dependencies."""
    from backend.app.trading.runtime.loop import TradingLoop

    loop = TradingLoop(
        mt5_client=mock_mt5_client,
        approvals_service=mock_approvals_service,
        order_service=mock_order_service,
        alert_service=mock_alert_service,
        loop_id="test_loop_123",
    )
    return loop


@pytest.fixture
def drawdown_guard():
    """Create DrawdownGuard with mocked dependencies."""
    from backend.app.trading.runtime.drawdown import DrawdownGuard

    guard = DrawdownGuard(
        max_drawdown_percent=20.0,
    )
    return guard
