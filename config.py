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
# Risk Management
# -----------------
TRAILING_STOP_PERCENT = 15.0  # Broker-side trailing stop; also the hard stop at entry (15% below fill)

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


# -----------------
# Sentiment (V4)
# -----------------
# "shadow": compute + report verdicts on fresh buys, but size at 1.0x and never veto.
# "live":   apply the multiplier to position size and honor vetoes.
SENTIMENT_MODE = "shadow"

# -----------------
# Capital Policy
# -----------------
CASH_RESERVE_PCT = 0.15   # fraction of buying power always held back as cash