import os
import pandas as pd
import yfinance as yf

# On AWS Lambda the project dir is read-only; only /tmp is writable.
# AWS sets AWS_LAMBDA_FUNCTION_NAME automatically, so we auto-switch there,
# while local runs keep using ./data. Override explicitly with the DATA_DIR env var.
DATA_DIR = os.getenv(
    "DATA_DIR",
    "/tmp/data" if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else "data",
)

def fetch_data(ticker, start="2020-01-01", end="2026-03-30", force_download=False):
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"{DATA_DIR}/{ticker}.csv"
    
    needs_update = False
    requested_end_date = pd.to_datetime(end)
    
    # 1. THE STALE DATA DETECTOR
    if os.path.exists(filename) and not force_download:
        # Quickly peek at the file to see how old it is
        df_temp = pd.read_csv(filename, index_col=0, parse_dates=True)
        last_cached_date = df_temp.index[-1]
        
        # If you ask for Sept 2026, but the cache stops at March 2026...
        if requested_end_date > last_cached_date:
            print(f"🔄 Cache for {ticker} is stale (stops at {last_cached_date.date()}). Auto-updating...")
            needs_update = True
            
    # 2. THE DOWNLOAD TRIGGER (Runs if missing, forced, or stale!)
    if not os.path.exists(filename) or force_download or needs_update:
        print(f"🌐 Downloading MASTER historical data for {ticker}...")
        try:
            data = yf.download(ticker, period="max", auto_adjust=True)
            
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)
                
            data.index.name = "Date"
            data.to_csv(filename)
            print(f"✅ Master cache built for {ticker} ({len(data)} rows).")
            
        except Exception as e:
            print(f"❌ Error fetching data for {ticker}: {e}")
            if not os.path.exists(filename):
                return pd.DataFrame()
            print(f"⚠️ Falling back to stale local data...")

    # 3. LOAD AND SLICE
    print(f"📁 Loading data for {ticker}...")
    df = pd.read_csv(filename, index_col=0, parse_dates=True)
    
    start_dt = pd.to_datetime(start)
    
    df_sliced = df.loc[start_dt:requested_end_date]
    
    if df_sliced.empty:
        print(f"⚠️ Warning: Requested date range {start} to {end} not found in cache for {ticker}.")
        
    return df_sliced