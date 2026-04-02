# run_portfolio.py
import argparse
import os
import config
from engine.portfolio import PortfolioSimulator

def main():
    # CLI argument parser for the portfolio
    parser = argparse.ArgumentParser(description="Multi-Ticker Portfolio Simulation")
    parser.add_argument("--tickers", nargs='+', default=["AAPL", "MSFT", "NVDA", "JNJ", "XOM"], help="List of ticker symbols")
    parser.add_argument("--start", type=str, default="2020-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2024-01-01", help="End date (YYYY-MM-DD)")
    parser.add_argument("--equity", type=float, default=100000.0, help="Initial portfolio equity")
    parser.add_argument("--profile", type=str, default="Swing", help="Trade profile to use (Aggressive, Swing, Long_Term, Volatile)")
    # ADDED THE STRATEGY FLAG HERE:
    parser.add_argument("--strategy", type=str, default="Combo", choices=["MA", "RSI", "Combo"], help="Which strategy to run")
    args = parser.parse_args()

    # Initialize the Simulator (Passing the strategy argument!)
    simulator = PortfolioSimulator(
        tickers=args.tickers,
        start_date=args.start,
        end_date=args.end,
        initial_equity=args.equity,
        profile=args.profile,
        strategy=args.strategy
    )

    # Run the Simulation
    df_portfolio = simulator.run_simulation()
    
    # Get and print the final metrics
    summary = simulator.portfolio_summary(df_portfolio)

    print("\n🏆 FINAL PORTFOLIO RESULTS:")
    print("-" * 30)
    for k, v in summary.items():
        print(f"{k}: {v}")
    print("-" * 30)

    # ... after summary is printed ...
    # Ensure results directory exists
    os.makedirs(config.RESULTS_DIR, exist_ok=True)

    
    # Example: Show the technical signals for the first ticker in the list
    print(f"\n📈 Visualizing signals for {args.tickers[0]}...")
    print("Note: Only the first ticker's signals will be visualized in this demo.")
    first_ticker = args.tickers[0]
    simulator.visualize_results(ticker=first_ticker)

    # Save results
    for ticker in args.tickers:
        results_path = os.path.join(config.RESULTS_DIR, f"{ticker}_position_test.csv")
        df_portfolio.to_csv(results_path, index=False)
        print(f"\n✅ Results saved to {results_path}")

if __name__ == "__main__":
    main()