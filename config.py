# config.py
import os

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
SENTIMENT_MODE = "live"

# -----------------
# Capital Policy
# -----------------
CASH_RESERVE_PCT = 0.15   # fraction of buying power always held back as cash

# -----------------
# Position Sizing (V4.1 — equal-weight, small-account aware)
# -----------------
# Deployable capital is split equally across every watchlist name NOT currently
# held:  base_allocation_usd = usable_budget_usd / not_held_count.
# The sentiment conviction_multiplier then scales that slice. There is NO flat
# cap — this auto-scales from a $400 account to a $1M account. When a slice is
# worth less than one whole share, the allocator falls back to a fractional buy.
ALLOW_FRACTIONAL = True

# Skip a fractional buy whose dollar size is below this — avoids buying dust.
MIN_FRACTIONAL_NOTIONAL_USD = 1.00

# -----------------
# Active Trading Mode (V5.0)
# -----------------
# "V4_Legacy" | "Aggressive" | "Swing" | "Long_Term" | "Volatile" | "Auto"
# Read from the environment so the Lambda can switch modes WITHOUT a redeploy.
# "V4_Legacy" == deployed V4.0 behavior (legacy free-searched per-ticker windows)
# — the safe rollback value. NOTE "Swing" is a preset with its own grid, NOT V4.0.
ACTIVE_MODE = os.getenv("ACTIVE_MODE", "V4_Legacy")