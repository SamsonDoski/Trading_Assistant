import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

# 1. Load credentials from .env
load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# 2. Initialize the Client
# paper=True is our safety harness!
client = TradingClient(API_KEY, SECRET_KEY, paper=True)

try:
    # 3. Fetch account details
    account = client.get_account()
    print("🚀 V3.0 CONNECTION SUCCESSFUL!")
    print(f"Account ID: {account.id}")
    print(f"Current Equity: ${account.equity}")
    print(f"Buying Power: ${account.buying_power}")
    print(f"Status: {account.status}")
except Exception as e:
    print(f"❌ Connection Failed: {e}")
    print("Check if your keys in .env match the dashboard!")