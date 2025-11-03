"""Main FastAPI application entry point."""

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.app.affiliates.routes import router as affiliates_router
from backend.app.analytics.routes import router as analytics_router
from backend.app.approvals.routes import router as approvals_router
from backend.app.auth.routes import router as auth_router
from backend.app.clients.devices.routes import router as devices_router
from backend.app.clients.exec.routes import router as exec_router
from backend.app.core.settings import get_settings
from backend.app.ea.routes_admin import router as ea_admin_router
from backend.app.polling.routes import router as polling_v2_router
from backend.app.public.performance_routes import router as performance_router
from backend.app.public.trust_index_routes import router as trust_index_router
from backend.app.revenue.routes import router as revenue_router
from backend.app.risk.routes import router as risk_router
from backend.app.signals.routes import router as signals_router
from backend.app.trust.routes import router as trust_router

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="Trading Signal Platform API",
    description="Backend API for trading signal ingestion, approvals, and execution",
    version="1.0.0",
    docs_url="/docs" if settings.app.debug else None,
    redoc_url="/redoc" if settings.app.debug else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(analytics_router, tags=["analytics"])
app.include_router(affiliates_router, prefix="/api/v1/affiliates", tags=["affiliates"])
app.include_router(approvals_router, prefix="/api/v1", tags=["approvals"])
app.include_router(performance_router, tags=["public"])
app.include_router(trust_index_router, tags=["public"])
app.include_router(polling_v2_router, tags=["polling-v2"])
app.include_router(revenue_router, prefix="/api/v1", tags=["revenue"])
app.include_router(risk_router, tags=["risk"])
app.include_router(signals_router, prefix="/api/v1", tags=["signals"])
app.include_router(devices_router, prefix="/api/v1", tags=["devices"])
app.include_router(exec_router, prefix="/api/v1", tags=["execution"])
app.include_router(ea_admin_router, tags=["executions"])
app.include_router(trust_router, tags=["trust"])


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "status": "ok",
        "service": "Trading Signal Platform API",
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    if PROMETHEUS_AVAILABLE:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
    else:
        return {"error": "Prometheus metrics not available"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.app.debug,
    )
