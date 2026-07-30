import os
import sys
import pandas as pd
import itertools
import argparse
from datetime import datetime, timedelta

# Force Python to recognize the parent directory (trading_assistant) as the root
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.append(parent_dir)

from utils.data_loader import fetch_data
from strategies.ma_rsi_combo import apply_combo_strategy
from strategies.moving_average import apply_moving_average_strategy
from research.backtest import BacktestEngine
from engine.modes import TRADING_MODES, MODE_GRIDS, DEFAULT_MODE

# Legacy grid (mode-agnostic, unchanged) used when no mode grid is supplied.
LEGACY_SHORT_MAS = [5, 10, 20, 30, 40, 50]
LEGACY_LONG_MAS = [10, 30, 50, 100, 150, 200, 250, 300, 350, 400]


def _strategy_kwargs(settings):
    """Strategy params for one mode. None -> the legacy V4 defaults, so existing
    callers keep their exact behavior."""
    if settings is None:
        return dict(rsi_window=14, rsi_buy_threshold=55, sell_on_overbought=False,
                    rsi_sell_threshold=70, stop_loss_pct=-0.15)
    return dict(rsi_window=settings.rsi_window,
                rsi_buy_threshold=settings.rsi_buy_threshold,
                sell_on_overbought=settings.sell_on_overbought,
                rsi_sell_threshold=settings.rsi_sell_threshold,
                stop_loss_pct=settings.signal_stop_loss_pct)


def _fetch_with_runway(ticker, start_date, end_date, runway_days=730):
    """Padded fetch so long indicators are warm before the trading window opens."""
    requested_start = datetime.strptime(start_date, "%Y-%m-%d")
    fetch_start = (requested_start - timedelta(days=runway_days)).strftime("%Y-%m-%d")
    return fetch_data(ticker, start=fetch_start, end=end_date)


def evaluate_window(df_raw, short_ma, long_ma, start_date, end_date,
                    settings=None, strategy="Combo", initial_equity=10000.0):
    """Backtest ONE parameter pair over one window. Returns a metrics dict, or
    None if the window is unusable."""
    df_test = df_raw.copy()
    if strategy == "Combo":
        df_test = apply_combo_strategy(df_test, short_window=short_ma, long_window=long_ma,
                                       **_strategy_kwargs(settings))
    elif strategy == "MA":
        df_test = apply_moving_average_strategy(df_test, short_window=short_ma,
                                                long_window=long_ma, stop_loss_pct=-0.15)
    else:
        return None

    # Ghost-trade fix: only count trades that OPEN inside the trading window.
    df_test["Buy_Trigger"] = (df_test["Signal"] == 1) & (df_test["Signal"].shift(1) == 0)
    window = df_test.loc[start_date:end_date].copy()
    if window.empty:
        return None
    window.loc[window["Buy_Trigger"].cumsum() == 0, "Signal"] = 0

    df_bt = BacktestEngine(initial_equity=initial_equity).run(window)
    final_equity = df_bt["Equity"].iloc[-1]
    total_return = (final_equity - initial_equity) / initial_equity
    roll_max = df_bt["Equity"].cummax()
    max_drawdown = ((df_bt["Equity"] / roll_max) - 1.0).min()
    # Floor the divisor so a zero-drawdown run isn't scored 0 (mode ranking uses Score).
    score = total_return / max(abs(max_drawdown), 0.01)

    return {"Short MA": short_ma, "Long MA": long_ma,
            "Return (%)": total_return * 100,
            "Max DD (%)": max_drawdown * 100,
            "Score": score}


def grid_search(ticker, start_date, end_date, settings=None, strategy="Combo",
                short_mas=None, long_mas=None, initial_equity=10000.0,
                rank_by="Return (%)", df_raw=None, verbose=True):
    """Search a window grid and return the ranked results DataFrame (or None)."""
    if df_raw is None:
        df_raw = _fetch_with_runway(ticker, start_date, end_date)
    if df_raw is None or df_raw.empty:
        if verbose:
            print("Data fetch failed.")
        return None

    short_mas = short_mas or LEGACY_SHORT_MAS
    long_mas = long_mas or LEGACY_LONG_MAS
    combos = [(s, l) for s, l in itertools.product(short_mas, long_mas) if s < l]
    if verbose:
        print(f"🧪 Testing {len(combos)} Moving Average combinations...\n")

    results = []
    for short_ma, long_ma in combos:
        row = evaluate_window(df_raw, short_ma, long_ma, start_date, end_date,
                              settings=settings, strategy=strategy,
                              initial_equity=initial_equity)
        if row is not None:
            results.append(row)

    if not results:
        return None
    return (pd.DataFrame(results)
            .sort_values(by=rank_by, ascending=False)
            .reset_index(drop=True))


def run_optimization(ticker, start_date, end_date, strategy="Combo",
                     initial_equity=10000.0, settings=None,
                     short_mas=None, long_mas=None, rank_by="Return (%)"):
    """LEGACY entry point (unchanged contract): returns (best_short, best_long),
    or (None, None) on failure. Defaults reproduce the V4 mode-agnostic search."""
    print(f"\n⚙️ Starting {strategy} Optimizer for {ticker.upper()}...")
    results_df = grid_search(ticker, start_date, end_date, settings=settings,
                             strategy=strategy, short_mas=short_mas, long_mas=long_mas,
                             initial_equity=initial_equity, rank_by=rank_by)
    if results_df is None:
        return None, None

    print(f"🏆 TOP 5 PARAMETER SETTINGS FOR {ticker.upper()} "
          f"({start_date} to {end_date}) | Strategy: {strategy}:")
    print("-" * 75)
    print(results_df.head(5).to_string(index=False, float_format="%.2f"))
    print("-" * 75)
    return int(results_df.iloc[0]["Short MA"]), int(results_df.iloc[0]["Long MA"])


def optimize_for_mode(ticker, mode_name, start_date, end_date,
                      initial_equity=10000.0, df_raw=None, verbose=True):
    """Grid-search ONE mode inside its own window family, ranked by risk-adjusted
    score. Returns {'short','long','score','return_pct','max_dd_pct'} or None."""
    settings = TRADING_MODES.get(mode_name)
    if settings is None or mode_name not in MODE_GRIDS:
        return None
    short_mas, long_mas = MODE_GRIDS[mode_name]
    results_df = grid_search(ticker, start_date, end_date, settings=settings,
                             short_mas=short_mas, long_mas=long_mas,
                             initial_equity=initial_equity, rank_by="Score",
                             df_raw=df_raw, verbose=verbose)
    if results_df is None:
        return None
    top = results_df.iloc[0]
    return {"short": int(top["Short MA"]), "long": int(top["Long MA"]),
            "score": float(top["Score"]), "return_pct": float(top["Return (%)"]),
            "max_dd_pct": float(top["Max DD (%)"])}


def select_best_mode(ticker, start_date, end_date, initial_equity=10000.0, verbose=True):
    """Grid-search every mode in its own window family over the SAME period, rank
    by risk-adjusted score, and return (best_mode_name, {mode: record})."""
    df_raw = _fetch_with_runway(ticker, start_date, end_date)
    if df_raw is None or df_raw.empty:
        return None, {}

    records = {}
    for mode_name in MODE_GRIDS:
        record = optimize_for_mode(ticker, mode_name, start_date, end_date,
                                   initial_equity=initial_equity,
                                   df_raw=df_raw, verbose=False)
        if record:
            records[mode_name] = record

    if not records:
        return None, {}

    best = max(records, key=lambda m: records[m]["score"])
    if verbose:
        print(f"\n🏆 Best mode for {ticker}: {best}")
        for name, r in sorted(records.items(), key=lambda kv: -kv[1]["score"]):
            print(f"   {name:<11} {r['short']:>3}/{r['long']:<4} "
                  f"score {r['score']:>7.2f} | return {r['return_pct']:>8.2f}% "
                  f"| maxDD {r['max_dd_pct']:>7.2f}%")
    return best, records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimize Trading Strategies")
    parser.add_argument("--ticker", type=str, required=True, help="Ticker to optimize")
    parser.add_argument("--start", type=str, default="2020-01-01", help="Start Date")
    parser.add_argument("--end", type=str, default="2024-01-01", help="End Date")
    parser.add_argument("--strategy", type=str, default="Combo", choices=["Combo", "MA"])
    parser.add_argument("--modes", action="store_true",
                        help="Per-mode search: pick the best mode for this ticker")
    args = parser.parse_args()

    if args.modes:
        select_best_mode(args.ticker.upper(), args.start, args.end)
    else:
        run_optimization(args.ticker, args.start, args.end, strategy=args.strategy)