"""Telegram checkout handler for order creation."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.pricing.calculator import PricingCalculator
from backend.app.orders.service import OrderService
from backend.app.telegram.schema import TelegramCallback

logger = logging.getLogger(__name__)


async def handle_checkout_callback(
    callback: TelegramCallback, db: AsyncSession
) -> None:
    """Handle checkout button click.

    Creates an order and initiates payment flow.

    Args:
        callback: Telegram callback query
        db: Database session
    """
    try:
        user_id = str(callback.from_user.id)
        chat_id = callback.message.chat.id if callback.message else None

        logger.info(
            f"Checkout callback from user {user_id}",
            extra={"user_id": user_id, "data": callback.data},
        )

        # Parse callback data: format is "checkout:product_tier_id"
        if not callback.data or ":" not in callback.data:
            logger.warning(f"Invalid checkout data: {callback.data}")
            await _send_telegram_message(
                chat_id, "❌ Invalid checkout data. Please try again."
            )
            return

        parts = callback.data.split(":", 1)
        product_tier_id = parts[1]

        # Calculate pricing
        pricing_calc = PricingCalculator(db)
        price_detail = await pricing_calc.get_price(
            product_tier_id, user_id, region="GB", months=1
        )

        # Create order
        order_service = OrderService(db)
        order = await order_service.create_order(
            user_id=user_id,
            product_tier_id=product_tier_id,
            base_price=price_detail.base_price,
            final_price=price_detail.final_price,
            currency=price_detail.currency,
            quantity=1,
            notes="Created from Telegram shop",
        )

        logger.info(
            f"Created order {order.id} for user {user_id}",
            extra={"order_id": order.id, "amount": order.final_price},
        )

        # Build checkout message
        text = "💰 **Checkout Summary**\n\n"
        text += f"Product Tier: {product_tier_id}\n"
        text += f"Base Price: £{price_detail.base_price:.2f}\n"
        text += f"Regional Markup: £{price_detail.regional_price - price_detail.base_price:.2f}\n"
        if price_detail.affiliate_discount > 0:
            text += f"Affiliate Discount: -£{price_detail.affiliate_discount:.2f}\n"
        if price_detail.volume_discount > 0:
            text += f"Volume Discount: -£{price_detail.volume_discount:.2f}\n"
        text += f"\n**Final Price: {price_detail.currency} {price_detail.final_price:.2f}**\n\n"
        text += f"Order ID: {order.id}\n\n"
        text += "Ready to proceed? Use /pay [order_id] or contact support.\n"

        await _send_telegram_message(chat_id, text)

        logger.info(
            f"Sent checkout summary for order {order.id}",
            extra={"order_id": order.id},
        )

    except Exception as e:
        logger.error(f"Error handling checkout: {e}", exc_info=True)
        await _send_telegram_message(
            chat_id, "❌ Error creating order. Please try again."
        )


async def _send_telegram_message(chat_id: int | None, text: str) -> None:
    """Send message to Telegram chat.

    In production, this would call Telegram Bot API.
    For now, just log it.

    Args:
        chat_id: Telegram chat ID
        text: Message text
    """
    if not chat_id:
        logger.warning("No chat ID to send message")
        return

    logger.info(
        f"Would send Telegram message to {chat_id}: {text[:100]}...",
        extra={"chat_id": chat_id},
    )
