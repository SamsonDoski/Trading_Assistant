import argparse
import os
import config
from utils.data_loader import fetch_data
from strategies.moving_average import apply_moving_average_strategy
from utils.visualize1 import plot_ma_signals as plot
from engine.backtest import BacktestEngine
from strategy_config import get_profile

def main():
    # CLI argument parser
    parser = argparse.ArgumentParser(description="Risk-Adjusted MA Strategy Backtester")
    parser.add_argument("--profile", type=str, default="Swing", help="Trade profile to use (Aggressive, Swing, Long-Term, Volatile)")
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
    # Fetch the correct settings based on the CLI input
    profile_settings = get_profile(args.profile)
    
    # Pass those dynamic settings into our strategy
    df = apply_moving_average_strategy(
        df, 
        short_window=profile_settings["short_window"], 
        long_window=profile_settings["long_window"], 
        stop_loss_pct=profile_settings["stop_loss_pct"]
    )

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


## Good job! The main.py file is well-structured and integrates the data loading, strategy application, backtesting, and visualization components effectively. The use of argparse allows for flexible command-line interaction, making it easy to specify different tickers, date ranges, and initial equity. The backtest summary is printed in a clean format, and results are saved to a CSV file for further analysis. The plotting function provides a visual representation of the strategy's signals, enhancing the overall user experience.
