"""Database connection management and session factory.

Provides SQLAlchemy engine, session management, and FastAPI dependencies
for database access throughout the application.
"""

import os
from typing import AsyncGenerator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.app.core.logging import get_logger

# Base class for all ORM models
Base = declarative_base()

logger = get_logger(__name__)


def get_database_url() -> str:
    """Get database URL from environment or use default.
    
    Returns:
        str: PostgreSQL connection string
        
    Raises:
        ValueError: If DATABASE_URL is invalid
        
    Example:
        >>> url = get_database_url()
        >>> assert url.startswith('postgresql') or url.startswith('sqlite')
    """
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:password@localhost:5432/telebot_test"
    )
    
    # Allow both PostgreSQL and SQLite for testing
    if not db_url.startswith(("postgresql", "postgresql+psycopg", "postgresql+asyncpg", "sqlite")):
        raise ValueError(f"Invalid DATABASE_URL: {db_url}")
    
    return db_url


def create_db_engine() -> AsyncEngine:
    """Create async SQLAlchemy engine with connection pooling.
    
    Returns:
        AsyncEngine: Configured async database engine
        
    Example:
        >>> engine = create_db_engine()
        >>> async with engine.begin() as conn:
        ...     await conn.execute(text("SELECT 1"))
    """
    db_url = get_database_url()
    
    # Convert sync URL to async URL if needed (PostgreSQL only)
    if db_url.startswith("postgresql://"):
        async_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    elif db_url.startswith("postgresql+psycopg://"):
        async_url = db_url.replace("postgresql+psycopg://", "postgresql+asyncpg://")
    else:
        async_url = db_url
    
    # Build engine kwargs - only apply pool settings to PostgreSQL
    engine_kwargs = {
        "echo": os.getenv("DATABASE_ECHO", "false").lower() == "true",
    }
    
    if async_url.startswith("postgresql"):
        pool_size = int(os.getenv("DATABASE_POOL_SIZE", "20"))
        max_overflow = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
        pool_pre_ping = os.getenv("DATABASE_POOL_PRE_PING", "true").lower() == "true"
        
        engine_kwargs.update({
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_pre_ping": pool_pre_ping,
            "pool_recycle": 3600,
        })
        
        logger.info(
            "Database engine created",
            extra={
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_pre_ping": pool_pre_ping,
            }
        )
    else:
        logger.info("Database engine created (SQLite - no pooling)")
    
    engine = create_async_engine(async_url, **engine_kwargs)
    
    return engine


# Global engine instance
_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """Get or create the global async database engine.
    
    Returns:
        AsyncEngine: Configured async database engine
        
    Example:
        >>> engine = get_engine()
        >>> # Use engine in application
    """
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


async def init_db() -> None:
    """Initialize database: create all tables.
    
    This runs on application startup to create tables from all models.
    
    Example:
        >>> await init_db()
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")


async def verify_db_connection() -> bool:
    """Verify database connection is working.
    
    Returns:
        bool: True if connection successful, False otherwise
        
    Example:
        >>> is_connected = await verify_db_connection()
        >>> assert is_connected
    """
    try:
        from sqlalchemy import text

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}", exc_info=True)
        return False


# Session factory for creating new sessions
def _get_sessionlocal():
    """Create session factory for global engine."""
    engine = get_engine()
    return sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

SessionLocal = _get_sessionlocal()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions.
    
    Yields:
        AsyncSession: Database session for request
        
    Example:
        >>> @app.get("/items")
        ... async def get_items(db: AsyncSession = Depends(get_db)):
        ...     return await db.execute(...)
    """
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}", exc_info=True)
            raise
        finally:
            await session.close()


async def close_db() -> None:
    """Close database connection pool.
    
    Call this on application shutdown.
    
    Example:
        >>> await close_db()
    """
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("Database connection closed")
