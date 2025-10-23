"""FastAPI application factory and lifespan management.

This module creates the FastAPI application with proper middleware and routing configuration.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from backend.app.core.logging import get_logger, setup_logging
from backend.app.core.middleware import RequestIDMiddleware
from backend.app.core.settings import settings
from backend.app.orchestrator import routes

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan context manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info(
        "Application starting",
        app_name=settings.APP_NAME,
        app_version=settings.APP_VERSION,
        app_env=settings.APP_ENV,
    )

    yield

    # Shutdown
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

    logger.info("FastAPI application created")

    return app
