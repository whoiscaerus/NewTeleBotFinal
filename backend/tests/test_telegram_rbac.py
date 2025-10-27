"""Tests for RBAC enforcement in Telegram handlers."""

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.telegram.commands import UserRole
from backend.app.telegram.models import TelegramUser
from backend.app.telegram.rbac import (
    RoleMiddleware,
    ensure_admin,
    ensure_owner,
    ensure_public,
    ensure_subscriber,
    get_user_role,
    require_role,
)


@pytest.mark.asyncio
class TestGetUserRole:
    """Test retrieving user role from database."""

    async def test_get_user_role_public(self, db_session: AsyncSession):
        """Test retrieving PUBLIC role user."""
        # Create public user
        user = TelegramUser(
            id="123",
            telegram_username="testuser",
            role=0,  # PUBLIC
        )
        db_session.add(user)
        await db_session.commit()

        role = await get_user_role("123", db_session)
        assert role == UserRole.PUBLIC

    async def test_get_user_role_subscriber(self, db_session: AsyncSession):
        """Test retrieving SUBSCRIBER role user."""
        user = TelegramUser(
            id="456",
            telegram_username="subscriber",
            role=1,  # SUBSCRIBER
        )
        db_session.add(user)
        await db_session.commit()

        role = await get_user_role("456", db_session)
        assert role == UserRole.SUBSCRIBER

    async def test_get_user_role_admin(self, db_session: AsyncSession):
        """Test retrieving ADMIN role user."""
        user = TelegramUser(
            id="789",
            telegram_username="admin",
            role=2,  # ADMIN
        )
        db_session.add(user)
        await db_session.commit()

        role = await get_user_role("789", db_session)
        assert role == UserRole.ADMIN

    async def test_get_user_role_owner(self, db_session: AsyncSession):
        """Test retrieving OWNER role user."""
        user = TelegramUser(
            id="999",
            telegram_username="owner",
            role=3,  # OWNER
        )
        db_session.add(user)
        await db_session.commit()

        role = await get_user_role("999", db_session)
        assert role == UserRole.OWNER

    async def test_get_user_role_not_found(self, db_session: AsyncSession):
        """Test unknown user returns None."""
        role = await get_user_role("nonexistent", db_session)
        assert role is None


@pytest.mark.asyncio
class TestEnsurePublic:
    """Test PUBLIC access check."""

    async def test_ensure_public_allows_public_user(self, db_session: AsyncSession):
        """Test public user is allowed."""
        user = TelegramUser(id="123", role=0)
        db_session.add(user)
        await db_session.commit()

        result = await ensure_public("123", db_session)
        assert result is True

    async def test_ensure_public_allows_subscriber(self, db_session: AsyncSession):
        """Test subscriber also has public access."""
        user = TelegramUser(id="456", role=1)
        db_session.add(user)
        await db_session.commit()

        result = await ensure_public("456", db_session)
        assert result is True

    async def test_ensure_public_denies_unknown_user(self, db_session: AsyncSession):
        """Test unknown user is denied."""
        with pytest.raises(HTTPException) as exc:
            await ensure_public("unknown", db_session)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
class TestEnsureSubscriber:
    """Test SUBSCRIBER access check."""

    async def test_ensure_subscriber_allows_subscriber(self, db_session: AsyncSession):
        """Test subscriber is allowed."""
        user = TelegramUser(id="456", role=1)  # SUBSCRIBER
        db_session.add(user)
        await db_session.commit()

        result = await ensure_subscriber("456", db_session)
        assert result is True

    async def test_ensure_subscriber_allows_admin(self, db_session: AsyncSession):
        """Test admin has subscriber access."""
        user = TelegramUser(id="789", role=2)  # ADMIN
        db_session.add(user)
        await db_session.commit()

        result = await ensure_subscriber("789", db_session)
        assert result is True

    async def test_ensure_subscriber_denies_public(self, db_session: AsyncSession):
        """Test public user is denied."""
        user = TelegramUser(id="123", role=0)  # PUBLIC
        db_session.add(user)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc:
            await ensure_subscriber("123", db_session)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_ensure_subscriber_denies_unknown(self, db_session: AsyncSession):
        """Test unknown user is denied."""
        with pytest.raises(HTTPException) as exc:
            await ensure_subscriber("unknown", db_session)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
class TestEnsureAdmin:
    """Test ADMIN access check."""

    async def test_ensure_admin_allows_admin(self, db_session: AsyncSession):
        """Test admin is allowed."""
        user = TelegramUser(id="789", role=2)  # ADMIN
        db_session.add(user)
        await db_session.commit()

        result = await ensure_admin("789", db_session)
        assert result is True

    async def test_ensure_admin_allows_owner(self, db_session: AsyncSession):
        """Test owner has admin access."""
        user = TelegramUser(id="999", role=3)  # OWNER
        db_session.add(user)
        await db_session.commit()

        result = await ensure_admin("999", db_session)
        assert result is True

    async def test_ensure_admin_denies_subscriber(self, db_session: AsyncSession):
        """Test subscriber is denied."""
        user = TelegramUser(id="456", role=1)  # SUBSCRIBER
        db_session.add(user)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc:
            await ensure_admin("456", db_session)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_ensure_admin_denies_public(self, db_session: AsyncSession):
        """Test public user is denied."""
        user = TelegramUser(id="123", role=0)  # PUBLIC
        db_session.add(user)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc:
            await ensure_admin("123", db_session)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
class TestEnsureOwner:
    """Test OWNER access check."""

    async def test_ensure_owner_allows_owner(self, db_session: AsyncSession):
        """Test owner is allowed."""
        user = TelegramUser(id="999", role=3)  # OWNER
        db_session.add(user)
        await db_session.commit()

        result = await ensure_owner("999", db_session)
        assert result is True

    async def test_ensure_owner_denies_admin(self, db_session: AsyncSession):
        """Test admin is denied owner access."""
        user = TelegramUser(id="789", role=2)  # ADMIN
        db_session.add(user)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc:
            await ensure_owner("789", db_session)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_ensure_owner_denies_subscriber(self, db_session: AsyncSession):
        """Test subscriber is denied."""
        user = TelegramUser(id="456", role=1)  # SUBSCRIBER
        db_session.add(user)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc:
            await ensure_owner("456", db_session)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
class TestRequireRole:
    """Test generic role requirement checker."""

    async def test_require_role_allows_matching_role(self, db_session: AsyncSession):
        """Test matching role is allowed."""
        user = TelegramUser(id="789", role=2)  # ADMIN
        db_session.add(user)
        await db_session.commit()

        result = await require_role("789", UserRole.ADMIN, db_session)
        assert result is True

    async def test_require_role_allows_higher_role(self, db_session: AsyncSession):
        """Test higher role is allowed."""
        user = TelegramUser(id="999", role=3)  # OWNER
        db_session.add(user)
        await db_session.commit()

        result = await require_role("999", UserRole.ADMIN, db_session)
        assert result is True

    async def test_require_role_denies_lower_role(self, db_session: AsyncSession):
        """Test lower role is denied."""
        user = TelegramUser(id="456", role=1)  # SUBSCRIBER
        db_session.add(user)
        await db_session.commit()

        with pytest.raises(HTTPException):
            await require_role("456", UserRole.ADMIN, db_session)

    async def test_require_role_public_role(self, db_session: AsyncSession):
        """Test PUBLIC role requirement allows all users."""
        user = TelegramUser(id="123", role=0)  # PUBLIC
        db_session.add(user)
        await db_session.commit()

        result = await require_role("123", UserRole.PUBLIC, db_session)
        assert result is True


@pytest.mark.asyncio
class TestRoleMiddleware:
    """Test RoleMiddleware for automatic role checking."""

    async def test_middleware_verify_success(self, db_session: AsyncSession):
        """Test middleware verify with allowed role."""
        user = TelegramUser(id="789", role=2)  # ADMIN
        db_session.add(user)
        await db_session.commit()

        middleware = RoleMiddleware("789", UserRole.ADMIN, db_session)
        role = await middleware.verify()

        assert role == UserRole.ADMIN

    async def test_middleware_verify_fails(self, db_session: AsyncSession):
        """Test middleware verify with denied role."""
        user = TelegramUser(id="123", role=0)  # PUBLIC
        db_session.add(user)
        await db_session.commit()

        middleware = RoleMiddleware("123", UserRole.ADMIN, db_session)

        with pytest.raises(HTTPException):
            await middleware.verify()

    async def test_middleware_get_user_success(self, db_session: AsyncSession):
        """Test middleware get_user after verification."""
        user = TelegramUser(id="789", telegram_username="admin", role=2)
        db_session.add(user)
        await db_session.commit()

        middleware = RoleMiddleware("789", UserRole.ADMIN, db_session)
        fetched_user = await middleware.get_user()

        assert fetched_user is not None
        assert fetched_user.id == "789"
        assert fetched_user.telegram_username == "admin"

    async def test_middleware_get_user_fails_if_no_permission(
        self, db_session: AsyncSession
    ):
        """Test middleware get_user fails if no permission."""
        user = TelegramUser(id="123", role=0)  # PUBLIC
        db_session.add(user)
        await db_session.commit()

        middleware = RoleMiddleware("123", UserRole.ADMIN, db_session)

        with pytest.raises(HTTPException):
            await middleware.get_user()


@pytest.mark.asyncio
class TestRoleHierarchy:
    """Test role hierarchy enforcement."""

    async def test_owner_can_access_all_levels(self, db_session: AsyncSession):
        """Test OWNER has access to all role levels."""
        user = TelegramUser(id="999", role=3)  # OWNER
        db_session.add(user)
        await db_session.commit()

        for role in [
            UserRole.PUBLIC,
            UserRole.SUBSCRIBER,
            UserRole.ADMIN,
            UserRole.OWNER,
        ]:
            result = await require_role("999", role, db_session)
            assert result is True

    async def test_admin_cannot_access_owner_level(self, db_session: AsyncSession):
        """Test ADMIN cannot access OWNER-only features."""
        user = TelegramUser(id="789", role=2)  # ADMIN
        db_session.add(user)
        await db_session.commit()

        with pytest.raises(HTTPException):
            await require_role("789", UserRole.OWNER, db_session)

    async def test_subscriber_cannot_access_admin_level(self, db_session: AsyncSession):
        """Test SUBSCRIBER cannot access ADMIN features."""
        user = TelegramUser(id="456", role=1)  # SUBSCRIBER
        db_session.add(user)
        await db_session.commit()

        with pytest.raises(HTTPException):
            await require_role("456", UserRole.ADMIN, db_session)

    async def test_public_can_only_access_public(self, db_session: AsyncSession):
        """Test PUBLIC can only access PUBLIC features."""
        user = TelegramUser(id="123", role=0)  # PUBLIC
        db_session.add(user)
        await db_session.commit()

        # Should succeed
        result = await require_role("123", UserRole.PUBLIC, db_session)
        assert result is True

        # Should fail for all others
        for role in [UserRole.SUBSCRIBER, UserRole.ADMIN, UserRole.OWNER]:
            with pytest.raises(HTTPException):
                await require_role("123", role, db_session)


@pytest.mark.asyncio
class TestRoleTransitions:
    """Test role transitions and updates."""

    async def test_user_can_transition_to_subscriber(self, db_session: AsyncSession):
        """Test user can be upgraded to SUBSCRIBER."""
        user = TelegramUser(id="123", role=0)  # PUBLIC
        db_session.add(user)
        await db_session.commit()

        # Should be PUBLIC
        role = await get_user_role("123", db_session)
        assert role == UserRole.PUBLIC

        # Upgrade to SUBSCRIBER
        user.role = 1
        await db_session.commit()

        # Should now be SUBSCRIBER
        role = await get_user_role("123", db_session)
        assert role == UserRole.SUBSCRIBER

    async def test_subscriber_can_be_promoted_to_admin(self, db_session: AsyncSession):
        """Test subscriber can be promoted to admin."""
        user = TelegramUser(id="456", role=1)  # SUBSCRIBER
        db_session.add(user)
        await db_session.commit()

        user.role = 2  # Promote to ADMIN
        await db_session.commit()

        role = await get_user_role("456", db_session)
        assert role == UserRole.ADMIN
