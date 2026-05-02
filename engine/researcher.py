import os
import sys
from datetime import datetime, timedelta

# Adjust path so we can import from the utils folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.profile_manager import load_profiles, save_profiles, is_stale

# --- IMPORT ACTUAL V2 OPTIMIZER ---
from engine.run_optimizer import run_optimization 

def update_profile(ticker, best_short, best_long, rsi_period=14):
    """Saves the newly discovered optimized parameters to the JSON file."""
    profiles = load_profiles()
    
    # Create or update the ticker's profile with today's date
    profiles[ticker] = {
        "last_optimized": datetime.now().strftime("%Y-%m-%d"),
        "strategy": "Combo",
        "best_short_window": best_short,
        "best_long_window": best_long,
        "rsi_period": rsi_period
    }
    
    save_profiles(profiles)
    print(f"\n✅ Successfully updated Memory Bank for {ticker} with {best_short}/{best_long} MA.")

def run_research_cycle(tickers):
    """Scans the watchlist and re-optimizes stale stocks."""
    print("\n🔍 Starting Autonomous Research Cycle...")
    
    # Dynamically calculate a 3-year lookback window for the backtest
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    
    for ticker in tickers:
        if is_stale(ticker):
            print(f"\n⚠️ {ticker} is stale or missing. Running Optimizer...")
            
            # --- THE REAL GRID SEARCH OPTIMIZER ---
            best_short, best_long = run_optimization(ticker, start_date, end_date, strategy="Combo")
            
            if best_short is not None and best_long is not None:
                # Save the real winning parameters back to the JSON file!
                update_profile(ticker, best_short, best_long)
            else:
                print(f"\n❌ Optimization failed for {ticker}. Skipping update.")
                
        else:
            print(f"\n✨ {ticker} is fresh. No optimization needed.")
    print("\n🔍 Research Cycle Completed.")
    return "Research cycle completed."

if __name__ == "__main__":
    # The same watchlist the Live Controller uses
   # Updated list in engine/researcher.py
    master_watchlist = [
    "NVDA", "AAPL", "MSFT", "TSLA", "AMZN", "META",
    "GOOGL", "NFLX", "AMD", "SMCI", "GLD", "PLTR", # Originals
    "ORCL", "CRWV", "JPM", "WMT", "LLY", "AVGO",
    "MU", "V", "COST", "CRWD", "AIQ", "QQQ" # The Expansion Pack
    ]
    run_research_cycle(master_watchlist)