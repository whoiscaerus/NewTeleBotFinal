import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackContext, ContextTypes

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot token (replace with your bot token)
BOT_TOKEN = "7709042826:AAH15jk2fn-RxH_lvRU5Isv2uGbASfDyjdk"

# Message content
GUIDES_MESSAGE = (
    "🌟 *Maximize Your Trading Potential!* 🌟\n\n"
    "Follow these guides to follow our Forex and Cryptocurrency signals effectively. \n"
    "Depending on where you are in the world, we have outlined how to best minimizing fees and taxes. \n\n"
    "📚 *Forex Trading Guides:* 📚\n"
    "- UK Clients: Learn tax benefits with spread betting.\n"
    "- US Clients: Understand brokers and strategies specific to the US market.\n"
    "- EU Clients: Navigate ESMA regulations and leverage responsibly.\n\n"
    "📚 *Cryptocurrency Trading Guides:* 📚\n"
    "- Binance, Kraken, and Coinbase guides help you buy and sell crypto safely with minimal fees and maximum security.\n\n"
    "📖 Click on the relevant button links below to get started! 📖"
)

# Inline buttons for guides
GUIDES_BUTTONS = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("UK Forex Guide", url="https://telegra.ph/Forex-Trading-Guide-for-UK-Clients-12-23"),
        InlineKeyboardButton("US Forex Guide", url="https://telegra.ph/Forex-Trading-Guide-for-US-Clients-12-23"),
    ],
    [
        InlineKeyboardButton("EU Forex Guide", url="https://telegra.ph/Forex-Trading-Guide-for-European-Clients-12-23"),
    ],
    [
        InlineKeyboardButton("Binance Guide", url="https://telegra.ph/Binance-Guide-Buying-and-Selling-Cryptos-While-Minimizing-Fees-12-23"),
        InlineKeyboardButton("Kraken Guide", url="https://telegra.ph/Kraken-Guide-Buying-and-Selling-Cryptos-While-Minimizing-Fees-12-23"),
    ],
    [
        InlineKeyboardButton("Coinbase Guide", url="https://telegra.ph/Coinbase-Guide-Buying-and-Selling-Cryptos-While-Minimizing-Fees-12-23"),
    ],
])

# List of chat IDs to send the message to
CHAT_IDS = []  # Replace with the IDs of the chats where the message should be sent

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler."""
    # Print user info (user ID and username)
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    await update.message.reply_text(f"Your User ID is: {user_id}\nYour Username is: {username}")

async def post_guides(context: CallbackContext) -> None:
    """Post the guides message to all chat IDs."""
    for chat_id in CHAT_IDS:
        try:
            await context.bot.send_message(chat_id=chat_id, text=GUIDES_MESSAGE, reply_markup=GUIDES_BUTTONS, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to send message to chat {chat_id}: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler."""
    await update.message.reply_text("This bot will post trading guides every 4 hours.")

def main() -> None:
    """Run the bot."""
    try:
        application = Application.builder().token(BOT_TOKEN).build()

        # Command handlers
        application.add_handler(CommandHandler("start", start))

        # Set up periodic task to send guides every 4 hours
        job_queue = application.job_queue
        job_queue.run_repeating(post_guides, interval=4 * 60 * 60, first=0)  # Every 4 hours

        # Run the bot
        logger.info("Bot started successfully!")
        application.run_polling()

    except Exception as e:
        logger.error(f"Error occurred: {e}")

if __name__ == "__main__":
    # No need to use asyncio.run() or await main
    main()
