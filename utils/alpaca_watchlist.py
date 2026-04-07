import os
import sys
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import CreateWatchlistRequest, UpdateWatchlistRequest

# Adjust path to import our profile manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.profile_manager import load_profiles, is_stale

# Load environment variables
load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# Initialize Alpaca Client (paper=True keeps us safe)
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)

WATCHLIST_NAME = "Combo_Optimized_V3"

def sync_watchlist():
    print(f"🔄 Syncing local profiles with Alpaca Watchlist: '{WATCHLIST_NAME}'...")
    
    # 1. Grab all tickers from the JSON file that are currently "fresh"
    profiles = load_profiles()
    active_tickers = []
    
    for ticker in profiles.keys():
        if not is_stale(ticker):
            active_tickers.append(ticker)
            
    if not active_tickers:
        print("⚠️ No fresh tickers found. Watchlist will be empty.")
    else:
        print(f"📋 Fresh local tickers to sync: {active_tickers}")
    
    # 2. Check if the watchlist already exists on Alpaca
    try:
        existing_watchlists = trading_client.get_watchlists()
        target_watchlist = next((wl for wl in existing_watchlists if wl.name == WATCHLIST_NAME), None)
        
        if target_watchlist is None:
            # Create a brand new watchlist
            print("➕ Watchlist not found on Alpaca. Creating it now...")
            req = CreateWatchlistRequest(name=WATCHLIST_NAME, symbols=active_tickers)
            trading_client.create_watchlist(req)
            print("✅ Watchlist created successfully!")
        else:
            # Overwrite the existing watchlist with our new fresh tickers
            print("✏️ Watchlist found on Alpaca. Updating symbols...")
            req = UpdateWatchlistRequest(name=WATCHLIST_NAME, symbols=active_tickers)
            trading_client.update_watchlist_by_id(target_watchlist.id, req)
            print("✅ Watchlist updated successfully!")
            
    except Exception as e:
        print(f"❌ Failed to sync with Alpaca: {e}")

if __name__ == "__main__":
    sync_watchlist()