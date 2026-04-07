import json
import os
from datetime import datetime, timedelta

# Pointing to your new folder and file name!
PROFILE_FILE = "memory/stock_profile.json"

def load_profiles():
    """Loads the stock profiles JSON file."""
    if not os.path.exists(PROFILE_FILE):
        return {}
    with open(PROFILE_FILE, "r") as file:
        return json.load(file)

def save_profiles(data):
    """Saves the updated dictionary back to the JSON file."""
    with open(PROFILE_FILE, "w") as file:
        json.dump(data, file, indent=4)
    print("Stock profiles updated successfully.")

def is_stale(ticker, days_limit=90):
    """
    Checks if a stock needs to be re-optimized.
    Returns True if stale or missing, False if fresh.
    """
    profiles = load_profiles()
    
    # If the bot has never seen this stock before, it's definitely stale
    if ticker not in profiles:
        return True
        
    last_opt_str = profiles[ticker].get("last_optimized")
    if not last_opt_str:
        return True
        
    # Convert string to datetime object
    last_opt_date = datetime.strptime(last_opt_str, "%Y-%m-%d")
    expiration_date = datetime.now() - timedelta(days=days_limit)
    
    # If the last optimization is older than 90 days
    return last_opt_date < expiration_date