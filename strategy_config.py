# strategy_congig.py
# This file is intended to hold any configuration parameters related to the strategy itself.
# For example, if we want to easily adjust the short and long moving average windows or the stop loss percentage,
# we can define them here and import them into main.py or the strategy file.
# Moving Average Windows

PROFILES = {
    "Aggressive": {
        "short_window": 10,
        "long_window": 30,
        "stop_loss_pct": -0.05
    },
    "Swing": {
        "short_window": 20,
        "long_window": 50,
        "stop_loss_pct": -0.08
    },
    "Long-Term": {
        "short_window": 50,
        "long_window": 200,
        "stop_loss_pct": -0.15
    },
    "Volatile": {
        "short_window": 15,
        "long_window": 40,
        "stop_loss_pct": -0.12
    }

}

def get_profile(profile_name):
    '''Returns the strategy parameters for the given trade profile.'''
    return PROFILES.get(profile_name, PROFILES["Swing"])  # Default  to "Swing" if profile not found