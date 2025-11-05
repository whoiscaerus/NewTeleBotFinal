"""Telegram shop command handler.

Handles:
- /shop - Shows available products
- /buy [product_id] [tier] - Initiate payment (offers Stripe vs Telegram Stars choice)
"""

import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.catalog.service import CatalogService
from backend.app.billing.entitlements.service import EntitlementService
from backend.app.observability.metrics import get_metrics
from backend.app.telegram.payments import TelegramPaymentHandler
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
            # Show tier options for each product
            if product.tiers:
                for tier in product.tiers:
                    text += f"  • {tier.tier_name}: £{tier.base_price}\n"
                text += "\n"

        # Add note about payment
        text += "\nTo upgrade, use /buy [product_id] [tier_level]\n"
        text += "Example: /buy signals 1\n"

        await _send_telegram_message(chat_id, text)

        logger.info(
            f"Showed {len(products)} products to user {user_id}",
            extra={"user_id": user_id, "products": len(products)},
        )

        get_metrics().record_telegram_shop_view(user_id)

    except Exception as e:
        logger.error(f"Error handling shop command: {e}", exc_info=True)
        await _send_telegram_message(
            chat_id, "❌ Error loading products. Please try again."
        )


async def handle_buy_command(
    message: TelegramMessage, db: AsyncSession, product_id: str, tier_level: int
) -> None:
    """Handle /buy [product_id] [tier_level] command.

    Shows payment options: Stripe checkout or Telegram Stars.

    Args:
        message: Telegram message from user
        db: Database session
        product_id: Product ID to purchase
        tier_level: Tier level (0=free, 1=premium, etc)
    """
    try:
        user_id = str(message.from_user.id)
        chat_id = message.chat.id

        logger.info(
            "Buy command",
            extra={
                "user_id": user_id,
                "product_id": product_id,
                "tier_level": tier_level,
            },
        )

        # Validate product and tier
        catalog_service = CatalogService(db)
        product = await catalog_service.get_product(product_id)

        if not product:
            await _send_telegram_message(chat_id, f"❌ Product not found: {product_id}")
            return

        # Find matching tier
        matching_tier = None
        for tier in product.tiers:
            if tier.tier_level == tier_level:
                matching_tier = tier
                break

        if not matching_tier:
            await _send_telegram_message(
                chat_id,
                f"❌ Tier level {tier_level} not found for product {product_id}",
            )
            return

        # Build invoice
        invoice_id = str(uuid4())
        payment_handler = TelegramPaymentHandler(db)

        try:
            invoice = await payment_handler.send_invoice(
                user_id=user_id,
                product_id=product_id,
                tier_level=tier_level,
                invoice_id=invoice_id,
            )
        except ValueError as e:
            await _send_telegram_message(chat_id, f"❌ Error: {e}")
            return

        # Present payment options
        text = f"💳 **Upgrade to {matching_tier.tier_name}**\n\n"
        text += f"Product: {product.name}\n"
        text += f"Price: £{matching_tier.base_price}\n"
        text += f"Equivalent: {invoice['amount_stars']} Telegram Stars\n\n"

        text += "Choose payment method:\n"
        text += "1️⃣ **Stripe Checkout** - Credit card, Apple Pay, Google Pay\n"
        text += "   Use: /checkout [product_id]\n\n"
        text += "2️⃣ **Telegram Stars** - Native Telegram payment\n"
        text += "   Use: /pay_stars [product_id]\n\n"

        text += (
            "Note: Telegram Stars payment is currently in beta.\n"
            "Please use Stripe for production purchases.\n"
        )

        await _send_telegram_message(chat_id, text)

        get_metrics().record_telegram_buy_initiated(product_id, tier_level)

        logger.info(
            "Buy command completed",
            extra={
                "user_id": user_id,
                "product_id": product_id,
                "tier_level": tier_level,
                "invoice_id": invoice_id,
            },
        )

    except Exception as e:
        logger.error(
            f"Error handling buy command: {e}",
            exc_info=True,
            extra={
                "user_id": message.from_user.id,
                "product_id": product_id,
            },
        )
        await _send_telegram_message(
            chat_id, "❌ Error processing buy request. Please try again."
        )


async def handle_pay_stars_command(
    message: TelegramMessage, db: AsyncSession, product_id: str, tier_level: int
) -> None:
    """Handle /pay_stars [product_id] [tier_level] command.

    Initiates Telegram Stars payment for a product.

    Args:
        message: Telegram message from user
        db: Database session
        product_id: Product ID to purchase
        tier_level: Tier level
    """
    try:
        user_id = str(message.from_user.id)
        chat_id = message.chat.id

        logger.info(
            "Pay Stars command",
            extra={
                "user_id": user_id,
                "product_id": product_id,
                "tier_level": tier_level,
            },
        )

        # Validate product and tier
        catalog_service = CatalogService(db)
        product = await catalog_service.get_product(product_id)

        if not product:
            await _send_telegram_message(chat_id, f"❌ Product not found: {product_id}")
            return

        # Find matching tier
        matching_tier = None
        for tier in product.tiers:
            if tier.tier_level == tier_level:
                matching_tier = tier
                break

        if not matching_tier:
            await _send_telegram_message(
                chat_id,
                f"❌ Tier level {tier_level} not found for product {product_id}",
            )
            return

        # Create invoice and validate
        invoice_id = str(uuid4())
        payment_handler = TelegramPaymentHandler(db)

        try:
            invoice = await payment_handler.send_invoice(
                user_id=user_id,
                product_id=product_id,
                tier_level=tier_level,
                invoice_id=invoice_id,
            )
        except ValueError as e:
            await _send_telegram_message(chat_id, f"❌ Error: {e}")
            return

        # In production, this would call Telegram Bot API:
        # await bot.send_invoice(
        #     chat_id=chat_id,
        #     title=f"{matching_tier.tier_name} Plan",
        #     description=product.description,
        #     payload=invoice_id,
        #     provider_token=TELEGRAM_PAYMENT_PROVIDER_TOKEN,
        #     currency="XTR",
        #     prices=[LabeledPrice(label="Amount", amount=invoice['amount_stars'])],
        # )

        await _send_telegram_message(
            chat_id,
            f"✅ Telegram invoice created!\n"
            f"Amount: {invoice['amount_stars']} Stars (£{invoice['amount_gbp']})\n"
            f"Invoice ID: {invoice_id}\n\n"
            f"(In production, invoice would be sent via Telegram)\n",
        )

        get_metrics().record_telegram_payment_initiated("stars", product_id, tier_level)

        logger.info(
            "Pay Stars command completed",
            extra={
                "user_id": user_id,
                "product_id": product_id,
                "invoice_id": invoice_id,
            },
        )

    except Exception as e:
        logger.error(
            f"Error handling pay_stars command: {e}",
            exc_info=True,
            extra={
                "user_id": message.from_user.id,
                "product_id": product_id,
            },
        )
        await _send_telegram_message(
            chat_id, "❌ Error processing Stars payment. Please try again."
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
