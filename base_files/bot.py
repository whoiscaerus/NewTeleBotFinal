import logging
import os
import requests
import re
import xrpl
import RateFetcher
import signal
import sys
import datetime
import asyncio
import sqlite3
import qrcode
from telegram.constants import ParseMode
from RateFetcher import fetch_rates, calculate_crypto_pricing  # Import the functions
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from requests import get
from xrpl.models.requests import AccountTx
from xrpl.models.transactions import Payment
from decimal import Decimal

# Fetch rates from RateFetcher.py
fetch_rates()

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Set up logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# Subscription Pricing
pricing = {
    "gold": {1: 49, 3: 147, 6: 294, 9: 441, 12: 588},
    "sp500": {1: 49, 3: 147, 6: 294, 9: 441, 12: 588},
    "crypto": {1: 49, 3: 147, 6: 294, 9: 441, 12: 588},
    "gold_crypto": {1: 90, 3: 270, 6: 540, 9: 810, 12: 1080},
    "sp500_crypto": {1: 90, 3: 270, 6: 540, 9: 810, 12: 1080},
    "gold_sp500": {1: 90, 3: 270, 6: 540, 9: 810, 12: 1080},
    "gold_sp500_crypto": {1: 115, 3: 345, 6: 690, 9: 1035, 12: 1380},
}

# Discounts (savings) and percentages (fixed values)
discounts = {
    "gold": {1: (0, 0), 3: (15, 10), 6: (59, 20), 9: (132, 30), 12: (235, 40)},
    "sp500": {1: (0, 0), 3: (15, 10), 6: (59, 20), 9: (132, 30), 12: (235, 40)},
    "crypto": {1: (0, 0), 3: (15, 10), 6: (59, 20), 9: (132, 30), 12: (235, 40)},
    "gold_crypto": {1: (8, 8), 3: (46, 17), 6: (146, 27), 9: (292, 36), 12: (486, 45)},
    "sp500_crypto": {1: (8, 8), 3: (46, 17), 6: (146, 27), 9: (292, 36), 12: (486, 45)},
    "gold_sp500": {1: (8, 8), 3: (46, 17), 6: (146, 27), 9: (292, 36), 12: (486, 45)},
    "gold_sp500_crypto": {1: (32, 22), 3: (104, 30), 6: (255, 37), 9: (466, 45), 12: (649, 53)},
}

# Categories and subcategories
categories = {
    "gold": "Gold",
    "sp500": "SP500",
    "crypto": "Crypto",
    "combination_packs": {
        "gold_crypto": "Gold + Crypto",
        "sp500_crypto": "SP500 + Crypto",
        "gold_sp500": "Gold + SP500",
        "gold_sp500_crypto": "Gold + SP500 + Crypto",
    },
}

# Cryptocurrency wallet addresses
crypto_wallets = {
    "bitcoin": "bc1qzkzlz6xfulwml7cr4nm2gfyd59ujgjtvhavvme",
    "litecoin": "ltc1q4czqsy2hcun5h4t5q5mpmt52h868mnqnznl3jh",
    "ethereum": "0xf45B4d0D5E75B87730e9C48aFEFd770C8E084aDc",
    "ripple": "rfMZAJ1ASCUkb58Zvg2vfhpaoVZVXqwaDD",
    "binancecoin": "0xf45B4d0D5E75B87730e9C48aFEFd770C8E084aDc",
    "bitcoin-cash": "qrzmh69m2hznhn0m6n8jvsq73sj7j4xpsvryezcgsq",
    "cardano": "addr1q803uyghztdy6hvu05dhtkgh97wm3s2h0jt0d8a5eduxl6rtltnk3sx6mw7rp5yem9cksynau2jyusnjw9hwjptkfnns8ajpz2",
    "dash": "XnfPME2BeXc8wgmXsNPUeBCmXCQyKXpD7S",
    "dodgecoin": "D5j9NjESiGmHWwtAUCtq6fwWz5XycFW8Wk",
    "ethereum-classic": "0x0cF98d79524C7feB25bbc579923e2AAE330c21a7",
    "polkadot": "15LaVkpj9frWa7SjG75WdLGHRoDVhJZrNdWTdkGxWKR3SPD7",
    "solana": "AzCVe9M2hrQbZToZ8mCkah6xeiVDwvjhJbdXSkCSTWy8",
    "stellar": "GD64A25HXRIDGS55O4M7Q3PCRODVXBBBIJ5TPBVLHXDBXJ3MINNHQTCJ", #needs small transaction to open acc
    "tron": "TE9dgQR91CUsFBwqjwPeXBHvnPByN4xFE2",
    "zcash": "t1U18YPYiJ4k4Pm8kuidFjj7tzjJEmdt9sa",
}

payment_guides = {
    "bitcoin": [
        "https://telegra.ph/Guide-to-Buying-Bitcoin-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Bitcoin-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Bitcoin-BTC-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "litecoin": [
        "https://telegra.ph/Guide-to-Buying-Litecoin-LTC-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Litecoin-LTC-on-Coinbase-safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Litecoin-LTC-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "ethereum": [
        "https://telegra.ph/Guide-to-Buying-Ethereum-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Ethereum-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Ethereum-ETH-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "xrp": [
        "https://telegra.ph/Guide-to-Buying-XRP-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-XRP-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-XRP-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "binancecoin": [
        "https://telegra.ph/Guide-to-Buying-Binance-Coin-BNB-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Binance-Coin-BNB-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Binance-Coin-BNB-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "bitcoin-cash": [
        "https://telegra.ph/Guide-to-Buying-Bitcoin-Cash-BCH-on-Binance-and-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Bitcoin-Cash-BCH-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Bitcoin-Cash-BCH-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "cardano": [
        "https://telegra.ph/Guide-to-Buying-Cardano-ADA-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Cardano-ADA-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Cardano-ADA-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "dash": [
        "https://telegra.ph/Guide-to-Buying-Dash-DASH-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Dash-DASH-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Dash-DASH-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "dodgecoin": [
        "https://telegra.ph/Guide-to-Buying-Dogecoin-DOGE-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Dogecoin-DOGE-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Dogecoin-DOGE-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "ethereum-classic": [
        "https://telegra.ph/Guide-to-Buying-Ethereum-Classic-ETC-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Ethereum-Classic-ETC-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Ethereum-Classic-ETC-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "polkadot": [
        "https://telegra.ph/Guide-to-Buying-Polkadot-DOT-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Polkadot-DOT-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Polkadot-DOT-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "solana": [
        "https://telegra.ph/Guide-to-Buying-Solana-SOL-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Solana-SOL-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Solana-SOL-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "stellar": [
        "https://telegra.ph/Guide-to-Buying-Stellar-XLM-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Stellar-XLM-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Stellar-XLM-on-Kraken-and-Sending-It-Safely-12-19"
    ],
    "tron": [
        "https://telegra.ph/Guide-to-Buying-TRON-TRX-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-TRON-TRX-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-TRON-TRX-on-Kraken-and-Sending-It-Safely-12-18"
    ],
    "zcash": [
        "https://telegra.ph/Guide-to-Buying-Zcash-ZEC-on-Binance-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Zcash-ZEC-on-Coinbase-and-Sending-It-Safely-12-18",
        "https://telegra.ph/Guide-to-Buying-Zcash-ZEC-on-Kraken-and-Sending-It-Safely-12-18"
    ]
}

def create_db():
    conn = sqlite3.connect('subscriptions.db')
    c = conn.cursor()
    # Create user and subscription tables
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    txid TEXT,
                    crypto_type TEXT,
                    amount_sent REAL,
                    subscription_category TEXT,
                    subscription_end_date TEXT
                )''')
    conn.commit()
    conn.close()

def add_user_subscription(user_id, username, txid, crypto_type, amount_sent, category, subscription_end_date):
    conn = sqlite3.connect('subscriptions.db')
    c = conn.cursor()
    c.execute('''INSERT INTO users (user_id, username, txid, crypto_type, amount_sent, subscription_category, subscription_end_date)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                 (user_id, username, txid, crypto_type, amount_sent, category, subscription_end_date))
    conn.commit()
    conn.close()

def get_user_subscription(txid):
    conn = sqlite3.connect('subscriptions.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM users WHERE txid = ?''', (txid,))
    user = c.fetchone()
    conn.close()
    return user

async def check_expired_subscriptions(application):
    # Access the bot from the application
    bot = application.bot
    conn = sqlite3.connect('subscriptions.db')
    c = conn.cursor()
    c.execute('SELECT user_id, subscription_category, subscription_end_date FROM users')
    users = c.fetchall()
    conn.close()

    for user in users:
        user_id, category, subscription_end_date = user
        category_chat_map = {
            'gold': -4608351708,
            'sp500': -4662755518,
            'crypto': -4740971535,
            'gold_crypto': -4767465199,
            'sp500_crypto': -4654433080,
            'gold_sp500': -4786454930,
            'gold_sp500_crypto': -4779379128
        }
        chat_id = category_chat_map.get(category)
        
        # Check if the subscription is expired
        if datetime.datetime.now() > datetime.datetime.strptime(subscription_end_date, '%Y-%m-%d'):
            await bot.kick_chat_member(chat_id, user_id)

def signal_handler(sig, frame):
    print('Shutting down gracefully...')
    # Add any clean-up code here if needed
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Recognize TXID based on regex patterns for each blockchain
def recognize_txid(txid):
    patterns = {
        "bitcoin": r"^[a-f0-9]{64}$",
        "litecoin": r"^[a-f0-9]{64}$",
        "ethereum": r"^0x[a-f0-9]{64}$",
        "ripple": r"^[A-F0-9]{64}$",
        "bitcoin-cash": r"^[a-fA-F0-9]{64}$",
        "ethereum-classic": r"^0x[a-fA-F0-9]{64}$",
        "binancecoin": r"^0x[a-fA-F0-9]{64}$",
        "dogecoin": r"^[a-fA-F0-9]{64}$",
        "dash": r"^[a-fA-F0-9]{64}$",
        "zcash": r"^[a-fA-F0-9]{64}$",
        "cardano": r"^[a-fA-F0-9]{64}$",
        "polkadot": r"^[1-9A-HJ-NP-Za-km-z]{48,66}$",
        "solana": r"^[1-9A-HJ-NP-Za-km-z]{88}$",
        "stellar": r"^[a-fA-F0-9]{64}$",
        "tron": r"^0x[a-fA-F0-9]{64}$"
}


    for blockchain, pattern in patterns.items():
        if re.match(pattern, txid):
            return blockchain

    return "Unknown"  # If no pattern matches

async def generate_qr_code(data: str, file_path: str = None):
    """
    Generates a QR code for the given data and saves it to the specified file path in the same directory.

    Args:
        data (str): The data to encode in the QR code.
        file_path (str): The file path where the QR code image will be saved.
                         If None, it defaults to 'crypto_qr.png' in the current directory.
    """
    if file_path is None:
        # Save the QR code in the same directory as the bot script
        current_directory = os.getcwd()
        file_path = os.path.join(current_directory, "crypto_qr.png")

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(file_path)
    print(f"QR Code saved to: {file_path}")  # Debugging output

# API - cryptoapis.io
async def get_cryptoapis(crypto, txid, recipient_wallet):
    """
    Fetch transaction details from CryptoAPIs for a specific cryptocurrency and TXID.
    
    :param crypto: The cryptocurrency type (e.g., 'bitcoin', 'ethereum', 'litecoin', 'xrp').
    :param txid: The transaction ID to validate.
    :param recipient_wallet: The wallet address to validate against.
    :return: A tuple (hasBeenSentToMe, amount_sent).
    """
    api_key = "36bcf2ade9193d879cdfc01eb2ad55b3ffe5b4a9"  # Define globally at the top of the code
    network = "mainnet"
    api_url = f"https://rest.cryptoapis.io/blockchain-data/{crypto}/{network}/transactions/{txid}"
    
    response = get(api_url, headers={'Content-Type': "application/json", 'x-api-key': api_key})
    if response.status_code != 200:
        print(f"❌ Failed to get API response. Status Code: {response.status_code}, Message: {response.text} ❌")
        return False, 0  # Return False with 0 amount on failure
    
    hasBeenSentToMe = False
    amount_sent = 0
    data = response.json()  # Extract JSON response
    
    # Loop through recipients to find if the transaction includes the recipient's wallet address
    for recipient in data["data"]["item"]["recipients"]:
        if recipient["address"] == recipient_wallet:
            amount_sent = float(recipient["amount"])
            hasBeenSentToMe = True
            break
    
    if hasBeenSentToMe:
        return True, amount_sent
    else:
        return False, 0  # Return False if no match is found

# Connect to Ripple Mainnet using XRPL client
client = xrpl.clients.JsonRpcClient("https://s1.ripple.com:51234/")

def validate_xrp_payment(txid: str, recipient_wallet: str, expected_amount: float) -> bool:
    """
    Validate an XRP transaction by its TXID, recipient wallet, and expected amount.
    
    :param txid: The transaction ID to validate.
    :param recipient_wallet: The wallet address to verify as the transaction recipient.
    :param expected_amount: The expected amount of XRP to be received.
    :return: True if the transaction is valid, False otherwise.
    """
    try:
        # Fetch transaction details
        tx_request = AccountTx(account=recipient_wallet, limit=5)
        tx_response = client.request(tx_request)

        if "result" not in tx_response.to_dict() or "error" in tx_response.to_dict():
            print("❌ Transaction not found or invalid. ❌")
            return False

        # Loop through the transactions to find the specific txid
        for tx in tx_response.result["transactions"]:
            if tx["tx"]["hash"] == txid:
                # Transaction found, verify the amount and destination
                tx_data = tx["tx"]

                if tx_data["TransactionType"] != "Payment":
                    print("❌ Transaction is not a payment. ❌")
                    return False

                # Verify the recipient wallet
                destination = tx_data["Destination"]
                if destination != recipient_wallet:
                    print(f"❌ Recipient wallet mismatch: expected {recipient_wallet}, got {destination}. ❌")
                    return False

                # Verify the amount (in drops, convert to XRP)
                received_amount = Decimal(tx_data["Amount"]) / Decimal(1_000_000)  # Convert drops to XRP
                if received_amount != Decimal(expected_amount):
                    print(f"❌ Amount mismatch: expected {expected_amount} XRP, got {received_amount} XRP. ❌")
                    return False

                # Check transaction success status
                if tx_data.get("meta", {}).get("TransactionResult") != "tesSUCCESS":
                    print(f"❌ Transaction failed with status: {tx_data['meta']['TransactionResult']} ❌")
                    return False

                print("✅ Transaction validated successfully! ✅")
                return True

        print("❌ Transaction ID not found in the account's recent transactions. ❌")
        return False

    except Exception as e:
        print(f"❌ Error during validation: {e} ❌")
        return False


def is_valid_txid(txid, crypto_type):
    patterns = {
        "bitcoin": r"^[a-f0-9]{64}$",
        "litecoin": r"^[a-f0-9]{64}$",
        "ethereum": r"^0x[a-f0-9]{64}$",
        "ripple": r"^[A-F0-9]{64}$",
        "bitcoin-cash": r"^[a-fA-F0-9]{64}$",
        "ethereum-classic": r"^0x[a-fA-F0-9]{64}$",
        "binancecoin": r"^0x[a-fA-F0-9]{64}$",
        "dogecoin": r"^[a-fA-F0-9]{64}$",
        "dash": r"^[a-fA-F0-9]{64}$",
        "zcash": r"^[a-fA-F0-9]{64}$",
        "cardano": r"^[a-fA-F0-9]{64}$",
        "polkadot": r"^[1-9A-HJ-NP-Za-km-z]{48,66}$",
        "solana": r"^[1-9A-HJ-NP-Za-km-z]{88}$",
        "stellar": r"^[a-fA-F0-9]{64}$",
        "tron": r"^0x[a-fA-F0-9]{64}$"
}

    pattern = patterns.get(crypto_type.lower())
    if not pattern:
        return False  # Unsupported crypto type
    return bool(re.match(pattern, txid))


#Fetch exchange rates from RateFetcher.py
async def pricing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Respond to the /pricing command by calculating and sending the pricing data.
    """
    pricing_data = calculate_crypto_pricing()
    if "error" in pricing_data:
        await update.message.reply_text(pricing_data["❌ error ❌"])
    else:
        # Format pricing data for user
        response = "Subscription Pricing:\n"
        for plan, durations in pricing_data.items():
            response += f"\n{plan.capitalize()}:\n"
            for months, rates in durations.items():
                response += (
                    f"  {months} month(s): ${rates['usd']} USD / {rates['bitcoin']} BTC\n"
                )
        await update.message.reply_text(response)



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Define the escaped message
    escaped_message = escape_markdown("💸 Save Up To £649 / 53% On Combination Packs. 💸 Save Up To 40% On Longer Durations. 💸", version=2)

    # Create the inline keyboard with category buttons
    keyboard = [
        [InlineKeyboardButton("💰 Gold 💰", callback_data="category:gold")],
        [InlineKeyboardButton("📈 SP500 📉", callback_data="category:sp500")],
        [InlineKeyboardButton("🅱️ Crypto 🅱️", callback_data="category:crypto")],
        [InlineKeyboardButton("🎁 Combination Packs 🎁", callback_data="category:combination_packs")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # If it's a command, send the main menu first, then the escaped message
    if update.message:
        # Send the main menu with inline buttons
        await update.message.reply_text(
            "🚀 Welcome to the subscription shop! 🛒 Choose a category, starting from £49/month:",
            reply_markup=reply_markup
        )
        # Send the escaped message below the main menu
        await update.message.reply_text(
            f"🎉 *Special Offer:*\n{escaped_message}",
            parse_mode="MarkdownV2"
        )
    # If it's a callback query, edit the existing message and send the escaped message
    elif update.callback_query:
        query = update.callback_query
        # Edit the main menu
        await query.edit_message_text(
            "🚀 Welcome to the subscription shop! 🛒 Choose a category:",
            reply_markup=reply_markup
        )
        # Send the escaped message below the main menu
        await query.message.reply_text(
            f"🎉 *Special Offer:*\n{escaped_message}",
            parse_mode="MarkdownV2"
        )

# Callback handler for inline buttons
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    callback_data = query.data

    if callback_data == "back_to_main_menu":
        await start(update, context)
    # Handle other callback data as needed



async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    category = query.data.split(":")[1]

    if category == "combination_packs":
        # Define custom button labels with emojis
        category_labels = {
            "gold_crypto": "💰 Gold + 🅱️ Crypto",
            "sp500_crypto": "📈 SP500 + 🅱️ Crypto",
            "gold_sp500": "💰 Gold + 📈 SP500",
            "gold_sp500_crypto": "💰 Gold + 📈 SP500 + 🅱️ Crypto"
        }

        # Show subcategories for combination packs with updated labels
        keyboard = [
            [InlineKeyboardButton(category_labels[key], callback_data=f"subcategory:{key}")]
            for key in categories["combination_packs"]
        ]

        # Add Back button to navigate to the main category menu
        keyboard.append([InlineKeyboardButton("🔙 Back 🔙", callback_data="back_to_main_menu")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🎉 Choose a combination pack: 🎉", reply_markup=reply_markup)
    else:
        # Show durations for standard categories
        await show_durations(query, category)


async def handle_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    subcategory = query.data.split(":")[1]
    await show_durations(query, subcategory)

async def show_durations(query, category):
    # Check if the category is in the top level or in combination_packs
    if category in categories:
        category_name = categories[category]
    elif category in categories['combination_packs']:
        category_name = categories['combination_packs'][category]
    else:
        print(f"❌ Error: {category} not found in categories. ❌")
        return

# Generate the duration buttons with pricing, discounts, and percentage
    duration_buttons = [
    [InlineKeyboardButton(
        f"⏳ {months} month{'s' if months > 1 else ''} - \u00a3{pricing[category][months] - discounts[category][months][0]} "
        f"(Save \u00a3{discounts[category][months][0]}, {discounts[category][months][1]}%) 🎉",
        callback_data=f"duration:{category}:{months}"  # Callback includes category and months
    )]
    for months in pricing[category]
]

    
    # Add the Back button
    duration_buttons.append([InlineKeyboardButton("🔙 Back 🔙", callback_data="back_to_main_menu")])
    
    # Set the reply markup for inline buttons
    reply_markup = InlineKeyboardMarkup(duration_buttons)
    
    # Edit the message to show subscription durations for the selected category
    await query.edit_message_text(f"⏳ Choose your subscription duration for {category_name}: ⏳", reply_markup=reply_markup)


async def handle_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    category, months = query.data.split(":")[1:3]
    months = int(months)

    # Check if it's a combination category and handle accordingly
    if category in categories['combination_packs']:
        category_name = categories['combination_packs'][category]
    else:
        category_name = categories[category]

    # Calculate price and discount
    price = pricing[category][months]
    saving = discounts[category][months][0]
    discount_percentage = discounts[category][months][1]

    # Store subscription details in context for later use
    context.user_data["selected_subscription"] = {
        "category": category,
        "months": months,
        "price": price,
        "saving": saving,
        "discount_percentage": discount_percentage,
    }

    # Determine whether to use "month" or "months"
    month_label = "month" if months == 1 else "months"

    # Present cryptocurrency payment options
    keyboard = [
        [InlineKeyboardButton("💱 Pay With Cryptocurrencies 💱", callback_data="cryptocurrencypaymentoptions")],
        [InlineKeyboardButton("🔙 Back to Main Menu 🔙", callback_data="back_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"💳 Select your payment method for {category_name} ({months} {month_label}): 💳", 
        reply_markup=reply_markup
    )


async def cryptocurrency_payment_options(update, context):
    query = update.callback_query
    await query.answer()  # Acknowledge the callback query to avoid a loading spinner in the client

    if query.data == "cryptocurrencypaymentoptions":
    # Define the new keyboard
        new_keyboard = [
        [InlineKeyboardButton("Binance Smart Chain - BNB 🟡", callback_data="crypto:binancecoin")],
        [InlineKeyboardButton("Bitcoin - BTC ₿", callback_data="crypto:bitcoin")],
        [InlineKeyboardButton("Bitcoin Cash - BCH 💵", callback_data="crypto:bitcoin-cash")],
        [InlineKeyboardButton("Cardano - ADA ♾️", callback_data="crypto:cardano")],
        [InlineKeyboardButton("Dash Coin - DASH 💨", callback_data="crypto:dash")],
        [InlineKeyboardButton("DodgeCoin - DOGE 🐕", callback_data="crypto:dogecoin")],
        [InlineKeyboardButton("Ethereum - ETH 💎", callback_data="crypto:ethereum")],
        [InlineKeyboardButton("Ethereum Classic - ETC ⚙️", callback_data="crypto:ethereum-classic")],
        [InlineKeyboardButton("Litecoin - LTC 🌕", callback_data="crypto:litecoin")],
        [InlineKeyboardButton("Polkadot - DOT 🎯", callback_data="crypto:polkadot")],
        [InlineKeyboardButton("Solana - SOL 🌞", callback_data="crypto:solana")],
        [InlineKeyboardButton("Stellar - XLM ✨", callback_data="crypto:stellar")],
        [InlineKeyboardButton("Tron - TRX 🌐", callback_data="crypto:tron")],
        [InlineKeyboardButton("XRP 💧", callback_data="crypto:ripple")],
        [InlineKeyboardButton("Zcash - ZEC 🔒", callback_data="crypto:zcash")],
        [InlineKeyboardButton("Back To Other Payment Methods 🔙", callback_data="back_to_other_payment_methods")],
    ]
        new_reply_markup = InlineKeyboardMarkup(new_keyboard)

        # Edit the current message to show the new keyboard
        await query.edit_message_text("💱 Please select a cryptocurrency to pay with:", reply_markup=new_reply_markup)

    elif query.data == "back_to_other_payment_methods":
        # Extract necessary data from the callback query to pass back to the first function
        # Here we assume that category and months are stored in context.user_data
        selected_subscription = context.user_data.get("selected_subscription")
        if selected_subscription:
            category = selected_subscription["category"]
            months = selected_subscription["months"]
            category_name = categories[category] if category not in categories['combination_packs'] else categories['combination_packs'][category]
            
            # Rebuild the original keyboard for payment options
            original_keyboard = [
                [InlineKeyboardButton("💳 Pay With  💳", callback_data="cryptocurrencypaymentoptions")],
            ]
            original_reply_markup = InlineKeyboardMarkup(original_keyboard)

            # Send the user back to the original message with payment options
            await query.edit_message_text(f"💱 Select your payment method for {category_name} ({months} month(s)): 💱", reply_markup=original_reply_markup)


# Handle the "Back To Other Payment Methods" button
async def back_to_other_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    # Extract subscription details from context (category and months)
    selected_subscription = context.user_data.get("selected_subscription")
    if selected_subscription:
        category = selected_subscription["category"]
        months = selected_subscription["months"]
        category_name = categories[category] if category not in categories['combination_packs'] else categories['combination_packs'][category]

        # Rebuild the original keyboard with the "Pay With Cryptocurrencies" button
        original_keyboard = [
            [InlineKeyboardButton("💳 Pay With Cryptocurrencies 💳", callback_data="cryptocurrencypaymentoptions")],
        ]
        original_reply_markup = InlineKeyboardMarkup(original_keyboard)

        # Send the user back to the original message with the payment options
        await query.edit_message_text(f"💱 Select your payment method for {category_name} ({months} month(s)): 💱", reply_markup=original_reply_markup)

def escape_markdown_v2(text: str) -> str:
    # Escape all special characters used in MarkdownV2 except double asterisks
    return re.sub(r'([\\_`[\]()~>`#+-=|{}.!])', r'\\\1', text)

async def handle_crypto_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    crypto_choice = query.data.split(":")[1].lower()

    # Retrieve category, duration, and price details from context
    selected_data = context.user_data.get("selected_subscription")
    if not selected_data:
        await query.edit_message_text("❌ An error occurred. Please start over. ❌")
        return

    category = selected_data["category"]
    months = selected_data["months"]
    price = selected_data["price"]
    saving = selected_data["saving"]
    discount_percentage = selected_data["discount_percentage"]

    # Debugging: Check values
    print(f"Category: {category}, Months: {months}, Price: {price}")

    # Ensure months is an integer for the lookup
    months = int(months)

    # Determine whether to use "month" or "months"
    month_label = "month" if months == 1 else "months"

    # Save the selected cryptocurrency type
    context.user_data["crypto_type"] = crypto_choice

    # Fetch the pricing data for cryptocurrencies
    pricing_data = calculate_crypto_pricing()
    if pricing_data is None:
        await query.edit_message_text("❌ Error fetching cryptocurrency prices. Please try again later. ❌")
        return

    # Check if category is in the pricing data
    category_data = pricing_data.get(category)
    if not category_data:
        await query.edit_message_text(f"❌ Invalid category: {category}. Please select a valid category. ❌")
        return

    # Check if months is in the pricing data for the selected category
    months_data = category_data.get(months)
    if not months_data:
        await query.edit_message_text(f"❌ Invalid subscription duration: {months} months. Please select a valid duration. ❌")
        return

    # Check if the selected cryptocurrency exists within the months data
    crypto_price = months_data.get(crypto_choice)
    if not crypto_price:
        await query.edit_message_text("❌ Invalid cryptocurrency choice. Please select a valid cryptocurrency. ❌")
        return

    # Get the corresponding wallet address
    wallet_address = crypto_wallets.get(crypto_choice)

    # Fetch the guides for the selected cryptocurrency
    guides = payment_guides.get(crypto_choice, [])

    # Generate inline buttons for each guide dynamically
    guide_buttons = [
        InlineKeyboardButton(f"📘 {name} Guide 📘", url=guide)
        for guide in guides
        for name in ["Binance", "Kraken", "Coinbase"]
        if name.lower() in guide.lower()
    ]

    # Create the main inline buttons
    submit_txid_button = InlineKeyboardButton("📤 Submit Transaction ID (TXID) 📤", callback_data="submit_txid")
    back_to_main_menu_button = InlineKeyboardButton("🔙 Back To Main Menu 🔙", callback_data="back_to_main_menu")
    cryptocurrency_payment_options = InlineKeyboardButton("💱 Pay With A Different Cryptocurrency 💱", callback_data="cryptocurrencypaymentoptions")

    # Combine all buttons into the markup
    reply_markup = InlineKeyboardMarkup([
        [submit_txid_button],
        [back_to_main_menu_button],
        [cryptocurrency_payment_options],
        *[[button] for button in guide_buttons]  # Add each guide as a separate row
    ])

    # Format category for better display
    formatted_category = category.replace("_", ", ").title().replace("And", "&")

    # Send the main subscription details
    await query.edit_message_text(
        escape_markdown_v2(f"🎉 *You’ve selected {crypto_choice.capitalize()} as your payment method!*\n\n"
                           f"📦 *Subscription:* {formatted_category} for {months} {month_label}\n"
                           f"💵 *Price:* £{price}\n"
                           f"🎁 *Savings:* £{saving} ({discount_percentage}% OFF)\n"
                           f"🔖 *Total After Discount:* £{price - saving}\n\n"
                           f"🚀 Please follow the steps below to complete your payment:\n\n"
                           f"1️⃣ *Pay the crypto amount:* {crypto_price:.8f} {crypto_choice.upper()}\n"
                           f"2️⃣ *Send payment to the wallet address below.* {wallet_address}\n"
                           f"📋 *Tap and hold twice on the address/amount above to copy it to your clipboard.*\n\n"
                           f"⚠️*This payable Crypto amount is valid for 15 minutes before a new rate is calculated*⚠️\n\n"
                           f"💡 *Need help? Use the guides below to sign up, deposit, buy, and send Crypto safely using three reputable Crypto Exchanges!* 📚"),
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )


    # Send wallet address in a separate message
    escaped_wallet_address = escape_markdown_v2(wallet_address)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"📤 *Wallet Address:*\n`{escaped_wallet_address}`",
        parse_mode="MarkdownV2"
    )

    # Send crypto price in a separate message
    escaped_crypto_price = escape_markdown_v2(f"{crypto_price:.8f}")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"💰 *Crypto Amount:*\n`{escaped_crypto_price} {crypto_choice.capitalize()}`",
        parse_mode="MarkdownV2"
    )

    

# Button handler for "Submit Transaction ID (TXID)"
async def handle_submit_txid_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    # Prompt the user to enter their TXID
    await query.edit_message_text("📤 Please paste your Transaction ID (TXID) below: 📤")

    # Save the state to indicate the bot is waiting for TXID
    context.user_data["waiting_for_txid"] = True


# Handle the "Back to Main Menu" button
async def handle_back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    # Send the user back to the start command
    await start(update, context)

# Handle the "Pay With A Different Cryptocurrency" button
async def handle_pay_with_a_different_cryptocurrency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    # Send the user back to the start command
    await cryptocurrency_payment_options(update, context)



async def handle_txid_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # If this is triggered by a CallbackQuery (button press)
    if update.callback_query:
        query = update.callback_query
        await query.answer()  # Acknowledge the button press
        await query.edit_message_text("📥 Please paste your Transaction ID (TXID) here: 📥")

        # Save state to handle the TXID in the next message
        context.user_data["waiting_for_txid"] = True
        context.user_data["txid_attempts"] = 0  # Track attempts
        return

    # Handle the user's pasted TXID if the state is set
    if context.user_data.get("waiting_for_txid"):
        # Ensure we are processing a valid user message
        if not update.message or not update.message.text:
            keyboard = [
                [InlineKeyboardButton("🔄 Click To Submit TXID Again 🔄", callback_data="restart_txid_submission")],
                [InlineKeyboardButton("📞 Contact Support @WhoIsCaerus 💬", url="https://t.me/WhoIsCaerus")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "⚠️ Please paste a valid Transaction ID (TXID). ⚠️",
                reply_markup=reply_markup
            )
            return

        # Extract the TXID and user details
        txid = update.message.text.strip()
        user_id = update.message.from_user.id
        username = update.message.from_user.username

        # Increment the attempt count
        context.user_data["txid_attempts"] += 1

        # Retrieve stored payment details
        crypto_type = context.user_data.get("crypto_type")
        price = context.user_data.get("price")
        saved_amount = context.user_data.get("saving")

        # Validate the existence of payment details
        if not crypto_type or not price or not saved_amount:
            keyboard = [
                [InlineKeyboardButton("🔄 Click To Submit TXID Again 🔄", callback_data="restart_txid_submission")],
                [InlineKeyboardButton("📞 Contact Support @WhoIsCaerus 💬", url="https://t.me/WhoIsCaerus")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "⚠️ Missing payment details. Please restart the process. ⚠️",
                reply_markup=reply_markup
            )
            context.user_data["waiting_for_txid"] = False
            return

        # Fetch the recipient wallet address
        recipient_wallet = crypto_wallets.get(crypto_type)
        if not recipient_wallet:
            keyboard = [
                [InlineKeyboardButton("🔄 Click To Submit TXID Again 🔄", callback_data="restart_txid_submission")],
                [InlineKeyboardButton("📞 Contact Support @WhoIsCaerus 💬", url="https://t.me/WhoIsCaerus")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ Invalid cryptocurrency selected. Please try again. ❌",
                reply_markup=reply_markup
            )
            context.user_data["waiting_for_txid"] = False
            return

        # Validate the TXID
        if is_valid_txid(txid, crypto_type):
            # Fetch transaction details
            sent_crypto, sent_amount = get_cryptoapis(crypto_type, txid, recipient_wallet)

            if sent_crypto and float(sent_amount) >= float(price - saved_amount):
                # Confirm payment and add user to subscription
                subscription_end_date = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime('%Y-%m-%d')
                add_user_subscription(user_id, username, txid, crypto_type, sent_amount, "Gold", subscription_end_date)

                # Map the category to the appropriate chat ID
                category_chat_map = {
                    'gold': -4608351708,
                    'sp500': -4662755518,
                    'crypto': -4740971535,
                    'gold_crypto': -4767465199,
                    'sp500_crypto': -4654433080,
                    'gold_sp500': -4786454930,
                    'gold_sp500_crypto': -4779379128
                }

                chat_id = category_chat_map.get("gold")  # Example category
                if chat_id:
                    await context.bot.add_chat_member(chat_id, user_id)

                # Schedule removal after subscription ends
                subscription_end_datetime = datetime.datetime.strptime(subscription_end_date, '%Y-%m-%d')
                time_left = (subscription_end_datetime - datetime.datetime.now()).total_seconds()
                await asyncio.sleep(time_left)
                await context.bot.kick_chat_member(chat_id, user_id)

                await update.message.reply_text(
                    f"✅ Your payment of {sent_amount} {crypto_type.capitalize()} has been confirmed. "
                    f"You have been added to the Gold chat! ✅"
                )
                context.user_data["waiting_for_txid"] = False  # Clear state
                return
            else:
                keyboard = [
                    [InlineKeyboardButton("🔄 Click To Submit TXID Again 🔄", callback_data="restart_txid_submission")],
                    [InlineKeyboardButton("📞 Contact Support @WhoIsCaerus 💬", url="https://t.me/WhoIsCaerus")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"❌ The amount sent ({sent_amount} {crypto_type.capitalize()}) is insufficient. "
                    f"📞 Please try again or contact support @WhoIsCaerus. 💬",
                    reply_markup=reply_markup
                )
                context.user_data["waiting_for_txid"] = False
                return
        else:
            # Invalid TXID format; check attempt count
            if context.user_data["txid_attempts"] < 2:
                keyboard = [
                    [InlineKeyboardButton("🔄 Click To Submit TXID Again 🔄", callback_data="restart_txid_submission")],
                    [InlineKeyboardButton("📞 Contact Support @WhoIsCaerus 💬", url="https://t.me/WhoIsCaerus")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "⚠️ Invalid Transaction ID format. Please try again. ⚠️",
                    reply_markup=reply_markup
                )
            else:
                keyboard = [
                    [InlineKeyboardButton("🔄 Click To Submit TXID Again 🔄", callback_data="restart_txid_submission")],
                    [InlineKeyboardButton("📞 Contact Support @WhoIsCaerus 💬", url="https://t.me/WhoIsCaerus")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "❌ Invalid Transaction ID format. ❌ 📞 Please contact support @WhoIsCaerus. 💬❌",
                    reply_markup=reply_markup
                )
                context.user_data["waiting_for_txid"] = False  # Clear state
            return

    # Fallback for unexpected situations
    else:
        keyboard = [
            [InlineKeyboardButton("🔄 Click To Submit TXID Again 🔄", callback_data="restart_txid_submission")],
            [InlineKeyboardButton("📞 Contact Support @WhoIsCaerus 💬", url="https://t.me/whoiscaerus")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "❌ Please click the button to restart the payment process. ❌",
            reply_markup=reply_markup
        )

async def handle_contact_support_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the button press
    # Since it's a URL button, the user will be redirected to the Telegram chat automatically

# Step 1: The handler for the retry button press
async def handle_txid_retry_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    # Check if the callback data matches the retry action
    if query.data == "restart_txid_submission":
        await handle_txid_submission(update, context)  # Restart the TXID submission process


        # Reset the state
        context.user_data["waiting_for_txid"] = False

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("pricing", pricing_command))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_category, pattern="^category:"))
    application.add_handler(CallbackQueryHandler(handle_subcategory, pattern="^subcategory:"))
    application.add_handler(CallbackQueryHandler(handle_duration, pattern="^duration:"))
    application.add_handler(CallbackQueryHandler(handle_crypto_selection, pattern="^crypto:"))
    application.add_handler(CallbackQueryHandler(handle_txid_submission, pattern="^submit_txid"))
    application.add_handler(CallbackQueryHandler(handle_back_to_main_menu, pattern="^back_to_main_menu$"))
    application.add_handler(CallbackQueryHandler(cryptocurrency_payment_options, pattern="^cryptocurrencypaymentoptions$"))
    application.add_handler(CallbackQueryHandler(back_to_other_payment_methods, pattern="^back_to_other_payment_methods$"))
    application.add_handler(CallbackQueryHandler(handle_submit_txid_button, pattern="^submit_txid$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_txid_submission))
    application.add_handler(CallbackQueryHandler(handle_txid_retry_button_press))
    
    
    application.run_polling()

if __name__ == "__main__":
    main()