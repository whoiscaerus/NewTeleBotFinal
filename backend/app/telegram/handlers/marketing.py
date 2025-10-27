"""Marketing content and promotional campaigns via Telegram."""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from backend.app.core.settings import settings
from backend.app.telegram.models import TelegramBroadcast, TelegramUser
from backend.app.telegram.schema import TelegramMessage, TelegramUpdate

logger = logging.getLogger(__name__)


class MarketingHandler:
    """Handle marketing campaigns and promotional content.

    Manages:
    - Marketing broadcast campaigns
    - Promotional content delivery
    - Newsletter distribution
    - Subscriber management
    - Campaign analytics tracking
    """

    def __init__(self, db: AsyncSession):
        """Initialize marketing handler.

        Args:
            db: Database session
        """
        self.db = db
        self.bot_token = settings.TELEGRAM_BOT_TOKEN

    async def _get_user(self, user_id: str) -> Optional[TelegramUser]:
        """Fetch user from database.

        Args:
            user_id: Telegram user ID

        Returns:
            TelegramUser object or None if not found
        """
        query = select(TelegramUser).where(TelegramUser.id == user_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def _get_active_broadcasts(self) -> list[TelegramBroadcast]:
        """Fetch all active broadcast campaigns.

        Returns:
            List of active TelegramBroadcast objects
        """
        now = datetime.utcnow()
        query = select(TelegramBroadcast).where(
            TelegramBroadcast.is_active == True,
            TelegramBroadcast.start_time <= now,
            TelegramBroadcast.end_time >= now,
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def _get_broadcast_by_id(
        self, broadcast_id: str
    ) -> Optional[TelegramBroadcast]:
        """Fetch specific broadcast campaign.

        Args:
            broadcast_id: Broadcast ID

        Returns:
            TelegramBroadcast object or None
        """
        query = select(TelegramBroadcast).where(TelegramBroadcast.id == broadcast_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    def _create_broadcast_keyboard(
        self, broadcast: TelegramBroadcast
    ) -> InlineKeyboardMarkup:
        """Create keyboard for broadcast message with CTA buttons.

        Args:
            broadcast: Broadcast campaign object

        Returns:
            InlineKeyboardMarkup with action buttons
        """
        buttons = []

        # Primary CTA button
        if broadcast.cta_url and broadcast.cta_text:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=broadcast.cta_text,
                        url=broadcast.cta_url,
                    )
                ]
            )

        # Secondary CTA button (optional)
        if broadcast.cta2_url and broadcast.cta2_text:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=broadcast.cta2_text,
                        url=broadcast.cta2_url,
                    )
                ]
            )

        # Feedback/unsubscribe buttons
        buttons.append(
            [
                InlineKeyboardButton(
                    text="👍 Helpful",
                    callback_data=f"campaign_feedback:{broadcast.id}:yes",
                ),
                InlineKeyboardButton(
                    text="👎 Not helpful",
                    callback_data=f"campaign_feedback:{broadcast.id}:no",
                ),
                InlineKeyboardButton(
                    text="🚫 Unsubscribe",
                    callback_data=f"campaign_unsubscribe:{broadcast.id}",
                ),
            ]
        )

        return InlineKeyboardMarkup(buttons)

    async def handle_broadcast_message(
        self, broadcast: TelegramBroadcast, message: TelegramMessage
    ) -> None:
        """Send broadcast campaign message.

        Args:
            broadcast: Broadcast campaign
            message: Telegram message object (context for chat_id)
        """
        try:
            keyboard = self._create_broadcast_keyboard(broadcast)

            # Format campaign message with rich formatting
            response_text = (
                f"{broadcast.emoji or '📢'} *{broadcast.title}*\n\n"
                f"{broadcast.content}\n\n"
            )

            # Add discount/offer details if applicable
            if broadcast.discount_percentage:
                response_text += (
                    f"🎉 *Special Offer:* {broadcast.discount_percentage}% off\n"
                )

            if broadcast.valid_until:
                days_left = (broadcast.valid_until - datetime.utcnow()).days
                if days_left > 0:
                    response_text += f"⏳ *Valid for {days_left} more days*"

            from telegram import Bot

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=message.chat.id,
                text=response_text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

            logger.info(
                "Broadcast message sent",
                extra={
                    "user_id": message.from_user.id,
                    "broadcast_id": broadcast.id,
                    "campaign": broadcast.title,
                },
            )

        except Exception as e:
            logger.error(f"Error sending broadcast message: {e}", exc_info=True)

    async def send_newsletter(self, message: TelegramMessage) -> None:
        """Send newsletter with current active campaigns.

        Args:
            message: Telegram message object
        """
        try:
            broadcasts = await self._get_active_broadcasts()

            if not broadcasts:
                from telegram import Bot

                bot = Bot(token=self.bot_token)
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=(
                        "📰 *Latest Updates*\n\n"
                        "No active campaigns at the moment. "
                        "Check back soon for exclusive offers!"
                    ),
                    parse_mode="Markdown",
                )
                return

            # Send each active broadcast
            for broadcast in broadcasts:
                await self.handle_broadcast_message(broadcast, message)

            logger.info(
                f"Newsletter sent with {len(broadcasts)} campaigns",
                extra={"user_id": message.from_user.id},
            )

        except Exception as e:
            logger.error(f"Error sending newsletter: {e}", exc_info=True)

    async def send_promotional_offer(
        self, offer_type: str, message: TelegramMessage
    ) -> None:
        """Send promotional offer based on type.

        Args:
            offer_type: Type of offer ("limited_time", "exclusive", "seasonal", etc.)
            message: Telegram message object
        """
        try:
            # Fetch active broadcasts matching offer type
            query = select(TelegramBroadcast).where(
                TelegramBroadcast.is_active == True,
                TelegramBroadcast.offer_type == offer_type,
            )
            result = await self.db.execute(query)
            broadcasts = result.scalars().all()

            if not broadcasts:
                from telegram import Bot

                bot = Bot(token=self.bot_token)
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=f"No {offer_type} offers available right now.",
                )
                return

            # Send first matching offer
            await self.handle_broadcast_message(broadcasts[0], message)

            logger.info(
                "Promotional offer sent",
                extra={
                    "user_id": message.from_user.id,
                    "offer_type": offer_type,
                    "broadcast_id": broadcasts[0].id,
                },
            )

        except Exception as e:
            logger.error(f"Error sending promotional offer: {e}", exc_info=True)

    async def handle_campaign_feedback(
        self, broadcast_id: str, feedback: str, user_id: str, chat_id: int
    ) -> None:
        """Record campaign feedback (helpful/not helpful).

        Args:
            broadcast_id: Broadcast campaign ID
            feedback: Feedback type ("yes" or "no")
            user_id: Telegram user ID
            chat_id: Chat ID for response
        """
        try:
            broadcast = await self._get_broadcast_by_id(broadcast_id)
            if not broadcast:
                return

            # Increment feedback counters
            if feedback == "yes":
                broadcast.feedback_positive = (broadcast.feedback_positive or 0) + 1
            elif feedback == "no":
                broadcast.feedback_negative = (broadcast.feedback_negative or 0) + 1

            await self.db.commit()

            from telegram import Bot

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=chat_id,
                text="Thanks for your feedback! 📊",
            )

            logger.info(
                "Campaign feedback recorded",
                extra={
                    "user_id": user_id,
                    "broadcast_id": broadcast_id,
                    "feedback": feedback,
                },
            )

        except Exception as e:
            logger.error(f"Error recording campaign feedback: {e}", exc_info=True)

    async def handle_campaign_unsubscribe(
        self, broadcast_id: str, user_id: str, chat_id: int
    ) -> None:
        """Unsubscribe user from marketing campaigns.

        Args:
            broadcast_id: Broadcast campaign ID
            user_id: Telegram user ID
            chat_id: Chat ID for response
        """
        try:
            user = await self._get_user(user_id)
            if not user:
                return

            # Mark user as unsubscribed from marketing
            user.subscribed_to_marketing = False
            await self.db.commit()

            from telegram import Bot

            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "✅ You've been unsubscribed from marketing campaigns.\n\n"
                    "You'll still receive important updates about your account."
                ),
            )

            logger.info(
                "User unsubscribed from marketing",
                extra={"user_id": user_id, "broadcast_id": broadcast_id},
            )

        except Exception as e:
            logger.error(f"Error processing unsubscribe: {e}", exc_info=True)

    async def record_broadcast_view(self, broadcast_id: str, user_id: str) -> None:
        """Record that user viewed a broadcast.

        Args:
            broadcast_id: Broadcast ID
            user_id: Telegram user ID
        """
        try:
            broadcast = await self._get_broadcast_by_id(broadcast_id)
            if broadcast:
                broadcast.views = (broadcast.views or 0) + 1
                await self.db.commit()

                logger.debug(
                    "Broadcast view recorded",
                    extra={"broadcast_id": broadcast_id, "user_id": user_id},
                )

        except Exception as e:
            logger.error(f"Error recording broadcast view: {e}", exc_info=True)


async def handle_marketing_updates(update: TelegramUpdate, db: AsyncSession) -> None:
    """Handle marketing/newsletter commands.

    Args:
        update: Telegram update
        db: Database session
    """
    if not update.message:
        return

    handler = MarketingHandler(db)
    await handler.send_newsletter(update.message)
