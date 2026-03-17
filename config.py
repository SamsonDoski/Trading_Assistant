# config.py

# -----------------
# Data Fetch Settings
# -----------------
DEFAULT_TICKER = "AAPL"
START_DATE = "2022-01-01"
END_DATE = "2025-09-10"

# -----------------
# Strategy Parameters
# -----------------
SHORT_MA = 7
LONG_MA = 30

# -----------------
# Backtest Settings
# -----------------
INITIAL_EQUITY = 10000
RISK_FREE_RATE = 0.02  # Optional: for Sharpe ratio

# -----------------
# File Paths
# -----------------
DATA_DIR = "data/historical_prices"
RESULTS_DIR = "results"
