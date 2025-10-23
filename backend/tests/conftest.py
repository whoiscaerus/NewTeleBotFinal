"""Pytest configuration and shared fixtures."""

import os

import pytest

# Set test environment variables
os.environ["APP_ENV"] = "development"
os.environ["DB_DSN"] = "postgresql+psycopg://user:pass@localhost:5432/test_app"


@pytest.fixture(autouse=True)
def reset_context():
    """Reset logging context before each test."""
    from backend.app.core.logging import _request_id_context

    _request_id_context.set("unknown")
    yield
    _request_id_context.set("unknown")
