"""Tests for logging module."""

import logging

from backend.app.core.logging import JSONFormatter, configure_logging, get_logger


class TestJSONFormatter:
    """Test JSON formatter."""

    def test_format_basic_record(self):
        """Test formatting basic log record."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        assert "timestamp" in result
        assert "level" in result
        assert "message" in result
        assert "Test message" in result
        assert "INFO" in result

    def test_format_with_request_id(self):
        """Test formatting with request ID."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.request_id = "req-123"

        result = formatter.format(record)
        assert "req-123" in result


class TestLoggingConfiguration:
    """Test logging configuration."""

    def test_configure_logging_succeeds(self):
        """Test logging configuration doesn't raise errors."""
        configure_logging()
        # If no exception, test passes

    def test_get_logger_returns_adapter(self):
        """Test get_logger returns LoggerAdapter."""
        logger = get_logger("test")
        assert isinstance(logger, logging.LoggerAdapter)

    def test_logger_has_valid_name(self):
        """Test logger has correct name."""
        logger = get_logger("backend.test")
        assert logger.logger.name == "backend.test"
