"""OpenTelemetry metrics collection."""

import logging

try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
except ImportError:
    raise ImportError(
        "prometheus-client not installed. Install with: pip install prometheus-client"
    )

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects and exposes Prometheus metrics."""

    def __init__(self):
        """Initialize metrics collector."""
        self.registry = CollectorRegistry()

        # HTTP metrics
        self.http_requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["route", "method", "status"],
            registry=self.registry,
        )

        self.request_duration_seconds = Histogram(
            "request_duration_seconds",
            "HTTP request duration in seconds",
            ["route", "method"],
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
            registry=self.registry,
        )

        # Authentication metrics
        self.auth_login_total = Counter(
            "auth_login_total",
            "Total login attempts",
            ["result"],  # success, failure
            registry=self.registry,
        )

        self.auth_register_total = Counter(
            "auth_register_total",
            "Total user registrations",
            ["result"],  # success, failure
            registry=self.registry,
        )

        # Rate limiting metrics
        self.ratelimit_block_total = Counter(
            "ratelimit_block_total",
            "Total rate limit rejections",
            ["route"],
            registry=self.registry,
        )

        # Error metrics
        self.errors_total = Counter(
            "errors_total",
            "Total errors",
            ["status", "endpoint"],
            registry=self.registry,
        )

        # Database metrics (placeholder for later)
        self.db_connection_pool_size = Gauge(
            "db_connection_pool_size",
            "Database connection pool size",
            registry=self.registry,
        )

        self.db_query_duration_seconds = Histogram(
            "db_query_duration_seconds",
            "Database query duration",
            ["query_type"],
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0),
            registry=self.registry,
        )

        # Redis metrics
        self.redis_connected = Gauge(
            "redis_connected",
            "Redis connection status (1=connected, 0=disconnected)",
            registry=self.registry,
        )

        # Business metrics (placeholders for trading domains)
        self.signals_ingested_total = Counter(
            "signals_ingested_total",
            "Total trading signals ingested",
            ["source"],
            registry=self.registry,
        )

        self.approvals_total = Counter(
            "approvals_total",
            "Total signal approvals",
            ["result"],  # approved, rejected
            registry=self.registry,
        )

        # Audit metrics
        self.audit_events_total = Counter(
            "audit_events_total",
            "Total audit events recorded",
            ["action", "status"],
            registry=self.registry,
        )

        logger.info("Metrics collector initialized")

    def record_http_request(
        self,
        route: str,
        method: str,
        status_code: int,
        duration_seconds: float,
    ):
        """Record HTTP request metrics.

        Args:
            route: API route (e.g., '/api/v1/auth/login')
            method: HTTP method (GET, POST, etc.)
            status_code: HTTP response status code
            duration_seconds: Request duration in seconds
        """
        self.http_requests_total.labels(
            route=route, method=method, status=status_code
        ).inc()
        self.request_duration_seconds.labels(route=route, method=method).observe(
            duration_seconds
        )

    def record_login_attempt(self, success: bool):
        """Record login attempt.

        Args:
            success: Whether login succeeded
        """
        result = "success" if success else "failure"
        self.auth_login_total.labels(result=result).inc()

    def record_registration(self, success: bool):
        """Record user registration.

        Args:
            success: Whether registration succeeded
        """
        result = "success" if success else "failure"
        self.auth_register_total.labels(result=result).inc()

    def record_rate_limit_rejection(self, route: str):
        """Record rate limit rejection.

        Args:
            route: API route that was rate limited
        """
        self.ratelimit_block_total.labels(route=route).inc()

    def record_error(self, status_code: int, endpoint: str):
        """Record error.

        Args:
            status_code: HTTP status code
            endpoint: API endpoint
        """
        self.errors_total.labels(status=status_code, endpoint=endpoint).inc()

    def record_audit_event(self, action: str, status: str):
        """Record audit event.

        Args:
            action: Audit action (e.g., 'auth.login')
            status: Status (success, failure, error)
        """
        self.audit_events_total.labels(action=action, status=status).inc()

    def set_db_connection_pool_size(self, size: int):
        """Set database connection pool size.

        Args:
            size: Number of connections in pool
        """
        self.db_connection_pool_size.set(size)

    def record_db_query(self, query_type: str, duration_seconds: float):
        """Record database query.

        Args:
            query_type: Type of query (select, insert, update, etc.)
            duration_seconds: Query duration
        """
        self.db_query_duration_seconds.labels(query_type=query_type).observe(
            duration_seconds
        )

    def set_redis_connected(self, connected: bool):
        """Set Redis connection status.

        Args:
            connected: True if connected, False otherwise
        """
        self.redis_connected.set(1 if connected else 0)

    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus format.

        Returns:
            bytes: Prometheus-formatted metrics
        """
        return generate_latest(self.registry)


# Global metrics instance
_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Get or initialize global metrics collector.

    Returns:
        MetricsCollector: Global instance
    """
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
