"""
Phase 6 validation gate: is ANY trading mode better than what we run today?

Applies each mode to the WHOLE watchlist and compares them head to head:
  V4_Legacy  - deployed V4.0 behavior: flat per-ticker windows, 15% trailing
               stop, single entry, -0.15 signal stop. The incumbent.
  Aggressive
  Swing      - each preset forced across all tickers, using that mode's own
  Long_Term    researched windows from best_windows[mode].
  Volatile
  Auto       - each ticker's researched best_mode (the mixed assignment).
  Buy & Hold - the baseline every config must beat.

Settings come from the REAL ModeResolver and signals from the REAL
apply_combo_strategy, so this exercises the shipping resolution logic rather
than a reimplementation of it.

Entry: fresh crossover (Signal 0->1), same edge the live bot buys on.
Exit:  whichever comes first —
         (a) trend reversal (Signal -> 0), when exit_on_trend_reversal is set, or
         (b) the mode's trailing stop = peak-High-since-entry * (1 - trail%),
             tested against each bar's Low (a gap-through fills at that bar's
             Open). Modes with trailing_stop_percent=None exit on signal only.

Drawdown is measured on a DAILY MARK-TO-MARKET equity curve, so it includes
how far underwater an open position went — not just realized trade-to-trade
swings. This matters: a trade-level measure systematically flatters modes that
hold few, long positions (Long_Term above all).

LIMITATIONS (read before trusting the numbers):
  * yfinance research lane, not the Alpaca feed the live bot executes on.
  * Per-ticker strategy comparison only — it does NOT model sentiment sizing,
    the cash reserve, or equal-weight allocation. It answers "are this mode's
    parameters better?", not "what would the portfolio have returned?".
  * Single in-sample window; no walk-forward. Windows were themselves chosen
    by research on overlapping data, so results flatter the researched modes.
  * No commissions or slippage; higher-frequency modes are favoured accordingly.

Not part of the live path. Run: python mode_backtest.py
"""
import numpy as np
import pandas as pd

from utils.data_loader import fetch_data
from utils.profile_manager import load_profiles
from strategies.ma_rsi_combo import apply_combo_strategy
from engine.modes import ModeResolver

WINDOW_START = "2020-01-01"
WINDOW_END = pd.Timestamp.today().strftime("%Y-%m-%d")

INCUMBENT = "V4_Legacy"
CONFIGURATIONS = ["V4_Legacy", "Aggressive", "Swing", "Long_Term", "Volatile", "Auto"]
BASELINE = "Buy & Hold"
WARMUP_BARS = 50            # bars required beyond ma_long before a config is evaluable


def _column(frame, name, fallback):
    return frame[name].to_numpy(float) if name in frame else fallback


def simulate_mode(frame, settings):
    """Run one mode over one ticker.

    Returns (trade_returns, daily_equity_curve). Equity starts at 1.0 and is
    marked to market every bar, so the curve captures intra-trade drawdown.
    """
    trail_percent = settings.trailing_stop_percent
    trail_fraction = None if trail_percent is None else trail_percent / 100.0

    close = frame["Close"].to_numpy(float)
    high = _column(frame, "High", close)
    low = _column(frame, "Low", close)
    open_ = _column(frame, "Open", close)
    signal = frame["Signal"].to_numpy(float)

    realized_equity = 1.0            # equity banked from closed trades
    equity_curve = np.ones(len(frame))
    trade_returns = []
    holding, entry_price, peak_price = False, 0.0, 0.0

    for i in range(1, len(frame)):
        if not holding:
            if signal[i] == 1 and signal[i - 1] == 0:        # fresh crossover
                holding, entry_price, peak_price = True, close[i], high[i]
            equity_curve[i] = realized_equity
            continue

        peak_price = max(peak_price, high[i])
        exited = False

        if trail_fraction is not None:
            stop_price = peak_price * (1 - trail_fraction)
            if low[i] <= stop_price:                          # trailing stop hit
                # A gap through the stop fills at the open, not the stop price.
                exit_price = stop_price if open_[i] > stop_price else open_[i]
                trade_return = (exit_price - entry_price) / entry_price
                trade_returns.append(trade_return)
                realized_equity *= (1 + trade_return)
                holding, exited = False, True

        if not exited and settings.exit_on_trend_reversal and signal[i] == 0:
            trade_return = (close[i] - entry_price) / entry_price
            trade_returns.append(trade_return)
            realized_equity *= (1 + trade_return)
            holding = False

        equity_curve[i] = (realized_equity if not holding
                           else realized_equity * (close[i] / entry_price))

    if holding:                                               # mark the open trade out
        trade_returns.append((close[-1] - entry_price) / entry_price)

    return trade_returns, equity_curve


def performance(equity_curve, trade_returns):
    """Headline numbers for one ticker under one config."""
    running_peak = np.maximum.accumulate(equity_curve)
    return {
        "total_return_pct": (equity_curve[-1] - 1.0) * 100,
        "max_drawdown_pct": (equity_curve / running_peak - 1.0).min() * 100,
        "trade_count": len(trade_returns),
    }


def buy_and_hold_performance(frame):
    close = frame["Close"].to_numpy(float)
    equity_curve = close / close[0]
    return performance(equity_curve, [])


def evaluate(frame, profile, configuration):
    """Resolve the configuration's settings for this ticker and score it."""
    settings = ModeResolver(configuration).settings_for(profile)
    if len(frame) < settings.ma_long + WARMUP_BARS:
        return None
    scored = apply_combo_strategy(
        frame.copy(),
        short_window=settings.ma_short,
        long_window=settings.ma_long,
        rsi_window=settings.rsi_window,
        rsi_buy_threshold=settings.rsi_buy_threshold,
        sell_on_overbought=settings.sell_on_overbought,
        rsi_sell_threshold=settings.rsi_sell_threshold,
        stop_loss_pct=settings.signal_stop_loss_pct,
    )
    trade_returns, equity_curve = simulate_mode(scored, settings)
    result = performance(equity_curve, trade_returns)
    result["resolved_mode"] = settings.name
    result["windows"] = f"{settings.ma_short}/{settings.ma_long}"
    return result


def collect_results(profiles):
    """Score every ticker under every configuration. Tickers that cannot support
    all configurations are skipped, so every column covers the same universe."""
    per_ticker = []
    for ticker, profile in profiles.items():
        frame = fetch_data(ticker, start=WINDOW_START, end=WINDOW_END)
        if frame.empty:
            print(f"skip {ticker}: no data")
            continue

        scored = {name: evaluate(frame, profile, name) for name in CONFIGURATIONS}
        missing = [name for name, result in scored.items() if result is None]
        if missing:
            print(f"skip {ticker}: insufficient history for {', '.join(missing)}")
            continue

        scored[BASELINE] = buy_and_hold_performance(frame)
        per_ticker.append({"ticker": ticker, "results": scored})
    return per_ticker


def print_per_ticker_table(per_ticker):
    columns = CONFIGURATIONS + [BASELINE]
    header = f"{'Ticker':<8}" + "".join(f"{name:>12}" for name in columns)
    print("\nTOTAL RETURN BY TICKER (%)")
    print(header)
    print("-" * len(header))
    for row in per_ticker:
        line = f"{row['ticker']:<8}"
        for name in columns:
            line += f"{row['results'][name]['total_return_pct']:>12,.0f}"
        print(line)


def print_summary_table(per_ticker):
    columns = CONFIGURATIONS + [BASELINE]
    header = (f"{'Configuration':<14}{'Mean Return':>13}{'Median Return':>15}"
              f"{'Mean MaxDD':>12}{'Worst MaxDD':>13}{'Trades':>8}"
              f"{'Beat ' + INCUMBENT:>16}{'Beat Baseline':>15}")
    print("\n\nSUMMARY ACROSS ALL TICKERS")
    print(header)
    print("-" * len(header))

    incumbent_returns = {row["ticker"]: row["results"][INCUMBENT]["total_return_pct"]
                         for row in per_ticker}
    baseline_returns = {row["ticker"]: row["results"][BASELINE]["total_return_pct"]
                        for row in per_ticker}
    total = len(per_ticker)

    for name in columns:
        returns = np.array([row["results"][name]["total_return_pct"] for row in per_ticker])
        drawdowns = np.array([row["results"][name]["max_drawdown_pct"] for row in per_ticker])
        trades = sum(row["results"][name]["trade_count"] for row in per_ticker)
        beat_incumbent = sum(1 for row in per_ticker
                             if row["results"][name]["total_return_pct"]
                             > incumbent_returns[row["ticker"]])
        beat_baseline = sum(1 for row in per_ticker
                            if row["results"][name]["total_return_pct"]
                            > baseline_returns[row["ticker"]])
        trades_text = f"{trades:>8}" if name != BASELINE else f"{'-':>8}"
        incumbent_text = "-" if name == INCUMBENT else f"{beat_incumbent}/{total}"
        print(f"{name:<14}{returns.mean():>12,.0f}%{np.median(returns):>14,.0f}%"
              f"{drawdowns.mean():>11.1f}%{drawdowns.min():>12.1f}%{trades_text}"
              f"{incumbent_text:>16}{f'{beat_baseline}/{total}':>15}")


def print_verdict(per_ticker):
    incumbent_returns = np.array([row["results"][INCUMBENT]["total_return_pct"]
                                  for row in per_ticker])
    print("\n" + "=" * 60)
    print("GATE: promote a mode only if it beats " + INCUMBENT + " on BOTH mean and")
    print("median total return without a materially worse mean drawdown.")
    print("Check the median and the beat-count together — a single runaway winner")
    print("can carry the mean while most tickers quietly underperform.")
    print(f"\n{INCUMBENT} reference: mean {incumbent_returns.mean():,.0f}%, "
          f"median {np.median(incumbent_returns):,.0f}%")


def main():
    profiles = load_profiles()
    if not profiles:
        print("No stock profiles found — nothing to compare.")
        return

    per_ticker = collect_results(profiles)
    if not per_ticker:
        print("No tickers had enough history for every configuration.")
        return

    print(f"\n=== Mode Validation ===")
    print(f"Window: {WINDOW_START} -> {WINDOW_END} | Tickers: {len(per_ticker)}")
    print("Drawdown is daily mark-to-market (includes intra-trade depth).")

    print_per_ticker_table(per_ticker)
    print_summary_table(per_ticker)
    print_verdict(per_ticker)


if __name__ == "__main__":
    main()
