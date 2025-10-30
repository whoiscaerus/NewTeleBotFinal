"""Main FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.affiliates.routes import router as affiliates_router
from backend.app.approvals.routes import router as approvals_router
from backend.app.auth.routes import router as auth_router
from backend.app.clients.devices.routes import router as devices_router
from backend.app.clients.exec.routes import router as exec_router
from backend.app.core.settings import get_settings
from backend.app.signals.routes import router as signals_router

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
app.include_router(affiliates_router, prefix="/api/v1/affiliates", tags=["affiliates"])
app.include_router(approvals_router, prefix="/api/v1", tags=["approvals"])
app.include_router(signals_router, prefix="/api/v1", tags=["signals"])
app.include_router(devices_router, prefix="/api/v1", tags=["devices"])
app.include_router(exec_router, prefix="/api/v1", tags=["execution"])


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.app.debug,
    )
