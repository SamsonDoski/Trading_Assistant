import os
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.profile_manager import load_profiles, save_profiles, is_stale
from research.run_optimizer import run_optimization, select_best_mode


def update_profile(ticker, best_short, best_long, rsi_period=14):
    """Saves newly discovered optimized parameters. MERGES into the existing
    profile so V5 fields (best_mode / best_windows) survive a legacy re-run."""
    profiles = load_profiles()
    profile = dict(profiles.get(ticker, {}))
    profile.update({
        "last_optimized": datetime.now().strftime("%Y-%m-%d"),
        "strategy": "Combo",
        "best_short_window": best_short,
        "best_long_window": best_long,
        "rsi_period": rsi_period,
    })
    profiles[ticker] = profile
    save_profiles(profiles)
    print(f"\n✅ Updated Memory Bank for {ticker} with {best_short}/{best_long} MA.")


def update_mode_research(ticker, best_mode, records):
    """Store per-mode research: the winning mode plus each mode's best windows.
    Additive — legacy fields stay intact so Swing resolves exactly as today."""
    profiles = load_profiles()
    profile = dict(profiles.get(ticker, {}))
    best_windows = dict(profile.get("best_windows", {}))
    mode_scores = {}
    for name, r in records.items():
        best_windows[name] = {"short": r["short"], "long": r["long"]}
        mode_scores[name] = {"score": round(r["score"], 4),
                             "return_pct": round(r["return_pct"], 2),
                             "max_dd_pct": round(r["max_dd_pct"], 2)}
    profile.update({
        "last_optimized": datetime.now().strftime("%Y-%m-%d"),
        "strategy": "Combo",
        "best_mode": best_mode,
        "best_windows": best_windows,
        "mode_scores": mode_scores,
    })
    profiles[ticker] = profile
    save_profiles(profiles)
    print(f"\n✅ {ticker}: best_mode={best_mode} "
          f"({best_windows[best_mode]['short']}/{best_windows[best_mode]['long']})")


def run_research_cycle(tickers, per_mode=False, force=False):
    """Scans the watchlist and re-optimizes stale stocks.
    per_mode=False -> legacy mode-agnostic grid search (unchanged V4 behavior).
    per_mode=True  -> search every mode's own window family and record the winner.
    force=True     -> ignore freshness and re-research every ticker."""
    print("\n🔍 Starting Autonomous Research Cycle"
          f"{' (per-mode)' if per_mode else ''}{' [FORCED]' if force else ''}...")

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")

    for ticker in tickers:
        if not force and not is_stale(ticker):
            print(f"\n✨ {ticker} is fresh. No optimization needed.")
            continue

        print(f"\n⚠️ {ticker} is stale or missing. Running Optimizer...")
        if per_mode:
            best_mode, records = select_best_mode(ticker, start_date, end_date)
            if best_mode:
                update_mode_research(ticker, best_mode, records)
            else:
                print(f"\n❌ Per-mode optimization failed for {ticker}. Skipping update.")
        else:
            best_short, best_long = run_optimization(ticker, start_date, end_date,
                                                     strategy="Combo")
            if best_short is not None and best_long is not None:
                update_profile(ticker, best_short, best_long)
            else:
                print(f"\n❌ Optimization failed for {ticker}. Skipping update.")

    print("\n🔍 Research Cycle Completed.")
    return "Research cycle completed."


if __name__ == "__main__":
    import argparse
    master_watchlist = [
        "NVDA", "AAPL", "MSFT", "TSLA", "AMZN", "META",
        "GOOGL", "NFLX", "AMD", "SMCI", "GLD", "PLTR",
        "ORCL", "CRWV", "JPM", "WMT", "LLY", "AVGO",
        "MU", "V", "COST", "CRWD", "AIQ", "QQQ"
    ]
    parser = argparse.ArgumentParser(description="Autonomous research cycle")
    parser.add_argument("--modes", action="store_true", help="Per-mode research")
    parser.add_argument("--force", action="store_true",
                        help="Re-research every ticker, ignoring freshness")
    args = parser.parse_args()

    run_research_cycle(master_watchlist, per_mode=args.modes, force=args.force)