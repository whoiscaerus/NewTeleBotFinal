"""
PR-043: Account Linking Service Unit Tests

Tests for AccountLinkingService methods:
- Account linking/unlinking
- Primary account selection
- Account info fetching with caching
- Error handling (duplicates, invalid MT5, etc.)
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.app.core.errors import NotFoundError, ValidationError

# Fixtures imported from conftest_pr_043.py


# ============================================================================
# LINKING ACCOUNT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_link_account_valid(account_service, db_session, test_user):
    """Test linking a valid MT5 account."""
    # Mock MT5 verification
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000,
            "equity": 10000,
        }
    )

    # Link account
    link = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    # Verify created
    assert link.id is not None
    assert link.user_id == test_user.id
    assert link.mt5_account_id == "12345678"
    assert link.mt5_login == "demo123"
    assert link.verified_at is not None
    assert link.is_primary is True  # First account is primary


@pytest.mark.asyncio
async def test_link_account_second_not_primary(account_service, db_session, test_user):
    """Test linking second account doesn't make it primary."""
    # Mock MT5 verification
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000,
            "equity": 10000,
        }
    )

    # Link first account
    link1 = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )
    assert link1.is_primary is True

    # Mock different account for second link
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "87654321",
            "balance": 5000,
            "equity": 5000,
        }
    )

    # Link second account
    link2 = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="87654321",
        mt5_login="demo456",
    )
    assert link2.is_primary is False  # Not primary


@pytest.mark.asyncio
async def test_link_account_duplicate_fails(account_service, db_session, test_user):
    """Test linking same account twice fails with ValidationError."""
    # Mock MT5 verification
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000,
            "equity": 10000,
        }
    )

    # Link account first time
    await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    # Try to link same account again
    with pytest.raises(ValidationError, match="already linked"):
        await account_service.link_account(
            user_id=test_user.id,
            mt5_account_id="12345678",
            mt5_login="demo123",
        )


@pytest.mark.asyncio
async def test_link_account_invalid_user_fails(account_service, db_session):
    """Test linking account with non-existent user fails."""
    fake_user_id = str(uuid4())

    with pytest.raises(NotFoundError, match="User not found"):
        await account_service.link_account(
            user_id=fake_user_id,
            mt5_account_id="12345678",
            mt5_login="demo123",
        )


@pytest.mark.asyncio
async def test_link_account_invalid_mt5_fails(account_service, db_session, test_user):
    """Test linking invalid MT5 account fails with ValidationError."""
    # Mock MT5 verification to fail
    account_service.mt5.get_account_info = AsyncMock(return_value=None)

    with pytest.raises(ValidationError, match="not accessible"):
        await account_service.link_account(
            user_id=test_user.id,
            mt5_account_id="99999999",
            mt5_login="invalid",
        )


@pytest.mark.asyncio
async def test_link_account_mt5_account_mismatch_fails(
    account_service, db_session, test_user
):
    """Test linking when MT5 account number doesn't match fails."""
    # Mock MT5 returning different account
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "87654321",  # Different from requested
            "balance": 10000,
            "equity": 10000,
        }
    )

    with pytest.raises(ValidationError, match="not accessible"):
        await account_service.link_account(
            user_id=test_user.id,
            mt5_account_id="12345678",  # Requested
            mt5_login="demo123",
        )


# ============================================================================
# GETTING ACCOUNT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_account_valid(account_service, db_session, test_user):
    """Test retrieving existing account."""
    # Create account
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000,
            "equity": 10000,
        }
    )

    link = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    # Get account
    retrieved = await account_service.get_account(link.id)

    assert retrieved.id == link.id
    assert retrieved.mt5_account_id == "12345678"


@pytest.mark.asyncio
async def test_get_account_not_found(account_service):
    """Test getting non-existent account fails."""
    fake_id = str(uuid4())

    with pytest.raises(NotFoundError, match="not found"):
        await account_service.get_account(fake_id)


# ============================================================================
# LISTING ACCOUNTS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_accounts_multiple(account_service, db_session, test_user):
    """Test listing all user accounts."""
    # Mock MT5 for linking
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000,
            "equity": 10000,
        }
    )

    # Link first account
    link1 = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    # Link second account
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "87654321",
            "balance": 5000,
            "equity": 5000,
        }
    )

    link2 = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="87654321",
        mt5_login="demo456",
    )

    # Get all accounts
    accounts = await account_service.get_user_accounts(test_user.id)

    assert len(accounts) == 2
    # Primary should be first
    assert accounts[0].is_primary is True
    assert accounts[1].is_primary is False


@pytest.mark.asyncio
async def test_get_user_accounts_empty(account_service, test_user):
    """Test listing accounts for user with no accounts."""
    accounts = await account_service.get_user_accounts(test_user.id)

    assert len(accounts) == 0


# ============================================================================
# PRIMARY ACCOUNT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_primary_account_exists(account_service, db_session, test_user):
    """Test getting user's primary account."""
    # Mock MT5
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000,
            "equity": 10000,
        }
    )

    # Link account
    await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    # Get primary
    primary = await account_service.get_primary_account(test_user.id)

    assert primary is not None
    assert primary.is_primary is True


@pytest.mark.asyncio
async def test_get_primary_account_none(account_service, test_user):
    """Test getting primary account when user has no accounts."""
    primary = await account_service.get_primary_account(test_user.id)

    assert primary is None


@pytest.mark.asyncio
async def test_set_primary_account_valid(account_service, db_session, test_user):
    """Test switching primary account."""
    # Mock MT5
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000,
            "equity": 10000,
        }
    )

    # Link first account (becomes primary)
    link1 = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    # Link second account
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "87654321",
            "balance": 5000,
            "equity": 5000,
        }
    )

    link2 = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="87654321",
        mt5_login="demo456",
    )

    # Verify first is primary
    primary = await account_service.get_primary_account(test_user.id)
    assert primary.id == link1.id

    # Switch to second as primary
    result = await account_service.set_primary_account(test_user.id, link2.id)

    assert result.is_primary is True
    assert result.id == link2.id

    # Verify first is no longer primary
    link1_updated = await account_service.get_account(link1.id)
    assert link1_updated.is_primary is False


@pytest.mark.asyncio
async def test_set_primary_account_wrong_user_fails(
    account_service, db_session, test_user, another_user
):
    """Test setting primary account for different user fails."""
    # Mock MT5
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000,
            "equity": 10000,
        }
    )

    # Link account to first user
    link = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    # Try to set as primary for different user
    with pytest.raises(ValidationError, match="does not belong"):
        await account_service.set_primary_account(another_user.id, link.id)


# ============================================================================
# UNLINKING ACCOUNT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unlink_account_valid(account_service, db_session, test_user):
    """Test unlinking account."""
    # Mock MT5
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000,
            "equity": 10000,
        }
    )

    # Link first account
    link1 = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    # Link second account
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "87654321",
            "balance": 5000,
            "equity": 5000,
        }
    )

    link2 = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="87654321",
        mt5_login="demo456",
    )

    # Unlink second account
    result = await account_service.unlink_account(test_user.id, link2.id)

    assert result is True

    # Verify only first account remains
    accounts = await account_service.get_user_accounts(test_user.id)
    assert len(accounts) == 1
    assert accounts[0].id == link1.id


@pytest.mark.asyncio
async def test_unlink_account_only_account_fails(
    account_service, db_session, test_user
):
    """Test unlinking only account fails."""
    # Mock MT5
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000,
            "equity": 10000,
        }
    )

    # Link only account
    link = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    # Try to unlink only account
    with pytest.raises(ValidationError, match="Cannot unlink only"):
        await account_service.unlink_account(test_user.id, link.id)


@pytest.mark.asyncio
async def test_unlink_account_wrong_user_fails(
    account_service, db_session, test_user, another_user
):
    """Test unlinking account of different user fails."""
    # Mock MT5
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000,
            "equity": 10000,
        }
    )

    # Link account to first user
    link = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    # Try to unlink as different user
    with pytest.raises(ValidationError, match="does not belong"):
        await account_service.unlink_account(another_user.id, link.id)


# ============================================================================
# ACCOUNT INFO TESTS (CACHING)
# ============================================================================


@pytest.mark.asyncio
async def test_get_account_info_fresh_fetch(account_service, db_session, test_user):
    """Test fetching fresh account info from MT5."""
    # Mock MT5
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

    # Get account info
    info = await account_service.get_account_info(link.id, force_refresh=True)

    assert info.balance == 10000.00
    assert info.equity == 9500.00
    assert info.free_margin == 4500.00
    assert info.margin_used == 5000.00
    assert info.margin_level == 190.0
    assert info.open_positions_count == 2
    # Drawdown = (balance - equity) / balance * 100 = 5%
    assert info.drawdown_percent == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_get_account_info_cache_hit(account_service, db_session, test_user):
    """Test cached account info is returned if fresh."""
    # Mock MT5
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

    # Get account info (fresh)
    info1 = await account_service.get_account_info(link.id, force_refresh=True)

    # Verify MT5 called
    assert (
        account_service.mt5.get_account_info.call_count == 2
    )  # link + get_account_info

    # Get account info again (should use cache)
    info2 = await account_service.get_account_info(link.id, force_refresh=False)

    # MT5 should not be called again (cache hit)
    assert account_service.mt5.get_account_info.call_count == 2

    assert info1.id == info2.id
    assert info1.equity == info2.equity


@pytest.mark.asyncio
async def test_get_account_info_cache_expired(account_service, db_session, test_user):
    """Test cache TTL expiry triggers fresh fetch."""
    # Mock MT5
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

    # Get account info (fresh)
    info1 = await account_service.get_account_info(link.id, force_refresh=True)

    # Manually expire cache by updating last_updated to past
    info1.last_updated = datetime.utcnow() - timedelta(seconds=60)
    db_session.add(info1)
    await db_session.commit()

    # Get account info again (cache expired, should fetch fresh)
    info2 = await account_service.get_account_info(link.id, force_refresh=False)

    # MT5 should be called again
    assert account_service.mt5.get_account_info.call_count == 3


@pytest.mark.asyncio
async def test_get_account_info_force_refresh(account_service, db_session, test_user):
    """Test force_refresh bypasses cache."""
    # Mock MT5
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

    # Get account info (fresh)
    await account_service.get_account_info(link.id, force_refresh=True)

    initial_calls = account_service.mt5.get_account_info.call_count

    # Get account info with force_refresh (should ignore cache)
    await account_service.get_account_info(link.id, force_refresh=True)

    # MT5 should be called again
    assert account_service.mt5.get_account_info.call_count == initial_calls + 1


@pytest.mark.asyncio
async def test_get_account_info_mt5_failure(account_service, db_session, test_user):
    """Test account info fetch handles MT5 failure gracefully."""
    # Mock MT5 to fail
    account_service.mt5.get_account_info = AsyncMock(return_value=None)

    # Link account
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

    link = await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="demo123",
    )

    # Mock MT5 to fail on fetch
    account_service.mt5.get_account_info = AsyncMock(return_value=None)

    # Get account info should raise ValidationError
    with pytest.raises(ValidationError, match="not available"):
        await account_service.get_account_info(link.id, force_refresh=True)


# ============================================================================
# CONCURRENT OPERATIONS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_link_multiple_accounts_concurrent(
    account_service, db_session, test_user
):
    """Test linking multiple accounts concurrently."""
    # Mock MT5
    account_service.mt5.get_account_info = AsyncMock(
        side_effect=[
            {"account": "11111111", "balance": 10000, "equity": 10000},
            {"account": "22222222", "balance": 5000, "equity": 5000},
            {"account": "33333333", "balance": 3000, "equity": 3000},
        ]
    )

    # Link three accounts concurrently
    import asyncio

    links = await asyncio.gather(
        account_service.link_account(
            user_id=test_user.id,
            mt5_account_id="11111111",
            mt5_login="demo1",
        ),
        account_service.link_account(
            user_id=test_user.id,
            mt5_account_id="22222222",
            mt5_login="demo2",
        ),
        account_service.link_account(
            user_id=test_user.id,
            mt5_account_id="33333333",
            mt5_login="demo3",
        ),
    )

    assert len(links) == 3
    # First should be primary
    primary_count = sum(1 for link in links if link.is_primary)
    assert primary_count == 1
