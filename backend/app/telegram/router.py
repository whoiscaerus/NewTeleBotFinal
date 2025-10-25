"""Telegram command routing and dispatch logic."""

import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.telegram.schema import (
    TelegramCallback,
    TelegramMessage,
    TelegramUpdate,
)

logger = logging.getLogger(__name__)


class CommandRouter:
    """Routes Telegram updates to appropriate handlers based on command."""

    def __init__(self, db: AsyncSession):
        """Initialize router.

        Args:
            db: Database session
        """
        self.db = db
        self.handlers: dict[str, Callable] = {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register built-in command handlers."""
        self.handlers = {
            "start": self.handle_start,
            "help": self.handle_help,
            "shop": self.handle_shop,
            "affiliate": self.handle_affiliate,
            "stats": self.handle_stats,
            "unknown": self.handle_unknown,
        }

    def register_handler(self, command: str, handler: Callable) -> None:
        """Register a custom command handler.

        Args:
            command: Command name (without leading /)
            handler: Async callable(update, db) → response
        """
        self.handlers[command] = handler
        logger.info(f"Registered handler for /{command}")

    async def route(self, update: TelegramUpdate) -> None:
        """Route update to appropriate handler.

        Args:
            update: Telegram update from webhook
        """
        try:
            if update.message and update.message.text:
                await self._route_message(update.message)
            elif update.callback_query:
                await self._route_callback(update.callback_query)
        except Exception as e:
            logger.error(f"Routing error: {e}", exc_info=True)

    async def _route_message(self, message: TelegramMessage) -> None:
        """Route message to command handler.

        Args:
            message: Telegram message
        """
        command = self._extract_command(message.text)

        if command in self.handlers:
            handler = self.handlers[command]
            await handler(message)
        else:
            await self.handle_unknown(message)

    async def _route_callback(self, callback: TelegramCallback) -> None:
        """Route callback query (button click) to handler.

        Args:
            callback: Telegram callback query
        """
        try:
            # Parse callback data format: "command:params"
            if callback.data:
                parts = callback.data.split(":", 1)
                command = parts[0]

                if command == "shop":
                    await self.handle_shop_callback(callback)
                elif command == "checkout":
                    await self.handle_checkout_callback(callback)
                else:
                    logger.warning(f"Unknown callback command: {command}")
        except Exception as e:
            logger.error(f"Callback routing error: {e}", exc_info=True)

    @staticmethod
    def _extract_command(text: str | None) -> str:
        """Extract command from message text.

        Args:
            text: Message text

        Returns:
            Command name (without leading /)
        """
        if not text or not text.startswith("/"):
            return "unknown"

        parts = text.split()
        command = parts[0][1:].lower()  # Remove leading /

        return command or "unknown"

    async def handle_start(self, message: TelegramMessage) -> None:
        """Handle /start command.

        Args:
            message: Telegram message
        """
        logger.info(f"Start command from user {message.from_user.id}")
        # Placeholder - would send welcome message

    async def handle_help(self, message: TelegramMessage) -> None:
        """Handle /help command.

        Args:
            message: Telegram message
        """
        logger.info(f"Help command from user {message.from_user.id}")
        # Placeholder - would show help menu

    async def handle_shop(self, message: TelegramMessage) -> None:
        """Handle /shop command.

        Args:
            message: Telegram message
        """
        logger.info(f"Shop command from user {message.from_user.id}")
        # Placeholder - would show product list (PR-030)

    async def handle_affiliate(self, message: TelegramMessage) -> None:
        """Handle /affiliate command.

        Args:
            message: Telegram message
        """
        logger.info(f"Affiliate command from user {message.from_user.id}")
        # Placeholder - would show affiliate stats (from PR-024)

    async def handle_stats(self, message: TelegramMessage) -> None:
        """Handle /stats command.

        Args:
            message: Telegram message
        """
        logger.info(f"Stats command from user {message.from_user.id}")
        # Placeholder - would show user statistics

    async def handle_unknown(self, message: TelegramMessage) -> None:
        """Handle unknown command.

        Args:
            message: Telegram message
        """
        logger.warning(
            f"Unknown command from user {message.from_user.id}: {message.text}"
        )
        # Placeholder - would send "I don't understand" message

    async def handle_shop_callback(self, callback: TelegramCallback) -> None:
        """Handle shop button click.

        Args:
            callback: Telegram callback query
        """
        logger.info(f"Shop callback from user {callback.from_user.id}: {callback.data}")
        # Placeholder - PR-030 will implement

    async def handle_checkout_callback(self, callback: TelegramCallback) -> None:
        """Handle checkout button click.

        Args:
            callback: Telegram callback query
        """
        logger.info(
            f"Checkout callback from user {callback.from_user.id}: {callback.data}"
        )
        # Placeholder - PR-030 will implement
