"""
Tests for A/B Testing Telemetry Endpoints (PR-086)

Tests cover:
- A/B variant exposure tracking (POST /api/v1/web/ab)
- A/B conversion tracking (POST /api/v1/web/ab/conversion)
- Validation of request payloads
- Prometheus metrics increments
- Error handling
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_track_ab_variant_success(client: AsyncClient):
    """Test successful A/B variant tracking."""
    response = await client.post(
        "/api/v1/web/ab",
        json={
            "experiment": "hero_copy",
            "variant": "benefit_focused",
            "timestamp": 1699564800000,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "recorded"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_track_ab_variant_invalid_experiment_empty(client: AsyncClient):
    """Test A/B tracking rejects empty experiment name."""
    response = await client.post(
        "/api/v1/web/ab",
        json={
            "experiment": "",
            "variant": "control",
            "timestamp": 1699564800000,
        },
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_track_ab_variant_invalid_variant_empty(client: AsyncClient):
    """Test A/B tracking rejects empty variant name."""
    response = await client.post(
        "/api/v1/web/ab",
        json={
            "experiment": "hero_copy",
            "variant": "",
            "timestamp": 1699564800000,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_track_ab_variant_missing_required_field(client: AsyncClient):
    """Test A/B tracking requires all fields."""
    response = await client.post(
        "/api/v1/web/ab",
        json={
            "experiment": "hero_copy",
            # Missing variant and timestamp
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ab_variant_increments_prometheus_counter(client: AsyncClient):
    """Test A/B variant tracking increments Prometheus counter."""
    # Track variant
    response = await client.post(
        "/api/v1/web/ab",
        json={
            "experiment": "pricing_layout",
            "variant": "3_tier",
            "timestamp": 1699564800000,
        },
    )
    assert response.status_code == 201

    # Verify metric recorded in Prometheus
    metrics_response = await client.get("/metrics")
    metrics_text = metrics_response.text

    # Check ab_variant_view_total metric exists
    assert "ab_variant_view_total" in metrics_text
    assert 'experiment="pricing_layout"' in metrics_text
    assert 'variant="3_tier"' in metrics_text


@pytest.mark.asyncio
async def test_track_ab_conversion_success(client: AsyncClient):
    """Test successful A/B conversion tracking."""
    response = await client.post(
        "/api/v1/web/ab/conversion",
        json={
            "experiment": "hero_copy",
            "variant": "urgency",
            "event": "signup",
            "timestamp": 1699564800000,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "recorded"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_track_ab_conversion_invalid_event_empty(client: AsyncClient):
    """Test A/B conversion rejects empty event name."""
    response = await client.post(
        "/api/v1/web/ab/conversion",
        json={
            "experiment": "cta_button",
            "variant": "start_trading",
            "event": "",
            "timestamp": 1699564800000,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_track_ab_conversion_missing_required_field(client: AsyncClient):
    """Test A/B conversion requires all fields."""
    response = await client.post(
        "/api/v1/web/ab/conversion",
        json={
            "experiment": "hero_copy",
            "variant": "control",
            # Missing event and timestamp
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ab_conversion_increments_prometheus_counter(client: AsyncClient):
    """Test A/B conversion tracking increments Prometheus counter."""
    # Track conversion
    response = await client.post(
        "/api/v1/web/ab/conversion",
        json={
            "experiment": "hero_copy",
            "variant": "benefit_focused",
            "event": "purchase",
            "timestamp": 1699564800000,
        },
    )
    assert response.status_code == 201

    # Verify metric recorded in Prometheus
    metrics_response = await client.get("/metrics")
    metrics_text = metrics_response.text

    # Check ab_conversion_total metric exists
    assert "ab_conversion_total" in metrics_text
    assert 'experiment="hero_copy"' in metrics_text
    assert 'variant="benefit_focused"' in metrics_text
    assert 'event="purchase"' in metrics_text


@pytest.mark.asyncio
async def test_ab_variant_multiple_experiments(client: AsyncClient):
    """Test tracking variants across multiple experiments."""
    # Experiment 1: hero_copy
    response1 = await client.post(
        "/api/v1/web/ab",
        json={
            "experiment": "hero_copy",
            "variant": "control",
            "timestamp": 1699564800000,
        },
    )
    assert response1.status_code == 201

    # Experiment 2: cta_button
    response2 = await client.post(
        "/api/v1/web/ab",
        json={
            "experiment": "cta_button",
            "variant": "get_started",
            "timestamp": 1699564801000,
        },
    )
    assert response2.status_code == 201

    # Verify both experiments tracked in Prometheus
    metrics_response = await client.get("/metrics")
    metrics_text = metrics_response.text

    assert 'experiment="hero_copy"' in metrics_text
    assert 'experiment="cta_button"' in metrics_text


@pytest.mark.asyncio
async def test_ab_conversion_multiple_events(client: AsyncClient):
    """Test tracking multiple conversion events."""
    # Event 1: signup
    response1 = await client.post(
        "/api/v1/web/ab/conversion",
        json={
            "experiment": "pricing_layout",
            "variant": "4_tier_with_enterprise",
            "event": "signup",
            "timestamp": 1699564800000,
        },
    )
    assert response1.status_code == 201

    # Event 2: purchase
    response2 = await client.post(
        "/api/v1/web/ab/conversion",
        json={
            "experiment": "pricing_layout",
            "variant": "4_tier_with_enterprise",
            "event": "purchase",
            "timestamp": 1699564801000,
        },
    )
    assert response2.status_code == 201

    # Verify both events tracked in Prometheus
    metrics_response = await client.get("/metrics")
    metrics_text = metrics_response.text

    assert 'event="signup"' in metrics_text
    assert 'event="purchase"' in metrics_text


@pytest.mark.asyncio
async def test_ab_experiment_names_validation(client: AsyncClient):
    """Test experiment names are properly validated."""
    # Valid: alphanumeric with underscores
    response = await client.post(
        "/api/v1/web/ab",
        json={
            "experiment": "hero_copy_v2",
            "variant": "control",
            "timestamp": 1699564800000,
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_ab_long_experiment_name_rejected(client: AsyncClient):
    """Test very long experiment names are rejected."""
    response = await client.post(
        "/api/v1/web/ab",
        json={
            "experiment": "a" * 101,  # Max length is 100
            "variant": "control",
            "timestamp": 1699564800000,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_track_cwv_with_tti(client: AsyncClient):
    """Test Core Web Vitals tracking includes TTI (PR-086 addition)."""
    response = await client.post(
        "/api/v1/web/cwv",
        json={
            "lcp": 2.5,
            "fid": 100,
            "cls": 0.1,
            "ttfb": 600,
            "tti": 3800,  # Time to Interactive (PR-086)
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "recorded"


@pytest.mark.asyncio
async def test_cwv_tti_increments_histogram(client: AsyncClient):
    """Test TTI metric is recorded in Prometheus histogram."""
    # Track TTI
    response = await client.post(
        "/api/v1/web/cwv",
        json={
            "tti": 4200,  # 4.2 seconds
        },
    )
    assert response.status_code == 201

    # Verify metric recorded in Prometheus
    metrics_response = await client.get("/metrics")
    metrics_text = metrics_response.text

    # Check web_cwv_tti_seconds histogram exists
    assert "web_cwv_tti_seconds" in metrics_text
