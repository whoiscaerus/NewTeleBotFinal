import requests
import threading
import signal
import sys

# API token and base URL for ExchangeRate-API
api_token = "7b8e8db657261aff7e5946c7"
gbp_to_usd_url = f"https://v6.exchangerate-api.com/v6/{api_token}/latest/GBP"

# CoinGecko API for cryptocurrency prices
coingecko_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,litecoin,ethereum,ripple,bitcoin-cash,ethereum-classic,binancecoin,dogecoin,dash,zcash,cardano,polkadot,solana,stellar,tron&vs_currencies=usd"

# Subscription Pricing and Discounts data
pricing = {
    "gold": {1: 49, 3: 132, 6: 235, 9: 308, 12: 353},
    "sp500": {1: 49, 3: 132, 6: 235, 9: 308, 12: 353},
    "crypto": {1: 49, 3: 132, 6: 235, 9: 308, 12: 353},
    "gold_crypto": {1: 90, 3: 224, 6: 394, 9: 518, 12: 594},
    "sp500_crypto": {1: 90, 3: 224, 6: 394, 9: 518, 12: 594},
    "gold_sp500": {1: 90, 3: 224, 6: 394, 9: 518, 12: 594},
    "gold_sp500_crypto": {1: 115, 3: 241, 6: 435, 9: 569, 12: 731},
}

# Global variables to store exchange rates
gbp_to_usd_rate = None
crypto_rates = None
previous_gbp_to_usd_rate = None
previous_crypto_rates = None

# Flag to control the program's running state
running = True

def fetch_rates():
    """
    Fetch the latest GBP to USD exchange rate and cryptocurrency prices in USD.
    """
    global gbp_to_usd_rate, crypto_rates, previous_gbp_to_usd_rate, previous_crypto_rates, running

    while running:
        try:
            # Fetch GBP to USD exchange rate
            gbp_response = requests.get(gbp_to_usd_url).json()
            gbp_to_usd_rate = gbp_response.get("conversion_rates", {}).get("USD", 1)

            # Fetch cryptocurrency rates in USD
            crypto_response = requests.get(coingecko_url).json()

            # Store the rates for each cryptocurrency
            crypto_rates = {
                "bitcoin": crypto_response.get("bitcoin", {}).get("usd", 0),
                "ethereum": crypto_response.get("ethereum", {}).get("usd", 0),
                "litecoin": crypto_response.get("litecoin", {}).get("usd", 0),
                "ripple": crypto_response.get("ripple", {}).get("usd", 0),
                "bitcoin-cash": crypto_response.get("bitcoin-cash", {}).get("usd", 0),
                "ethereum-classic": crypto_response.get("ethereum-classic", {}).get("usd", 0),
                "binancecoin": crypto_response.get("binancecoin", {}).get("usd", 0),
                "dogecoin": crypto_response.get("dogecoin", {}).get("usd", 0),
                "dash": crypto_response.get("dash", {}).get("usd", 0),
                "zcash": crypto_response.get("zcash", {}).get("usd", 0),
                "cardano": crypto_response.get("cardano", {}).get("usd", 0),
                "polkadot": crypto_response.get("polkadot", {}).get("usd", 0),
                "solana": crypto_response.get("solana", {}).get("usd", 0),
                "stellar": crypto_response.get("stellar", {}).get("usd", 0),
                "tron": crypto_response.get("tron", {}).get("usd", 0),
            }

            # Store previous values if the new rates are successfully fetched
            previous_gbp_to_usd_rate = gbp_to_usd_rate
            previous_crypto_rates = crypto_rates
        except Exception as e:
            # On error, revert to previous rates if available
            print(f"Error fetching rates: {e}")
            if previous_gbp_to_usd_rate is None or previous_crypto_rates is None:
                print("No previous exchange rates available, using defaults.")
            else:
                gbp_to_usd_rate = previous_gbp_to_usd_rate
                crypto_rates = previous_crypto_rates

        # Sleep for 15 minutes (900 seconds) before fetching again
        if running:
            threading.Event().wait(900)

def signal_handler(sig, frame):
    global running
    running = False
    print("Exiting program gracefully...")
    sys.exit(0)

# Set up the signal handler for Ctrl+C (SIGINT)
signal.signal(signal.SIGINT, signal_handler)

# Start the rate fetching in a separate thread
rate_thread = threading.Thread(target=fetch_rates)
rate_thread.daemon = True
rate_thread.start()

# Main program can continue running here (or wait for termination)
print("Started fetching exchange rates... Press Ctrl+C to stop.")
while running:
    pass
