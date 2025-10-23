import time
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
import sqlite3
from datetime import datetime, timedelta

# Set up logging to debug if needed
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup to store users who click on the button
def create_db():
    conn = sqlite3.connect('clicked_users.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users
                      (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

def log_user_click(user_id):
    conn = sqlite3.connect('clicked_users.db')
    cursor = conn.cursor()
    cursor.execute('''INSERT OR IGNORE INTO users (user_id) VALUES (?)''', (user_id,))
    conn.commit()
    conn.close()

# Define the function to send the subscription message
async def send_subscription_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = -4654207380
    message = (
        "🚀 *Unlock Your Full Potential with Our Exclusive Subscription Service\\!* 🚀\n\n"
        "✅ *Start at just £49\\/month*\n"
        "💥 *Save up to 53%* \\(that's *£649*\\) depending on your chosen combination pack and subscription duration\\!\n\n"
        "⚡ *Why Choose Us\\?* ⚡\n"
        "We don’t provide a *“signals per week”* estimate because our focus is on quality, not quantity\\. Our signals are based on the *highest probability trade opportunities*, aiming to maximize your returns\\.\n\n"
        "🔑 We don't force trades to meet arbitrary signal volume expectations\\. Our goal is to provide *accurate*, *rewarding* trades that help our clients *successfully grow their capital*\\.\n\n"
        "💬 Interested in subscribing\\? Have a chat with *@CaerusTradingBot* to explore options and checkout\\! 📈\n\n"
        "👇 Click the button below to get started\\! 👇"
    )
    
    keyboard = [
        [InlineKeyboardButton("Chat with @CaerusTradingBot", url="https://t.me/CaerusTradingBot")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        # Send the message with MarkdownV2 formatting
        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info("Subscription message sent to the chat.")
    except Exception as e:
        # Log any errors if sending the message fails
        logger.error(f"Error sending message: {e}")

    # Log the time of the next post
    next_post_time = datetime.now() + timedelta(seconds=14400)  # Add 4 hours
    logger.info(f"Next post scheduled at {next_post_time.strftime('%Y-%m-%d %H:%M:%S')}")

# Define the function to handle button clicks (log users who click)
async def button_click(update, context):
    user_id = update.effective_user.id
    log_user_click(user_id)
    await update.callback_query.answer()

# Define the function to start the periodic message schedule
async def start(update, context):
    # Log the time the bot is started
    logger.info("Bot started. Sending a test message.")
    
    # Send a test message immediately upon bot start to verify that it can post
    await send_subscription_message(context)
    
    # Send subscription message every 4 hours (14400 seconds)
    context.job_queue.run_repeating(send_subscription_message, interval=14400, first=0)

# Define main function to set up the bot
def main():
    # Create database to store users who click the button
    create_db()

    # Set up the Application and Dispatcher (v20+)
    application = Application.builder().token("7804882491:AAHsXuxliLe5euh0Ei9NMB2odxPb5MWx_6s").build()
    
    # Add handlers for commands and button clicks
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click))

    # Start polling to receive updates
    application.run_polling()

if __name__ == '__main__':
    main()

