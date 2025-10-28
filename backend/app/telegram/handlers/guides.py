"""Guide/tutorial content delivery via Telegram inline keyboards."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from backend.app.core.settings import settings
from backend.app.telegram.models import TelegramGuide, TelegramUser
from backend.app.telegram.schema import TelegramMessage, TelegramUpdate

logger = logging.getLogger(__name__)


class GuideHandler:
    """Deliver educational content and guides via Telegram.

    Provides:
    - Guide discovery and browsing
    - Tutorial content delivery
    - Learning path progression
    - Guide bookmarking/saving
    - Related guide suggestions
    """

    # Guide categories for easy discovery
    GUIDE_CATEGORIES = {
        "trading": "📈 Trading Basics",
        "technical": "🔬 Technical Analysis",
        "risk": "⚠️ Risk Management",
        "psychology": "🧠 Trading Psychology",
        "automation": "⚙️ Automation & Bots",
        "platform": "💻 Platform Features",
    }

    def __init__(self, db: AsyncSession):
        """Initialize guide handler.

        Args:
            db: Database session
        """
        self.db = db
        self.bot_token = settings.TELEGRAM_BOT_TOKEN

    async def _get_user(self, user_id: str) -> TelegramUser | None:
        """Fetch user from database.

        Args:
            user_id: Telegram user ID

        Returns:
            TelegramUser object or None if not found
        """
        query = select(TelegramUser).where(TelegramUser.id == user_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def _get_guides_by_category(self, category: str) -> list[TelegramGuide]:
        """Fetch all guides in a category.

        Args:
            category: Guide category

        Returns:
            List of TelegramGuide objects
        """
        query = select(TelegramGuide).where(
            TelegramGuide.category == category,
            TelegramGuide.is_active,
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _get_guide_by_id(self, guide_id: str) -> TelegramGuide | None:
        """Fetch specific guide.

        Args:
            guide_id: Guide ID

        Returns:
            TelegramGuide object or None
        """
        query = select(TelegramGuide).where(TelegramGuide.id == guide_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    def _create_category_keyboard(self) -> InlineKeyboardMarkup:
        """Create inline keyboard for guide category selection.

        Returns:
            InlineKeyboardMarkup with category buttons
        """
        buttons = []

        for category_key, category_name in self.GUIDE_CATEGORIES.items():
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=category_name,
                        callback_data=f"guide_category:{category_key}",
                    )
                ]
            )

        # Add back button
        buttons.append(
            [InlineKeyboardButton(text="🔙 Back", callback_data="guide_back_menu")]
        )

        return InlineKeyboardMarkup(buttons)

    def _create_guides_list_keyboard(
        self, guides: list[TelegramGuide]
    ) -> InlineKeyboardMarkup:
        """Create keyboard listing guides in category.

        Args:
            guides: List of guides to display

        Returns:
            InlineKeyboardMarkup with guide buttons
        """
        buttons = []

        for guide in guides:
            # Format: "📘 Title" → callback includes guide ID
            display_name = f"📘 {guide.title[:30]}"
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=display_name,
                        callback_data=f"guide_view:{guide.id}",
                    )
                ]
            )

        # Add back to categories
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🔙 Back to Categories", callback_data="guide_categories"
                )
            ]
        )

        return InlineKeyboardMarkup(buttons)

    def _create_guide_detail_keyboard(self, guide_id: str) -> InlineKeyboardMarkup:
        """Create keyboard for guide detail view.

        Args:
            guide_id: Guide ID

        Returns:
            InlineKeyboardMarkup with guide actions
        """
        buttons = [
            [
                InlineKeyboardButton(
                    text="💾 Save Guide",
                    callback_data=f"guide_save:{guide_id}",
                ),
                InlineKeyboardButton(
                    text="🔗 Read Full",
                    url=f"{settings.FRONTEND_URL}/guides/{guide_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➡️ Next Guide",
                    callback_data=f"guide_next:{guide_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Back to Guides",
                    callback_data="guide_categories",
                ),
            ],
        ]

        return InlineKeyboardMarkup(buttons)

    async def handle_guide_menu(self, message: TelegramMessage) -> None:
        """Send guide category selection menu.

        Args:
            message: Telegram message object
        """
        try:
            keyboard = self._create_category_keyboard()

            response_text = (
                "📚 *Available Guides*\n\n"
                "Choose a category to explore our guides and tutorials:\n\n"
                f"{'📈'} *Trading Basics* - Start here if you're new\n"
                f"{'🔬'} *Technical Analysis* - Chart reading and patterns\n"
                f"{'⚠️'} *Risk Management* - Protecting your capital\n"
                f"{'🧠'} *Trading Psychology* - Mental strategies\n"
                f"{'⚙️'} *Automation* - Using our bot features\n"
                f"{'💻'} *Platform Features* - How to use our platform"
            )

            # Send via Telegram API
            from telegram import Bot

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=message.chat.id,
                text=response_text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

            logger.info(
                "Guide menu sent",
                extra={"user_id": message.from_user.id, "chat_id": message.chat.id},
            )

        except Exception as e:
            logger.error(f"Error sending guide menu: {e}", exc_info=True)

    async def handle_category_selection(
        self, category: str, message: TelegramMessage
    ) -> None:
        """Handle category selection and list guides in category.

        Args:
            category: Guide category
            message: Telegram message object
        """
        try:
            # Fetch guides in category
            guides = await self._get_guides_by_category(category)

            if not guides:
                from telegram import Bot

                bot = Bot(token=self.bot_token)
                await bot.send_message(
                    chat_id=message.chat.id,
                    text="No guides available in this category yet. Check back soon!",
                )
                return

            # Create keyboard with guides
            keyboard = self._create_guides_list_keyboard(guides)

            category_name = self.GUIDE_CATEGORIES.get(category, category)
            response_text = (
                f"*Guides in {category_name}*\n\nSelect a guide to learn more:"
            )

            from telegram import Bot

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=message.chat.id,
                text=response_text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

            logger.info(
                "Category guides displayed",
                extra={"user_id": message.from_user.id, "category": category},
            )

        except Exception as e:
            logger.error(f"Error handling category selection: {e}", exc_info=True)

    async def handle_guide_view(self, guide_id: str, message: TelegramMessage) -> None:
        """Display specific guide content.

        Args:
            guide_id: Guide ID
            message: Telegram message object
        """
        try:
            guide = await self._get_guide_by_id(guide_id)

            if not guide:
                from telegram import Bot

                bot = Bot(token=self.bot_token)
                await bot.send_message(
                    chat_id=message.chat.id,
                    text="Guide not found.",
                )
                return

            keyboard = self._create_guide_detail_keyboard(guide_id)

            # Format guide content
            response_text = (
                f"*{guide.title}*\n\n"
                f"{guide.summary}\n\n"
                f"📖 *Category:* {self.GUIDE_CATEGORIES.get(guide.category, guide.category)}\n"
                f"⏱️ *Read Time:* ~{guide.read_time_minutes} minutes\n"
                f"⭐ *Difficulty:* {'Beginner' if guide.difficulty == 0 else 'Intermediate' if guide.difficulty == 1 else 'Advanced'}\n\n"
                f"👇 Select an action below"
            )

            from telegram import Bot

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=message.chat.id,
                text=response_text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

            logger.info(
                "Guide displayed",
                extra={"user_id": message.from_user.id, "guide_id": guide_id},
            )

        except Exception as e:
            logger.error(f"Error viewing guide: {e}", exc_info=True)

    async def handle_save_guide(
        self, guide_id: str, user_id: str, chat_id: int
    ) -> None:
        """Save guide to user's saved collection.

        Args:
            guide_id: Guide ID
            user_id: Telegram user ID
            chat_id: Chat ID for response
        """
        try:
            user = await self._get_user(user_id)
            if not user:
                return

            # Add to saved guides (assuming many-to-many relationship)
            guide = await self._get_guide_by_id(guide_id)
            if guide and user not in guide.saved_by_users:
                guide.saved_by_users.append(user)
                await self.db.commit()

            from telegram import Bot

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=chat_id,
                text="✅ Guide saved to your collection! Access saved guides anytime.",
            )

            logger.info(
                "Guide saved",
                extra={"user_id": user_id, "guide_id": guide_id},
            )

        except Exception as e:
            logger.error(f"Error saving guide: {e}", exc_info=True)


async def handle_guides_command(update: TelegramUpdate, db: AsyncSession) -> None:
    """Handle /guides command.

    Args:
        update: Telegram update
        db: Database session
    """
    if not update.message:
        return

    handler = GuideHandler(db)
    await handler.handle_guide_menu(update.message)
