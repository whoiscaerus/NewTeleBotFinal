"""Telegram command routing and dispatch logic."""

import logging
from collections.abc import Callable
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from backend.app.core.settings import settings
from backend.app.telegram.commands import UserRole, get_registry
from backend.app.telegram.handlers.distribution import MessageDistributor
from backend.app.telegram.handlers.guides import handle_guides_command
from backend.app.telegram.handlers.marketing import handle_marketing_updates
from backend.app.telegram.models import TelegramUser
from backend.app.telegram.rbac import get_user_role
from backend.app.telegram.schema import (
    TelegramCallback,
    TelegramMessage,
    TelegramUpdate,
)

logger = logging.getLogger(__name__)


class CommandRouter:
    """Routes Telegram updates to appropriate handlers based on command.

    Handles:
    - Command extraction and routing
    - Role-based access control
    - Message distribution to intent-specific handlers
    - Callback query routing
    - Error handling and logging

    Integrates with:
    - CommandRegistry (command definitions, roles)
    - MessageDistributor (keyword-based routing)
    - GuideHandler (guide delivery)
    - MarketingHandler (promotional content)
    - RBAC module (permission checking)
    """

    def __init__(self, db: AsyncSession):
        """Initialize router.

        Args:
            db: Database session
        """
        self.db = db
        self.bot_token = settings.telegram_bot_token
        self.command_registry = get_registry()
        self._initialize_command_registry()

    def _initialize_command_registry(self) -> None:
        """Initialize command registry with all command definitions.

        Registers all Telegram commands with their handlers and role requirements.
        """
        try:
            # Only register if not already done
            if len(self.command_registry.get_all_commands()) > 0:
                return

            # /start - Welcome and user registration
            self.command_registry.register(
                name="start",
                description="Welcome and initialize bot",
                required_role=UserRole.PUBLIC,
                handler=self.handle_start,
                help_text=(
                    "Start the bot and register your account.\n\n"
                    "This initializes your user profile and subscribes you to updates."
                ),
            )

            # /help - Command help and menu
            self.command_registry.register(
                name="help",
                description="Show available commands",
                required_role=UserRole.PUBLIC,
                handler=self.handle_help,
                help_text=(
                    "Display this help menu with all available commands "
                    "for your user role."
                ),
            )

            # /shop - Browse and purchase products
            self.command_registry.register(
                name="shop",
                description="Browse products and courses",
                required_role=UserRole.PUBLIC,
                handler=self.handle_shop,
                help_text="Browse our product catalog and courses. Click to view details.",
                aliases=["products", "catalog"],
            )

            # /affiliate - Affiliate program stats
            self.command_registry.register(
                name="affiliate",
                description="View affiliate earnings",
                required_role=UserRole.PUBLIC,
                handler=self.handle_affiliate,
                help_text="View your referral stats and earnings from the affiliate program.",
                aliases=["referral"],
            )

            # /stats - User trading statistics
            self.command_registry.register(
                name="stats",
                description="View your statistics",
                required_role=UserRole.SUBSCRIBER,
                handler=self.handle_stats,
                help_text="View your trading statistics and performance metrics.",
                aliases=["performance"],
            )

            # /guides - Educational guides
            self.command_registry.register(
                name="guides",
                description="Access educational guides",
                required_role=UserRole.PUBLIC,
                handler=self.handle_guides,
                help_text="Browse tutorials and educational content to improve your trading.",
                aliases=["tutorials", "learn"],
            )

            # /newsletter - Marketing updates
            self.command_registry.register(
                name="newsletter",
                description="View latest updates and offers",
                required_role=UserRole.PUBLIC,
                handler=self.handle_newsletter,
                help_text="Stay updated with latest features, offers, and announcements.",
                aliases=["updates", "news"],
            )

            # /admin - Admin commands (owner only)
            self.command_registry.register(
                name="admin",
                description="Admin control panel",
                required_role=UserRole.ADMIN,
                handler=self.handle_admin,
                help_text="Access admin functions for bot management.",
                hidden=True,  # Don't show to regular users
            )

            logger.info(
                f"Command registry initialized with {len(self.command_registry.get_all_commands())} commands"
            )

        except Exception as e:
            logger.error(f"Error initializing command registry: {e}", exc_info=True)

    async def _get_user_or_register(
        self, message: TelegramMessage
    ) -> Optional[TelegramUser]:
        """Get user from database, creating if necessary.

        Args:
            message: Telegram message

        Returns:
            TelegramUser object or None
        """
        user_id = str(message.from_user.id)

        # Try to fetch existing user
        query = select(TelegramUser).where(TelegramUser.id == user_id)
        result = await self.db.execute(query)
        user = result.scalars().first()

        if user:
            return user

        # Create new user
        try:
            user = TelegramUser(
                id=user_id,
                telegram_username=message.from_user.username or "",
                telegram_first_name=message.from_user.first_name or "",
                telegram_last_name=message.from_user.last_name or "",
                role=0,  # PUBLIC
                is_active=True,
            )
            self.db.add(user)
            await self.db.commit()

            logger.info(f"New user created: {user_id}")
            return user

        except Exception as e:
            logger.error(f"Error creating user: {e}", exc_info=True)
            return None

    async def route(self, update: TelegramUpdate) -> None:
        """Route update to appropriate handler.

        Handles:
        - Message commands (/start, /help, etc.)
        - Keyword-based message distribution
        - Callback queries (button clicks)

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
        """Route message to command handler or distributor.

        Priority:
        1. If message starts with /, treat as command and route to command handler
        2. Otherwise, use MessageDistributor for keyword-based routing
        3. If no handler matches, send help message

        Args:
            message: Telegram message
        """
        user_id = str(message.from_user.id)

        # Ensure user exists
        user = await self._get_user_or_register(message)
        if not user:
            return

        # Check if message is a command
        if message.text and message.text.startswith("/"):
            command = self._extract_command(message.text)

            # Check if command is registered
            if not self.command_registry.is_registered(command):
                await self.handle_unknown(message)
                return

            # Check if user has permission
            user_role = await get_user_role(user_id, self.db)
            if user_role is None:
                user_role = UserRole.PUBLIC

            if not self.command_registry.is_allowed(command, user_role):
                await self._send_permission_denied(message)
                return

            # Get and execute handler
            command_info = self.command_registry.get_command(command)
            if command_info:
                await command_info.handler(message)
                logger.info(
                    f"Command executed: /{command}",
                    extra={"user_id": user_id, "command": command},
                )

        else:
            # Use MessageDistributor for keyword-based routing
            distributor = MessageDistributor(self.db)
            distributed = await distributor.distribute(
                TelegramUpdate(message=message),
                {
                    "shop": lambda m: self._execute_handler_with_update(
                        self.handle_shop, TelegramUpdate(message=m)
                    ),
                    "affiliate": lambda m: self._execute_handler_with_update(
                        self.handle_affiliate, TelegramUpdate(message=m)
                    ),
                    "guide": handle_guides_command,
                    "marketing": handle_marketing_updates,
                },
            )

            if not distributed:
                # No keyword match - show help
                await self._send_help_menu(message)

    async def _execute_handler_with_update(
        self, handler: Callable, update: TelegramUpdate
    ) -> None:
        """Execute handler that expects TelegramUpdate instead of message.

        Args:
            handler: Handler function
            update: Telegram update
        """
        try:
            await handler(update, self.db)
        except Exception as e:
            logger.error(f"Handler error: {e}", exc_info=True)

    async def _route_callback(self, callback: TelegramCallback) -> None:
        """Route callback query (button click) to handler.

        Callback data format: "command:params"

        Args:
            callback: Telegram callback query
        """
        try:
            if not callback.data:
                return

            # Parse callback data
            parts = callback.data.split(":", 1)
            command = parts[0]

            user_id = str(callback.from_user.id)
            user_role = await get_user_role(user_id, self.db)

            # Route by callback command
            if command == "shop":
                await self.handle_shop_callback(callback)
            elif command == "checkout":
                await self.handle_checkout_callback(callback)
            elif command.startswith("guide_"):
                await self.handle_guide_callback(callback)
            elif command.startswith("campaign_"):
                await self.handle_campaign_callback(callback)
            else:
                logger.warning(f"Unknown callback command: {command}")

            # Answer callback (remove loading indicator)
            bot = Bot(token=self.bot_token)
            await bot.answer_callback_query(callback_query_id=callback.id)

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

    async def _send_permission_denied(self, message: TelegramMessage) -> None:
        """Send permission denied message.

        Args:
            message: Telegram message
        """
        try:
            user_role = await get_user_role(str(message.from_user.id), self.db)
            role_name = user_role.value if user_role else "user"

            response_text = (
                f"❌ *Permission Denied*\n\n"
                f"This command requires higher privileges.\n"
                f"Your role: {role_name}\n\n"
                f"Consider subscribing to premium to unlock more features!"
            )

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=message.chat.id,
                text=response_text,
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.error(f"Error sending permission denied: {e}", exc_info=True)

    async def _send_help_menu(self, message: TelegramMessage) -> None:
        """Send help menu for user's role.

        Args:
            message: Telegram message
        """
        try:
            user_role = await get_user_role(str(message.from_user.id), self.db)
            if user_role is None:
                user_role = UserRole.PUBLIC

            help_text = self.command_registry.get_help_text(user_role)

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=message.chat.id,
                text=help_text,
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.error(f"Error sending help menu: {e}", exc_info=True)

    # Command Handlers

    async def handle_start(self, message: TelegramMessage) -> None:
        """Handle /start command - Welcome and registration.

        Sends welcome message and ensures user is registered.

        Args:
            message: Telegram message
        """
        try:
            user = await self._get_user_or_register(message)
            if not user:
                return

            user_id = str(message.from_user.id)
            first_name = message.from_user.first_name or "Trader"

            response_text = (
                f"👋 *Welcome to TradingBot, {first_name}!*\n\n"
                f"🤖 I'm your AI-powered trading signal and strategy assistant.\n\n"
                f"*What I can help with:*\n"
                f"📊 Real-time trading signals and alerts\n"
                f"📈 Technical analysis and chart insights\n"
                f"💡 Trading strategies and best practices\n"
                f"💰 Portfolio management and tracking\n"
                f"🎓 Educational guides and tutorials\n\n"
                f"*Get started:*\n"
                f"• Type /help to see available commands\n"
                f"• Type /shop to explore premium features\n"
                f"• Type /guides to learn trading strategies\n\n"
                f"Let's start trading! 🚀"
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="📚 View Guides", callback_data="guide_categories"
                        ),
                        InlineKeyboardButton(
                            text="🛒 Browse Shop", callback_data="shop:featured"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            text="⭐ Premium Features", callback_data="premium_info"
                        ),
                        InlineKeyboardButton(text="📖 Help", callback_data="help_menu"),
                    ],
                ]
            )

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=message.chat.id,
                text=response_text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

            logger.info("Start command executed", extra={"user_id": user_id})

        except Exception as e:
            logger.error(f"Error in handle_start: {e}", exc_info=True)

    async def handle_help(self, message: TelegramMessage) -> None:
        """Handle /help command - Show available commands.

        Args:
            message: Telegram message
        """
        try:
            await self._send_help_menu(message)
            logger.info(
                "Help command executed", extra={"user_id": str(message.from_user.id)}
            )

        except Exception as e:
            logger.error(f"Error in handle_help: {e}", exc_info=True)

    async def handle_shop(self, message: TelegramMessage) -> None:
        """Handle /shop command - Browse products.

        This is a placeholder that shows shop menu. Full product browsing
        is handled in PR-030.

        Args:
            message: Telegram message
        """
        try:
            response_text = (
                "🛒 *Our Shop*\n\n"
                "Browse our premium courses and tools:\n\n"
                "📚 *Trading Courses*\n"
                "• Beginner Trading Fundamentals\n"
                "• Advanced Technical Analysis\n"
                "• Automated Trading Strategies\n\n"
                "⚙️ *Tools*\n"
                "• Trading Signal Bot\n"
                "• Technical Indicator Pack\n\n"
                "💎 *Premium Membership*\n"
                "Unlimited signals, priority support, and more!\n\n"
                "_Use buttons below to explore products_"
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="📚 Browse Courses", callback_data="shop:courses"
                        )
                    ],
                    [InlineKeyboardButton(text="⚙️ Tools", callback_data="shop:tools")],
                    [
                        InlineKeyboardButton(
                            text="💎 Premium", callback_data="premium_info"
                        )
                    ],
                ]
            )

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=message.chat.id,
                text=response_text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

            logger.info(
                "Shop command executed", extra={"user_id": str(message.from_user.id)}
            )

        except Exception as e:
            logger.error(f"Error in handle_shop: {e}", exc_info=True)

    async def handle_affiliate(self, message: TelegramMessage) -> None:
        """Handle /affiliate command - Show affiliate stats.

        Shows referral earnings and program info.

        Args:
            message: Telegram message
        """
        try:
            response_text = (
                "🤝 *Affiliate Program*\n\n"
                "*Your Earnings:*\n"
                "💰 Current Balance: $0.00\n"
                "📊 Total Referrals: 0\n"
                "✅ Active Subscribers: 0\n"
                "🎁 Lifetime Earnings: $0.00\n\n"
                "*Referral Link:*\n"
                "Share your link to earn 20% of every sale!\n\n"
                "_Full affiliate details available on web dashboard_"
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="🔗 Get Referral Link",
                            url=f"{settings.FRONTEND_URL}/affiliate",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="📈 Affiliate Dashboard",
                            url=f"{settings.FRONTEND_URL}/dashboard/affiliate",
                        )
                    ],
                ]
            )

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=message.chat.id,
                text=response_text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

            logger.info(
                "Affiliate command executed",
                extra={"user_id": str(message.from_user.id)},
            )

        except Exception as e:
            logger.error(f"Error in handle_affiliate: {e}", exc_info=True)

    async def handle_stats(self, message: TelegramMessage) -> None:
        """Handle /stats command - Show user statistics.

        Requires SUBSCRIBER role or higher.

        Args:
            message: Telegram message
        """
        try:
            user_id = str(message.from_user.id)
            user_role = await get_user_role(user_id, self.db)

            # Check subscription
            if user_role not in (UserRole.SUBSCRIBER, UserRole.ADMIN, UserRole.OWNER):
                await self._send_permission_denied(message)
                return

            response_text = (
                "📊 *Your Trading Statistics*\n\n"
                "Today:\n"
                "• Signals: 0\n"
                "• Wins: 0%\n"
                "• P/L: $0.00\n\n"
                "This Week:\n"
                "• Signals: 0\n"
                "• Wins: 0%\n"
                "• P/L: $0.00\n\n"
                "_Full analytics on web dashboard_"
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="📈 Full Dashboard",
                            url=f"{settings.FRONTEND_URL}/dashboard",
                        )
                    ],
                ]
            )

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=message.chat.id,
                text=response_text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

            logger.info("Stats command executed", extra={"user_id": user_id})

        except Exception as e:
            logger.error(f"Error in handle_stats: {e}", exc_info=True)

    async def handle_guides(self, message: TelegramMessage) -> None:
        """Handle /guides command - Show guides menu.

        Delegates to guides handler.

        Args:
            message: Telegram message
        """
        try:
            update = TelegramUpdate(message=message)
            await handle_guides_command(update, self.db)
            logger.info(
                "Guides command executed", extra={"user_id": str(message.from_user.id)}
            )

        except Exception as e:
            logger.error(f"Error in handle_guides: {e}", exc_info=True)

    async def handle_newsletter(self, message: TelegramMessage) -> None:
        """Handle /newsletter command - Show marketing updates.

        Delegates to marketing handler.

        Args:
            message: Telegram message
        """
        try:
            update = TelegramUpdate(message=message)
            await handle_marketing_updates(update, self.db)
            logger.info(
                "Newsletter command executed",
                extra={"user_id": str(message.from_user.id)},
            )

        except Exception as e:
            logger.error(f"Error in handle_newsletter: {e}", exc_info=True)

    async def handle_admin(self, message: TelegramMessage) -> None:
        """Handle /admin command - Admin control panel.

        Only accessible to ADMIN or OWNER roles.

        Args:
            message: Telegram message
        """
        try:
            user_id = str(message.from_user.id)
            user_role = await get_user_role(user_id, self.db)

            if user_role not in (UserRole.ADMIN, UserRole.OWNER):
                await self._send_permission_denied(message)
                return

            response_text = "🔧 *Admin Panel*\n\n" "Select an admin function:"

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="📢 Send Broadcast", callback_data="admin:broadcast"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="👥 User Management", callback_data="admin:users"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="📊 Analytics", callback_data="admin:analytics"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⚙️ Settings", callback_data="admin:settings"
                        )
                    ],
                ]
            )

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=message.chat.id,
                text=response_text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

            logger.info(
                "Admin panel accessed", extra={"user_id": user_id, "role": user_role}
            )

        except Exception as e:
            logger.error(f"Error in handle_admin: {e}", exc_info=True)

    async def handle_unknown(self, message: TelegramMessage) -> None:
        """Handle unknown command.

        Shows helpful error message and suggests alternatives.

        Args:
            message: Telegram message
        """
        try:
            response_text = (
                "🤔 Sorry, I don't understand that command.\n\n"
                "Type /help to see available commands or\n"
                "try asking about:\n"
                "• /shop - Browse products\n"
                "• /guides - Learning materials\n"
                "• /stats - Your statistics\n"
            )

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=message.chat.id,
                text=response_text,
                parse_mode="Markdown",
            )

            logger.warning(
                f"Unknown command: {message.text}",
                extra={"user_id": str(message.from_user.id)},
            )

        except Exception as e:
            logger.error(f"Error in handle_unknown: {e}", exc_info=True)

    async def handle_shop_callback(self, callback: TelegramCallback) -> None:
        """Handle shop button click.

        Placeholder for PR-030 implementation.

        Args:
            callback: Telegram callback query
        """
        try:
            logger.debug(
                f"Shop callback: {callback.data}",
                extra={"user_id": str(callback.from_user.id)},
            )
            # PR-030 will implement full shop browsing and checkout

        except Exception as e:
            logger.error(f"Error in handle_shop_callback: {e}", exc_info=True)

    async def handle_checkout_callback(self, callback: TelegramCallback) -> None:
        """Handle checkout button click.

        Placeholder for PR-030 implementation.

        Args:
            callback: Telegram callback query
        """
        try:
            logger.debug(
                f"Checkout callback: {callback.data}",
                extra={"user_id": str(callback.from_user.id)},
            )
            # PR-030 will implement full checkout flow

        except Exception as e:
            logger.error(f"Error in handle_checkout_callback: {e}", exc_info=True)

    async def handle_guide_callback(self, callback: TelegramCallback) -> None:
        """Handle guide-related button clicks.

        Routes to appropriate guide handler based on callback data.

        Args:
            callback: Telegram callback query
        """
        try:
            from backend.app.telegram.handlers.guides import GuideHandler

            parts = callback.data.split(":", 2) if callback.data else []
            action = parts[1] if len(parts) > 1 else "menu"
            param = parts[2] if len(parts) > 2 else None

            handler = GuideHandler(self.db)

            if action == "categories":
                (
                    await handler.handle_guide_menu(callback.message)
                    if callback.message
                    else None
                )
            elif action == "category" and param:
                (
                    await handler.handle_category_selection(param, callback.message)
                    if callback.message
                    else None
                )
            elif action == "view" and param:
                (
                    await handler.handle_guide_view(param, callback.message)
                    if callback.message
                    else None
                )
            elif action == "save" and param:
                (
                    await handler.handle_save_guide(
                        param, str(callback.from_user.id), callback.message.chat.id
                    )
                    if callback.message
                    else None
                )

            logger.debug(
                "Guide callback handled", extra={"action": action, "param": param}
            )

        except Exception as e:
            logger.error(f"Error in handle_guide_callback: {e}", exc_info=True)

    async def handle_campaign_callback(self, callback: TelegramCallback) -> None:
        """Handle marketing campaign button clicks.

        Routes to appropriate marketing handler based on callback data.

        Args:
            callback: Telegram callback query
        """
        try:
            from backend.app.telegram.handlers.marketing import MarketingHandler

            parts = callback.data.split(":", 2) if callback.data else []
            action = parts[1] if len(parts) > 1 else None
            param = parts[2] if len(parts) > 2 else None

            handler = MarketingHandler(self.db)

            if action == "feedback" and len(parts) > 2:
                feedback_type = parts[2]
                await handler.handle_campaign_feedback(
                    param,
                    feedback_type,
                    str(callback.from_user.id),
                    callback.message.chat.id if callback.message else 0,
                )
            elif action == "unsubscribe" and param:
                await handler.handle_campaign_unsubscribe(
                    param,
                    str(callback.from_user.id),
                    callback.message.chat.id if callback.message else 0,
                )

            logger.debug("Campaign callback handled", extra={"action": action})

        except Exception as e:
            logger.error(f"Error in handle_campaign_callback: {e}", exc_info=True)
