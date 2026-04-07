import pandas as pd
import itertools
import argparse
from utils.data_loader import fetch_data
from strategies.ma_rsi_combo import apply_combo_strategy
from strategies.moving_average import apply_moving_average_strategy
from engine.backtest import BacktestEngine

def run_optimization(ticker, start_date, end_date, strategy="Combo", initial_equity=10000.0):
    print(f"\n⚙️ Starting {strategy} Optimizer for {ticker.upper()}...")
    
    # 1. Fetch Data
    df_raw = fetch_data(ticker, start_date, end_date)
    if df_raw.empty:
        print("Data fetch failed.")
        return None, None # <-- RETURN NONE IF FAILED

    # 2. Define the Grid
    short_mas = [5, 10, 20, 30, 40, 50]
    long_mas = [10, 30, 50, 100, 150, 200, 250, 300, 350, 400]
    
    combinations = list(itertools.product(short_mas, long_mas))
    results = []
    print(f"🧪 Testing {len(combinations)} different Moving Average combinations...\n")

    # 3. The Optimization Loop
    for short_ma, long_ma in combinations:
        if short_ma >= long_ma:
            continue
            
        df_test = df_raw.copy()
        
        # --- STRATEGY SWITCHBOARD ---
        if strategy == "Combo":
            df_test = apply_combo_strategy(
                df_test,
                short_window=short_ma,
                long_window=long_ma,
                rsi_window=14,
                overbought=70,
                oversold=30,
                stop_loss_pct=-0.15 
            )
        elif strategy == "MA":
            df_test = apply_moving_average_strategy(
                df_test,
                short_window=short_ma,
                long_window=long_ma,
                stop_loss_pct=-0.15
            )
        else:
            print(f"Strategy {strategy} not supported for this grid.")
            return None, None # <-- RETURN NONE IF FAILED
        
        # 4. Run Backtest
        engine = BacktestEngine(initial_equity=initial_equity)
        df_bt = engine.run(df_test)
        
        final_equity = df_bt['Equity'].iloc[-1]
        total_return = (final_equity - initial_equity) / initial_equity
        
        roll_max = df_bt['Equity'].cummax()
        drawdown = (df_bt['Equity'] / roll_max) - 1.0
        max_drawdown = drawdown.min()
        
        score = 0 if max_drawdown == 0 else (total_return / abs(max_drawdown))
            
        results.append({
            "Short MA": short_ma,
            "Long MA": long_ma,
            "Return (%)": total_return * 100,
            "Max DD (%)": max_drawdown * 100,
            "Score": score
        })

    # 5. Rank the Results
    if not results:
        return None, None
        
    results_df = pd.DataFrame(results)
    # Will stick to 'Return (%)' for now!
    results_df = results_df.sort_values(by="Return (%)", ascending=False).reset_index(drop=True)
    
    print(f"🏆 TOP 5 PARAMETER SETTINGS FOR {ticker.upper()} ({start_date} to {end_date}) | Strategy: {strategy}:")
    print("-" * 75)
    print(results_df.head(5).to_string(index=False, float_format="%.2f"))
    print("-" * 75)
    
    # --- NEW V3 LOGIC: GRAB THE #1 WINNER AND RETURN IT ---
    best_short = int(results_df.iloc[0]["Short MA"])
    best_long = int(results_df.iloc[0]["Long MA"])
    
    return best_short, best_long

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimize Trading Strategies")
    parser.add_argument("--ticker", type=str, required=True, help="Ticker to optimize")
    parser.add_argument("--start", type=str, default="2020-01-01", help="Start Date")
    parser.add_argument("--end", type=str, default="2024-01-01", help="End Date")
    parser.add_argument("--strategy", type=str, default="Combo", choices=["Combo", "MA"], help="Which strategy to optimize")
    args = parser.parse_args()
    
    # It still works manually from the terminal!
    run_optimization(args.ticker, args.start, args.end, strategy=args.strategy)