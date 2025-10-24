"""Main FastAPI application factory."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Trading Signal Platform",
        version="0.1.0",
        description="Production trading signal platform with Telegram integration",
    )

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
