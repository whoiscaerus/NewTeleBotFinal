"""Database setup and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.app.core.settings import get_settings

# SQLAlchemy declarative base
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting AsyncSession in FastAPI endpoints.

    Yields:
        AsyncSession: Database session
    """
    settings = get_settings()
    engine: AsyncEngine = create_async_engine(settings.db.url, echo=settings.app.debug)
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


# Standalone async session factory for schedulers/background jobs
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Create standalone async session for background jobs and schedulers.

    Use this in schedulers, CLI scripts, and background workers where
    FastAPI dependency injection is not available.

    Yields:
        AsyncSession: Database session

    Example:
        >>> async with get_async_session() as session:
        ...     result = await session.execute(select(User))
        ...     users = result.scalars().all()
    """
    settings = get_settings()
    engine: AsyncEngine = create_async_engine(
        settings.db.url,
        echo=settings.app.debug,
        pool_pre_ping=True,
    )
    async_session = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
            await engine.dispose()


# For non-async contexts (imports, etc.)
def create_sync_session():
    """Create synchronous session for setup/migration tasks.

    Returns:
        sessionmaker: Synchronous session factory
    """
    settings = get_settings()
    # For sync, use the synchronous driver
    sync_url = settings.db.url.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(sync_url, echo=settings.app.debug, pool_pre_ping=True)
    return sessionmaker(bind=engine)
