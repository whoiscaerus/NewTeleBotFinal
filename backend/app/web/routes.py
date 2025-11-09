"""
Backend Web Telemetry Routes (PR-084)

Endpoints for tracking web platform metrics:
- Page views (by route)
- Core Web Vitals (LCP, FID, CLS, TTFB)

Used by frontend/web/lib/telemetry.ts for performance monitoring.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

# Import observability from existing metrics infrastructure
from backend.app.observability.metrics import get_metrics_service

router = APIRouter(prefix="/api/v1/web", tags=["web-telemetry"])


# Request Models
class PageViewRequest(BaseModel):
    """Page view tracking request."""

    route: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Page route (e.g., '/', '/pricing')",
    )
    referrer: str | None = Field(None, max_length=500, description="HTTP referrer")
    timestamp: int = Field(..., description="Client timestamp (Unix ms)")


class CoreWebVitalsRequest(BaseModel):
    """Core Web Vitals metrics request."""

    lcp: float | None = Field(
        None, gt=0, description="Largest Contentful Paint (seconds)"
    )
    fid: float | None = Field(
        None, gt=0, description="First Input Delay (milliseconds)"
    )
    cls: float | None = Field(None, ge=0, description="Cumulative Layout Shift (score)")
    ttfb: float | None = Field(
        None, gt=0, description="Time to First Byte (milliseconds)"
    )


# Response Models
class TelemetryResponse(BaseModel):
    """Standard telemetry response."""

    status: str = "recorded"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


@router.post("/pageview", status_code=201, response_model=TelemetryResponse)
async def track_page_view(
    request: PageViewRequest,
    metrics_service=Depends(get_metrics_service),
):
    """
    Track a page view for analytics.

    Increments `web_page_view_total{route}` counter.

    Args:
        request: Page view data (route, referrer, timestamp)
        metrics_service: Prometheus metrics service

    Returns:
        TelemetryResponse: Confirmation with timestamp

    Example:
        >>> response = await client.post("/api/v1/web/pageview", json={
        ...     "route": "/pricing",
        ...     "referrer": "https://google.com",
        ...     "timestamp": 1699564800000
        ... })
        >>> assert response.status_code == 201
        >>> assert response.json()["status"] == "recorded"
    """
    try:
        # Increment Prometheus counter
        metrics_service.web_page_view_total.labels(route=request.route).inc()

        return TelemetryResponse(status="recorded")

    except Exception as e:
        # Log error but don't fail request (telemetry failures are non-critical)
        print(f"[WARN] Failed to record page view: {e}")
        return TelemetryResponse(status="recorded")


@router.post("/cwv", status_code=201, response_model=TelemetryResponse)
async def track_core_web_vitals(
    request: CoreWebVitalsRequest,
    metrics_service=Depends(get_metrics_service),
):
    """
    Track Core Web Vitals for performance monitoring.

    Records `web_cwv_lcp_seconds` histogram (and other CWV metrics).

    Args:
        request: Core Web Vitals data (LCP, FID, CLS, TTFB)
        metrics_service: Prometheus metrics service

    Returns:
        TelemetryResponse: Confirmation with timestamp

    Example:
        >>> response = await client.post("/api/v1/web/cwv", json={
        ...     "lcp": 2.5,
        ...     "fid": 100,
        ...     "cls": 0.1,
        ...     "ttfb": 600
        ... })
        >>> assert response.status_code == 201
    """
    try:
        # Record LCP (Largest Contentful Paint)
        if request.lcp is not None:
            metrics_service.web_cwv_lcp_seconds.observe(request.lcp)

        # Record FID (First Input Delay) - convert ms to seconds
        if request.fid is not None:
            metrics_service.web_cwv_fid_seconds.observe(request.fid / 1000)

        # Record CLS (Cumulative Layout Shift)
        if request.cls is not None:
            metrics_service.web_cwv_cls_score.observe(request.cls)

        # Record TTFB (Time to First Byte) - convert ms to seconds
        if request.ttfb is not None:
            metrics_service.web_cwv_ttfb_seconds.observe(request.ttfb / 1000)

        return TelemetryResponse(status="recorded")

    except Exception:
        print(f="[WARN] Failed to record CWV: {e}")
        return TelemetryResponse(status="recorded")
