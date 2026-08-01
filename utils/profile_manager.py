import json
import math
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

def days_until_stale(profile, days_limit=90):
    """Days left before one profile expires. Negative once it already has,
    None if it carries no usable last_optimized date."""
    last_opt_str = (profile or {}).get("last_optimized")
    if not last_opt_str:
        return None
    try:
        last_opt_date = datetime.strptime(last_opt_str, "%Y-%m-%d")
    except ValueError:
        return None
    remaining = last_opt_date + timedelta(days=days_limit) - datetime.now()
    # Round UP: dates parse to midnight, so a profile expiring in a few hours
    # would otherwise report "0 days left" when "1" is what a human means.
    return math.ceil(remaining.total_seconds() / 86400)


def expiring_profiles(profiles, days_limit=90, warn_within_days=2):
    """[(ticker, days_left)] for profiles about to expire, soonest first.

    Already-expired ones are excluded — the controller reports those per ticker
    as it skips them. This is the ADVANCE warning: the whole watchlist is
    usually optimized in one batch, so it all goes stale on the same day and the
    bot stops trading entirely. Takes the loaded dict rather than re-reading the
    file per ticker."""
    upcoming = []
    for ticker, profile in (profiles or {}).items():
        days_left = days_until_stale(profile, days_limit)
        if days_left is not None and 0 <= days_left <= warn_within_days:
            upcoming.append((ticker, days_left))
    return sorted(upcoming, key=lambda pair: pair[1])


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