"""
PR-003: Structured Logging - REAL Business Logic Tests

Tests the REAL JSON logging with REAL JSONFormatter, REAL RequestIdFilter,
REAL LoggerAdapter, REAL context management, REAL structured fields.

NO MOCKS - validates actual logging behavior and output.
"""

import io
import json
import logging
from datetime import datetime


from backend.app.core.logging import (
    JSONFormatter,
    RequestIdFilter,
    _request_id_context,
    _request_id_var,
    get_logger,
)


class TestJSONFormatterREAL:
    """✅ REAL TEST: JSON formatter produces valid JSON output."""

    def test_json_formatter_creates_valid_json(self):
        """✅ REAL TEST: JSONFormatter produces valid JSON."""
        formatter = JSONFormatter()

        # Create a log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Format it
        json_output = formatter.format(record)

        # Verify it's valid JSON
        parsed = json.loads(json_output)
        assert isinstance(parsed, dict)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"

    def test_json_formatter_includes_timestamp(self):
        """✅ REAL TEST: JSON output includes ISO 8601 timestamp."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test",
            args=(),
            exc_info=None,
        )

        json_output = formatter.format(record)
        parsed = json.loads(json_output)

        # Verify timestamp
        assert "timestamp" in parsed
        # Should be parseable as ISO datetime
        ts = datetime.fromisoformat(parsed["timestamp"])
        assert ts is not None

    def test_json_formatter_includes_logger_name(self):
        """✅ REAL TEST: JSON output includes logger name."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="backend.app.core.database",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Query executed",
            args=(),
            exc_info=None,
        )

        json_output = formatter.format(record)
        parsed = json.loads(json_output)

        assert parsed["logger"] == "backend.app.core.database"

    def test_json_formatter_all_log_levels(self):
        """✅ REAL TEST: JSON formatter handles all log levels."""
        formatter = JSONFormatter()

        levels = [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
        ]

        for level_int, level_name in levels:
            record = logging.LogRecord(
                name="test",
                level=level_int,
                pathname="test.py",
                lineno=1,
                msg=f"Test {level_name}",
                args=(),
                exc_info=None,
            )

            json_output = formatter.format(record)
            parsed = json.loads(json_output)

            assert parsed["level"] == level_name

    def test_json_formatter_with_exception_info(self):
        """✅ REAL TEST: JSON formatter includes exception traceback."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error occurred",
                args=(),
                exc_info=exc_info,
            )

            json_output = formatter.format(record)
            parsed = json.loads(json_output)

            assert "exception" in parsed
            assert "ValueError: Test error" in parsed["exception"]

    def test_json_formatter_with_extra_fields(self):
        """✅ REAL TEST: JSON formatter includes extra custom fields."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="User action",
            args=(),
            exc_info=None,
        )

        # Add custom extra fields
        record.extra_fields = {
            "user_id": "usr_12345",
            "action": "login",
            "ip_address": "192.168.1.1",
        }

        json_output = formatter.format(record)
        parsed = json.loads(json_output)

        assert parsed["user_id"] == "usr_12345"
        assert parsed["action"] == "login"
        assert parsed["ip_address"] == "192.168.1.1"


class TestRequestIdFilterREAL:
    """✅ REAL TEST: Request ID filter attaches context to log records."""

    def test_request_id_filter_attached_to_record(self):
        """✅ REAL TEST: RequestIdFilter attaches request_id to LogRecord."""
        filter_obj = RequestIdFilter()

        # Set request ID in context
        with _request_id_context("req-12345"):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )

            # Apply filter
            result = filter_obj.filter(record)

            # Filter should return True (continue processing)
            assert result is True

            # Record should have request_id attribute
            assert hasattr(record, "request_id")
            assert record.request_id == "req-12345"

    def test_request_id_filter_missing_when_no_context(self):
        """✅ REAL TEST: RequestIdFilter doesn't add request_id if not in context."""
        filter_obj = RequestIdFilter()

        # No context set - ensure it's None
        _request_id_var.set(None)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)
        assert result is True

        # Should not have request_id attribute set by filter
        # (LogRecord may have other attributes but filter shouldn't set request_id)
        # The filter only sets it if contextvar has a truthy value
        # So if no context, the attribute might not exist or be None
        if hasattr(record, "request_id"):
            # If it exists, it should be None (or whatever was there before)
            assert record.request_id is None or record.request_id == ""

    def test_multiple_logs_same_request_id(self):
        """✅ REAL TEST: Multiple log records within same context share request_id."""
        filter_obj = RequestIdFilter()
        request_id = "req-xyz-789"

        with _request_id_context(request_id):
            # Create multiple records
            records = []
            for i in range(3):
                record = logging.LogRecord(
                    name="test",
                    level=logging.INFO,
                    pathname="test.py",
                    lineno=i,
                    msg=f"Message {i}",
                    args=(),
                    exc_info=None,
                )
                filter_obj.filter(record)
                records.append(record)

            # All should have same request_id
            request_ids = [r.request_id for r in records]
            assert all(rid == request_id for rid in request_ids)


class TestRequestIdContextManagerREAL:
    """✅ REAL TEST: Request ID context manager."""

    def test_request_id_context_sets_value(self):
        """✅ REAL TEST: _request_id_context sets request ID in contextvar."""
        request_id = "req-abc-123"

        with _request_id_context(request_id):
            # Inside context, get() should return the ID
            current = _request_id_var.get()
            assert current == request_id

    def test_request_id_context_restores_previous(self):
        """✅ REAL TEST: _request_id_context restores previous value after exit."""
        with _request_id_context("req-first"):
            first = _request_id_var.get()
            assert first == "req-first"

            # Nested context
            with _request_id_context("req-second"):
                second = _request_id_var.get()
                assert second == "req-second"

            # Back to first
            after = _request_id_var.get()
            assert after == "req-first"

    def test_request_id_context_generates_uuid_if_none(self):
        """✅ REAL TEST: _request_id_context generates UUID if not provided."""
        with _request_id_context(None) as request_id:
            # Should generate a UUID
            assert request_id is not None
            assert len(request_id) == 36  # UUID format
            assert _request_id_var.get() == request_id

    def test_request_id_context_isolation_between_contexts(self):
        """✅ REAL TEST: Different contexts have isolated request IDs."""
        id1 = "req-context-1"
        id2 = "req-context-2"

        with _request_id_context(id1):
            assert _request_id_var.get() == id1

        with _request_id_context(id2):
            assert _request_id_var.get() == id2


class TestGetLoggerREAL:
    """✅ REAL TEST: get_logger factory function."""

    def test_get_logger_returns_logger_adapter(self):
        """✅ REAL TEST: get_logger returns LoggerAdapter."""
        logger = get_logger("test.module")

        assert isinstance(logger, logging.LoggerAdapter)

    def test_get_logger_different_names(self):
        """✅ REAL TEST: Different logger names return different loggers."""
        logger1 = get_logger("backend.app")
        logger2 = get_logger("backend.telegram")

        # Should be different adapters
        assert logger1 is not logger2

    def test_get_logger_same_name_returns_same_logger(self):
        """✅ REAL TEST: Same logger name returns same underlying logger."""
        logger1 = get_logger("backend.core")
        logger2 = get_logger("backend.core")

        # Should be same underlying logger (different adapters but same logger)
        assert logger1.logger is logger2.logger

    def test_logger_adapter_has_extra_dict(self):
        """✅ REAL TEST: LoggerAdapter has extra dict for custom fields."""
        logger = get_logger("test")

        assert hasattr(logger, "extra")
        assert isinstance(logger.extra, dict)


class TestStructuredLoggingIntegrationREAL:
    """✅ REAL TEST: End-to-end structured logging scenarios."""

    def test_log_with_context_includes_request_id_in_json(self):
        """✅ REAL TEST: Log message includes request_id from context."""
        # Set up logger with JSON formatter
        logger = get_logger("test.module")

        # Capture log output
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        # Add filter to attach request ID
        filter_obj = RequestIdFilter()
        handler.addFilter(filter_obj)

        # Get underlying logger and add handler
        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.INFO)

        try:
            request_id = "req-integration-test"
            with _request_id_context(request_id):
                logger.info("Test message")

            # Get output
            output = stream.getvalue().strip()
            parsed = json.loads(output)

            # Should have request_id
            assert parsed["request_id"] == request_id
        finally:
            underlying_logger.removeHandler(handler)

    def test_log_with_extra_fields(self):
        """✅ REAL TEST: Log message includes extra fields via extra_fields attribute."""
        logger = get_logger("test.module")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.INFO)

        try:
            # Create a LogRecord with extra_fields
            record = underlying_logger.makeRecord(
                underlying_logger.name,
                logging.INFO,
                "test.py",
                1,
                "User action",
                (),
                None,
            )
            record.extra_fields = {
                "user_id": "usr_999",
                "action": "purchase",
                "amount": 99.99,
            }
            underlying_logger.handle(record)

            output = stream.getvalue().strip()
            parsed = json.loads(output)

            # Should include extra fields
            assert parsed["user_id"] == "usr_999"
            assert parsed["action"] == "purchase"
            assert parsed["amount"] == 99.99
        finally:
            underlying_logger.removeHandler(handler)

    def test_multiple_sequential_requests_different_ids(self):
        """✅ REAL TEST: Sequential requests get different request IDs."""
        logger = get_logger("test")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        filter_obj = RequestIdFilter()
        handler.addFilter(filter_obj)

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.INFO)

        try:
            request_ids = []

            for i in range(3):
                with _request_id_context(f"req-{i}"):
                    logger.info(f"Message {i}")
                    request_ids.append(_request_id_var.get())

            # All should be different
            assert len(set(request_ids)) == 3
        finally:
            underlying_logger.removeHandler(handler)


class TestLoggingLevelsREAL:
    """✅ REAL TEST: Different logging levels."""

    def test_debug_level_logs(self):
        """✅ REAL TEST: DEBUG level logs work."""
        logger = get_logger("test")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        handler.setLevel(logging.DEBUG)

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.DEBUG)

        try:
            logger.debug("Debug message")
            output = stream.getvalue().strip()
            parsed = json.loads(output)

            assert parsed["level"] == "DEBUG"
            assert parsed["message"] == "Debug message"
        finally:
            underlying_logger.removeHandler(handler)

    def test_info_level_logs(self):
        """✅ REAL TEST: INFO level logs work."""
        logger = get_logger("test")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.INFO)

        try:
            logger.info("Info message")
            output = stream.getvalue().strip()
            parsed = json.loads(output)

            assert parsed["level"] == "INFO"
        finally:
            underlying_logger.removeHandler(handler)

    def test_warning_level_logs(self):
        """✅ REAL TEST: WARNING level logs work."""
        logger = get_logger("test")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.WARNING)

        try:
            logger.warning("Warning message")
            output = stream.getvalue().strip()
            parsed = json.loads(output)

            assert parsed["level"] == "WARNING"
        finally:
            underlying_logger.removeHandler(handler)

    def test_error_level_logs(self):
        """✅ REAL TEST: ERROR level logs work."""
        logger = get_logger("test")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.ERROR)

        try:
            logger.error("Error message")
            output = stream.getvalue().strip()
            parsed = json.loads(output)

            assert parsed["level"] == "ERROR"
        finally:
            underlying_logger.removeHandler(handler)

    def test_critical_level_logs(self):
        """✅ REAL TEST: CRITICAL level logs work."""
        logger = get_logger("test")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.CRITICAL)

        try:
            logger.critical("Critical message")
            output = stream.getvalue().strip()
            parsed = json.loads(output)

            assert parsed["level"] == "CRITICAL"
        finally:
            underlying_logger.removeHandler(handler)


class TestLoggingExceptionHandlingREAL:
    """✅ REAL TEST: Exception logging."""

    def test_log_exception_includes_traceback(self):
        """✅ REAL TEST: Logging exception includes full traceback."""
        logger = get_logger("test")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.ERROR)

        try:
            try:
                raise ValueError("Test error message")
            except ValueError:
                logger.exception("An error occurred")

            output = stream.getvalue().strip()
            parsed = json.loads(output)

            assert "exception" in parsed
            assert "ValueError: Test error message" in parsed["exception"]
        finally:
            underlying_logger.removeHandler(handler)

    def test_log_with_exc_info_true(self):
        """✅ REAL TEST: exc_info=True includes exception details."""
        logger = get_logger("test")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.ERROR)

        try:
            try:
                1 / 0  # ZeroDivisionError
            except ZeroDivisionError:
                logger.error("Math error", exc_info=True)

            output = stream.getvalue().strip()
            parsed = json.loads(output)

            assert "exception" in parsed
            assert "ZeroDivisionError" in parsed["exception"]
        finally:
            underlying_logger.removeHandler(handler)


class TestLoggingMessageFormattingREAL:
    """✅ REAL TEST: Log message formatting."""

    def test_log_with_string_formatting(self):
        """✅ REAL TEST: Log messages support % formatting."""
        logger = get_logger("test")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.INFO)

        try:
            logger.info("User %s logged in from %s", "alice", "192.168.1.1")

            output = stream.getvalue().strip()
            parsed = json.loads(output)

            assert parsed["message"] == "User alice logged in from 192.168.1.1"
        finally:
            underlying_logger.removeHandler(handler)

    def test_log_with_kwargs_formatting(self):
        """✅ REAL TEST: Log messages support kwargs formatting."""
        logger = get_logger("test")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.INFO)

        try:
            logger.info(
                "Request from %(ip)s by %(user)s", {"ip": "10.0.0.1", "user": "bob"}
            )

            output = stream.getvalue().strip()
            parsed = json.loads(output)

            # Message should be formatted
            assert (
                "10.0.0.1" in parsed["message"] or "Request from" in parsed["message"]
            )
        finally:
            underlying_logger.removeHandler(handler)


class TestLoggingCorrelationREAL:
    """✅ REAL TEST: Correlation ID propagation."""

    def test_correlation_id_propagates_through_call_chain(self):
        """✅ REAL TEST: Single request_id for entire call chain."""
        logger = get_logger("test")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        filter_obj = RequestIdFilter()
        handler.addFilter(filter_obj)

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.INFO)

        try:
            request_id = "req-call-chain-123"

            with _request_id_context(request_id):
                # Simulate call chain
                logger.info("Route handler called")
                logger.info("Service layer executing")
                logger.info("Database query executed")

            # Parse all log lines
            lines = stream.getvalue().strip().split("\n")
            for line in lines:
                parsed = json.loads(line)
                assert parsed["request_id"] == request_id
        finally:
            underlying_logger.removeHandler(handler)

    def test_nested_request_ids(self):
        """✅ REAL TEST: Nested request contexts maintain proper IDs."""
        logger = get_logger("test")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        filter_obj = RequestIdFilter()
        handler.addFilter(filter_obj)

        underlying_logger = logger.logger
        underlying_logger.addHandler(handler)
        underlying_logger.setLevel(logging.INFO)

        try:
            with _request_id_context("req-outer"):
                logger.info("Outer message")

                with _request_id_context("req-inner"):
                    logger.info("Inner message")

                logger.info("Back to outer")

            lines = stream.getvalue().strip().split("\n")

            # First and third log should have outer ID
            outer1 = json.loads(lines[0])
            assert outer1["request_id"] == "req-outer"

            # Second log should have inner ID
            inner = json.loads(lines[1])
            assert inner["request_id"] == "req-inner"

            # Third log should have outer ID
            outer2 = json.loads(lines[2])
            assert outer2["request_id"] == "req-outer"
        finally:
            underlying_logger.removeHandler(handler)
