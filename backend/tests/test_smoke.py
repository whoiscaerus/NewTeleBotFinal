"""Smoke test - verify Python environment works."""

import sys


def test_python_version():
    """Test Python 3.11+ available."""
    assert sys.version_info >= (3, 11), "Python 3.11+ required"


def test_imports():
    """Test core dependencies available."""
    import pytest
    import fastapi
    import sqlalchemy
    import pydantic

    assert pytest.__version__
    assert fastapi.__version__
    assert sqlalchemy.__version__
    assert pydantic.__version__
