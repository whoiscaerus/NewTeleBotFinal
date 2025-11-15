"""Root conftest for backend tests - sets up Python path and fixtures."""

import asyncio
import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add backend directory to Python path so imports work correctly
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Set test database URL before importing settings
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


def pytest_configure(config):
    """Configure pytest before test collection."""
    print("\n[ROOT CONFTEST] pytest_configure called")
    # Import only essential models to avoid circular dependencies
    print("[ROOT CONFTEST] Importing minimal models...")
    from backend.app.core.db import Base

    print(f"[ROOT CONFTEST] Base.metadata.tables: {list(Base.metadata.tables.keys())}")

    # Ensure event loop is set up for asyncio tests
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session with fresh schema for each test.

    This is defined in ROOT conftest to ensure it's available to all tests.
    """
    print("\n[ROOT CONFTEST] db_session fixture CALLED!")
    sys.stdout.flush()

    # Import Base (all models should already be imported by now via test modules)
    from backend.app.core.db import Base

    # Try importing key models that tests rely on, skip failures gracefully
    try:
        from backend.app.accounts.service import AccountLink  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.affiliates.models import (  # noqa: F401
            Affiliate,
            AffiliateEarnings,
            Commission,
            Payout,
            Referral,
            ReferralEvent,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.ai.models import (  # noqa: F401
            ChatMessage,
            ChatSession,
            KBEmbedding,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.alerts.rules import (  # noqa: F401
            RuleNotification,
            SmartAlertRule,
        )
        from backend.app.alerts.service import (  # noqa: F401
            AlertNotification,
            PriceAlert,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.approvals.models import Approval  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.audit.models import AuditLog  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.auth.models import User  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.billing.catalog.models import (  # noqa: F401
            Product,
            ProductCategory,
            ProductTier,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.billing.entitlements.models import (  # noqa: F401
            EntitlementType,
            UserEntitlement,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.billing.stripe.models import StripeEvent  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.clients.devices.models import Device  # noqa: F401
        from backend.app.clients.exec.models import ExecutionRecord  # noqa: F401
        from backend.app.clients.models import Client  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.ea.models import Execution  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.education.models import (  # noqa: F401
            Attempt,
            Course,
            Lesson,
            Quiz,
            QuizQuestion,
            Reward,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.journeys.models import (  # noqa: F401
            Journey,
            JourneyStep,
            StepExecution,
            UserJourney,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.kb.models import Article, ArticleVersion, Tag  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.marketing.models import MarketingClick  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.orders.models import Order, OrderItem  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.signals.models import Signal  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.support.models import Ticket  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.telegram.models import (  # noqa: F401
            DistributionAuditLog,
            TelegramBroadcast,
            TelegramCommand,
            TelegramGuide,
            TelegramUser,
            TelegramUserGuideCollection,
            TelegramWebhook,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.trading.data.models import (  # noqa: F401
            DataPullLog,
            OHLCCandle,
            SymbolPrice,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.trading.positions.models import OpenPosition  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.trading.reconciliation.models import (  # noqa: F401
            DrawdownAlert,
            PositionSnapshot,
            ReconciliationLog,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.trading.store.models import (  # noqa: F401
            EquityPoint,
            Position,
            Trade,
            ValidationLog,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from backend.app.trust.models import (  # noqa: F401
            Endorsement,
            TrustCalculationLog,
            UserTrustScore,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    # Create fresh in-memory engine
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Create all tables with checkfirst=True to avoid index conflicts
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, checkfirst=True))
        print("[ROOT CONFTEST] Tables created!")
        sys.stdout.flush()

    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = async_session()

    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()
