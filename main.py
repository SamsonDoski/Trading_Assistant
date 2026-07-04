import argparse
from datetime import datetime, timedelta
from research.backtest import BacktestEngine
import os
import config
from utils.data_loader import fetch_data
from strategies.moving_average import apply_moving_average_strategy
from strategies.rsi import apply_rsi_strategy
from strategies.ma_rsi_combo import apply_combo_strategy
from utils.visualize1 import plot_ma_signals as plot_ma
from utils.visualize1 import plot_rsi_signals as plot_rsi
from utils.visualize1 import plot_combo_signals as plot_combo
from strategy_config import get_profile

def main():
    # CLI argument parser
    parser = argparse.ArgumentParser(description="Risk-Adjusted MA Strategy Backtester")
    parser.add_argument("--profile", type=str, default="Swing", help="Trade profile to use (Aggressive, Swing, Long_Term, Volatile)")
    parser.add_argument("--ticker", type=str, default=config.DEFAULT_TICKER, help="Stock ticker symbol")
    parser.add_argument("--start", type=str, default=config.START_DATE, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=config.END_DATE, help="End date (YYYY-MM-DD)")
    parser.add_argument("--equity", type=float, default=config.INITIAL_EQUITY, help="Initial equity for backtest")
    parser.add_argument("--strategy", type=str, default="MA", help="Which strategy to run (MA, RSI, or Combo)")
    args = parser.parse_args()

    ticker = args.ticker.upper()



    # Fetch data
    # requested start date formatted to datetime 
    requested_start = datetime.strptime(args.start, "%Y-%m-%d")

    # fetches data for buffer and MA warm up for 730 days before requested date.
    df = fetch_data(ticker, start=(requested_start - timedelta(days=730)).strftime("%Y-%m-%d"), end=args.end)
    if df.empty:
        print(f"[ERROR] No data found for {ticker} in the given date range.")
        return

    # Apply strategy
    # Fetch the correct settings based on the CLI input
    profile_settings = get_profile(args.profile)
    
    # Pass those dynamic settings into our strategy
    if args.strategy == "MA":
        df = apply_moving_average_strategy(
            df, 
            short_window=profile_settings["short_window"], 
            long_window=profile_settings["long_window"], 
            stop_loss_pct=profile_settings["stop_loss_pct"]
        )

    elif args.strategy == "RSI":
        df = apply_rsi_strategy(
            df,
            rsi_window=profile_settings["rsi_window"],
            overbought=profile_settings["overbought"],
            oversold=profile_settings["oversold"],
            stop_loss_pct=profile_settings["stop_loss_pct"]
        )

    elif args.strategy == "Combo":
        df = apply_combo_strategy(
            df,
            short_window=profile_settings["short_window"],
            long_window=profile_settings["long_window"],
            rsi_window=profile_settings["rsi_window"],
            overbought=profile_settings["overbought"],
            oversold=profile_settings["oversold"],
            stop_loss_pct=profile_settings["stop_loss_pct"]
        )


    # --- NEW: THE GHOST TRADE FIX ---
    # 1. Flagging the exact days a FRESH buy signal happens (Transition from 0 to 1)
    # Because we calculate this on df_test, it uses the runway data to check yesterday's signal perfectly.
    df['Buy_Trigger'] = (df['Signal'] == 1) & (df['Signal'].shift(1) == 0)
    
    # --- THE SLICE ---
    df_trading_window = df.loc[args.start : args.end].copy()
    
    # 2. Wipe out ongoing trades from the past. 
    # If the cumulative sum of fresh Buy_Triggers is 0, a new trade hasn't officially started yet.
    df_trading_window.loc[df_trading_window['Buy_Trigger'].cumsum() == 0, 'Signal'] = 0

    # Run backtest
    engine = BacktestEngine(initial_equity=args.equity)
    df_bt = engine.run(df_trading_window)
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
    # --- VISUALIZATION SWITCHBOARD ---
    if args.strategy == "MA":
        # Only try to plot MAs if we actually ran the MA strategy
        plot_ma(df_bt, ticker) 
    elif args.strategy == "RSI":
        # Only try to plot RSI if we actually ran the RSI strategy
        plot_rsi(df_bt, ticker)
    elif args.strategy == "Combo":
        # Only try to plot combo signals if we actually ran the Combo strategy
        plot_combo(df_bt, ticker)

if __name__ == "__main__":
    main()


# Good job! The main.py file is well-structured and integrates the data loading, strategy application,
# backtesting, and visualization components effectively. 
# The use of argparse allows for flexible command-line interaction, making it easy to
# specify different tickers, date ranges, and initial equity. The backtest summary is printed in a clean 
# format, and results are saved to a CSV file for further analysis. The plotting function provides a visual 
# representation of the strategy's signals, enhancing the overall user experience. 
