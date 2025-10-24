"""FastAPI application factory and lifespan management.

This module creates the FastAPI application with proper middleware and routing configuration.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from backend.app.approvals import routes as approvals_routes
from backend.app.core.db import close_db, init_db, verify_db_connection
from backend.app.core.logging import get_logger, setup_logging
from backend.app.core.middleware import RequestIDMiddleware
from backend.app.core.settings import settings
from backend.app.orchestrator import routes
from backend.app.signals import routes as signals_routes

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan context manager.

    Handles startup and shutdown events.

    Startup tasks:
    - Log application start
    - Initialize database tables
    - Verify database connectivity

    Shutdown tasks:
    - Close database connections
    - Log application stop
    """
    # Startup
    logger.info(
        "Application starting",
        app_name=settings.APP_NAME,
        app_version=settings.APP_VERSION,
        app_env=settings.APP_ENV,
    )

    try:
        # Initialize database tables
        await init_db()
        logger.info("Database tables initialized")

        # Verify database connectivity
        is_connected = await verify_db_connection()
        if is_connected:
            logger.info("Database connection verified")
        else:
            logger.warning("Database connection check failed")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        # Continue startup even if DB init fails (may retry on requests)

    yield

    # Shutdown
    try:
        await close_db()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database: {e}", exc_info=True)

    logger.info("Application shutting down")


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        FastAPI: Configured application instance.
    """
    # Setup logging first
    setup_logging()

    # Create FastAPI app
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="FXPro Trading Bot - Trading Signal Platform",
        lifespan=lifespan,
    )

    # Add middleware (order matters - outermost first)
    app.add_middleware(RequestIDMiddleware)

    # Include routers
    app.include_router(routes.router)
    app.include_router(signals_routes.router)
    app.include_router(approvals_routes.router)

    logger.info("FastAPI application created")

    return app
