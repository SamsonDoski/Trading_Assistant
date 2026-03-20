import pandas as pd
import numpy as np

class BacktestEngine:
    def __init__(self, initial_equity=10000, slippage_bps=2):
        self.initial_equity = initial_equity
        self.slippage = slippage_bps / 10000  # Convert bps to decimal

    def run(self, df):
        df = df.copy()
        df["Position"] = df["Signal"].shift(1).fillna(0)  # Enter after signal
        df["Returns"] = df["Close"].pct_change().fillna(0)
        df["Strategy_Returns"] = df["Returns"] * df["Position"]
        df["Equity"] = (1 + df["Strategy_Returns"]).cumprod() * self.initial_equity
        return df

    def summary(self, df):
        final_equity = df["Equity"].iloc[-1]
        net_profit = final_equity - self.initial_equity
        
        total_return = final_equity / self.initial_equity - 1
        max_drawdown = self._max_drawdown(df["Equity"])
        win_rate = self._win_rate(df)
        
        return {
            "Total Return": f"{total_return:.2%}",
            "Net Profit": f"${net_profit:,.2f}",       # <--- NEW
            "Final Balance": f"${final_equity:,.2f}",  # <--- NEW
            "Max Drawdown": f"{max_drawdown:.2%}",
            "Win Rate": f"{win_rate:.2%}"
        }

    def _max_drawdown(self, equity):
        peak = equity.cummax()
        drawdown = (equity - peak) / peak
        return drawdown.min()

    def _win_rate(self, df):
        trades = df[df["Signal"].diff() != 0]
        wins = trades[trades["Returns"] > 0]
        return len(wins) / len(trades) if len(trades) > 0 else 0
