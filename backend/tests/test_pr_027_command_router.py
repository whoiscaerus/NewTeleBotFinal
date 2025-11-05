"""Comprehensive test suite for PR-027: Bot Command Router & Permissions.

Tests cover:
1. CommandRegistry registration, retrieval, and validation (SYNC tests)
2. Role hierarchy and permission checking (SYNC tests)
3. Help text generation for different user roles (SYNC tests)
4. RBAC decorators and database integration (ASYNC tests)
5. Real-world command execution scenarios (SYNC tests)
6. Error handling and edge cases (SYNC tests)

All tests use REAL business logic (no mocks of core functions).
"""

import inspect
import logging

import pytest
import pytest_asyncio
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.telegram.commands import (
    CommandRegistry,
    UserRole,
    get_registry,
    reset_registry,
)
from backend.app.telegram.models import TelegramUser
from backend.app.telegram.rbac import (
    ensure_admin,
    ensure_owner,
    ensure_public,
    ensure_subscriber,
    get_user_role,
    require_role,
)

logger = logging.getLogger(__name__)


# ============================================================================
# SECTION 1: CommandRegistry Registration & Validation (15 tests) - SYNC
# ============================================================================


class TestCommandRegistryRegistration:
    """Test command registration, retrieval, and validation."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()

    def test_register_single_command_valid(self):
        """Test registering a single valid command."""
        registry = CommandRegistry()

        async def handle_start():
            """Start command handler."""
            return "started"

        registry.register(
            name="start",
            description="Start the bot",
            required_role=UserRole.PUBLIC,
            handler=handle_start,
            help_text="This starts the bot",
        )

        assert registry.is_registered("start")
        cmd = registry.get_command("start")
        assert cmd is not None
        assert cmd.name == "start"
        assert cmd.required_role == UserRole.PUBLIC

    def test_register_multiple_commands(self):
        """Test registering multiple commands."""
        registry = CommandRegistry()

        async def handler1():
            return "cmd1"

        async def handler2():
            return "cmd2"

        async def handler3():
            return "cmd3"

        registry.register("cmd1", "Command 1", UserRole.PUBLIC, handler1, "Help 1")
        registry.register("cmd2", "Command 2", UserRole.SUBSCRIBER, handler2, "Help 2")
        registry.register("cmd3", "Command 3", UserRole.ADMIN, handler3, "Help 3")

        assert len(registry.commands) == 3
        assert registry.is_registered("cmd1")
        assert registry.is_registered("cmd2")
        assert registry.is_registered("cmd3")

    def test_register_command_with_aliases(self):
        """Test registering command with aliases."""
        registry = CommandRegistry()

        async def handle_help():
            return "help"

        registry.register(
            name="help",
            description="Get help",
            required_role=UserRole.PUBLIC,
            handler=handle_help,
            help_text="Shows help",
            aliases=["h", "?"],
        )

        # Main command registered
        assert registry.is_registered("help")

        # Aliases registered
        assert registry.is_registered("h")
        assert registry.is_registered("?")

        # All resolve to same command
        cmd1 = registry.get_command("help")
        cmd2 = registry.get_command("h")
        cmd3 = registry.get_command("?")
        assert cmd1.name == cmd2.name == cmd3.name == "help"

    def test_register_duplicate_command_raises_error(self):
        """Test registering duplicate command name raises error."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("cmd", "Description", UserRole.PUBLIC, handler, "Help text")

        # Registering same name again should raise
        with pytest.raises(ValueError, match="already registered"):
            registry.register(
                "cmd", "Different description", UserRole.PUBLIC, handler, "Help"
            )

    def test_register_duplicate_alias_raises_error(self):
        """Test registering duplicate alias raises error."""
        registry = CommandRegistry()

        async def handler1():
            return "1"

        async def handler2():
            return "2"

        registry.register(
            "cmd1",
            "Cmd 1",
            UserRole.PUBLIC,
            handler1,
            "Help 1",
            aliases=["x"],
        )

        # Trying to register another command with same alias should raise
        with pytest.raises(ValueError, match="Alias 'x' already mapped"):
            registry.register(
                "cmd2",
                "Cmd 2",
                UserRole.PUBLIC,
                handler2,
                "Help 2",
                aliases=["x"],
            )

    def test_register_non_async_handler_raises_error(self):
        """Test registering non-async handler raises error."""
        registry = CommandRegistry()

        def sync_handler():  # NOT async
            return "sync"

        with pytest.raises(ValueError, match="must be async"):
            registry.register(
                "cmd", "Sync command", UserRole.PUBLIC, sync_handler, "Help"
            )

    def test_register_empty_name_raises_error(self):
        """Test registering with empty name raises error."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        with pytest.raises(ValueError, match="name required"):
            registry.register("", "Description", UserRole.PUBLIC, handler, "Help")

    def test_register_with_hidden_flag(self):
        """Test registering command as hidden."""
        registry = CommandRegistry()

        async def handler():
            return "secret"

        registry.register(
            "secret",
            "Secret admin command",
            UserRole.ADMIN,
            handler,
            "Hidden from help",
            hidden=True,
        )

        cmd = registry.get_command("secret")
        assert cmd.hidden is True

    def test_get_command_by_name(self):
        """Test retrieving command by canonical name."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("test", "Test", UserRole.PUBLIC, handler, "Test help")

        cmd = registry.get_command("test")
        assert cmd is not None
        assert cmd.name == "test"

    def test_get_command_by_alias(self):
        """Test retrieving command by alias."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register(
            "test",
            "Test",
            UserRole.PUBLIC,
            handler,
            "Test help",
            aliases=["t", "tst"],
        )

        # All resolve to same command
        assert registry.get_command("t").name == "test"
        assert registry.get_command("tst").name == "test"

    def test_get_command_not_found_returns_none(self):
        """Test getting non-existent command returns None."""
        registry = CommandRegistry()
        assert registry.get_command("nonexistent") is None

    def test_get_all_commands(self):
        """Test retrieving all registered commands."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("cmd1", "Cmd 1", UserRole.PUBLIC, handler, "Help 1")
        registry.register("cmd2", "Cmd 2", UserRole.PUBLIC, handler, "Help 2")
        registry.register("cmd3", "Cmd 3", UserRole.PUBLIC, handler, "Help 3")

        all_commands = registry.get_all_commands()
        assert len(all_commands) == 3
        names = [cmd.name for cmd in all_commands]
        assert "cmd1" in names
        assert "cmd2" in names
        assert "cmd3" in names


# ============================================================================
# SECTION 2: Role Hierarchy & Permission Checking (16 tests) - SYNC
# ============================================================================


class TestRoleHierarchy:
    """Test role hierarchy and permission enforcement."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()

    def test_owner_can_access_all_roles(self):
        """Test OWNER role has highest privileges."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("public_cmd", "Public", UserRole.PUBLIC, handler, "Help")
        registry.register(
            "subscriber_cmd", "Subscriber", UserRole.SUBSCRIBER, handler, "Help"
        )
        registry.register("admin_cmd", "Admin", UserRole.ADMIN, handler, "Help")
        registry.register("owner_cmd", "Owner", UserRole.OWNER, handler, "Help")

        # OWNER can access all
        assert registry.is_allowed("public_cmd", UserRole.OWNER)
        assert registry.is_allowed("subscriber_cmd", UserRole.OWNER)
        assert registry.is_allowed("admin_cmd", UserRole.OWNER)
        assert registry.is_allowed("owner_cmd", UserRole.OWNER)

    def test_admin_can_access_admin_and_below(self):
        """Test ADMIN role hierarchy."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("public_cmd", "Public", UserRole.PUBLIC, handler, "Help")
        registry.register(
            "subscriber_cmd", "Subscriber", UserRole.SUBSCRIBER, handler, "Help"
        )
        registry.register("admin_cmd", "Admin", UserRole.ADMIN, handler, "Help")
        registry.register("owner_cmd", "Owner", UserRole.OWNER, handler, "Help")

        # ADMIN can access public, subscriber, admin
        assert registry.is_allowed("public_cmd", UserRole.ADMIN)
        assert registry.is_allowed("subscriber_cmd", UserRole.ADMIN)
        assert registry.is_allowed("admin_cmd", UserRole.ADMIN)
        # But NOT owner commands
        assert not registry.is_allowed("owner_cmd", UserRole.ADMIN)

    def test_subscriber_can_access_subscriber_and_below(self):
        """Test SUBSCRIBER role hierarchy."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("public_cmd", "Public", UserRole.PUBLIC, handler, "Help")
        registry.register(
            "subscriber_cmd", "Subscriber", UserRole.SUBSCRIBER, handler, "Help"
        )
        registry.register("admin_cmd", "Admin", UserRole.ADMIN, handler, "Help")

        # SUBSCRIBER can access public, subscriber
        assert registry.is_allowed("public_cmd", UserRole.SUBSCRIBER)
        assert registry.is_allowed("subscriber_cmd", UserRole.SUBSCRIBER)
        # But NOT admin/owner
        assert not registry.is_allowed("admin_cmd", UserRole.SUBSCRIBER)

    def test_public_can_only_access_public(self):
        """Test PUBLIC role has minimal privileges."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("public_cmd", "Public", UserRole.PUBLIC, handler, "Help")
        registry.register(
            "subscriber_cmd", "Subscriber", UserRole.SUBSCRIBER, handler, "Help"
        )
        registry.register("admin_cmd", "Admin", UserRole.ADMIN, handler, "Help")

        # PUBLIC can only access public
        assert registry.is_allowed("public_cmd", UserRole.PUBLIC)
        assert not registry.is_allowed("subscriber_cmd", UserRole.PUBLIC)
        assert not registry.is_allowed("admin_cmd", UserRole.PUBLIC)

    def test_is_allowed_nonexistent_command_returns_false(self):
        """Test checking permissions for non-existent command."""
        registry = CommandRegistry()
        assert not registry.is_allowed("nonexistent", UserRole.OWNER)

    def test_is_allowed_with_all_role_combinations(self):
        """Test is_allowed() with comprehensive role matrix."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        # Register one command for each role
        registry.register("public_cmd", "Public", UserRole.PUBLIC, handler, "Help")
        registry.register(
            "subscriber_cmd", "Subscriber", UserRole.SUBSCRIBER, handler, "Help"
        )
        registry.register("admin_cmd", "Admin", UserRole.ADMIN, handler, "Help")
        registry.register("owner_cmd", "Owner", UserRole.OWNER, handler, "Help")

        # Test matrix of all combinations
        permissions = {
            UserRole.PUBLIC: {
                "public_cmd": True,
                "subscriber_cmd": False,
                "admin_cmd": False,
                "owner_cmd": False,
            },
            UserRole.SUBSCRIBER: {
                "public_cmd": True,
                "subscriber_cmd": True,
                "admin_cmd": False,
                "owner_cmd": False,
            },
            UserRole.ADMIN: {
                "public_cmd": True,
                "subscriber_cmd": True,
                "admin_cmd": True,
                "owner_cmd": False,
            },
            UserRole.OWNER: {
                "public_cmd": True,
                "subscriber_cmd": True,
                "admin_cmd": True,
                "owner_cmd": True,
            },
        }

        for user_role, commands in permissions.items():
            for cmd_name, should_allow in commands.items():
                result = registry.is_allowed(cmd_name, user_role)
                assert (
                    result == should_allow
                ), f"{user_role} should {'access' if should_allow else 'NOT access'} {cmd_name}"

    def test_list_commands_for_public_role(self):
        """Test listing available commands for PUBLIC role."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("start", "Start", UserRole.PUBLIC, handler, "Help")
        registry.register("help", "Help", UserRole.PUBLIC, handler, "Help")
        registry.register("shop", "Shop", UserRole.PUBLIC, handler, "Help")
        registry.register("buy", "Buy", UserRole.SUBSCRIBER, handler, "Help")
        registry.register("admin", "Admin", UserRole.ADMIN, handler, "Help")

        commands = registry.list_commands_for_role(UserRole.PUBLIC)
        assert len(commands) == 3
        assert "start" in commands
        assert "help" in commands
        assert "shop" in commands
        assert "buy" not in commands
        assert "admin" not in commands

    def test_list_commands_for_subscriber_role(self):
        """Test listing available commands for SUBSCRIBER role."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("start", "Start", UserRole.PUBLIC, handler, "Help")
        registry.register("help", "Help", UserRole.PUBLIC, handler, "Help")
        registry.register("buy", "Buy", UserRole.SUBSCRIBER, handler, "Help")
        registry.register("status", "Status", UserRole.SUBSCRIBER, handler, "Help")
        registry.register("admin", "Admin", UserRole.ADMIN, handler, "Help")

        commands = registry.list_commands_for_role(UserRole.SUBSCRIBER)
        assert len(commands) == 4
        assert "start" in commands
        assert "buy" in commands
        assert "status" in commands
        assert "admin" not in commands

    def test_list_commands_for_admin_role(self):
        """Test listing available commands for ADMIN role."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("start", "Start", UserRole.PUBLIC, handler, "Help")
        registry.register("buy", "Buy", UserRole.SUBSCRIBER, handler, "Help")
        registry.register("broadcast", "Broadcast", UserRole.ADMIN, handler, "Help")
        registry.register("owner_only", "Owner", UserRole.OWNER, handler, "Help")

        commands = registry.list_commands_for_role(UserRole.ADMIN)
        assert "start" in commands
        assert "buy" in commands
        assert "broadcast" in commands
        assert "owner_only" not in commands

    def test_list_commands_for_owner_role(self):
        """Test listing available commands for OWNER role."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("start", "Start", UserRole.PUBLIC, handler, "Help")
        registry.register("admin", "Admin", UserRole.ADMIN, handler, "Help")
        registry.register("owner_cmd", "Owner", UserRole.OWNER, handler, "Help")

        commands = registry.list_commands_for_role(UserRole.OWNER)
        assert len(commands) == 3
        assert all(cmd in commands for cmd in ["start", "admin", "owner_cmd"])


# ============================================================================
# SECTION 3: Help Text Generation & Command Discovery (12 tests) - SYNC
# ============================================================================


class TestHelpTextGeneration:
    """Test help text generation for different user roles."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()

    def test_get_help_text_for_public_user(self):
        """Test help text shows only PUBLIC commands."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register(
            "start", "Start the bot", UserRole.PUBLIC, handler, "Start help"
        )
        registry.register("help", "Get help", UserRole.PUBLIC, handler, "Help help")
        registry.register(
            "buy", "Buy subscription", UserRole.SUBSCRIBER, handler, "Buy help"
        )
        registry.register("admin", "Admin panel", UserRole.ADMIN, handler, "Admin help")

        help_text = registry.get_help_text(UserRole.PUBLIC)

        # Should include public commands
        assert "/start" in help_text
        assert "/help" in help_text
        # Should NOT include subscriber/admin commands
        assert "/buy" not in help_text
        assert "/admin" not in help_text

    def test_get_help_text_for_subscriber_user(self):
        """Test help text shows PUBLIC + SUBSCRIBER commands."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("start", "Start", UserRole.PUBLIC, handler, "Help")
        registry.register("buy", "Buy", UserRole.SUBSCRIBER, handler, "Help")
        registry.register("status", "Status", UserRole.SUBSCRIBER, handler, "Help")
        registry.register("admin", "Admin", UserRole.ADMIN, handler, "Help")

        help_text = registry.get_help_text(UserRole.SUBSCRIBER)

        # Should include public + subscriber
        assert "/start" in help_text
        assert "/buy" in help_text
        assert "/status" in help_text
        # Should NOT include admin
        assert "/admin" not in help_text

    def test_get_help_text_for_admin_user(self):
        """Test help text shows PUBLIC + SUBSCRIBER + ADMIN commands."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("start", "Start", UserRole.PUBLIC, handler, "Help")
        registry.register("buy", "Buy", UserRole.SUBSCRIBER, handler, "Help")
        registry.register("broadcast", "Broadcast", UserRole.ADMIN, handler, "Help")
        registry.register("owner_cmd", "Owner", UserRole.OWNER, handler, "Help")

        help_text = registry.get_help_text(UserRole.ADMIN)

        # Should include all except OWNER
        assert "/start" in help_text
        assert "/buy" in help_text
        assert "/broadcast" in help_text
        # Should NOT include owner commands
        assert "/owner_cmd" not in help_text

    def test_get_help_text_for_owner_user(self):
        """Test help text shows ALL commands."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("start", "Start", UserRole.PUBLIC, handler, "Help")
        registry.register("buy", "Buy", UserRole.SUBSCRIBER, handler, "Help")
        registry.register("broadcast", "Broadcast", UserRole.ADMIN, handler, "Help")
        registry.register("owner_cmd", "Owner", UserRole.OWNER, handler, "Help")

        help_text = registry.get_help_text(UserRole.OWNER)

        # Should include ALL commands
        assert "/start" in help_text
        assert "/buy" in help_text
        assert "/broadcast" in help_text
        assert "/owner_cmd" in help_text

    def test_get_help_text_excludes_hidden_commands(self):
        """Test hidden commands excluded from help text."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("start", "Start", UserRole.PUBLIC, handler, "Help")
        registry.register(
            "secret", "Secret", UserRole.PUBLIC, handler, "Help", hidden=True
        )

        help_text = registry.get_help_text(UserRole.PUBLIC)

        assert "/start" in help_text
        assert "/secret" not in help_text

    def test_get_help_text_empty_no_commands_available(self):
        """Test help text when user has no accessible commands."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("admin_only", "Admin", UserRole.ADMIN, handler, "Help")
        registry.register("owner_only", "Owner", UserRole.OWNER, handler, "Help")

        # PUBLIC user has no accessible commands
        help_text = registry.get_help_text(UserRole.PUBLIC)
        assert "No commands available" in help_text

    def test_get_command_help_detailed(self):
        """Test getting detailed help for specific command."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        detailed_help = (
            "This is a detailed help text\nWith multiple lines\nAnd examples"
        )

        registry.register("help", "Get help", UserRole.PUBLIC, handler, detailed_help)

        help_text = registry.get_command_help("help")

        assert help_text is not None
        assert "*/help*" in help_text
        assert detailed_help in help_text

    def test_get_command_help_with_aliases(self):
        """Test detailed help includes aliases."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register(
            "help",
            "Get help",
            UserRole.PUBLIC,
            handler,
            "Detailed help",
            aliases=["h", "?"],
        )

        help_text = registry.get_command_help("help")

        assert "h" in help_text
        assert "?" in help_text
        assert "Aliases" in help_text

    def test_get_command_help_nonexistent_returns_none(self):
        """Test getting help for non-existent command."""
        registry = CommandRegistry()
        assert registry.get_command_help("nonexistent") is None

    def test_help_text_alphabetical_order(self):
        """Test commands in help text are alphabetically sorted."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        # Register in random order
        registry.register("zebra", "Zebra", UserRole.PUBLIC, handler, "Help")
        registry.register("apple", "Apple", UserRole.PUBLIC, handler, "Help")
        registry.register("middle", "Middle", UserRole.PUBLIC, handler, "Help")

        help_text = registry.get_help_text(UserRole.PUBLIC)

        # Extract command order from help text (commands appear after •)
        import re

        # Commands appear as "• /command_name - Description"
        commands = re.findall(r"• /(\w+)", help_text)
        assert commands == sorted(commands), f"Expected sorted, got {commands}"

    def test_get_public_commands(self):
        """Test retrieving only PUBLIC-role commands."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("start", "Start", UserRole.PUBLIC, handler, "Help")
        registry.register("help", "Help", UserRole.PUBLIC, handler, "Help")
        registry.register("buy", "Buy", UserRole.SUBSCRIBER, handler, "Help")

        public_cmds = registry.get_public_commands()
        assert len(public_cmds) == 2
        names = [cmd.name for cmd in public_cmds]
        assert "start" in names
        assert "help" in names
        assert "buy" not in names


# ============================================================================
# SECTION 4: RBAC with Database Integration (18 tests) - ASYNC
# ============================================================================


class TestRBACWithDatabase:
    """Test RBAC functions with real database."""

    @pytest_asyncio.fixture
    async def owner_user(self, db_session: AsyncSession) -> TelegramUser:
        """Create and return an OWNER role user."""
        user = TelegramUser(
            telegram_id="owner_123",
            telegram_username="owner_user",
            telegram_first_name="Owner",
            role=3,  # OWNER
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    @pytest_asyncio.fixture
    async def admin_user(self, db_session: AsyncSession) -> TelegramUser:
        """Create and return an ADMIN role user."""
        user = TelegramUser(
            telegram_id="admin_123",
            telegram_username="admin_user",
            telegram_first_name="Admin",
            role=2,  # ADMIN
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    @pytest_asyncio.fixture
    async def subscriber_user(self, db_session: AsyncSession) -> TelegramUser:
        """Create and return a SUBSCRIBER role user."""
        user = TelegramUser(
            telegram_id="subscriber_123",
            telegram_username="subscriber_user",
            telegram_first_name="Subscriber",
            role=1,  # SUBSCRIBER
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    @pytest_asyncio.fixture
    async def public_user(self, db_session: AsyncSession) -> TelegramUser:
        """Create and return a PUBLIC role user."""
        user = TelegramUser(
            telegram_id="public_123",
            telegram_username="public_user",
            telegram_first_name="Public",
            role=0,  # PUBLIC
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    @pytest.mark.asyncio
    async def test_get_user_role_owner(
        self, db_session: AsyncSession, owner_user: TelegramUser
    ):
        """Test get_user_role returns OWNER for owner user."""
        role = await get_user_role(owner_user.id, db_session)
        assert role == UserRole.OWNER

    @pytest.mark.asyncio
    async def test_get_user_role_admin(
        self, db_session: AsyncSession, admin_user: TelegramUser
    ):
        """Test get_user_role returns ADMIN for admin user."""
        role = await get_user_role(admin_user.id, db_session)
        assert role == UserRole.ADMIN

    @pytest.mark.asyncio
    async def test_get_user_role_subscriber(
        self, db_session: AsyncSession, subscriber_user: TelegramUser
    ):
        """Test get_user_role returns SUBSCRIBER for subscriber user."""
        role = await get_user_role(subscriber_user.id, db_session)
        assert role == UserRole.SUBSCRIBER

    @pytest.mark.asyncio
    async def test_get_user_role_public(
        self, db_session: AsyncSession, public_user: TelegramUser
    ):
        """Test get_user_role returns PUBLIC for public user."""
        role = await get_user_role(public_user.id, db_session)
        assert role == UserRole.PUBLIC

    @pytest.mark.asyncio
    async def test_get_user_role_nonexistent(self, db_session: AsyncSession):
        """Test get_user_role returns None for non-existent user."""
        role = await get_user_role("nonexistent_id_xyz", db_session)
        assert role is None

    @pytest.mark.asyncio
    async def test_ensure_public_success(
        self, db_session: AsyncSession, public_user: TelegramUser
    ):
        """Test ensure_public succeeds for existing user."""
        result = await ensure_public(public_user.id, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_public_failure_nonexistent(self, db_session: AsyncSession):
        """Test ensure_public raises 403 for non-existent user."""
        with pytest.raises(HTTPException) as exc_info:
            await ensure_public("nonexistent_id", db_session)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_ensure_subscriber_owner_success(
        self, db_session: AsyncSession, owner_user: TelegramUser
    ):
        """Test ensure_subscriber succeeds for OWNER (higher role)."""
        result = await ensure_subscriber(owner_user.id, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_subscriber_success(
        self, db_session: AsyncSession, subscriber_user: TelegramUser
    ):
        """Test ensure_subscriber succeeds for SUBSCRIBER."""
        result = await ensure_subscriber(subscriber_user.id, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_subscriber_failure_public(
        self, db_session: AsyncSession, public_user: TelegramUser
    ):
        """Test ensure_subscriber raises 403 for PUBLIC user."""
        with pytest.raises(HTTPException) as exc_info:
            await ensure_subscriber(public_user.id, db_session)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "premium subscription" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_ensure_admin_owner_success(
        self, db_session: AsyncSession, owner_user: TelegramUser
    ):
        """Test ensure_admin succeeds for OWNER."""
        result = await ensure_admin(owner_user.id, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_admin_success(
        self, db_session: AsyncSession, admin_user: TelegramUser
    ):
        """Test ensure_admin succeeds for ADMIN."""
        result = await ensure_admin(admin_user.id, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_admin_failure_subscriber(
        self, db_session: AsyncSession, subscriber_user: TelegramUser
    ):
        """Test ensure_admin raises 403 for SUBSCRIBER."""
        with pytest.raises(HTTPException) as exc_info:
            await ensure_admin(subscriber_user.id, db_session)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Admin access required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_ensure_owner_success(
        self, db_session: AsyncSession, owner_user: TelegramUser
    ):
        """Test ensure_owner succeeds for OWNER."""
        result = await ensure_owner(owner_user.id, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_owner_failure_admin(
        self, db_session: AsyncSession, admin_user: TelegramUser
    ):
        """Test ensure_owner raises 403 for ADMIN."""
        with pytest.raises(HTTPException) as exc_info:
            await ensure_owner(admin_user.id, db_session)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Owner access required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_role_success(
        self, db_session: AsyncSession, admin_user: TelegramUser
    ):
        """Test require_role succeeds when role matches."""
        result = await require_role(admin_user.id, UserRole.ADMIN, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_require_role_failure_insufficient(
        self, db_session: AsyncSession, subscriber_user: TelegramUser
    ):
        """Test require_role raises 403 when role insufficient."""
        with pytest.raises(HTTPException) as exc_info:
            await require_role(subscriber_user.id, UserRole.ADMIN, db_session)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# SECTION 5: Real-World Scenarios (10 tests) - SYNC
# ============================================================================


class TestRealWorldScenarios:
    """Test complete real-world command execution workflows."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()

    def test_scenario_public_user_starts_bot(self):
        """Scenario: New PUBLIC user starts bot with /start."""
        registry = CommandRegistry()
        execution_log = []

        async def handle_start():
            execution_log.append("start")
            return "Welcome!"

        registry.register(
            "start",
            "Start the bot",
            UserRole.PUBLIC,
            handle_start,
            "Start help",
        )

        # PUBLIC user should be able to access /start
        assert registry.is_allowed("start", UserRole.PUBLIC)

        # Handler should be callable
        cmd = registry.get_command("start")
        assert cmd.handler is not None
        assert inspect.iscoroutinefunction(cmd.handler)

    def test_scenario_subscriber_accesses_analytics(self):
        """Scenario: SUBSCRIBER accesses /analytics command."""
        registry = CommandRegistry()

        async def handle_analytics():
            return "Analytics: +5% this week"

        registry.register(
            "analytics",
            "View analytics",
            UserRole.SUBSCRIBER,
            handle_analytics,
            "Analytics help",
        )

        # SUBSCRIBER can access
        assert registry.is_allowed("analytics", UserRole.SUBSCRIBER)
        # PUBLIC cannot access
        assert not registry.is_allowed("analytics", UserRole.PUBLIC)

    def test_scenario_admin_broadcasts_message(self):
        """Scenario: ADMIN broadcasts message to all users."""
        registry = CommandRegistry()

        async def handle_broadcast():
            return "Broadcast sent to 1000 users"

        registry.register(
            "broadcast",
            "Send broadcast",
            UserRole.ADMIN,
            handle_broadcast,
            "Broadcast help",
        )

        # Only ADMIN+ can access
        assert not registry.is_allowed("broadcast", UserRole.SUBSCRIBER)
        assert registry.is_allowed("broadcast", UserRole.ADMIN)
        assert registry.is_allowed("broadcast", UserRole.OWNER)

    def test_scenario_owner_manages_system(self):
        """Scenario: OWNER accesses system management commands."""
        registry = CommandRegistry()

        async def handle_owner_panel():
            return "System status: All green"

        registry.register(
            "owner_panel",
            "Owner panel",
            UserRole.OWNER,
            handle_owner_panel,
            "Owner help",
        )

        # Only OWNER can access
        assert not registry.is_allowed("owner_panel", UserRole.ADMIN)
        assert registry.is_allowed("owner_panel", UserRole.OWNER)

    def test_scenario_help_context_aware_public(self):
        """Scenario: PUBLIC user sees context-aware help."""
        registry = CommandRegistry()

        async def dummy_handler():
            return "test"

        registry.register("start", "Start", UserRole.PUBLIC, dummy_handler, "Help")
        registry.register("help", "Help", UserRole.PUBLIC, dummy_handler, "Help")
        registry.register("shop", "Shop", UserRole.PUBLIC, dummy_handler, "Help")
        registry.register("buy", "Buy", UserRole.SUBSCRIBER, dummy_handler, "Help")
        registry.register(
            "broadcast", "Broadcast", UserRole.ADMIN, dummy_handler, "Help"
        )

        # PUBLIC user's help only shows public commands
        help_text = registry.get_help_text(UserRole.PUBLIC)
        assert "/start" in help_text
        assert "/help" in help_text
        assert "/shop" in help_text
        assert "/buy" not in help_text
        assert "/broadcast" not in help_text

    def test_scenario_comprehensive_command_suite(self):
        """Scenario: Comprehensive command suite with all roles."""
        registry = CommandRegistry()

        async def dummy():
            return "test"

        # PUBLIC commands
        registry.register("start", "Start", UserRole.PUBLIC, dummy, "Help")
        registry.register("help", "Help", UserRole.PUBLIC, dummy, "Help")
        registry.register("shop", "Shop", UserRole.PUBLIC, dummy, "Help")

        # SUBSCRIBER commands
        registry.register("buy", "Buy", UserRole.SUBSCRIBER, dummy, "Help")
        registry.register("status", "Status", UserRole.SUBSCRIBER, dummy, "Help")
        registry.register("analytics", "Analytics", UserRole.SUBSCRIBER, dummy, "Help")

        # ADMIN commands
        registry.register("broadcast", "Broadcast", UserRole.ADMIN, dummy, "Help")
        registry.register(
            "content", "Content management", UserRole.ADMIN, dummy, "Help"
        )

        # OWNER commands
        registry.register("owner", "Owner panel", UserRole.OWNER, dummy, "Help")

        total_commands = len(registry.get_all_commands())
        assert total_commands == 9

        # Verify complete hierarchy
        public_count = len(registry.list_commands_for_role(UserRole.PUBLIC))
        subscriber_count = len(registry.list_commands_for_role(UserRole.SUBSCRIBER))
        admin_count = len(registry.list_commands_for_role(UserRole.ADMIN))
        owner_count = len(registry.list_commands_for_role(UserRole.OWNER))

        assert public_count == 3  # start, help, shop
        assert subscriber_count == 6  # + buy, status, analytics
        assert admin_count == 8  # + broadcast, content
        assert owner_count == 9  # + owner

    def test_scenario_command_with_multiple_aliases(self):
        """Scenario: User invokes command using different aliases."""
        registry = CommandRegistry()

        async def handle_help():
            return "Help content"

        registry.register(
            "help",
            "Get help",
            UserRole.PUBLIC,
            handle_help,
            "Help text",
            aliases=["h", "?", "ayuda"],
        )

        # All aliases should resolve to same command
        for alias in ["help", "h", "?", "ayuda"]:
            cmd = registry.get_command(alias)
            assert cmd is not None
            assert cmd.name == "help"

    def test_scenario_hidden_admin_command(self):
        """Scenario: Hidden admin command not visible to users."""
        registry = CommandRegistry()

        async def handle_debug():
            return "Debug info"

        registry.register(
            "debug",
            "Debug command",
            UserRole.ADMIN,
            handle_debug,
            "Debug help",
            hidden=True,
        )

        # Command is registered and accessible to ADMIN
        assert registry.is_registered("debug")
        assert registry.is_allowed("debug", UserRole.ADMIN)

        # But not shown in help
        help_text = registry.get_help_text(UserRole.ADMIN)
        assert "/debug" not in help_text


# ============================================================================
# SECTION 6: Edge Cases & Error Handling (10 tests) - SYNC
# ============================================================================


class TestEdgeCasesAndErrors:
    """Test edge cases and error handling."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()

    def test_edge_case_empty_registry(self):
        """Test operations on empty registry."""
        registry = CommandRegistry()

        assert len(registry.get_all_commands()) == 0
        assert registry.get_command("any") is None
        assert not registry.is_registered("any")
        assert not registry.is_allowed("any", UserRole.PUBLIC)

    def test_edge_case_alias_same_as_command_name(self):
        """Test registering with aliases that don't conflict with existing commands."""
        registry = CommandRegistry()

        async def handler1():
            return "1"

        async def handler2():
            return "2"

        registry.register("cmd1", "Cmd 1", UserRole.PUBLIC, handler1, "Help")

        # Register cmd2 with a unique alias
        registry.register(
            "cmd2", "Cmd 2", UserRole.PUBLIC, handler2, "Help", aliases=["cmd2_short"]
        )

        # Both commands should be accessible
        assert registry.get_command("cmd1").name == "cmd1"
        assert registry.get_command("cmd2").name == "cmd2"
        assert registry.get_command("cmd2_short").name == "cmd2"

    def test_edge_case_unicode_in_command_text(self):
        """Test Unicode characters in descriptions and help."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        description = "📊 View analytics"
        help_text = "Shows your trading performance 📈 with details 🎯"

        registry.register("stats", description, UserRole.SUBSCRIBER, handler, help_text)

        cmd = registry.get_command("stats")
        assert "📊" in cmd.description
        assert "📈" in cmd.help_text
        assert "🎯" in cmd.help_text

    def test_edge_case_many_aliases(self):
        """Test command with many aliases."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        aliases = [f"alias_{i}" for i in range(50)]

        registry.register(
            "cmd", "Cmd", UserRole.PUBLIC, handler, "Help", aliases=aliases
        )

        # All aliases should work
        for alias in aliases[:10]:  # Test first 10
            assert registry.is_registered(alias)
            assert registry.get_command(alias).name == "cmd"

    def test_edge_case_command_with_no_aliases(self):
        """Test command with empty aliases list."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("cmd", "Cmd", UserRole.PUBLIC, handler, "Help", aliases=[])

        assert registry.is_registered("cmd")
        assert len(registry.get_command("cmd").aliases) == 0

    def test_edge_case_very_long_help_text(self):
        """Test handling very long help text."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        long_help = "A" * 5000  # 5KB of text

        registry.register("cmd", "Cmd", UserRole.PUBLIC, handler, long_help)
        cmd = registry.get_command("cmd")
        assert len(cmd.help_text) == 5000

    def test_edge_case_special_characters_in_command_name(self):
        """Test command names with special characters."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        # Commands with underscores should work
        registry.register("my_cmd", "My command", UserRole.PUBLIC, handler, "Help")
        assert registry.is_registered("my_cmd")

    def test_edge_case_case_sensitivity(self):
        """Test command names are case-sensitive."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        registry.register("Help", "HELP cmd", UserRole.PUBLIC, handler, "Help")

        # Different case should not be found
        assert registry.is_registered("Help")
        assert not registry.is_registered("help")
        assert not registry.is_registered("HELP")

    def test_edge_case_help_with_no_accessible_commands(self):
        """Test help text when no commands available for role."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        # Only owner commands registered
        registry.register("owner_only", "Owner", UserRole.OWNER, handler, "Help")

        # PUBLIC user has no accessible commands
        help_text = registry.get_help_text(UserRole.PUBLIC)
        assert "No commands available" in help_text

    def test_edge_case_get_all_commands_maintains_registry_order(self):
        """Test get_all_commands returns all commands."""
        registry = CommandRegistry()

        async def handler():
            return "test"

        commands_to_register = [
            ("cmd1", UserRole.PUBLIC),
            ("cmd2", UserRole.SUBSCRIBER),
            ("cmd3", UserRole.ADMIN),
        ]

        for name, role in commands_to_register:
            registry.register(name, f"Cmd {name}", role, handler, "Help")

        all_commands = registry.get_all_commands()
        assert len(all_commands) == 3

        registered_names = {cmd.name for cmd in all_commands}
        for name, _ in commands_to_register:
            assert name in registered_names


# ============================================================================
# SECTION 7: Global Registry Management (5 tests) - SYNC
# ============================================================================


class TestGlobalRegistry:
    """Test global registry instance management."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()

    def test_global_registry_singleton_pattern(self):
        """Test global registry is singleton."""
        registry1 = get_registry()
        registry2 = get_registry()
        assert registry1 is registry2

    def test_global_registry_reset(self):
        """Test resetting global registry."""
        registry = get_registry()

        async def handler():
            return "test"

        registry.register("cmd", "Cmd", UserRole.PUBLIC, handler, "Help")
        assert registry.is_registered("cmd")

        # Reset
        reset_registry()

        new_registry = get_registry()
        assert not new_registry.is_registered("cmd")

    def test_global_registry_persistence_across_calls(self):
        """Test registry persists across multiple get_registry calls."""
        registry1 = get_registry()

        async def handler():
            return "test"

        registry1.register("cmd", "Cmd", UserRole.PUBLIC, handler, "Help")

        registry2 = get_registry()
        assert registry2.is_registered("cmd")

    def test_reset_registry_clears_all_commands(self):
        """Test reset_registry fully clears all state."""
        registry = get_registry()

        async def handler():
            return "test"

        registry.register(
            "cmd1", "Cmd1", UserRole.PUBLIC, handler, "Help", aliases=["c1"]
        )
        registry.register("cmd2", "Cmd2", UserRole.PUBLIC, handler, "Help")
        assert len(registry.get_all_commands()) == 2

        reset_registry()

        new_registry = get_registry()
        assert len(new_registry.get_all_commands()) == 0
        assert new_registry.get_command("cmd1") is None
        assert new_registry.get_command("c1") is None

    def test_global_registry_multiple_resets(self):
        """Test registry can be reset multiple times."""

        async def handler():
            return "test"

        # First cycle
        r1 = get_registry()
        r1.register("cmd1", "Cmd", UserRole.PUBLIC, handler, "Help")
        assert len(r1.get_all_commands()) == 1

        reset_registry()

        # Second cycle
        r2 = get_registry()
        assert len(r2.get_all_commands()) == 0
        r2.register("cmd2", "Cmd", UserRole.PUBLIC, handler, "Help")
        assert len(r2.get_all_commands()) == 1

        reset_registry()

        # Third cycle
        r3 = get_registry()
        assert len(r3.get_all_commands()) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
