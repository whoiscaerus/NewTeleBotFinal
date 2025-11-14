"""Pytest configuration and shared fixtures."""

import os
import sys
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

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
from fastapi import Header, HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Set test environment variables BEFORE importing app
os.environ["APP_ENV"] = "development"
os.environ["APP_NAME"] = "test-app"
os.environ["APP_VERSION"] = "0.1.0-test"
os.environ["APP_LOG_LEVEL"] = "DEBUG"
os.environ["DB_DSN"] = "postgresql+psycopg://user:pass@localhost:5432/test_app"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["SMTP_HOST"] = "localhost"
os.environ["SMTP_PORT"] = "587"
os.environ["SMTP_USER"] = "test@example.com"
os.environ["SMTP_PASSWORD"] = "test_password"
os.environ["SMTP_FROM"] = "noreply@test.com"
os.environ["PUSH_ENABLED"] = "false"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_12345678901234567890"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_EXPIRE_MINUTES"] = "30"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_123456789"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_123456789"
os.environ["TELEGRAM_PAYMENT_PROVIDER_TOKEN"] = "test_payment_token"
os.environ["SIGNALS_API_BASE"] = "http://localhost:8000"
os.environ["SIGNALS_HMAC_KEY"] = "test_hmac_key_12345678901234567890"
os.environ["TELEGRAM_BOT_TOKEN"] = "test_bot_token"
os.environ["TELEGRAM_BOT_USERNAME"] = "TestBot"
os.environ["OTEL_ENABLED"] = "false"
os.environ["PROMETHEUS_ENABLED"] = "false"
os.environ["MEDIA_DIR"] = "test_media"
os.environ["HMAC_PRODUCER_ENABLED"] = "false"


def pytest_configure(config):
    """Import all models BEFORE test collection to ensure consistent Base.metadata.

    Problem: Test files import models at module level (top of file).
    When pytest collects tests, it imports all test files.
    If test file imports model before conftest, model registers with Base.metadata twice.
    Result: "index already exists" errors during table creation.

    Solution: pytest_configure runs BEFORE test collection.
    Import all models here so they're in Base.metadata before ANY test file imports them.
    """
    print("[ROOT CONFTEST] pytest_configure called")
    print("[ROOT CONFTEST] Importing minimal models...")

    # Import all models to register with Base.metadata BEFORE test collection
    from backend.app.accounts.models import AccountLink  # noqa: F401
    from backend.app.approvals.models import Approval  # noqa: F401
    from backend.app.audit.models import AuditLog  # noqa: F401
    from backend.app.auth.models import User  # noqa: F401
    from backend.app.billing.stripe.models import StripeEvent  # noqa: F401
    from backend.app.clients.models import Client, Device  # noqa: F401

    # Debug: Show which tables are registered
    from backend.app.core.db import Base
    from backend.app.ea.models import Execution  # noqa: F401
    from backend.app.features.models import FeatureSnapshot  # noqa: F401
    from backend.app.fraud.models import AnomalyEvent  # noqa: F401
    from backend.app.gamification.models import (  # noqa: F401
        Badge,
        EarnedBadge,
        LeaderboardOptIn,
        Level,
    )
    from backend.app.paper.models import (  # noqa: F401
        PaperAccount,
        PaperPosition,
        PaperTrade,
    )
    from backend.app.prefs.models import UserPreferences  # noqa: F401
    from backend.app.privacy.models import PrivacyRequest  # noqa: F401
    from backend.app.reports.models import Report  # noqa: F401
    from backend.app.strategy.logs.models import DecisionLog  # noqa: F401
    from backend.app.strategy.models import (  # noqa: F401
        CanaryConfig,
        ShadowDecisionLog,
        StrategyVersion,
    )
    from backend.app.trading.positions.close_commands import CloseCommand  # noqa: F401
    from backend.app.trading.positions.models import OpenPosition  # noqa: F401
    from backend.app.trading.store.models import (  # noqa: F401
        EquityPoint,
        Position,
        Trade,
        ValidationLog,
    )
    from backend.app.trust.models import Endorsement, UserTrustScore  # noqa: F401
    from backend.app.trust.social.models import VerificationEdge  # noqa: F401
    from backend.app.upsell.models import (  # noqa: F401
        Experiment,
        Exposure,
        Recommendation,
        Variant,
    )
    from backend.app.marketing.models import MarketingClick  # noqa: F401

    print(f"[ROOT CONFTEST] Base.metadata.tables: {list(Base.metadata.tables.keys())}")


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
        from backend.app.marketing.models import MarketingClick

        await conn.run_sync(MarketingClick.__table__.create, checkfirst=True)

    # Create session factory
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    # Cleanup: drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c))

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create in-memory SQLite session for unit tests with proper cleanup.

    Each test gets a fresh database session with clean state:
    - Creates new in-memory database for each test
    - All tables created fresh
    - After test: engine disposed to clear all data

    This ensures complete test isolation - no data leaks between tests.
    """

    from backend.app.core.db import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    # Cleanup: dispose engine (destroys in-memory database)
    # Each test gets a fresh database, ensuring complete isolation
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

    # Create a simple callable that returns an async generator yielding the session
    # This ensures the endpoint uses the EXACT same session object as the test
    async def override_get_db():
        try:
            yield db_session
        finally:
            # Don't close or commit - let the test manage the session lifecycle
            pass

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

    # Override get_current_user to use mock user from test fixture
    from backend.app.auth.dependencies import get_current_user

    # Default mock user (will be overridden by fixture-specific users)
    async def mock_get_current_user():
        """Mock auth - returns default test user.

        Tests using auth_headers fixture will have their specific user injected
        by adding the user to the db_session before calling endpoints.
        """
        # Return the first user from the database if any
        from sqlalchemy import select
        from backend.app.auth.models import User

        result = await db_session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return user

    app.dependency_overrides[get_current_user] = mock_get_current_user

    # Override get_device_auth to bypass signature verification in tests
    # Device already imported at top of file
    from backend.app.ea.auth import get_device_auth
    from backend.app.clients.models import Device
    from sqlalchemy import select

    async def mock_get_device_auth(
        x_device_id: str = Header("", alias="X-Device-Id"),
        nonce: str = Header("", alias="X-Nonce"),
        timestamp: str = Header("", alias="X-Timestamp"),
        signature: str = Header("", alias="X-Signature"),
    ):
        """Mock device auth that accepts any headers (for testing)."""
        device_id = x_device_id
        print(f"[MOCK AUTH] Received device_id={device_id}")
        # Load device from DB if provided
        if device_id:
            try:
                stmt = select(Device).where(Device.id == device_id)
                result = await db_session.execute(stmt)
                device = result.scalar_one_or_none()
                print(f"[MOCK AUTH] Device lookup result: {device}")

                if device:
                    print(f"[MOCK AUTH] Device found! client_id={device.client_id}")

                    # Create a mock auth object with device_id and client_id
                    class MockDeviceAuth:
                        def __init__(self, device_id, client_id):
                            self.device_id = device_id
                            self.client_id = client_id

                    return MockDeviceAuth(device.id, device.client_id)
                else:
                    # Device not found - return mock with None client_id
                    # This will cause 403 in the endpoint as intended
                    print("[MOCK AUTH] Device NOT FOUND!")

                    class MockDeviceAuth:
                        def __init__(self, device_id):
                            self.device_id = device_id
                            self.client_id = None

                    return MockDeviceAuth(device_id)
            except Exception as e:
                # Log any errors but still return a mock
                print(f"[MOCK AUTH] ERROR: {e}")
                import traceback

                traceback.print_exc()

                class MockDeviceAuth:
                    def __init__(self, device_id):
                        self.device_id = device_id
                        self.client_id = None

                return MockDeviceAuth(device_id)

        # Return empty mock if device not provided
        print("[MOCK AUTH] No device_id provided!")

        class MockDeviceAuth:
            def __init__(self):
                self.device_id = None
                self.client_id = None

        return MockDeviceAuth()

    app.dependency_overrides[get_device_auth] = mock_get_device_auth

    # Create a shared mock MT5 manager that tests can configure
    from unittest.mock import AsyncMock

    shared_mock_mt5 = AsyncMock()
    shared_mock_mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000.00,
            "equity": 9500.00,
        }
    )
    shared_mock_mt5.get_positions = AsyncMock(return_value=[])

    # Override get_account_service to use shared mock MT5 manager
    from backend.app.accounts.routes import get_account_service
    from backend.app.accounts.service import AccountLinkingService

    async def override_get_account_service():
        """Override to use shared mock MT5 manager."""
        return AccountLinkingService(db_session, shared_mock_mt5)

    app.dependency_overrides[get_account_service] = override_get_account_service

    # Store shared mock on the app for tests to access
    app._test_shared_mock_mt5 = shared_mock_mt5

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Also attach to client for easy access
        client._test_shared_mock_mt5 = shared_mock_mt5
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def ws_client(db_session: AsyncSession, monkeypatch):
    """Create FastAPI TestClient with WebSocket support for testing real connections.
    
    This fixture provides a synchronous TestClient that supports websocket_connect(),
    unlike the async AsyncClient. Use this fixture for WebSocket tests.
    
    Example:
        with ws_client.websocket_connect("/api/v1/dashboard/ws?token=...") as ws:
            data = ws.receive_json()
    """
    from fastapi.testclient import TestClient
    from backend.app.core.db import get_db
    from backend.app.orchestrator.main import app
    
    # Create override for get_db
    async def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    # Mock the rate limiter
    class NoOpRateLimiter:
        def __init__(self):
            self._initialized = False
            self.redis_client = None

        async def is_allowed(self, key: str, **kwargs) -> bool:
            return True

        async def get_remaining(self, key: str, max_tokens: int, **kwargs) -> int:
            return max_tokens

    async def mock_get_rate_limiter():
        return NoOpRateLimiter()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        "backend.app.core.decorators.get_rate_limiter", mock_get_rate_limiter
    )

    # Override get_current_user for auth
    from backend.app.auth.dependencies import get_current_user
    
    async def mock_get_current_user():
        from sqlalchemy import select
        from backend.app.auth.models import User
        result = await db_session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return user

    app.dependency_overrides[get_current_user] = mock_get_current_user
    
    # Create synchronous TestClient for WebSocket support
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def real_auth_client(db_session: AsyncSession, monkeypatch):
    """FastAPI test client with REAL device auth (no mocking).

    Use this fixture for security tests that need to validate:
    - Timestamp freshness
    - Nonce replay detection
    - HMAC signature validation
    - Error handling for invalid auth

    Example:
        @pytest.mark.asyncio
        async def test_timestamp_validation(real_auth_client, device):
            response = await real_auth_client.get(
                "/api/v1/client/poll",
                headers={
                    "X-Device-Id": device.id,
                    "X-Nonce": "nonce_123",
                    "X-Timestamp": old_timestamp,  # 6 minutes old
                    "X-Signature": signature,
                }
            )
            assert response.status_code == 400
    """
    from httpx import ASGITransport

    from backend.app.core.db import get_db
    from backend.app.orchestrator.main import app

    # Override database
    async def override_get_db():
        try:
            yield db_session
        finally:
            pass

    # Mock rate limiter
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
    monkeypatch.setattr(
        "backend.app.core.decorators.get_rate_limiter", mock_get_rate_limiter
    )

    # DO NOT override get_device_auth - use real implementation!
    # This allows timestamp validation and other security checks to work

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def clear_auth_override():
    """Clear the get_current_user override for tests that need real auth checking.
    
    Use this fixture in tests that verify 401 responses for missing/invalid JWT.
    Example:
        @pytest.mark.asyncio
        async def test_missing_auth_returns_401(self, client, clear_auth_override):
            response = await client.post("/api/v1/approvals", json={...})
            assert response.status_code == 401
    """
    from backend.app.auth.dependencies import get_current_user
    from backend.app.orchestrator.main import app
    
    # Remove the override if it exists
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]
    
    yield
    
    # Restore override after test (though conftest sets it up again)
    # This is just safety - the autouse fixture will restore it anyway


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


@pytest_asyncio.fixture
async def admin_token(db_session: AsyncSession) -> str:
    """
    Create admin user and return JWT token.

    Creates a test admin user with UserRole.ADMIN and generates
    a valid JWT access token for authentication in tests.

    Returns:
        str: JWT access token for admin user

    Example:
        >>> response = await client.get(
        ...     "/api/v1/admin/users",
        ...     headers={"Authorization": f"Bearer {admin_token}"}
        ... )
    """
    from uuid import uuid4

    from backend.app.auth.models import User, UserRole
    from backend.app.auth.utils import create_access_token, hash_password

    # Create admin user
    admin_user = User(
        id=str(uuid4()),
        email="admin@test.com",
        telegram_user_id="999999999",
        password_hash=hash_password("admin_password"),
        role=UserRole.ADMIN,
    )

    db_session.add(admin_user)
    await db_session.commit()
    await db_session.refresh(admin_user)

    # Generate JWT token
    token = create_access_token(subject=str(admin_user.id), role="admin")

    return token


# DEPRECATED: Use create_access_token() directly instead
# Kept for backwards compatibility with existing tests that call it as a helper
async def create_auth_token(user) -> str:
    """Helper to generate JWT token for a test user.
    
    Args:
        user: User model instance
        
    Returns:
        JWT token string
        
    Usage:
        token = await create_auth_token(user)
        headers = {"Authorization": f"Bearer {token}"}
    """
    from backend.app.auth.utils import create_access_token
    
    return create_access_token(subject=str(user.id), role=getattr(user, "role", "user"))


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


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user for integration tests."""
    from uuid import uuid4

    from backend.app.auth.models import User, UserRole
    from backend.app.auth.utils import hash_password

    user = User(
        id=str(uuid4()),
        email="testuser@example.com",
        telegram_user_id="123456789",
        password_hash=hash_password("test_password"),
        role=UserRole.USER,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def owner_user(db_session: AsyncSession):
    """Create an owner user for admin/owner-only tests."""
    from uuid import uuid4

    from backend.app.auth.models import User, UserRole
    from backend.app.auth.utils import hash_password

    user = User(
        id=str(uuid4()),
        email="owner@example.com",
        telegram_user_id="111111111",
        password_hash=hash_password("owner_password"),
        role=UserRole.OWNER,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession):
    """Create an admin user for admin-only tests."""
    from uuid import uuid4

    from backend.app.auth.models import User, UserRole
    from backend.app.auth.utils import hash_password

    user = User(
        id=str(uuid4()),
        email="admin@example.com",
        telegram_user_id="333333333",
        password_hash=hash_password("admin_password"),
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession):
    """Create a regular (non-admin) user for authorization tests."""
    from uuid import uuid4

    from backend.app.auth.models import User, UserRole
    from backend.app.auth.utils import hash_password

    user = User(
        id=str(uuid4()),
        email="regular@example.com",
        telegram_user_id="222222222",
        password_hash=hash_password("regular_password"),
        role=UserRole.USER,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def owner_auth_headers(owner_user) -> dict:
    """Create JWT authentication headers for owner user."""
    from backend.app.auth.utils import create_access_token

    token = create_access_token(
        subject=owner_user.id, role=owner_user.role, expires_delta=None
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def regular_auth_headers(regular_user) -> dict:
    """Create JWT authentication headers for regular user."""
    from backend.app.auth.utils import create_access_token

    token = create_access_token(
        subject=regular_user.id, role=regular_user.role, expires_delta=None
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_auth_headers(admin_user) -> dict:
    """Create JWT authentication headers for admin user."""
    from backend.app.auth.utils import create_access_token

    token = create_access_token(
        subject=admin_user.id, role=admin_user.role, expires_delta=None
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_client(db_session: AsyncSession):
    """Create a test client for device registration."""
    from uuid import uuid4
    from backend.app.clients.models import Client

    # Client already imported at top of file

    client = Client(
        id=str(uuid4()),
        email="testclient@example.com",
        telegram_id="9876543210",
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


@pytest_asyncio.fixture
async def test_device(db_session: AsyncSession, test_client):
    """Create a test EA device for integration tests."""
    from uuid import uuid4
    from backend.app.clients.models import Device

    # Device already imported at top of file

    device = Device(
        id=str(uuid4()),
        client_id=test_client.id,
        device_name="Test EA Device",
        hmac_key_hash="test_hmac_key_hash_12345",
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


# ============================================================================
# PR-043: ACCOUNT LINKING & POSITIONS TEST FIXTURES
# ============================================================================


@pytest_asyncio.fixture
def mock_mt5_manager():
    """Mock MT5SessionManager for PR-043 testing."""
    from unittest.mock import AsyncMock

    manager = AsyncMock()
    manager.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000.00,
            "equity": 9500.00,
            "free_margin": 4500.00,
            "margin_used": 5000.00,
            "margin_level": 190.0,
            "open_positions": 2,
        }
    )
    manager.get_positions = AsyncMock(return_value=[])
    return manager


@pytest_asyncio.fixture
async def account_service(db_session: AsyncSession, mock_mt5_manager):
    """Create AccountLinkingService for PR-043 testing."""
    from backend.app.accounts.service import AccountLinkingService

    service = AccountLinkingService(db_session, mock_mt5_manager)
    return service


@pytest_asyncio.fixture
async def positions_service(
    db_session: AsyncSession, account_service, mock_mt5_manager
):
    """Create PositionsService for PR-043 testing."""
    from backend.app.positions.service import PositionsService

    service = PositionsService(db_session, account_service, mock_mt5_manager)
    return service


@pytest_asyncio.fixture
async def linked_account(db_session: AsyncSession, test_user, account_service):
    """Create a linked MT5 account for PR-043 testing."""
    # Mock MT5 account info response
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000.00,
            "equity": 9500.00,
            "free_margin": 4500.00,
            "margin_used": 5000.00,
            "margin_level": 190.0,
            "open_positions": 2,
        }
    )

    # Link account
    link = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    return link


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession):
    """Create another test user for PR-043 authorization testing."""
    from uuid import uuid4

    from backend.app.auth.models import User, UserRole
    from backend.app.auth.utils import hash_password

    user = User(
        id=str(uuid4()),
        email="otheruser@example.com",
        telegram_user_id="987654321",
        password_hash=hash_password("other_password"),
        role=UserRole.USER,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user) -> dict:
    """Create JWT authentication headers for test user."""
    from backend.app.auth.utils import create_access_token

    token = create_access_token(
        subject=test_user.id, role=test_user.role, expires_delta=None
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_headers(admin_token: str) -> dict:
    """Create JWT authentication headers for admin user.

    Returns headers dict with Authorization bearer token containing
    admin JWT. Used in tests that require admin access.

    Returns:
        dict: Headers with Authorization bearer token

    Example:
        >>> response = await client.get(
        ...     "/api/v1/revenue/summary",
        ...     headers=admin_headers
        ... )
    """
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def test_signal(db_session: AsyncSession, test_user):
    """Create a test signal for integration tests."""
    from uuid import uuid4

    from backend.app.signals.models import Signal

    signal = Signal(
        id=str(uuid4()),
        user_id=test_user.id,
        instrument="XAUUSD",
        side=0,  # buy
        price=1950.50,
        payload={"rsi": 75.5, "confidence": 0.85},
        version="1.0",
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(signal)
    return signal


@pytest_asyncio.fixture
async def create_test_user(db_session: AsyncSession):
    """Factory fixture to create test users with custom email.
    
    Usage:
        user1 = await create_test_user("user1@test.com")
        user2 = await create_test_user("user2@test.com", role="ADMIN")
    """
    from uuid import uuid4
    from passlib.context import CryptContext
    
    from backend.app.auth.models import User
    
    pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
    
    async def _create_user(email: str = None, password: str = "test123", role: str = "USER"):
        if email is None:
            email = f"user{str(uuid4())[:8]}@test.com"
        
        user = User(
            id=str(uuid4()),
            email=email,
            password_hash=pwd_context.hash(password),
            role=role,
            telegram_user_id=None,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user
    
    return _create_user


@pytest_asyncio.fixture
async def create_test_signal(db_session: AsyncSession):
    """Factory fixture to create test signals with custom parameters.
    
    Usage:
        signal = await create_test_signal(user_id=user.id, instrument="EURUSD")
    """
    from uuid import uuid4
    
    from backend.app.signals.models import Signal
    
    async def _create_signal(
        user_id: str,
        instrument: str = "XAUUSD",
        side: int = 0,
        price: float = 1950.50,
        payload: dict = None,
    ):
        if payload is None:
            payload = {"rsi": 75.5, "confidence": 0.85}
        
        signal = Signal(
            id=str(uuid4()),
            user_id=user_id,
            instrument=instrument,
            side=side,
            price=price,
            payload=payload,
            version="1.0",
        )
        db_session.add(signal)
        await db_session.commit()
        await db_session.refresh(signal)
        return signal
    
    return _create_signal
