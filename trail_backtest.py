"""
Ad-hoc backtest: 8% vs 10% vs 15% trailing stop, on the live combo signals.

Entry: fresh crossover (Signal 0->1), same edge the live bot buys on.
Exit:  whichever comes first —
         (a) trend death (combo Signal -> 0, i.e. MA cross-down), or
         (b) trailing stop = peak-High-since-entry * (1 - trail%), checked
             against each day's Low (gap-through fills at that day's Open).
The combo's built-in -15% hard stop is DISABLED (stop_loss_pct=-0.99) so the
trailing stop is the only price-based exit being measured.

Not in the repo — a throwaway analysis script. Run: python trail_backtest.py
"""
import numpy as np
import pandas as pd

from utils.data_loader import fetch_data
from utils.profile_manager import load_profiles
from strategies.ma_rsi_combo import apply_combo_strategy

START = "2020-01-01"
END = pd.Timestamp.today().strftime("%Y-%m-%d")
TRAILS = [8.0, 10.0, 15.0]


def simulate(df, trail_pct):
    """Return list of (trade_return, peak_gain) for one ticker at one trail%."""
    trail = trail_pct / 100.0
    close = df["Close"].to_numpy(float)
    high = df["High"].to_numpy(float) if "High" in df else close
    low = df["Low"].to_numpy(float) if "Low" in df else close
    op = df["Open"].to_numpy(float) if "Open" in df else close
    sig = df["Signal"].to_numpy(float)

    trades, in_pos, entry, peak = [], False, 0.0, 0.0
    for i in range(1, len(df)):
        if not in_pos:
            if sig[i] == 1 and sig[i - 1] == 0:      # fresh crossover
                in_pos, entry, peak = True, close[i], high[i]
        else:
            peak = max(peak, high[i])
            stop = peak * (1 - trail)
            if low[i] <= stop:                        # trailing stop hit intraday
                exit_px = stop if op[i] > stop else op[i]   # gap-through -> fill at open
                trades.append(((exit_px - entry) / entry, (peak - entry) / entry))
                in_pos = False
            elif sig[i] == 0:                         # trend death
                trades.append(((close[i] - entry) / entry, (peak - entry) / entry))
                in_pos = False
    if in_pos:                                        # mark open trade to last close
        trades.append(((close[-1] - entry) / entry, (peak - entry) / entry))
    return trades


def main():
    profiles = load_profiles()
    if not profiles:
        print("No profiles found — nothing to backtest.")
        return

    all_trades = {t: [] for t in TRAILS}   # trail% -> list of (ret, peak_gain)
    per_ticker_mult = {t: [] for t in TRAILS}  # trail% -> ending equity multiple per ticker
    bh_returns = []
    used = 0

    for ticker, rules in profiles.items():
        short = rules["best_short_window"]
        long = rules["best_long_window"]
        rsi = rules.get("rsi_period", 14)

        df = fetch_data(ticker, start=START, end=END)
        if df.empty or len(df) < long + 50:
            print(f"skip {ticker}: insufficient data ({len(df)} bars)")
            continue

        # Pure-trend signal: disable the built-in hard stop so we isolate the trail.
        df = apply_combo_strategy(df.copy(), short_window=short, long_window=long,
                                  rsi_window=rsi, stop_loss_pct=-0.99)
        used += 1
        bh_returns.append(df["Close"].iloc[-1] / df["Close"].iloc[0] - 1)

        for t in TRAILS:
            trades = simulate(df, t)
            all_trades[t].extend(trades)
            mult = np.prod([1 + r for r, _ in trades]) if trades else 1.0
            per_ticker_mult[t].append(mult)

    if not used:
        print("No tickers had enough data.")
        return

    print(f"\n=== Trailing-Stop Backtest ===")
    print(f"Window: {START} -> {END} | Tickers used: {used}")
    print(f"Entry = fresh crossover; exit = trend-death OR trailing stop.\n")
    hdr = f"{'Trail':>6} {'Trades':>7} {'Win%':>6} {'AvgTrade':>9} {'MedTrade':>9} " \
          f"{'AvgPeak':>8} {'GiveBack':>9} {'AvgEqX':>7} {'MedEqX':>7} {'WorstTrade':>11}"
    print(hdr)
    print("-" * len(hdr))
    for t in TRAILS:
        rets = np.array([r for r, _ in all_trades[t]])
        peaks = np.array([p for _, p in all_trades[t]])
        if len(rets) == 0:
            print(f"{t:>5.0f}% (no trades)")
            continue
        win = (rets > 0).mean()
        giveback = (peaks - rets).mean()          # avg unrealized peak surrendered
        mults = np.array(per_ticker_mult[t])
        print(f"{t:>5.0f}% {len(rets):>7d} {win:>6.1%} {rets.mean():>9.2%} "
              f"{np.median(rets):>9.2%} {peaks.mean():>8.2%} {giveback:>9.2%} "
              f"{mults.mean():>6.2f}x {np.median(mults):>6.2f}x {rets.min():>11.2%}")

    bh = np.array(bh_returns)
    print(f"\nBuy & Hold baseline over the same window: "
          f"avg per-ticker {bh.mean():+.1%} | median {np.median(bh):+.1%}")
    print("\nReading it: lower GiveBack = tighter trail keeps more of the peak, but watch\n"
          "AvgEqX/Win% — if a tighter stop whipsaws you out of the big trends, total\n"
          "equity drops even though give-back improves. Compare AvgEqX across rows,\n"
          "and all three against Buy & Hold.")


if __name__ == "__main__":
    main()
