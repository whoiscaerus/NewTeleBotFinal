"""Root conftest for backend tests - sets up Python path and fixtures."""

import asyncio
import os
import sys
from pathlib import Path


# Add backend directory to Python path so imports work correctly
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Set test database URL before importing settings
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


def pytest_configure(config):
    """Configure pytest before test collection."""
    # Ensure event loop is set up for asyncio tests
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
