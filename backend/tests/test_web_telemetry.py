"""
Tests for Web Telemetry Endpoints (PR-084)

Tests cover:
- Page view tracking (POST /api/v1/web/pageview)
- Core Web Vitals tracking (POST /api/v1/web/cwv)
- Validation of request payloads
- Prometheus metrics increments
- Error handling (non-critical failures)
"""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_track_page_view_success(client: AsyncClient):
    """Test successful page view tracking."""
    response = await client.post(
        "/api/v1/web/pageview",
        json={
            "route": "/pricing",
            "referrer": "https://google.com",
            "timestamp": 1699564800000,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "recorded"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_track_page_view_no_referrer(client: AsyncClient):
    """Test page view tracking without referrer (optional field)."""
    response = await client.post(
        "/api/v1/web/pageview",
        json={
            "route": "/",
            "timestamp": 1699564800000,
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "recorded"


@pytest.mark.asyncio
async def test_track_page_view_invalid_route_empty(client: AsyncClient):
    """Test page view tracking with empty route (should fail validation)."""
    response = await client.post(
        "/api/v1/web/pageview",
        json={
            "route": "",
            "timestamp": 1699564800000,
        },
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_track_page_view_missing_required_field(client: AsyncClient):
    """Test page view tracking without required 'route' field."""
    response = await client.post(
        "/api/v1/web/pageview",
        json={
            "timestamp": 1699564800000,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_track_cwv_all_metrics(client: AsyncClient):
    """Test Core Web Vitals tracking with all metrics."""
    response = await client.post(
        "/api/v1/web/cwv",
        json={
            "lcp": 2.5,
            "fid": 100,
            "cls": 0.1,
            "ttfb": 600,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "recorded"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_track_cwv_partial_metrics(client: AsyncClient):
    """Test Core Web Vitals tracking with only LCP (others optional)."""
    response = await client.post(
        "/api/v1/web/cwv",
        json={
            "lcp": 2.5,
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "recorded"


@pytest.mark.asyncio
async def test_track_cwv_no_metrics(client: AsyncClient):
    """Test Core Web Vitals tracking with no metrics (all optional, but body required)."""
    response = await client.post(
        "/api/v1/web/cwv",
        json={},
    )

    assert response.status_code == 201  # Empty body is valid (all fields optional)


@pytest.mark.asyncio
async def test_track_cwv_invalid_lcp_negative(client: AsyncClient):
    """Test Core Web Vitals tracking with invalid negative LCP."""
    response = await client.post(
        "/api/v1/web/cwv",
        json={
            "lcp": -1.0,
        },
    )

    assert response.status_code == 422  # Validation error (lcp must be > 0)


@pytest.mark.asyncio
async def test_track_cwv_invalid_cls_negative(client: AsyncClient):
    """Test Core Web Vitals tracking with invalid negative CLS."""
    response = await client.post(
        "/api/v1/web/cwv",
        json={
            "cls": -0.5,
        },
    )

    assert response.status_code == 422  # Validation error (cls must be >= 0)


@pytest.mark.asyncio
@patch("backend.app.web.routes.get_metrics_service")
async def test_page_view_increments_prometheus_counter(
    mock_metrics_service, client: AsyncClient
):
    """Test that page view endpoint increments Prometheus counter."""
    # Mock metrics service
    mock_service = MagicMock()
    mock_service.web_page_view_total = MagicMock()
    mock_metrics_service.return_value = mock_service

    response = await client.post(
        "/api/v1/web/pageview",
        json={
            "route": "/pricing",
            "timestamp": 1699564800000,
        },
    )

    assert response.status_code == 201

    # Verify Prometheus counter was incremented
    mock_service.web_page_view_total.labels.assert_called_once_with(route="/pricing")
    mock_service.web_page_view_total.labels.return_value.inc.assert_called_once()


@pytest.mark.asyncio
@patch("backend.app.web.routes.get_metrics_service")
async def test_cwv_records_all_histogram_metrics(
    mock_metrics_service, client: AsyncClient
):
    """Test that CWV endpoint records all histogram metrics correctly."""
    # Mock metrics service
    mock_service = MagicMock()
    mock_service.web_cwv_lcp_seconds = MagicMock()
    mock_service.web_cwv_fid_seconds = MagicMock()
    mock_service.web_cwv_cls_score = MagicMock()
    mock_service.web_cwv_ttfb_seconds = MagicMock()
    mock_metrics_service.return_value = mock_service

    response = await client.post(
        "/api/v1/web/cwv",
        json={
            "lcp": 2.5,
            "fid": 100,
            "cls": 0.1,
            "ttfb": 600,
        },
    )

    assert response.status_code == 201

    # Verify all histograms were recorded
    mock_service.web_cwv_lcp_seconds.observe.assert_called_once_with(2.5)
    mock_service.web_cwv_fid_seconds.observe.assert_called_once_with(
        0.1
    )  # 100ms -> 0.1s
    mock_service.web_cwv_cls_score.observe.assert_called_once_with(0.1)
    mock_service.web_cwv_ttfb_seconds.observe.assert_called_once_with(
        0.6
    )  # 600ms -> 0.6s


@pytest.mark.asyncio
@patch("backend.app.web.routes.get_metrics_service")
async def test_page_view_metric_failure_does_not_fail_request(
    mock_metrics_service, client: AsyncClient
):
    """Test that Prometheus metric failure doesn't fail the API request."""
    # Mock metrics service to raise exception
    mock_service = MagicMock()
    mock_service.web_page_view_total.labels.side_effect = Exception("Prometheus down")
    mock_metrics_service.return_value = mock_service

    response = await client.post(
        "/api/v1/web/pageview",
        json={
            "route": "/pricing",
            "timestamp": 1699564800000,
        },
    )

    # Request should still succeed (telemetry failures are non-critical)
    assert response.status_code == 201
    assert response.json()["status"] == "recorded"


@pytest.mark.asyncio
async def test_page_view_multiple_routes(client: AsyncClient):
    """Test tracking multiple different page routes."""
    routes = ["/", "/pricing", "/legal/terms", "/legal/privacy"]

    for route in routes:
        response = await client.post(
            "/api/v1/web/pageview",
            json={
                "route": route,
                "timestamp": 1699564800000,
            },
        )
        assert response.status_code == 201


@pytest.mark.asyncio
async def test_cwv_realistic_values(client: AsyncClient):
    """Test Core Web Vitals with realistic production values."""
    response = await client.post(
        "/api/v1/web/cwv",
        json={
            "lcp": 2.3,  # Good LCP (< 2.5s)
            "fid": 80,  # Good FID (< 100ms)
            "cls": 0.05,  # Good CLS (< 0.1)
            "ttfb": 400,  # Good TTFB (< 600ms)
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "recorded"
