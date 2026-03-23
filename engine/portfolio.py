# engine/portfolio.py
import pandas as pd
import numpy as np
from utils.data_loader import fetch_data
from strategies.ma_rsi_combo import apply_combo_strategy
from strategies.moving_average import apply_moving_average_strategy
from strategies.rsi import apply_rsi_strategy
from engine.backtest import BacktestEngine
from strategy_config import get_profile

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
        
        all_daily_returns = []

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
            engine = BacktestEngine(initial_equity=self.initial_equity)
            df_bt = engine.run(df)
            
            # 4. Extract Daily Returns for the Portfolio
            daily_returns = df_bt['Equity'].pct_change().fillna(0)
            daily_returns.name = ticker
            all_daily_returns.append(daily_returns)

        # Combine all individual stock returns into one giant DataFrame
        portfolio_returns_df = pd.concat(all_daily_returns, axis=1)
        
        # Calculate the equally weighted daily return of the whole portfolio
        portfolio_returns_df['Portfolio_Daily_Return'] = portfolio_returns_df.mean(axis=1)

        # Calculate the Master Equity Curve
        portfolio_returns_df['Portfolio_Equity'] = self.initial_equity * (1 + portfolio_returns_df['Portfolio_Daily_Return']).cumprod()
        
        return portfolio_returns_df

    def portfolio_summary(self, df_portfolio):
        """Calculates final metrics for the entire portfolio."""
        final_equity = df_portfolio['Portfolio_Equity'].iloc[-1]
        total_return = (final_equity - self.initial_equity) / self.initial_equity
        
        # Calculate Max Drawdown for the whole portfolio
        roll_max = df_portfolio['Portfolio_Equity'].cummax()
        drawdown = df_portfolio['Portfolio_Equity'] / roll_max - 1.0
        max_drawdown = drawdown.min()

        return {
            "Total Portfolio Return": f"{total_return * 100:.2f}%",
            "Final Portfolio Balance": f"${final_equity:,.2f}",
            "Portfolio Max Drawdown": f"{max_drawdown * 100:.2f}%"
        }