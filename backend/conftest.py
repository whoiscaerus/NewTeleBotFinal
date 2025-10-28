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

    # Force import ALL models before table creation
    from backend.app.core.db import Base

    # Create fresh in-memory engine
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
