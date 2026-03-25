# strategies/combo.py
import numpy as np
import pandas as pd

def apply_combo_strategy(df, short_window=50, long_window=200, rsi_window=14, overbought=70, oversold=30, stop_loss_pct=-0.08):
    """
    Combines Moving Average trend-following with RSI momentum.
    Buys dips in an uptrend, sells on trend reversals.
    """
    # Force "Close" to be a 1D Series safely
    if isinstance(df["Close"], pd.DataFrame):
        close_prices = df["Close"].iloc[:, 0]
    else:
        close_prices = df["Close"]

    # --- 1. MOVING AVERAGES ---
    df["MA_short"] = close_prices.rolling(window=short_window).mean()
    df["MA_long"] = close_prices.rolling(window=long_window).mean()

    # --- 2. THE RSI MATH (WITH DIV-BY-ZERO FIX) ---
    delta = close_prices.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(com=(rsi_window - 1), min_periods=rsi_window).mean()
    avg_loss = loss.ewm(com=(rsi_window - 1), min_periods=rsi_window).mean()
    
    # Safely handle division by zero
    rs = np.where(avg_loss == 0, 0, avg_gain / avg_loss)
    df["RSI"] = np.where(avg_loss == 0, 100, 100 - (100 / (1 + rs)))

    # --- 3. COMBO SIGNALS (WITH MEMORY FIX) ---
    df["Signal"] = np.nan  # Step 1: Initialize with blanks so it Remembers!
    
    # BUY: We are in a macro uptrend AND the stock just dipped (Using a looser < 55 rule for uptrends)
    buy_condition = (df["MA_short"] > df["MA_long"]) & (df["RSI"] < 55)
    df.loc[buy_condition, "Signal"] = 1
    
    # SELL: The macro trend dies. (We do NOT sell just because RSI is overbought)
    sell_condition = (df["MA_short"] < df["MA_long"])
    df.loc[sell_condition, "Signal"] = 0

    # Step 2: Forward fill the blanks! This tells the bot to HOLD the stock while RSI > 55.
    df["Signal"] = df["Signal"].ffill().fillna(0)

    # --- 4. STOP-LOSS ---
    buy_triggers = (df["Signal"] == 1) & (df["Signal"].shift(1) != 1)
    df["Entry_Price"] = np.nan
    df.loc[buy_triggers, "Entry_Price"] = close_prices
    df["Entry_Price"] = df["Entry_Price"].ffill()
    df["Trade_Return"] = (close_prices - df["Entry_Price"]) / df["Entry_Price"]
    
    stop_loss_hit = (df["Signal"] == 1) & (df["Trade_Return"] <= stop_loss_pct)
    df.loc[stop_loss_hit, "Signal"] = 0
    
    df = df.drop(columns=["Entry_Price", "Trade_Return"])
    
    return df
