"""
PR-043 Test Fixtures

Fixtures for account linking and positions service tests.
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.accounts.service import AccountLinkingService
from backend.app.positions.service import PositionsService


@pytest.fixture
def mock_mt5_manager():
    """Mock MT5SessionManager for testing."""
    manager = AsyncMock()
    manager.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000.00,
            "equity": 9500.00,
            "free_margin": 4500.00,
            "margin_used": 5000.00,
            "margin_level": 190.0,
            "open_positions": 2,
        }
    )
    manager.get_positions = AsyncMock(return_value=[])
    return manager


@pytest.fixture
async def account_service(db_session: AsyncSession, mock_mt5_manager):
    """Create AccountLinkingService for testing."""
    service = AccountLinkingService(db_session, mock_mt5_manager)
    return service


@pytest.fixture
async def positions_service(
    db_session: AsyncSession, account_service, mock_mt5_manager
):
    """Create PositionsService for testing."""
    service = PositionsService(db_session, account_service, mock_mt5_manager)
    return service


@pytest.fixture
async def linked_account(
    db_session: AsyncSession, test_user, account_service, mock_mt5_manager
):
    """Create a linked MT5 account for testing."""
    # Mock MT5 account info response
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000.00,
            "equity": 9500.00,
            "free_margin": 4500.00,
            "margin_used": 5000.00,
            "margin_level": 190.0,
            "open_positions": 2,
        }
    )

    # Link account
    link = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    return link


@pytest.fixture
async def other_user(db_session: AsyncSession):
    """Create another test user for authorization testing."""
    from uuid import uuid4

    from backend.app.auth.models import User, UserRole
    from backend.app.auth.utils import hash_password

    user = User(
        id=str(uuid4()),
        email="otheruser@example.com",
        telegram_user_id="987654321",
        password_hash=hash_password("other_password"),
        role=UserRole.USER,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def auth_headers(test_user) -> dict:
    """Create JWT authentication headers for test user."""
    from backend.app.auth.security import create_access_token

    token = create_access_token(subject=test_user.id, expires_delta=None)
    return {"Authorization": f"Bearer {token}"}
