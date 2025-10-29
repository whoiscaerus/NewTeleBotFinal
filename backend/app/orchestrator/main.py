"""Main FastAPI application factory."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from backend.app.affiliates.routes import router as affiliates_router
from backend.app.approvals.routes import router as approvals_router
from backend.app.auth.routes import router as auth_router
from backend.app.billing.routes import router as billing_router
from backend.app.clients.devices.routes import router as devices_router
from backend.app.clients.exec.routes import router as exec_router
from backend.app.core.errors import (
    APIException,
    generic_exception_handler,
    permission_error_handler,
    problem_detail_exception_handler,
    pydantic_validation_exception_handler,
)
from backend.app.core.middleware import RequestIDMiddleware
from backend.app.ea.routes import router as ea_router
from backend.app.miniapp.auth_bridge import router as miniapp_router
from backend.app.signals.routes import router as signals_router
from backend.app.telegram.webhook import router as telegram_router
from backend.app.trading.routes import router as trading_router


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Initializes:
    - FastAPI app with metadata
    - CORS middleware
    - Request ID middleware for tracing
    - Error handlers (RFC 7807)
    - Authentication routes
    - Health check endpoints

    Returns:
        FastAPI: Configured application instance
    """
    app = FastAPI(
        title="Trading Signal Platform",
        version="0.1.0",
        description="Production trading signal platform with Telegram integration",
    )

    # Add middlewares
    app.add_middleware(RequestIDMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add exception handlers (RFC 7807 error responses)
    app.add_exception_handler(APIException, problem_detail_exception_handler)
    app.add_exception_handler(PermissionError, permission_error_handler)
    app.add_exception_handler(
        RequestValidationError, pydantic_validation_exception_handler
    )
    app.add_exception_handler(Exception, generic_exception_handler)

    # Include routers
    app.include_router(auth_router)
    app.include_router(billing_router)
    app.include_router(miniapp_router)
    app.include_router(affiliates_router)
    app.include_router(approvals_router)
    app.include_router(devices_router)
    app.include_router(ea_router)
    app.include_router(exec_router)
    app.include_router(signals_router)
    app.include_router(telegram_router)
    app.include_router(trading_router)

    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/ready")
    async def readiness_check() -> dict:
        """Readiness check endpoint."""
        return {"ready": True}

    @app.get("/version")
    async def version() -> dict:
        """API version endpoint."""
        return {"version": "0.1.0"}

    return app


app = create_app()
