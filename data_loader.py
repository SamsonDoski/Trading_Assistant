# utils/data_loader.py
import os
import pandas as pd
import yfinance as yf

DATA_DIR = "data"

#fetching data with default parameters satrt and end
def fetch_data(ticker, start="2020-01-01", end="2025-08-12"):
    filename = f"{DATA_DIR}/{ticker}.csv"
    
    # If file exists, load from CSV
    '''
    if os.path.exists(filename):
        print(f"Loading cached data for {ticker}")
        return pd.read_csv(filename, index_col=0, parse_dates=True, date_format="%Y-%m-%d")
        '''
    
    # Otherwise, download from yfinance
    print(f"Downloading data for {ticker}")
    # yfinance downloads data, if error, print error
    try:
        data = yf.download(ticker, start=start, end=end, auto_adjust=True)
        data.index.name = "Date"
        data.to_csv(filename)
        print(f"Fetched {len(data)} rows. Last date: {data.index[-1].date()}")
        return data
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        print(f"Loading archived cached data for {ticker}")
        return pd.read_csv(filename, index_col=0, parse_dates=True, date_format="%Y-%m-%d")

   # print(f"Fetched {len(data)} rows. Last date: {data.index[-1].date()}")
