# strategies/rsi.py
import numpy as np
import pandas as pd

def apply_rsi_strategy(df, rsi_window=14, overbought=70, oversold=30, stop_loss_pct=-0.08):
    """
    Calculates the Relative Strength Index (RSI) and generates buy/sell signals.
    """
    if isinstance(df["Close"], pd.DataFrame):
        close_prices = df["Close"].iloc[:, 0]
    else:
        close_prices = df["Close"]

    # --- 1. THE RSI MATH ---
    delta = close_prices.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)

    avg_gain = gain.ewm(com=(rsi_window - 1), min_periods=rsi_window).mean()
    avg_loss = loss.ewm(com=(rsi_window - 1), min_periods=rsi_window).mean()

    # PRO-TIP: Handle division by zero if a stock literally never has a red day
    rs = np.where(avg_loss == 0, 0, avg_gain / avg_loss)
    df["RSI"] = np.where(avg_loss == 0, 100, 100 - (100 / (1 + rs)))

    # --- 2. THE RSI SIGNALS (FIXED STATE MANAGEMENT) ---
    df["Signal"] = np.nan  # Step 1: Initialize with Blanks instead of 0
    
    # Step 2: Set the exact trigger points
    df.loc[df["RSI"] < oversold, "Signal"] = 1   # BUY
    df.loc[df["RSI"] > overbought, "Signal"] = 0  # SELL
    
    # Step 3: Forward fill the blanks so it HOLDS the position between 30 and 70!
    df["Signal"] = df["Signal"].ffill().fillna(0)

    # --- 3. THE STOP-LOSS LOGIC ---
    buy_triggers = (df["Signal"] == 1) & (df["Signal"].shift(1) != 1)
    df["Entry_Price"] = np.nan
    df.loc[buy_triggers, "Entry_Price"] = close_prices
    df["Entry_Price"] = df["Entry_Price"].ffill()
    df["Trade_Return"] = (close_prices - df["Entry_Price"]) / df["Entry_Price"]
    
    stop_loss_hit = (df["Signal"] == 1) & (df["Trade_Return"] <= stop_loss_pct)
    df.loc[stop_loss_hit, "Signal"] = 0
    
    df = df.drop(columns=["Entry_Price", "Trade_Return"])
    
    return df