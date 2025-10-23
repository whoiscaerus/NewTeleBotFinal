from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Replace 'YOUR_BOT_TOKEN' with your actual bot token
BOT_TOKEN = '7601276047:AAF5aQk6Sfz1P34DUyoZmsi3QrFPqu2DPpo'


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the bot starts."""
    await update.message.reply_text("Hi! Send me any message, and I'll fetch your Telegram account ID.")

async def get_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch the user's Telegram ID and display it in the terminal."""
    user = update.message.from_user
    print(f"Username: @{user.username if user.username else 'No Username'} | User ID: {user.id}")
    await update.message.reply_text(f"Your Telegram ID is: {user.id}")

def main():
    """Run the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_user_id))

    # Start the bot
    print("Bot is running... Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()
