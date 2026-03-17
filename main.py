import argparse
import os
import config
from utils.data_loader import fetch_data
from strategies.moving_average import apply_moving_average_strategy
from utils.visualize1 import plot_ma_signals as plot
from engine.backtest import BacktestEngine

def main():
    # CLI argument parser
    parser = argparse.ArgumentParser(description="Risk-Adjusted MA Strategy Backtester")
    parser.add_argument("--ticker", type=str, default=config.DEFAULT_TICKER, help="Stock ticker symbol")
    parser.add_argument("--start", type=str, default=config.START_DATE, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=config.END_DATE, help="End date (YYYY-MM-DD)")
    parser.add_argument("--equity", type=float, default=config.INITIAL_EQUITY, help="Initial equity for backtest")
    args = parser.parse_args()

    ticker = args.ticker.upper()

    # Fetch data
    df = fetch_data(ticker, start=args.start, end=args.end)
    if df.empty:
        print(f"[ERROR] No data found for {ticker} in the given date range.")
        return

    # Apply strategy
    df = apply_moving_average_strategy(df, short_window=config.SHORT_MA, long_window=config.LONG_MA)

    # Run backtest
    engine = BacktestEngine(initial_equity=args.equity)
    df_bt = engine.run(df)
    summary = engine.summary(df_bt)

    # Print summary in a clean format
    print(f"\n📊 Backtest Summary for {ticker}:")
    for k, v in summary.items():
        print(f"{k}: {v}")

    # Ensure results directory exists
    os.makedirs(config.RESULTS_DIR, exist_ok=True)

    # Save results
    results_path = os.path.join(config.RESULTS_DIR, f"{ticker}_backtest.csv")
    df_bt.to_csv(results_path, index=False)
    print(f"\n✅ Results saved to {results_path}")

    # Plot signals
    plot(df, ticker)

if __name__ == "__main__":
    main()
