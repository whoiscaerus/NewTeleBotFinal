import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Replace with your bot's token
BOT_TOKEN = '7804882491:AAEGqHclr61ROeHYj8RGZxV7mx5DpmeOuXw'

# Function to log the chat ID
async def get_chat_id(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id  # Get the chat ID
    user = update.effective_user  # Get the user who sent the message
    message = update.message.text  # Get the message text

    # Log the chat ID and user info to the terminal
    print(f"Chat ID: {chat_id}, User: {user.first_name if user else 'Unknown'}, Message: {message}")

    # Reply to the user with the chat ID
    await update.message.reply_text(f"Chat ID for this group is: {chat_id}")

def main():
    # Create the Application object
    application = Application.builder().token(BOT_TOKEN).build()

    # Register the message handler to log chat ID
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_chat_id))

    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main()

