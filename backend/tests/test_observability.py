"""Observability metrics tests."""

from unittest.mock import MagicMock, patch

import pytest

from backend.app.observability.metrics import MetricsCollector, get_metrics


class TestMetricsCollector:
    """Test metrics collector."""

    def test_metrics_collector_initialization(self):
        """Test metrics collector initializes."""
        with patch("backend.app.observability.metrics.CollectorRegistry"):
            collector = MetricsCollector()
            assert collector is not None

    def test_record_http_request(self):
        """Test recording HTTP request metrics."""
        with patch("backend.app.observability.metrics.CollectorRegistry"):
            with patch("backend.app.observability.metrics.Counter") as mock_counter:
                with patch(
                    "backend.app.observability.metrics.Histogram"
                ) as mock_histogram:
                    collector = MetricsCollector()

                    # Mock the metric objects
                    mock_counter.return_value = MagicMock()
                    mock_histogram.return_value = MagicMock()

                    # Record request
                    collector.record_http_request(
                        route="/api/v1/auth/login",
                        method="POST",
                        status_code=200,
                        duration_seconds=0.05,
                    )

    def test_record_login_attempt_success(self):
        """Test recording successful login."""
        with patch("backend.app.observability.metrics.CollectorRegistry"):
            with patch("backend.app.observability.metrics.Counter") as mock_counter:
                collector = MetricsCollector()
                mock_counter.return_value = MagicMock()

                collector.record_login_attempt(success=True)

    def test_record_login_attempt_failure(self):
        """Test recording failed login."""
        with patch("backend.app.observability.metrics.CollectorRegistry"):
            with patch("backend.app.observability.metrics.Counter") as mock_counter:
                collector = MetricsCollector()
                mock_counter.return_value = MagicMock()

                collector.record_login_attempt(success=False)

    def test_record_rate_limit_rejection(self):
        """Test recording rate limit rejection."""
        with patch("backend.app.observability.metrics.CollectorRegistry"):
            with patch("backend.app.observability.metrics.Counter") as mock_counter:
                collector = MetricsCollector()
                mock_counter.return_value = MagicMock()

                collector.record_rate_limit_rejection(route="/api/v1/auth/login")

    def test_record_error(self):
        """Test recording error metrics."""
        with patch("backend.app.observability.metrics.CollectorRegistry"):
            with patch("backend.app.observability.metrics.Counter") as mock_counter:
                collector = MetricsCollector()
                mock_counter.return_value = MagicMock()

                collector.record_error(status_code=500, endpoint="/api/v1/auth/login")

    def test_record_audit_event(self):
        """Test recording audit event metric."""
        with patch("backend.app.observability.metrics.CollectorRegistry"):
            with patch("backend.app.observability.metrics.Counter") as mock_counter:
                collector = MetricsCollector()
                mock_counter.return_value = MagicMock()

                collector.record_audit_event(action="auth.login", status="success")

    def test_set_redis_connected(self):
        """Test setting Redis connection status."""
        with patch("backend.app.observability.metrics.CollectorRegistry"):
            with patch("backend.app.observability.metrics.Gauge") as mock_gauge:
                collector = MetricsCollector()
                mock_gauge.return_value = MagicMock()

                collector.set_redis_connected(True)
                collector.set_redis_connected(False)

    def test_get_metrics_singleton(self):
        """Test get_metrics returns same instance."""
        with patch("backend.app.observability.metrics.CollectorRegistry"):
            with patch("backend.app.observability.metrics.Counter"):
                with patch("backend.app.observability.metrics.Histogram"):
                    with patch("backend.app.observability.metrics.Gauge"):
                        metrics1 = get_metrics()
                        metrics2 = get_metrics()

                        assert metrics1 is metrics2


class TestMetricsExposure:
    """Test metrics exposure in HTTP."""

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, client):
        """Test /metrics endpoint returns Prometheus format."""
        # Metrics endpoint not created yet in main.py
        # This test will be updated when /api/v1/metrics is added


class TestMetricsInstrumentation:
    """Test metrics are properly instrumented."""

    def test_http_request_instrumentation(self):
        """Test HTTP requests can be instrumented."""
        with patch("backend.app.observability.metrics.CollectorRegistry"):
            with patch("backend.app.observability.metrics.Counter") as mock_counter:
                with patch(
                    "backend.app.observability.metrics.Histogram"
                ) as mock_histogram:
                    collector = MetricsCollector()

                    # Simulate multiple requests
                    for i in range(5):
                        collector.record_http_request(
                            route="/api/v1/auth/login",
                            method="POST",
                            status_code=200 if i < 4 else 401,
                            duration_seconds=0.01 * (i + 1),
                        )

    def test_business_metrics_placeholder(self):
        """Test business metrics are defined but not used yet."""
        with patch("backend.app.observability.metrics.CollectorRegistry"):
            with patch("backend.app.observability.metrics.Counter") as mock_counter:
                collector = MetricsCollector()
                mock_counter.return_value = MagicMock()

                # Verify business metrics exist
                assert hasattr(collector, "signals_ingested_total")
                assert hasattr(collector, "approvals_total")
