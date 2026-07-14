import os
from datetime import datetime

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment, DataFeed

_client = None


def _get_client():
    """Lazy singleton so we don't rebuild the client per ticker."""
    global _client
    if _client is None:
        _client = StockHistoricalDataClient(
            os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
        )
    return _client


def fetch_data(ticker, start="2016-01-01", end=None, force_download=False):
    """Alpaca daily bars — split/dividend-adjusted so the series matches how
    Alpaca reports your positions. Drop-in replacement for the yfinance loader:
    same (ticker, start, end) signature, returns a DatetimeIndex DataFrame with
    a 'Close' column (empty DataFrame on failure, so the scanner degrades cleanly).
    `force_download` is accepted for signature parity and ignored (no cache)."""
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Day,
        start=pd.to_datetime(start),
        end=pd.to_datetime(end),
        adjustment=Adjustment.ALL,   # split + dividend adjusted -> matches your positions
        feed=DataFeed.IEX,           # free-tier feed
    )

    try:
        bars = _get_client().get_stock_bars(request)
    except Exception as e:
        print(f"❌ Alpaca data fetch failed for {ticker}: {e}")
        return pd.DataFrame()

    df = bars.df
    if df is None or df.empty:
        print(f"⚠️ No Alpaca data for {ticker} in range {start} → {end}.")
        return pd.DataFrame()

    # bars.df is a MultiIndex (symbol, timestamp); reduce to the single symbol
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(ticker, level="symbol")

    # normalize to the yfinance loader's shape so apply_combo_strategy is happy
    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    })
    df.index = pd.to_datetime(df.index).tz_localize(None)  # drop tz to match yfinance
    df.index.name = "Date"
    print(f"📡 Alpaca: loaded {len(df)} daily bars for {ticker}.")
    return df