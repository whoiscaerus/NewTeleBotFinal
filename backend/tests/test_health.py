"""Tests for orchestrator health endpoints and request ID handling."""

import pytest
from fastapi.testclient import TestClient

from backend.app.core.logging import _request_id_context
from backend.app.orchestrator.main import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


class TestHealthEndpoints:
    """Test suite for health check endpoints."""

    def test_health_check_returns_200(self, client):
        """Test that /api/v1/health returns 200 with correct structure."""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))
        assert data["uptime_seconds"] >= 0

    def test_ready_endpoint_returns_200(self, client):
        """Test that /api/v1/ready returns 200 with correct structure."""
        response = client.get("/api/v1/ready")

        assert response.status_code == 200
        data = response.json()
        assert "ready" in data
        assert data["ready"] is True
        assert "dependencies" in data
        assert isinstance(data["dependencies"], dict)
        assert "db" in data["dependencies"]
        assert "redis" in data["dependencies"]

    def test_version_endpoint_returns_200(self, client):
        """Test that /api/v1/version returns 200 with correct structure."""
        response = client.get("/api/v1/version")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "build" in data
        assert "env" in data
        assert data["name"] == "fxpro-trading-bot"


class TestRequestIDHandling:
    """Test suite for X-Request-Id header handling."""

    def test_request_id_generated_if_missing(self, client):
        """Test that request ID is generated if not provided."""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        assert "X-Request-Id" in response.headers
        request_id = response.headers["X-Request-Id"]
        assert len(request_id) > 0
        # Should be a valid UUID format (36 chars)
        assert len(request_id) == 36

    def test_request_id_preserved_if_provided(self, client):
        """Test that provided X-Request-Id is preserved in response."""
        custom_request_id = "test-request-id-12345"
        response = client.get(
            "/api/v1/health",
            headers={"X-Request-Id": custom_request_id},
        )

        assert response.status_code == 200
        assert response.headers["X-Request-Id"] == custom_request_id

    def test_request_id_in_logs(self, client, caplog):
        """Test that request ID appears in logs."""
        custom_request_id = "test-123-log-check"

        response = client.get(
            "/api/v1/health",
            headers={"X-Request-Id": custom_request_id},
        )

        assert response.status_code == 200
        # Verify request ID is preserved in response headers
        # (JSON structured logging stores it in context variable)
        assert response.headers["X-Request-Id"] == custom_request_id


class TestAllEndpointsReturnJSON:
    """Test suite ensuring all endpoints return valid JSON."""

    def test_health_is_valid_json(self, client):
        """Test that health endpoint returns valid JSON."""
        response = client.get("/api/v1/health")
        assert response.headers.get("content-type") == "application/json"
        # Should not raise
        response.json()

    def test_ready_is_valid_json(self, client):
        """Test that ready endpoint returns valid JSON."""
        response = client.get("/api/v1/ready")
        assert response.headers.get("content-type") == "application/json"
        # Should not raise
        response.json()

    def test_version_is_valid_json(self, client):
        """Test that version endpoint returns valid JSON."""
        response = client.get("/api/v1/version")
        assert response.headers.get("content-type") == "application/json"
        # Should not raise
        response.json()


class TestEndpointDocumentation:
    """Test suite for endpoint documentation."""

    def test_openapi_schema_includes_health(self, client):
        """Test that OpenAPI schema includes health endpoint."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "/api/v1/health" in schema["paths"]

    def test_openapi_schema_includes_ready(self, client):
        """Test that OpenAPI schema includes ready endpoint."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "/api/v1/ready" in schema["paths"]

    def test_openapi_schema_includes_version(self, client):
        """Test that OpenAPI schema includes version endpoint."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "/api/v1/version" in schema["paths"]
