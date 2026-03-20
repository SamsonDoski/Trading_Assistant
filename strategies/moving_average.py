import numpy as np
import pandas as pd

# function calculates and adds Moving Averages to all rows(days)
# and indicates buy and sell signals
def apply_moving_average_strategy(df, short_window=50, long_window=200, stop_loss_pct=-0.05):
    
    # SAFETY FIX: Force "Close" to be a 1D Series to prevent yfinance MultiIndex bugs
    if isinstance(df["Close"], pd.DataFrame):
        close_prices = df["Close"].iloc[:, 0]
    else:
        close_prices = df["Close"]
        
    # 1. Calculate Moving Averages (using our safe 1D close_prices)
    df["MA_short"] = close_prices.rolling(window=short_window).mean()
    df["MA_long"] = close_prices.rolling(window=long_window).mean()
    
    # 2. Standard MA Crossover Logic
    df["Signal"] = 0
    df.loc[df["MA_short"] > df["MA_long"], "Signal"] = 1  # Buy
    df.loc[df["MA_short"] < df["MA_long"], "Signal"] = 0 # Exit to Cash (DO NOT SHORT)
    
    # --- PHASE 1: STRICT STOP-LOSS LOGIC ---
    
    # Step A: Find the exact days we entered a trade
    buy_triggers = (df["Signal"] == 1) & (df["Signal"].shift(1) != 1)
    
    # Step B: Log the purchase price (Pre-filling with NaN forces it to be a 1D column)
    df["Entry_Price"] = np.nan
    df.loc[buy_triggers, "Entry_Price"] = close_prices
    
    # Step C: Forward-fill that entry price down the column
    df["Entry_Price"] = df["Entry_Price"].ffill()
    
    # Step D: Calculate how much the active trade has gained or lost
    df["Trade_Return"] = (close_prices - df["Entry_Price"]) / df["Entry_Price"]
    
    # Step E: The Override. If we hold AND the return drops below stop loss, SELL!
    stop_loss_hit = (df["Signal"] == 1) & (df["Trade_Return"] <= stop_loss_pct)
    df.loc[stop_loss_hit, "Signal"] = 0 # Exit to Cash
    
    # Clean up temporary columns
    df = df.drop(columns=["Entry_Price", "Trade_Return"])
    
    return df