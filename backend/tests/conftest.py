"""Pytest configuration and shared fixtures."""

import os
import sys
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import MagicMock

# Mock MetaTrader5 BEFORE any imports that might use it
# MetaTrader5 is Windows-only and not available on Linux/GitHub Actions
# This allows tests to run in CI/CD environments without errors
if "MetaTrader5" not in sys.modules:
    mock_mt5 = MagicMock()
    mock_mt5.VERSION = "5.0.38"
    mock_mt5.RES_S_OK = 1
    mock_mt5.ORDER_TIME_GTC = 0
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.ORDER_TYPE_SELL = 1
    mock_mt5.ORDER_FILLING_IOC = 1
    mock_mt5.TIMEFRAME_M5 = 301
    mock_mt5.TIMEFRAME_M15 = 302
    mock_mt5.TIMEFRAME_H1 = 16400
    mock_mt5.TIMEFRAME_D1 = 16408
    mock_mt5.copy_rates_from_pos.return_value = []
    mock_mt5.get_account_info.return_value = None
    mock_mt5.initialize.return_value = True
    mock_mt5.shutdown.return_value = True
    sys.modules["MetaTrader5"] = mock_mt5

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
from backend.app.billing.stripe.models import StripeEvent  # noqa: F401, E402
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
    """Create test database session with fresh schema each test.

    Uses in-memory SQLite with checkfirst=True to avoid duplicate index errors.
    Each test gets a completely fresh database.
    """
    from sqlalchemy import text

    from backend.app.core.db import Base

    # Create fresh engine for this test
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Drop all existing tables and indexes
    async with engine.begin() as conn:
        # Get list of all tables
        result = await conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        )
        tables = [row[0] for row in result.fetchall()]

        # Drop all tables (cascade not needed in SQLite for this case)
        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS [{table}]"))

        # Drop all indexes
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index'")
        )
        indexes = [row[0] for row in result.fetchall()]
        for index in indexes:
            if not index.startswith("sqlite_"):
                await conn.execute(text(f"DROP INDEX IF EXISTS [{index}]"))

    # Create all tables from Base.metadata (no checkfirst since DB is fresh)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c))

    # Create session factory
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    # Cleanup: close session and dispose engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_postgres() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session with REAL PostgreSQL backend.

    Use this fixture for integration tests that need real database behavior:
    - Constraint validation
    - Transaction semantics
    - Complex query patterns

    Requires: docker-compose up (PostgreSQL running on localhost:5432)

    Example:
        async def test_signal_creation(db_postgres):
            signal = StripeEvent(...)
            db_postgres.add(signal)
            await db_postgres.commit()
            assert signal.id is not None
    """
    from backend.app.core.db import Base

    # Connect to real PostgreSQL (same one as docker-compose)
    db_url = (
        "postgresql+psycopg_async://postgres:postgres@localhost:5432/trading_db_test"
    )
    engine = create_async_engine(
        db_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
    )

    # Drop all tables first
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c))

    # Create all tables fresh
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
def stripe_webhook_timestamp():
    """Return test webhook timestamp."""
    from datetime import datetime

    return datetime.utcnow()


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
