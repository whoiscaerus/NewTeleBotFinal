"""Main FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.auth.routes import router as auth_router
from backend.app.core.errors import (
    APIException,
    problem_detail_exception_handler,
    generic_exception_handler,
)
from backend.app.core.middleware import RequestIDMiddleware
from backend.app.core.settings import get_settings


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
    settings = get_settings()
    
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
    app.add_exception_handler(Exception, generic_exception_handler)

    # Include routers
    app.include_router(auth_router)

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
