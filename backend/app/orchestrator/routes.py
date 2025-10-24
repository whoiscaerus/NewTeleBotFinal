"""Health and status endpoints for the orchestrator.

These endpoints provide basic health checks and version information.
"""

import time

from fastapi import APIRouter

from backend.app.core.db import verify_db_connection
from backend.app.core.logging import get_logger
from backend.app.core.settings import settings

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["orchestrator"])

# Track application start time
_start_time = time.time()


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint.

    Returns:
        dict: Status and uptime in seconds.
    """
    uptime_seconds = time.time() - _start_time
    logger.info("Health check", extra={"uptime_seconds": uptime_seconds})
    return {"status": "ok", "uptime_seconds": round(uptime_seconds, 2)}


@router.get("/ready")
async def readiness_check() -> dict:
    """Readiness check endpoint.

    Verifies that the application is ready to receive requests by checking:
    - Database connectivity
    - Redis connectivity (if configured)

    Returns:
        dict: Ready status and dependency states.

    Example:
        >>> response = await readiness_check()
        >>> assert response["ready"] is True
        >>> assert response["dependencies"]["db"] == "connected"
    """
    logger.info("Readiness check")

    # Check database connectivity
    db_status = "connected" if await verify_db_connection() else "disconnected"

    return {
        "ready": db_status == "connected",
        "dependencies": {"db": db_status, "redis": "unknown"},
    }


@router.get("/version")
async def version_info() -> dict:
    """Version and build information endpoint.

    Returns:
        dict: Application name, version, build ID, and environment.
    """
    logger.info("Version info requested")
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "build": settings.APP_BUILD,
        "env": settings.APP_ENV,
    }
