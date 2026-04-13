# strategy_congig.py
# This file is intended to hold any configuration parameters related to the strategy itself.
# For example, if we want to easily adjust the short and long moving average windows or the stop loss percentage,
# we can define them here and import them into main.py or the strategy file.
# Moving Average Windows

PROFILES = {
    "Aggressive": {
        "short_window": 10,
        "long_window": 30,
        "stop_loss_pct": -0.05,
        "rsi_window": 10,      # Faster RSI to catch quick swings
        "overbought": 80,      # Give it room to run
        "oversold": 20         # Wait for deep crashes
    },
    "Swing": {
        "short_window": 20,
        "long_window": 50,
        "stop_loss_pct": -0.08,
        "rsi_window": 14,      # Standard RSI
        "overbought": 70,      # Standard sell line
        "oversold": 30         # Standard buy line
    },
    "Long_Term": {
        "short_window": 50,
        "long_window": 200,
        "stop_loss_pct": -0.15,
        "rsi_window": 21,      # Slower, smoother RSI
        "overbought": 70,
        "oversold": 30
    },
    "Volatile": {  # Perfect for TSLA or NVDA
        "short_window": 15,
        "long_window": 40,
        "stop_loss_pct": -0.12,
        "rsi_window": 14,
        "overbought": 85,      # Volatile stocks stay overbought longer!
        "oversold": 25         # They also crash harder!
    }
}

def get_profile(profile_name):
    '''Returns the strategy parameters for the given trade profile.'''
    return PROFILES.get(profile_name, PROFILES["Swing"])  # Default  to "Swing" if profile not found