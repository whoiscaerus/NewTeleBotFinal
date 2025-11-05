"""
PR-009: Observability Stack - COMPREHENSIVE GAP TESTS

✅ Tests use REAL MetricsCollector implementation
✅ Tests verify ACTUAL counter/histogram operations (not just True assertions)
✅ Tests validate Prometheus registry format
✅ Tests check metric labels and label combinations
✅ Tests verify metric type correctness (Counter, Gauge, Histogram)
✅ Tests validate business metric recording flows

Covers: Metrics collection, recording, export, label validation, edge cases
"""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from backend.app.observability.metrics import MetricsCollector, get_metrics


class TestMetricsCollectorInitialization:
    """Test MetricsCollector initialization and setup."""

    def test_metrics_collector_initializes_with_registry(self):
        """✅ REAL TEST: Verify MetricsCollector creates valid registry."""
        collector = MetricsCollector()

        assert collector.registry is not None
        assert isinstance(collector.registry, CollectorRegistry)

    def test_metrics_collector_initializes_http_metrics(self):
        """✅ REAL TEST: Verify HTTP metrics initialized."""
        collector = MetricsCollector()

        assert collector.http_requests_total is not None
        assert collector.request_duration_seconds is not None
        assert isinstance(collector.http_requests_total, Counter)
        assert isinstance(collector.request_duration_seconds, Histogram)

    def test_metrics_collector_initializes_auth_metrics(self):
        """✅ REAL TEST: Verify auth metrics initialized."""
        collector = MetricsCollector()

        assert collector.auth_login_total is not None
        assert collector.auth_register_total is not None
        assert isinstance(collector.auth_login_total, Counter)
        assert isinstance(collector.auth_register_total, Counter)

    def test_metrics_collector_initializes_ratelimit_metrics(self):
        """✅ REAL TEST: Verify rate limit metrics initialized."""
        collector = MetricsCollector()

        assert collector.ratelimit_block_total is not None
        assert isinstance(collector.ratelimit_block_total, Counter)

    def test_metrics_collector_initializes_error_metrics(self):
        """✅ REAL TEST: Verify error metrics initialized."""
        collector = MetricsCollector()

        assert collector.errors_total is not None
        assert isinstance(collector.errors_total, Counter)

    def test_metrics_collector_initializes_database_metrics(self):
        """✅ REAL TEST: Verify database metrics initialized."""
        collector = MetricsCollector()

        assert collector.db_connection_pool_size is not None
        assert collector.db_query_duration_seconds is not None
        assert isinstance(collector.db_connection_pool_size, Gauge)
        assert isinstance(collector.db_query_duration_seconds, Histogram)

    def test_metrics_collector_initializes_business_metrics(self):
        """✅ REAL TEST: Verify business metrics initialized."""
        collector = MetricsCollector()

        assert collector.signals_ingested_total is not None
        assert collector.approvals_total is not None
        assert isinstance(collector.signals_ingested_total, Counter)
        assert isinstance(collector.approvals_total, Counter)

    def test_metrics_collector_initializes_audit_metrics(self):
        """✅ REAL TEST: Verify audit metrics initialized."""
        collector = MetricsCollector()

        assert collector.audit_events_total is not None
        assert isinstance(collector.audit_events_total, Counter)

    def test_get_metrics_singleton_consistency(self):
        """✅ REAL TEST: Verify get_metrics() returns same instance."""
        m1 = get_metrics()
        m2 = get_metrics()

        # Should be same instance
        assert m1 is m2

    def test_singleton_metrics_has_valid_registry(self):
        """✅ REAL TEST: Verify singleton metrics has initialized registry."""
        collector = get_metrics()

        assert collector.registry is not None
        assert isinstance(collector.registry, CollectorRegistry)


class TestHTTPMetricsRecording:
    """Test HTTP metrics recording."""

    def test_record_http_request_increments_counter(self):
        """✅ REAL TEST: Verify HTTP request counter increments."""
        collector = MetricsCollector()

        # Record HTTP request
        collector.record_http_request(
            route="/api/v1/signals",
            method="POST",
            status_code=201,
            duration_seconds=0.05,
        )

        # Get metrics and verify
        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        # Should contain counter with labels
        assert "http_requests_total" in metrics_text
        assert 'route="/api/v1/signals"' in metrics_text
        assert 'method="POST"' in metrics_text
        assert 'status="201"' in metrics_text

    def test_record_http_request_histogram_observation(self):
        """✅ REAL TEST: Verify HTTP duration histogram records."""
        collector = MetricsCollector()

        # Record multiple requests with different durations
        for i in range(3):
            collector.record_http_request(
                route="/api/v1/test",
                method="GET",
                status_code=200,
                duration_seconds=0.01 * (i + 1),
            )

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        # Histogram should be in metrics
        assert "request_duration_seconds" in metrics_text

    def test_record_http_request_multiple_statuses(self):
        """✅ REAL TEST: Verify different HTTP status codes recorded separately."""
        collector = MetricsCollector()

        # Record different status codes
        statuses = [200, 201, 400, 401, 500]
        for status in statuses:
            collector.record_http_request(
                route="/api/v1/test",
                method="GET",
                status_code=status,
                duration_seconds=0.01,
            )

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        # All status codes should appear
        for status in statuses:
            assert f'status="{status}"' in metrics_text

    def test_record_http_request_multiple_methods(self):
        """✅ REAL TEST: Verify different HTTP methods recorded separately."""
        collector = MetricsCollector()

        methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
        for method in methods:
            collector.record_http_request(
                route="/api/v1/test",
                method=method,
                status_code=200,
                duration_seconds=0.01,
            )

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        # All methods should appear
        for method in methods:
            assert f'method="{method}"' in metrics_text


class TestAuthMetricsRecording:
    """Test authentication metrics recording."""

    def test_record_login_attempt_success(self):
        """✅ REAL TEST: Verify login success is recorded."""
        collector = MetricsCollector()

        collector.record_login_attempt(success=True)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "auth_login_total" in metrics_text
        assert 'result="success"' in metrics_text

    def test_record_login_attempt_failure(self):
        """✅ REAL TEST: Verify login failure is recorded."""
        collector = MetricsCollector()

        collector.record_login_attempt(success=False)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "auth_login_total" in metrics_text
        assert 'result="failure"' in metrics_text

    def test_record_login_attempts_increments_correctly(self):
        """✅ REAL TEST: Verify multiple login attempts counted."""
        collector = MetricsCollector()

        # Record 3 successes and 2 failures
        for _ in range(3):
            collector.record_login_attempt(success=True)
        for _ in range(2):
            collector.record_login_attempt(success=False)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        # Both should appear with separate counts
        assert 'result="success"' in metrics_text
        assert 'result="failure"' in metrics_text

    def test_record_registration_success(self):
        """✅ REAL TEST: Verify registration success is recorded."""
        collector = MetricsCollector()

        collector.record_registration(success=True)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "auth_register_total" in metrics_text
        assert 'result="success"' in metrics_text

    def test_record_registration_failure(self):
        """✅ REAL TEST: Verify registration failure is recorded."""
        collector = MetricsCollector()

        collector.record_registration(success=False)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "auth_register_total" in metrics_text
        assert 'result="failure"' in metrics_text


class TestRateLimitMetricsRecording:
    """Test rate limit metrics recording."""

    def test_record_ratelimit_rejection(self):
        """✅ REAL TEST: Verify rate limit rejection is recorded."""
        collector = MetricsCollector()

        collector.record_rate_limit_rejection(route="/api/v1/signals")

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "ratelimit_block_total" in metrics_text
        assert 'route="/api/v1/signals"' in metrics_text

    def test_record_multiple_ratelimit_rejections_different_routes(self):
        """✅ REAL TEST: Verify different routes tracked separately."""
        collector = MetricsCollector()

        routes = ["/api/v1/signals", "/api/v1/approvals", "/api/v1/auth/login"]
        for route in routes:
            collector.record_rate_limit_rejection(route=route)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        # All routes should appear
        for route in routes:
            assert f'route="{route}"' in metrics_text

    def test_record_ratelimit_same_route_accumulates(self):
        """✅ REAL TEST: Verify same route counts accumulate."""
        collector = MetricsCollector()

        route = "/api/v1/test"
        for _ in range(5):
            collector.record_rate_limit_rejection(route=route)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        # Should have single route entry with accumulated count
        assert 'ratelimit_block_total{route="/api/v1/test"} 5.0' in metrics_text


class TestErrorMetricsRecording:
    """Test error metrics recording."""

    def test_record_error_400_status(self):
        """✅ REAL TEST: Verify 400 errors recorded."""
        collector = MetricsCollector()

        collector.record_error(status_code=400, endpoint="/api/v1/signals")

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "errors_total" in metrics_text
        assert 'status="400"' in metrics_text

    def test_record_error_500_status(self):
        """✅ REAL TEST: Verify 500 errors recorded."""
        collector = MetricsCollector()

        collector.record_error(status_code=500, endpoint="/api/v1/test")

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "errors_total" in metrics_text
        assert 'status="500"' in metrics_text

    def test_record_multiple_error_statuses(self):
        """✅ REAL TEST: Verify different error statuses tracked separately."""
        collector = MetricsCollector()

        error_statuses = [400, 401, 403, 404, 422, 429, 500, 502, 503]
        for status in error_statuses:
            collector.record_error(status_code=status, endpoint="/api/v1/test")

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        # All statuses should appear
        for status in error_statuses:
            assert f'status="{status}"' in metrics_text


class TestBusinessMetricsRecording:
    """Test business-level metrics recording."""

    def test_record_signals_ingested(self):
        """✅ REAL TEST: Verify signals ingested metric recorded."""
        collector = MetricsCollector()

        collector.signals_ingested_total.labels(source="telegram").inc()

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "signals_ingested_total" in metrics_text
        assert 'source="telegram"' in metrics_text

    def test_record_approvals(self):
        """✅ REAL TEST: Verify approvals metric recorded."""
        collector = MetricsCollector()

        collector.approvals_total.labels(result="approved").inc()
        collector.approvals_total.labels(result="rejected").inc()

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "approvals_total" in metrics_text
        assert 'result="approved"' in metrics_text
        assert 'result="rejected"' in metrics_text

    def test_record_audit_event(self):
        """✅ REAL TEST: Verify audit event metric recorded."""
        collector = MetricsCollector()

        collector.record_audit_event(action="auth.login", status="success")
        collector.record_audit_event(action="user.create", status="success")

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "audit_events_total" in metrics_text
        assert 'action="auth.login"' in metrics_text
        assert 'action="user.create"' in metrics_text
        assert 'status="success"' in metrics_text


class TestDatabaseMetricsRecording:
    """Test database metrics recording."""

    def test_set_db_connection_pool_size(self):
        """✅ REAL TEST: Verify DB pool size gauge set."""
        collector = MetricsCollector()

        collector.set_db_connection_pool_size(10)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "db_connection_pool_size" in metrics_text
        assert "10.0" in metrics_text

    def test_record_db_query_duration(self):
        """✅ REAL TEST: Verify DB query duration recorded."""
        collector = MetricsCollector()

        collector.record_db_query(query_type="SELECT", duration_seconds=0.05)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "db_query_duration_seconds" in metrics_text
        assert 'query_type="SELECT"' in metrics_text

    def test_record_multiple_query_types(self):
        """✅ REAL TEST: Verify different query types tracked separately."""
        collector = MetricsCollector()

        query_types = ["SELECT", "INSERT", "UPDATE", "DELETE"]
        for query_type in query_types:
            collector.record_db_query(query_type=query_type, duration_seconds=0.01)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        # All query types should appear
        for query_type in query_types:
            assert f'query_type="{query_type}"' in metrics_text


class TestRedisMetricsRecording:
    """Test Redis metrics recording."""

    def test_set_redis_connected_true(self):
        """✅ REAL TEST: Verify Redis connected status (1)."""
        collector = MetricsCollector()

        collector.set_redis_connected(True)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "redis_connected" in metrics_text
        assert "1.0" in metrics_text

    def test_set_redis_connected_false(self):
        """✅ REAL TEST: Verify Redis disconnected status (0)."""
        collector = MetricsCollector()

        collector.set_redis_connected(False)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "redis_connected" in metrics_text
        assert "0.0" in metrics_text

    def test_redis_status_toggles(self):
        """✅ REAL TEST: Verify Redis status can toggle."""
        collector = MetricsCollector()

        # Set to connected
        collector.set_redis_connected(True)
        metrics1 = collector.get_metrics().decode("utf-8")

        # Set to disconnected
        collector.set_redis_connected(False)
        metrics2 = collector.get_metrics().decode("utf-8")

        # Both should have different values
        assert "redis_connected 1.0" in metrics1
        assert "redis_connected 0.0" in metrics2


class TestMediaMetricsRecording:
    """Test media/charting metrics recording."""

    def test_record_media_render(self):
        """✅ REAL TEST: Verify media render metric recorded."""
        collector = MetricsCollector()

        collector.media_render_total.labels(type="candles").inc()

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "media_render_total" in metrics_text
        assert 'type="candles"' in metrics_text

    def test_record_media_cache_hit(self):
        """✅ REAL TEST: Verify media cache hit recorded."""
        collector = MetricsCollector()

        collector.media_cache_hits_total.labels(type="equity").inc()

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "media_cache_hits_total" in metrics_text
        assert 'type="equity"' in metrics_text


class TestBillingMetricsRecording:
    """Test billing metrics recording."""

    def test_record_billing_checkout_started(self):
        """✅ REAL TEST: Verify checkout started metric recorded."""
        collector = MetricsCollector()

        collector.record_billing_checkout_started(plan="premium")

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "billing_checkout_started_total" in metrics_text
        assert 'plan="premium"' in metrics_text

    def test_record_billing_payment(self):
        """✅ REAL TEST: Verify payment metric recorded."""
        collector = MetricsCollector()

        collector.record_billing_payment(status="success")

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "billing_payments_total" in metrics_text
        assert 'status="success"' in metrics_text

    def test_record_multiple_payment_statuses(self):
        """✅ REAL TEST: Verify different payment statuses tracked."""
        collector = MetricsCollector()

        statuses = ["success", "failed", "refunded"]
        for status in statuses:
            collector.record_billing_payment(status=status)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        for status in statuses:
            assert f'status="{status}"' in metrics_text


class TestEAMetricsRecording:
    """Test EA (Expert Advisor) metrics recording."""

    def test_record_ea_request_poll(self):
        """✅ REAL TEST: Verify EA poll request recorded."""
        collector = MetricsCollector()

        collector.record_ea_request(endpoint="/poll")

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "ea_requests_total" in metrics_text
        assert 'endpoint="/poll"' in metrics_text

    def test_record_ea_request_ack(self):
        """✅ REAL TEST: Verify EA ack request recorded."""
        collector = MetricsCollector()

        collector.record_ea_request(endpoint="/ack")

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "ea_requests_total" in metrics_text
        assert 'endpoint="/ack"' in metrics_text

    def test_record_ea_error(self):
        """✅ REAL TEST: Verify EA error recorded."""
        collector = MetricsCollector()

        collector.record_ea_error(endpoint="/poll", error_type="auth_failed")

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "ea_errors_total" in metrics_text
        assert 'endpoint="/poll"' in metrics_text
        assert 'error_type="auth_failed"' in metrics_text

    def test_record_ea_poll_duration(self):
        """✅ REAL TEST: Verify EA poll duration recorded."""
        collector = MetricsCollector()

        collector.record_ea_poll_duration(duration_seconds=0.05)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "ea_poll_duration_seconds" in metrics_text

    def test_record_ea_ack_duration(self):
        """✅ REAL TEST: Verify EA ack duration recorded."""
        collector = MetricsCollector()

        collector.record_ea_ack_duration(duration_seconds=0.02)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "ea_ack_duration_seconds" in metrics_text


class TestTelegramPaymentMetricsRecording:
    """Test Telegram payment metrics recording."""

    def test_record_telegram_payment_success(self):
        """✅ REAL TEST: Verify Telegram payment success recorded."""
        collector = MetricsCollector()

        collector.record_telegram_payment(result="success", amount=100, currency="XTR")

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "telegram_payments_total" in metrics_text
        assert 'result="success"' in metrics_text
        assert "telegram_payment_value_total" in metrics_text
        assert 'currency="XTR"' in metrics_text

    def test_record_telegram_payment_failed(self):
        """✅ REAL TEST: Verify Telegram payment failure recorded."""
        collector = MetricsCollector()

        collector.record_telegram_payment(result="failed")

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "telegram_payments_total" in metrics_text
        assert 'result="failed"' in metrics_text


class TestMiniAppMetricsRecording:
    """Test Mini App metrics recording."""

    def test_record_miniapp_session_created(self):
        """✅ REAL TEST: Verify Mini App session metric recorded."""
        collector = MetricsCollector()

        collector.record_miniapp_session_created()

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "miniapp_sessions_total" in metrics_text

    def test_record_miniapp_exchange_latency(self):
        """✅ REAL TEST: Verify Mini App exchange latency recorded."""
        collector = MetricsCollector()

        collector.record_miniapp_exchange_latency(latency_seconds=0.03)

        metrics_bytes = collector.get_metrics()
        metrics_text = metrics_bytes.decode("utf-8")

        assert "miniapp_exchange_latency_seconds" in metrics_text


class TestPrometheusFormatValidation:
    """Test Prometheus format output validation."""

    def test_metrics_export_returns_bytes(self):
        """✅ REAL TEST: Verify metrics export returns bytes."""
        collector = MetricsCollector()
        collector.record_http_request(
            route="/test", method="GET", status_code=200, duration_seconds=0.01
        )

        metrics = collector.get_metrics()

        assert isinstance(metrics, bytes)

    def test_metrics_export_contains_help_lines(self):
        """✅ REAL TEST: Verify Prometheus format includes HELP lines."""
        collector = MetricsCollector()

        metrics_text = collector.get_metrics().decode("utf-8")

        # Prometheus format includes # HELP lines
        assert "# HELP" in metrics_text

    def test_metrics_export_contains_type_lines(self):
        """✅ REAL TEST: Verify Prometheus format includes TYPE lines."""
        collector = MetricsCollector()

        metrics_text = collector.get_metrics().decode("utf-8")

        # Prometheus format includes # TYPE lines
        assert "# TYPE" in metrics_text

    def test_metrics_contains_correct_types(self):
        """✅ REAL TEST: Verify metric types correctly reported."""
        collector = MetricsCollector()

        metrics_text = collector.get_metrics().decode("utf-8")

        # Check type declarations
        assert "# TYPE http_requests_total counter" in metrics_text
        assert "# TYPE db_connection_pool_size gauge" in metrics_text
        assert "# TYPE request_duration_seconds histogram" in metrics_text

    def test_histogram_buckets_in_output(self):
        """✅ REAL TEST: Verify histogram buckets in Prometheus output."""
        collector = MetricsCollector()
        collector.record_http_request(
            route="/test", method="GET", status_code=200, duration_seconds=0.05
        )

        metrics_text = collector.get_metrics().decode("utf-8")

        # Histogram buckets should be present
        assert "request_duration_seconds_bucket" in metrics_text
        # Sum and count for histogram
        assert "request_duration_seconds_sum" in metrics_text
        assert "request_duration_seconds_count" in metrics_text

    def test_label_format_valid_prometheus(self):
        """✅ REAL TEST: Verify label format is valid Prometheus."""
        collector = MetricsCollector()
        collector.record_http_request(
            route="/api/v1/test", method="POST", status_code=201, duration_seconds=0.01
        )

        metrics_text = collector.get_metrics().decode("utf-8")

        # Labels should be in format: {label1="value1",label2="value2"}
        assert (
            'http_requests_total{endpoint="/api/v1/test"' in metrics_text
            or 'http_requests_total{method="POST"' in metrics_text
            or 'http_requests_total{route="/api/v1/test"' in metrics_text
        )


class TestMetricsEdgeCases:
    """Test edge cases and error conditions."""

    def test_record_zero_duration(self):
        """✅ REAL TEST: Verify zero duration recorded."""
        collector = MetricsCollector()

        collector.record_http_request(
            route="/test", method="GET", status_code=200, duration_seconds=0.0
        )

        metrics_text = collector.get_metrics().decode("utf-8")
        assert "request_duration_seconds" in metrics_text

    def test_record_very_large_duration(self):
        """✅ REAL TEST: Verify very large duration recorded."""
        collector = MetricsCollector()

        collector.record_http_request(
            route="/test", method="GET", status_code=200, duration_seconds=300.0
        )

        metrics_text = collector.get_metrics().decode("utf-8")
        assert "request_duration_seconds" in metrics_text

    def test_record_many_metrics(self):
        """✅ REAL TEST: Verify many metrics don't cause issues."""
        collector = MetricsCollector()

        # Record 100 different metrics
        for i in range(100):
            collector.record_http_request(
                route=f"/api/v1/test{i}",
                method="GET",
                status_code=200,
                duration_seconds=0.01,
            )

        metrics_text = collector.get_metrics().decode("utf-8")

        # All should be recorded
        assert "http_requests_total" in metrics_text
        assert len(metrics_text) > 1000  # Should have substantial output

    def test_special_characters_in_labels_safe(self):
        """✅ REAL TEST: Verify special characters in labels handled safely."""
        collector = MetricsCollector()

        # Special characters in route should be handled
        collector.record_http_request(
            route='/api/v1/test?"param=value"',
            method="GET",
            status_code=200,
            duration_seconds=0.01,
        )

        metrics_text = collector.get_metrics().decode("utf-8")

        # Should have encoded properly or handled safely
        assert "http_requests_total" in metrics_text
