from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
import asyncio  # Import asyncio to run the event loop properly

# Replace this with your bot's API token
API_TOKEN = 'YOUR_BOT_API_TOKEN'

# Subscription prices in GBP
monthly_price = 49
discount = 0.1

# Calculate subscription prices with discounts
def calculate_price(months: int):
    total_price = monthly_price * months
    if months >= 3:
        total_price -= total_price * (discount * (months // 3))
    return total_price

# Function to start the bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_message = f"Hello {user.first_name}, welcome to the Gold & Crypto Subscription Bot!\n\nUse /menu to see subscription options."
    await update.message.reply_text(welcome_message)

# Function to show the help message
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "This bot allows you to subscribe to our Gold & Cryptocurrency service.\n\n"
        "/menu - View subscription options\n"
        "Select a plan from the options to subscribe and enjoy exclusive content."
    )
    await update.message.reply_text(help_text)

# Function to show subscription menu
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(f"1 Month - £{monthly_price}", callback_data='1_month')],
        [InlineKeyboardButton(f"3 Months - £{calculate_price(3):.2f}", callback_data='3_months')],
        [InlineKeyboardButton(f"6 Months - £{calculate_price(6):.2f}", callback_data='6_months')],
        [InlineKeyboardButton(f"9 Months - £{calculate_price(9):.2f}", callback_data='9_months')],
        [InlineKeyboardButton(f"12 Months - £{calculate_price(12):.2f}", callback_data='12_months')]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please select a subscription plan:", reply_markup=reply_markup)

# Handle callback queries (user selects a subscription)
async def handle_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the callback
    months_map = {
        '1_month': 1,
        '3_months': 3,
        '6_months': 6,
        '9_months': 9,
        '12_months': 12
    }
    
    selected_months = months_map.get(query.data)
    price = calculate_price(selected_months)
    
    confirmation_message = (
        f"You have selected a {selected_months}-month subscription.\n"
        f"Total Price: £{price:.2f}\n\n"
        "Please proceed with the payment to complete the subscription."
    )
    
    await query.edit_message_text(text=confirmation_message, parse_mode=ParseMode.MARKDOWN)

# Set up the Application and Dispatcher
async def main():
    application = Application.builder().token(API_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("menu", menu))
    
    application.add_handler(CallbackQueryHandler(handle_subscription))
    
    # Start polling for updates
    await application.run_polling()

# Start polling for updates using asyncio.run to properly await the main function
if __name__ == '__main__':
    asyncio.run(main())  # This properly runs the async main function in an event loop
