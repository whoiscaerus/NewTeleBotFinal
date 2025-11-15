"""Main FastAPI application entry point."""

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.app.accounts.routes import router as accounts_router
from backend.app.admin.routes import router as admin_router  # PR-099: Admin Portal
from backend.app.affiliates.routes import router as affiliates_router
from backend.app.alerts.routes import router as alerts_router
from backend.app.alerts.routes_smart import router as smart_alerts_router
from backend.app.analytics.routes import router as analytics_router
from backend.app.approvals.routes import router as approvals_router
from backend.app.auth.routes import router as auth_router
from backend.app.clients.devices.routes import router as devices_router
from backend.app.clients.exec.routes import router as exec_router
from backend.app.copy.routes import router as copy_router
from backend.app.core.settings import get_settings
from backend.app.crm.routes import router as crm_router
from backend.app.ea.routes_admin import router as ea_admin_router
from backend.app.education.routes import router as education_router
from backend.app.explain.routes import router as explain_router
from backend.app.exports.routes import router as exports_router
from backend.app.health.routes import (
    router as health_router,  # PR-100: Health Monitoring
)
from backend.app.journeys.routes import router as journeys_router
from backend.app.messaging.routes import router as messaging_router
from backend.app.polling.routes import router as polling_v2_router
from backend.app.prefs.routes import router as prefs_router
from backend.app.privacy.routes import router as privacy_router
from backend.app.profile.routes import router as profile_router
from backend.app.public.performance_routes import router as performance_router
from backend.app.public.trust_index_routes import router as trust_index_router
from backend.app.reports.routes import (
    router as reports_router,  # PR-101: AI-Generated Reports
)
from backend.app.revenue.routes import router as revenue_router
from backend.app.risk.routes import router as risk_router
from backend.app.risk.routes import trading_router
from backend.app.signals.routes import router as signals_router
from backend.app.strategy.decision_search import router as decision_search_router
from backend.app.trust.ledger.routes import router as ledger_router
from backend.app.trust.routes import router as trust_router
from backend.app.web3.routes import router as web3_router  # PR-102: NFT Access
from backend.app.web.routes import router as web_router

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
app.include_router(admin_router, tags=["admin"])  # PR-099: Admin Portal
app.include_router(health_router, tags=["health"])  # PR-100: Health Monitoring
app.include_router(auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(alerts_router, prefix="/api/v1", tags=["alerts"])
app.include_router(smart_alerts_router, tags=["smart-alerts"])
app.include_router(analytics_router, tags=["analytics"])
app.include_router(accounts_router, tags=["accounts"])
app.include_router(affiliates_router, prefix="/api/v1/affiliates", tags=["affiliates"])
app.include_router(approvals_router, prefix="/api/v1", tags=["approvals"])
app.include_router(performance_router, tags=["public"])
app.include_router(trust_index_router, tags=["public"])
app.include_router(
    ledger_router, tags=["public"]
)  # PR-093: Blockchain ledger proof routes
app.include_router(polling_v2_router, tags=["polling-v2"])
app.include_router(prefs_router, tags=["preferences"])
app.include_router(profile_router, tags=["profile"])  # PR-090: Theme settings
app.include_router(revenue_router, prefix="/api/v1", tags=["revenue"])
app.include_router(risk_router, tags=["risk"])
app.include_router(trading_router, tags=["trading-controls"])  # PR-075
app.include_router(signals_router, prefix="/api/v1", tags=["signals"])
app.include_router(decision_search_router, tags=["decisions"])  # PR-080
app.include_router(explain_router, tags=["explain"])  # PR-080
app.include_router(devices_router, prefix="/api/v1", tags=["devices"])
app.include_router(exec_router, prefix="/api/v1", tags=["execution"])
app.include_router(ea_admin_router, tags=["executions"])
app.include_router(education_router, tags=["education"])
app.include_router(exports_router, prefix="/api/v1", tags=["exports"])
app.include_router(journeys_router, tags=["journeys"])
app.include_router(trust_router, tags=["trust"])
app.include_router(messaging_router, tags=["messaging"])
app.include_router(privacy_router, tags=["privacy"])
app.include_router(copy_router, tags=["copy"])
app.include_router(web_router, tags=["web-telemetry"])  # PR-084
app.include_router(
    crm_router, tags=["crm"]
)  # PR-098: Smart CRM & Retention Automations
app.include_router(reports_router, tags=["reports"])  # PR-101: AI-Generated Reports
app.include_router(web3_router, tags=["web3"])  # PR-102: NFT Access


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
