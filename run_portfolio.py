# run_portfolio.py
import argparse
from engine.portfolio import PortfolioSimulator

def main():
    # CLI argument parser for the portfolio
    parser = argparse.ArgumentParser(description="Multi-Ticker Portfolio Simulation")
    # nargs='+' allows us to pass a space-separated list of tickers!
    parser.add_argument("--tickers", nargs='+', default=["AAPL", "MSFT", "NVDA", "JNJ", "XOM"], help="List of ticker symbols")
    parser.add_argument("--start", type=str, default="2020-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2024-01-01", help="End date (YYYY-MM-DD)")
    parser.add_argument("--equity", type=float, default=100000.0, help="Initial portfolio equity")
    parser.add_argument("--profile", type=str, default="Swing", help="Trade profile to use (Aggressive, Swing, Long_Term, Volatile)")
    args = parser.parse_args()

    # Initialize the Simulator
    simulator = PortfolioSimulator(
        tickers=args.tickers,
        start_date=args.start,
        end_date=args.end,
        initial_equity=args.equity,
        profile=args.profile
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

if __name__ == "__main__":
    main()