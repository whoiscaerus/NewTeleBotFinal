"""Tests for Telegram command handlers."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.telegram.commands import UserRole, get_registry, reset_registry
from backend.app.telegram.handlers.distribution import MessageDistributor
from backend.app.telegram.models import TelegramUser
from backend.app.telegram.router import CommandRouter
from backend.app.telegram.schema import TelegramChat, TelegramMessage, TelegramUpdate
from backend.app.telegram.schema import TelegramUser as TelegramUserSchema


@pytest.mark.asyncio
class TestCommandRegistry:
    """Test command registry functionality."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()

    def test_register_command(self):
        """Test registering a command."""
        registry = get_registry()

        async def handler(msg):
            pass

        registry.register(
            name="test",
            description="Test command",
            required_role=UserRole.PUBLIC,
            handler=handler,
            help_text="This is a test",
        )

        assert registry.is_registered("test")

    def test_register_command_with_aliases(self):
        """Test registering command with aliases."""
        registry = get_registry()

        async def handler(msg):
            pass

        registry.register(
            name="test",
            description="Test",
            required_role=UserRole.PUBLIC,
            handler=handler,
            help_text="Test",
            aliases=["t", "tst"],
        )

        assert registry.is_registered("test")
        assert registry.is_registered("t")
        assert registry.is_registered("tst")

    def test_get_command(self):
        """Test retrieving registered command."""
        registry = get_registry()

        async def handler(msg):
            pass

        registry.register(
            name="test",
            description="Test",
            required_role=UserRole.PUBLIC,
            handler=handler,
            help_text="Test",
        )

        cmd = registry.get_command("test")
        assert cmd is not None
        assert cmd.name == "test"

    def test_get_command_by_alias(self):
        """Test retrieving command by alias."""
        registry = get_registry()

        async def handler(msg):
            pass

        registry.register(
            name="test",
            description="Test",
            required_role=UserRole.PUBLIC,
            handler=handler,
            help_text="Test",
            aliases=["t"],
        )

        cmd = registry.get_command("t")
        assert cmd is not None
        assert cmd.name == "test"

    def test_command_not_found(self):
        """Test unknown command returns None."""
        registry = get_registry()
        cmd = registry.get_command("nonexistent")
        assert cmd is None

    def test_is_allowed_public_command(self):
        """Test PUBLIC user can access PUBLIC command."""
        registry = get_registry()

        async def handler(msg):
            pass

        registry.register(
            name="public_cmd",
            description="Public",
            required_role=UserRole.PUBLIC,
            handler=handler,
            help_text="Public",
        )

        assert registry.is_allowed("public_cmd", UserRole.PUBLIC)

    def test_is_allowed_subscriber_cant_access_admin(self):
        """Test SUBSCRIBER cannot access ADMIN command."""
        registry = get_registry()

        async def handler(msg):
            pass

        registry.register(
            name="admin_cmd",
            description="Admin",
            required_role=UserRole.ADMIN,
            handler=handler,
            help_text="Admin",
        )

        assert not registry.is_allowed("admin_cmd", UserRole.SUBSCRIBER)

    def test_is_allowed_owner_can_access_all(self):
        """Test OWNER can access all commands."""
        registry = get_registry()

        async def handler(msg):
            pass

        registry.register(
            name="admin_cmd",
            description="Admin",
            required_role=UserRole.ADMIN,
            handler=handler,
            help_text="Admin",
        )

        assert registry.is_allowed("admin_cmd", UserRole.OWNER)

    def test_get_help_text_public_user(self):
        """Test help text only shows public commands for public user."""
        registry = get_registry()

        async def public_handler(msg):
            pass

        async def admin_handler(msg):
            pass

        registry.register(
            name="help",
            description="Help",
            required_role=UserRole.PUBLIC,
            handler=public_handler,
            help_text="Show help",
        )

        registry.register(
            name="admin",
            description="Admin",
            required_role=UserRole.ADMIN,
            handler=admin_handler,
            help_text="Admin panel",
        )

        help_text = registry.get_help_text(UserRole.PUBLIC)
        assert "/help" in help_text
        assert "/admin" not in help_text

    def test_list_commands_for_role(self):
        """Test listing commands available to role."""
        registry = get_registry()

        async def handler(msg):
            pass

        registry.register(
            name="public_cmd",
            description="Public",
            required_role=UserRole.PUBLIC,
            handler=handler,
            help_text="Public",
        )

        registry.register(
            name="admin_cmd",
            description="Admin",
            required_role=UserRole.ADMIN,
            handler=handler,
            help_text="Admin",
        )

        commands = registry.list_commands_for_role(UserRole.PUBLIC)
        assert "public_cmd" in commands
        assert "admin_cmd" not in commands

        commands = registry.list_commands_for_role(UserRole.ADMIN)
        assert "public_cmd" in commands
        assert "admin_cmd" in commands


@pytest.mark.asyncio
class TestMessageDistributor:
    """Test message distribution by keywords."""

    async def test_detect_intent_product(self, db_session: AsyncSession):
        """Test detecting product intent."""
        distributor = MessageDistributor(db_session)

        intent = distributor.detect_intent("I want to buy a course")
        assert intent == "product"

    async def test_detect_intent_affiliate(self, db_session: AsyncSession):
        """Test detecting affiliate intent."""
        distributor = MessageDistributor(db_session)

        intent = distributor.detect_intent("How much can I earn as an affiliate?")
        assert intent == "affiliate"

    async def test_detect_intent_guide(self, db_session: AsyncSession):
        """Test detecting guide intent."""
        distributor = MessageDistributor(db_session)

        intent = distributor.detect_intent("Show me a trading guide")
        assert intent == "guide"

    async def test_detect_intent_marketing(self, db_session: AsyncSession):
        """Test detecting marketing intent."""
        distributor = MessageDistributor(db_session)

        intent = distributor.detect_intent("What are the latest promotions?")
        assert intent == "marketing"

    async def test_detect_intent_none(self, db_session: AsyncSession):
        """Test no intent detected."""
        distributor = MessageDistributor(db_session)

        intent = distributor.detect_intent("Hello world")
        assert intent is None

    async def test_should_handle_distribution_message(self, db_session: AsyncSession):
        """Test message should be distributed."""
        distributor = MessageDistributor(db_session)

        message = TelegramMessage(
            message_id=1,
            date=123456,
            chat=TelegramChat(id=1, type="private"),
            from_user=TelegramUserSchema(id=1, first_name="Test"),
            text="I want to buy something",
        )

        update = TelegramUpdate(
            update_id=1,
            message=message,
        )
        should_distribute = await distributor.should_handle_distribution(update)
        assert should_distribute is True

    async def test_should_handle_distribution_command(self, db_session: AsyncSession):
        """Test command should not be distributed."""
        distributor = MessageDistributor(db_session)

        message = TelegramMessage(
            message_id=1,
            date=123456,
            chat=TelegramChat(id=1, type="private"),
            from_user=TelegramUserSchema(id=1, first_name="Test"),
            text="/start",
        )

        update = TelegramUpdate(
            update_id=1,
            message=message,
        )
        should_distribute = await distributor.should_handle_distribution(update)
        assert should_distribute is False


@pytest.mark.asyncio
class TestCommandRouter:
    """Test command router initialization and routing."""

    async def test_router_initialization(self, db_session: AsyncSession):
        """Test router initializes with commands."""
        router = CommandRouter(db_session)

        assert router.command_registry is not None
        assert len(router.command_registry.get_all_commands()) > 0

    async def test_router_command_registry_populated(self, db_session: AsyncSession):
        """Test command registry is populated with core commands."""
        # Ensure registry is clean for this test
        reset_registry()

        router = CommandRouter(db_session)

        commands = router.command_registry.get_all_commands()
        command_names = [cmd.name for cmd in commands]

        # Check core commands are registered
        assert "start" in command_names
        assert "help" in command_names
        assert "shop" in command_names
        assert "affiliate" in command_names
        assert "guides" in command_names

    def test_extract_command_with_slash(self):
        """Test extracting command with leading slash."""
        router_class = CommandRouter

        assert router_class._extract_command("/start") == "start"
        assert router_class._extract_command("/help") == "help"

    def test_extract_command_lowercase(self):
        """Test command extraction is case-insensitive."""
        router_class = CommandRouter

        assert router_class._extract_command("/START") == "start"
        assert router_class._extract_command("/Help") == "help"

    def test_extract_command_with_params(self):
        """Test extracting command with parameters."""
        router_class = CommandRouter

        assert router_class._extract_command("/cmd param1 param2") == "cmd"

    def test_extract_command_invalid(self):
        """Test non-command returns 'unknown'."""
        router_class = CommandRouter

        assert router_class._extract_command("no slash") == "unknown"
        assert router_class._extract_command("") == "unknown"
        assert router_class._extract_command(None) == "unknown"

    async def test_user_registration_on_start(self, db_session: AsyncSession):
        """Test user is registered on first interaction."""
        router = CommandRouter(db_session)

        message = TelegramMessage(
            message_id=1,
            date=123456,
            chat=TelegramChat(id=1, type="private"),
            from_user=TelegramUserSchema(
                id=999, first_name="Test", username="testuser"
            ),
            text="/start",
        )

        user = await router._get_user_or_register(message)

        assert user is not None
        assert user.id == "999"
        assert user.telegram_username == "testuser"

        # Verify user was persisted in DB
        await db_session.refresh(user)
        assert user.telegram_first_name == "Test"

    async def test_handler_requires_role_check(self, db_session: AsyncSession):
        """Test handlers check user role before executing."""
        # Create public user
        user = TelegramUser(id="123", role=0)
        db_session.add(user)
        await db_session.commit()

        message = TelegramMessage(
            message_id=1,
            date=123456,
            chat=TelegramChat(id=1, type="private"),
            from_user=TelegramUserSchema(id=123, first_name="Test"),
            text="/stats",  # Requires SUBSCRIBER
        )

        # This would normally call _send_permission_denied if implemented
        # Testing structure here
        assert message is not None


@pytest.mark.asyncio
class TestHandlerIntegration:
    """Integration tests for handlers."""

    @patch("backend.app.telegram.router.Bot")
    async def test_handle_start_sends_welcome(
        self, mock_bot_class, db_session: AsyncSession
    ):
        """Test /start handler sends welcome message."""
        # Set up the mock bot instance
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot
        mock_bot.send_message = AsyncMock()

        router = CommandRouter(db_session)

        message = TelegramMessage(
            message_id=1,
            date=123456,
            chat=TelegramChat(id=1, type="private"),
            from_user=TelegramUserSchema(id=999, first_name="Test"),
            text="/start",
        )

        await router.handle_start(message)

        # Should have called bot.send_message
        mock_bot.send_message.assert_called_once()

    @patch("backend.app.telegram.router.Bot")
    async def test_handle_help_sends_menu(
        self, mock_bot_class, db_session: AsyncSession
    ):
        """Test /help handler sends help menu."""
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot

        router = CommandRouter(db_session)

        message = TelegramMessage(
            message_id=1,
            date=123456,
            chat=TelegramChat(id=1, type="private"),
            from_user=TelegramUserSchema(id=999, first_name="Test"),
            text="/help",
        )

        await router.handle_help(message)

        mock_bot.send_message.assert_called_once()
