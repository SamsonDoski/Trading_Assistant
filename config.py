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

# -----------------
# Brokerage Endpoint
# -----------------
# Which Alpaca environment the ALPACA_API_KEY/SECRET belong to.
# Defaults to PAPER: going live must be an explicit, deliberate opt-in
# (set ALPACA_PAPER=false), never something a missing variable can cause.
# Paper and live keys are not interchangeable — a mismatch fails to authenticate.
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").strip().lower() not in ("false", "0", "no")

# -----------------
# Kill Switch
# -----------------
# Manual freeze on OPENING new positions. Set TRADING_HALTED=true to stop the bot
# buying, effective on the next run, with no redeploy.
#
# This is deliberately surgical: sells, stop attachment and stop-out reporting all
# KEEP RUNNING while it is on. Disabling the EventBridge schedules would stop those
# too — i.e. it would switch off your safety systems in the exact situation where
# you want them most. Halting buys is the correct emergency action.
#
# Defaults to NOT halted: a missing or garbled variable must never silently freeze
# trading. When it IS on, every run announces it loudly so it can't be forgotten.
# NOTE: with parallel accounts this must be set on EACH Lambda function separately.
TRADING_HALTED = os.getenv("TRADING_HALTED", "false").strip().lower() in ("true", "1", "yes", "on")