import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# Bot token
BOT_TOKEN = "8156882507:AAFnLNYU6q-eVryEpUA7MdOtmUcMkMEazKk"

# Chat IDs for groups
GROUPS = {
    "gold": -4608351708,
    "sp500": -4662755518,
    "crypto": -4740971535,
    "gold_crypto": -4767465199,
    "sp500_crypto": -4654433080,
    "gold_sp500": -4786454930,
    "gold_sp500_crypto": -4779379128,
}

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG,  # Use DEBUG level to capture all details
)
logger = logging.getLogger(__name__)

async def handle_message(update: Update, context: CallbackContext):
    """Handle messages from the admin and forward to relevant groups."""
    user = update.effective_user
    text = update.message.text.lower()  # Convert to lowercase for case-insensitive matching
    sent_to = []

    logger.info(f"Message received from user {user.id}: {update.message.text}")

    try:
        # Forward to all matching groups
        for group_name, chat_id in GROUPS.items():
            if any(keyword in group_name for keyword in text.split()):  # Check for any keyword match
                await context.bot.send_message(chat_id=chat_id, text=update.message.text)
                sent_to.append(group_name.capitalize().replace("_", " "))
                logger.debug(f"Message sent to {group_name.capitalize()}.")

        # Reply with confirmation to the admin
        if sent_to:
            confirmation_message = f"Message forwarded to: {', '.join(sent_to)}"
            await update.message.reply_text(confirmation_message)
            logger.info(confirmation_message)
        else:
            no_match_message = "No matching category found. Message not sent."
            await update.message.reply_text(no_match_message)
            logger.warning(no_match_message)

    except Exception as e:
        error_message = f"Error while forwarding message: {e}"
        await update.message.reply_text("An error occurred while processing your message.")
        logger.error(error_message)

async def start_command(update: Update, context: CallbackContext):
    """Send a welcome message and usage instructions."""
    welcome_message = (
        "Welcome! Send messages containing keywords like 'Gold', 'Crypto', or 'SP500' to forward them to the relevant groups."
    )
    await update.message.reply_text(welcome_message)
    logger.info(f"Start command invoked by user {update.effective_user.id}")

def main():
    """Start the bot."""
    logger.info("Starting the bot...")
    app = Application.builder().token(BOT_TOKEN).build()

    # Command handler for /start
    app.add_handler(CommandHandler("start", start_command))

    # Message handler for all messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the bot
    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
