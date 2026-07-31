# strategies/ma_rsi_combo.py
import numpy as np
import pandas as pd


def apply_combo_strategy(df, short_window=50, long_window=200, rsi_window=14,
                         overbought=70, oversold=30, stop_loss_pct=-0.15,
                         rsi_buy_threshold=55, sell_on_overbought=False,
                         rsi_sell_threshold=70):
    """
    Combines Moving Average trend-following with RSI momentum.
    Buys dips in an uptrend, sells on trend reversals.

    V5.0 — entry/exit RSI thresholds are parameters (mode-driven), not hardcoded:
      rsi_buy_threshold   : buy when RSI dips below this (default 55 == V4.0).
      sell_on_overbought  : if True, also exit when RSI >= rsi_sell_threshold
                            (default False == V4.0: exit on trend reversal only).
      stop_loss_pct       : signal-level hard stop from entry; pass None to
                            disable it (used once stops consolidate onto the
                            broker trailing stop). Default -0.15 == V4.0.

    `overbought` / `oversold` are DEPRECATED no-ops, kept in place so legacy
    positional and **profile callers don't break. They are superseded by
    rsi_buy_threshold / rsi_sell_threshold and will be removed in a later cleanup.
    """
    if isinstance(df["Close"], pd.DataFrame):
        close_prices = df["Close"].iloc[:, 0]
    else:
        close_prices = df["Close"]

    # --- 1. MOVING AVERAGES ---
    df["MA_short"] = close_prices.rolling(window=short_window).mean()
    df["MA_long"] = close_prices.rolling(window=long_window).mean()

    # --- 2. RSI (with div-by-zero fix) ---
    delta = close_prices.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(com=(rsi_window - 1), min_periods=rsi_window).mean()
    avg_loss = loss.ewm(com=(rsi_window - 1), min_periods=rsi_window).mean()
    rs = np.where(avg_loss == 0, 0, avg_gain / avg_loss)
    df["RSI"] = np.where(avg_loss == 0, 100, 100 - (100 / (1 + rs)))

    # --- 3. COMBO SIGNALS ---
    df["Signal"] = np.nan
    # BUY: macro uptrend AND RSI dipped below the (mode-driven) buy threshold.
    buy_condition = (df["MA_short"] > df["MA_long"]) & (df["RSI"] < rsi_buy_threshold)
    df.loc[buy_condition, "Signal"] = 1
    # SELL: macro trend reverses (MA cross-down).
    sell_condition = (df["MA_short"] < df["MA_long"])
    df.loc[sell_condition, "Signal"] = 0
    # Optional take-profit: exit when RSI runs hot (Aggressive mode only).
    if sell_on_overbought:
        df.loc[df["RSI"] >= rsi_sell_threshold, "Signal"] = 0
    # Forward-fill: hold the position between a buy and the next exit.
    df["Signal"] = df["Signal"].ffill().fillna(0)

    # --- 4. SIGNAL-LEVEL HARD STOP (optional; None disables) ---
    if stop_loss_pct is not None:
        buy_triggers = (df["Signal"] == 1) & (df["Signal"].shift(1) != 1)
        df["Entry_Price"] = np.nan
        df.loc[buy_triggers, "Entry_Price"] = close_prices
        df["Entry_Price"] = df["Entry_Price"].ffill()
        df["Trade_Return"] = (close_prices - df["Entry_Price"]) / df["Entry_Price"]
        stop_loss_hit = (df["Signal"] == 1) & (df["Trade_Return"] <= stop_loss_pct)
        df.loc[stop_loss_hit, "Signal"] = 0
        df = df.drop(columns=["Entry_Price", "Trade_Return"])

    return df
