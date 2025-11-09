"""
PR-083: FlaskAPI Compatibility Shims

Feature-flagged redirects from legacy Flask routes to new FastAPI endpoints.

Behavior:
- FLASK_COMPATIBILITY_MODE=true: 301 redirects (old → new routes)
- FLASK_COMPATIBILITY_MODE=false: 410 Gone (endpoints removed)

All requests to old routes increment the legacy_calls_total metric.
"""

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import RedirectResponse

from backend.app.core.settings import settings
from backend.app.observability.metrics import metrics

router = APIRouter(tags=["legacy-compat"])


async def verify_legacy_auth(x_user_id: str | None = Header(None)):
    """
    Verify X-User-ID header for legacy Flask endpoints.

    Raises:
        HTTPException: 401 if X-User-ID missing or invalid
    """
    if not x_user_id or x_user_id != settings.gateway.telegram_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_user_id


def legacy_redirect(old_route: str, new_route: str):
    """
    Handle legacy route with feature-flagged behavior.

    Args:
        old_route: Legacy Flask route path
        new_route: New FastAPI route path

    Returns:
        RedirectResponse (301) if compat mode on, else HTTPException (410)
    """
    # Increment telemetry
    metrics.legacy_calls_total.labels(route=old_route).inc()

    if settings.gateway.flask_compatibility_mode:
        # 301 Moved Permanently
        return RedirectResponse(
            url=new_route,
            status_code=301,
            headers={
                "X-Deprecation-Warning": f"This endpoint moved to {new_route}",
                "X-Sunset": "2025-03-31",  # 90 days from deployment
            },
        )
    else:
        # 410 Gone (endpoint removed)
        raise HTTPException(
            status_code=410,
            detail=f"This endpoint has been removed. Use {new_route} instead.",
            headers={
                "X-Migration-Guide": "/api/v1/docs/migration",
            },
        )


@router.get("/")
async def legacy_index(user: str | None = Query(None)):
    """
    Legacy: GET /?user=<id>
    New: GET /dashboard?user=<id>
    """
    # Validate auth
    if not user or user != settings.gateway.telegram_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return legacy_redirect("/", f"/dashboard?user={user}")


@router.get("/images/{filename}")
async def legacy_serve_image(
    filename: str, x_user_id: str = Header(..., alias="X-User-ID")
):
    """
    Legacy: GET /images/<filename>
    New: GET /api/v1/charts/<filename>
    """
    await verify_legacy_auth(x_user_id)
    return legacy_redirect(f"/images/{filename}", f"/api/v1/charts/{filename}")


@router.get("/api/price")
async def legacy_price(x_user_id: str = Header(..., alias="X-User-ID")):
    """
    Legacy: GET /api/price
    New: GET /api/v1/market/price

    Response:
        {
            "symbol": "XAUUSD",
            "bid": 1950.50,
            "ask": 1950.75,
            "time": "2025-01-01T12:00:00"
        }
    """
    await verify_legacy_auth(x_user_id)
    return legacy_redirect("/api/price", "/api/v1/market/price")


@router.get("/api/trades")
async def legacy_trades(
    x_user_id: str = Header(..., alias="X-User-ID"),
    since: str | None = Query(None),
    to: str | None = Query(None),
):
    """
    Legacy: GET /api/trades?since=YYYY-MM-DD&to=YYYY-MM-DD
    New: GET /api/v1/trading/trades?since=YYYY-MM-DD&to=YYYY-MM-DD

    Query Params:
        since: Start date (optional)
        to: End date (optional)

    Response:
        [
            {
                "ticket": 12345,
                "symbol": "XAUUSD",
                "type": 0,  # 0=buy, 1=sell
                "volume": 0.1,
                "open_price": 1950.50,
                "close_price": 1955.00,
                "profit": 45.00,
                "open_time": "2025-01-01T10:00:00",
                "close_time": "2025-01-01T11:00:00"
            }
        ]
    """
    await verify_legacy_auth(x_user_id)

    # Build query params
    query_params = []
    if since:
        query_params.append(f"since={since}")
    if to:
        query_params.append(f"to={to}")

    query_string = f"?{'&'.join(query_params)}" if query_params else ""
    return legacy_redirect("/api/trades", f"/api/v1/trading/trades{query_string}")


@router.get("/api/images")
async def legacy_images(x_user_id: str = Header(..., alias="X-User-ID")):
    """
    Legacy: GET /api/images
    New: GET /api/v1/charts

    Response:
        {
            "images": ["chart_20250101.png", "chart_20250102.png"]
        }
    """
    await verify_legacy_auth(x_user_id)
    return legacy_redirect("/api/images", "/api/v1/charts")


@router.get("/api/positions")
async def legacy_positions(x_user_id: str = Header(..., alias="X-User-ID")):
    """
    Legacy: GET /api/positions
    New: GET /api/v1/trading/positions

    Response:
        [
            {
                "ticket": 12345,
                "symbol": "XAUUSD",
                "type": 0,  # 0=buy, 1=sell
                "volume": 0.1,
                "entry_price": 1950.50,
                "current_price": 1955.00,
                "pl": 45.00,  # Profit/Loss in USD
                "pl_pips": 4.5,  # Profit/Loss in pips
                "open_time": "2025-01-01T10:00:00"
            }
        ]
    """
    await verify_legacy_auth(x_user_id)
    return legacy_redirect("/api/positions", "/api/v1/trading/positions")


@router.get("/api/metrics")
async def legacy_metrics(x_user_id: str = Header(..., alias="X-User-ID")):
    """
    Legacy: GET /api/metrics
    New: GET /api/v1/analytics/performance

    Response:
        {
            "total_trades": 100,
            "win_rate": 0.65,
            "avg_profit": 25.50,
            "total_profit": 2550.00,
            "sharpe_ratio": 1.8,
            "max_drawdown": -0.15,
            "avg_drawdown": -0.05,
            "pips_per_trade": 12.5
        }
    """
    await verify_legacy_auth(x_user_id)
    return legacy_redirect("/api/metrics", "/api/v1/analytics/performance")


@router.get("/api/indicators")
async def legacy_indicators(x_user_id: str = Header(..., alias="X-User-ID")):
    """
    Legacy: GET /api/indicators
    New: GET /api/v1/market/indicators

    Response:
        {
            "rsi": 65.5,
            "ma_20": 1950.75,
            "ma_50": 1948.25,
            "time": "2025-01-01T12:00:00"
        }
    """
    await verify_legacy_auth(x_user_id)
    return legacy_redirect("/api/indicators", "/api/v1/market/indicators")


@router.get("/api/historical")
async def legacy_historical(
    x_user_id: str = Header(..., alias="X-User-ID"),
    timeframe: str | None = Query("15m"),
    period: str | None = Query("1y"),
):
    """
    Legacy: GET /api/historical?timeframe=15m&period=1y
    New: GET /api/v1/market/historical?timeframe=15m&period=1y

    Query Params:
        timeframe: 15m, 30m, 1h, 4h, 1d, 1w (default: 15m)
        period: 1y, 10y (default: 1y)

    Response:
        {
            "data": [
                {
                    "timestamp": 1704110400000,  # Unix ms
                    "open": 1950.50,
                    "high": 1955.00,
                    "low": 1948.00,
                    "close": 1952.50
                }
            ]
        }
    """
    await verify_legacy_auth(x_user_id)

    query_string = f"?timeframe={timeframe}&period={period}"
    return legacy_redirect(
        "/api/historical", f"/api/v1/market/historical{query_string}"
    )


# WebSocket compatibility note
# Legacy: SocketIO connect via socket.io protocol
# New: FastAPI WebSocket at /ws/market?user_id=<id>
#
# SocketIO cannot be shimmed with HTTP redirects (different protocol).
# Clients must update to WebSocket directly.
# See migration.md for WebSocket migration guide.
