# engine/portfolio.py
import pandas as pd
import numpy as np
from utils.data_loader import fetch_data
from strategies.ma_rsi_combo import apply_combo_strategy
from strategies.moving_average import apply_moving_average_strategy
from strategies.rsi import apply_rsi_strategy
from research.backtest import BacktestEngine
from strategy_config import get_profile
from utils.visualize1 import plot_combo_signals, plot_ma_signals, plot_rsi_signals # Assuming these exist


class PortfolioSimulator:
    def __init__(self, tickers, start_date, end_date, initial_equity=100000.0, profile="Swing", strategy="Combo"):
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.initial_equity = initial_equity
        self.profile = profile
        self.strategy = strategy
        self.profile_settings = get_profile(profile)
        self.portfolio_data = {}

    def run_simulation(self):
        print(f"\n🚀 Starting Portfolio Simulation for: {', '.join(self.tickers)}")
        print(f"📈 Profile: {self.profile} | Strategy: {self.strategy} | Initial Equity: ${self.initial_equity:,.2f}")
        
        # 1. Split the cash evenly on Day 1
        allocated_capital = self.initial_equity / len(self.tickers)
        all_equity_curves = []

        for ticker in self.tickers:
            print(f"Processing {ticker}...")
            # 1. Fetch Data
            df = fetch_data(ticker, self.start_date, self.end_date)
            if df.empty:
                print(f"Skipping {ticker} due to missing data.")
                continue

            # 2. STRATEGY SWITCHBOARD
            if self.strategy == "MA":
                df = apply_moving_average_strategy(
                    df, 
                    short_window=self.profile_settings["short_window"], 
                    long_window=self.profile_settings["long_window"], 
                    stop_loss_pct=self.profile_settings["stop_loss_pct"]
                )
            elif self.strategy == "RSI":
                df = apply_rsi_strategy(
                    df,
                    rsi_window=self.profile_settings["rsi_window"],
                    overbought=self.profile_settings["overbought"],
                    oversold=self.profile_settings["oversold"],
                    stop_loss_pct=self.profile_settings["stop_loss_pct"]
                )
            elif self.strategy == "Combo":
                df = apply_combo_strategy(
                    df,
                    short_window=self.profile_settings["short_window"],
                    long_window=self.profile_settings["long_window"],
                    rsi_window=self.profile_settings["rsi_window"],
                    overbought=self.profile_settings["overbought"],
                    oversold=self.profile_settings["oversold"],
                    stop_loss_pct=self.profile_settings["stop_loss_pct"]
                )

           # 3. Run Backtest
            engine = BacktestEngine(initial_equity=allocated_capital)
            
            # --- THE CLONE FIX ---
            # Hand the engine a copy() so it doesn't destroy our original columns!
            df_bt = engine.run(df.copy())
            
            # Copy the newly calculated Equity column back onto our untouched original data
            df['Equity'] = df_bt['Equity']
            
            # Store the original dataframe (RSI and MAs are now safe!)
            self.portfolio_data[ticker] = df
            
            # 4. Extract just the raw dollar equity curve
            equity_curve = df['Equity']
            equity_curve.name = ticker
            all_equity_curves.append(equity_curve)

        # Combine all individual dollar curves into one giant DataFrame
        portfolio_returns_df = pd.concat(all_equity_curves, axis=1)
        
        # Calculate the Master Equity Curve by simply ADDING the bank accounts together
        portfolio_returns_df['Portfolio_Equity'] = portfolio_returns_df.sum(axis=1)
        
        return portfolio_returns_df

    def portfolio_summary(self, df_portfolio):
            """Calculates final metrics for the entire portfolio and individual stocks."""
            
            # 1. Global Portfolio Metrics
            final_equity = df_portfolio['Portfolio_Equity'].iloc[-1]
            peak_equity = df_portfolio['Portfolio_Equity'].max() # The highest the account ever reached
            total_return = (final_equity - self.initial_equity) / self.initial_equity
            
            roll_max = df_portfolio['Portfolio_Equity'].cummax()
            drawdown = df_portfolio['Portfolio_Equity'] / roll_max - 1.0
            max_drawdown = drawdown.min()

            # 2. Individual Stock Breakdown
            stock_stats = []
            best_stock = ""
            best_profit = -float('inf')

            # Calculate how much cash was actually given to each stock
            allocated_capital = self.initial_equity / len(self.tickers)
            
            for ticker, df in self.portfolio_data.items():
                # Since we passed allocated_capital to the engine, df['Equity'] is already correct!
                stock_final = df['Equity'].iloc[-1] 
                
                # Calculate profit
                stock_profit = stock_final - allocated_capital
                
                # Count exact Buy and Sell executions
                buys = ((df['Signal'] == 1) & (df['Signal'].shift(1) != 1)).sum()
                sells = ((df['Signal'] == 0) & (df['Signal'].shift(1) == 1)).sum()

                stock_stats.append(f"  • {ticker.upper():<5} | Profit: ${stock_profit:>10,.2f} | Buys: {buys:<3} | Sells: {sells:<3}")

                # Track the top performer
                if stock_profit > best_profit:
                    best_profit = stock_profit
                    best_stock = ticker.upper()

            # Format the breakdown list into a clean multi-line string
            breakdown_str = "\n" + "\n".join(stock_stats)

            # 3. Return the expanded dictionary
            return {
                "Total Portfolio Return": f"{total_return * 100:.2f}%",
                "Peak Portfolio Balance": f"${peak_equity:,.2f}",
                "Final Portfolio Balance": f"${final_equity:,.2f}",
                "Portfolio Max Drawdown": f"{max_drawdown * 100:.2f}%",
                "Top Performing Stock": f"{best_stock} (+${best_profit:,.2f})",
                "Individual Breakdown": breakdown_str
            }
        

    def visualize_results(self, ticker=None):
            """
            If ticker is provided, shows the technical breakdown for that stock.
            Otherwise, shows the total Portfolio Equity Curve.
            """        
            if ticker and ticker in self.portfolio_data:
                print(f"📊 Generating technical breakdown for {ticker}...")
                
                df_to_plot = self.portfolio_data[ticker]
                
                # Route to the correct visualizer based on the strategy!
                if self.strategy == "Combo":
                    plot_combo_signals(df_to_plot, ticker)
                elif self.strategy == "MA":
                    plot_ma_signals(df_to_plot, ticker)
                elif self.strategy == "RSI":
                    plot_rsi_signals(df_to_plot, ticker)
                    
            else:
                print("📈 Generating global portfolio performance...")
                pass