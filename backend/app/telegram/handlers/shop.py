"""Telegram shop command handler."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.catalog.service import CatalogService
from backend.app.billing.entitlements.service import EntitlementService
from backend.app.telegram.schema import TelegramMessage

logger = logging.getLogger(__name__)


async def handle_shop_command(message: TelegramMessage, db: AsyncSession) -> None:
    """Handle /shop command.

    Shows available products accessible to user's tier level.

    Args:
        message: Telegram message from user
        db: Database session
    """
    try:
        user_id = str(message.from_user.id)
        chat_id = message.chat.id

        logger.info(
            f"Shop command from user {user_id}",
            extra={"user_id": user_id, "chat_id": chat_id},
        )

        # Get user's tier level
        ent_service = EntitlementService(db)
        user_tier = await ent_service.get_user_tier(user_id)

        # Get products accessible to this tier
        catalog_service = CatalogService(db)
        products = await catalog_service.get_products_for_tier(user_tier)

        if not products:
            # No products for this tier
            await _send_telegram_message(
                chat_id,
                "📦 No products available for your tier at this time.",
            )
            return

        # Build product list
        text = "📦 **Premium Plans Available**\n\n"
        text += f"Your tier level: {user_tier}\n\n"

        for product in products:
            text += f"**{product.name}**\n"
            if product.description:
                text += f"{product.description}\n\n"

        # Add note about payment
        text += "\nTo upgrade, use /checkout [product_id]\n"

        await _send_telegram_message(chat_id, text)

        logger.info(
            f"Showed {len(products)} products to user {user_id}",
            extra={"user_id": user_id, "products": len(products)},
        )

    except Exception as e:
        logger.error(f"Error handling shop command: {e}", exc_info=True)
        await _send_telegram_message(
            chat_id, "❌ Error loading products. Please try again."
        )


async def _send_telegram_message(chat_id: int, text: str) -> None:
    """Send message to Telegram chat.

    In production, this would call Telegram Bot API.
    For now, just log it.

    Args:
        chat_id: Telegram chat ID
        text: Message text
    """
    logger.info(
        f"Would send Telegram message to {chat_id}: {text[:100]}...",
        extra={"chat_id": chat_id},
    )
