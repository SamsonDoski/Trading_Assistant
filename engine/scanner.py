from datetime import datetime, timedelta
# Importing your existing tools
from utils.alpaca_data import fetch_data  # was: from utils.data_loader import fetch_data
from strategies.ma_rsi_combo import apply_combo_strategy

class StrategyScanner:
    def __init__(self):
        pass

    def get_signals(self, ticker, short_ma, long_ma, rsi_period):
        """
        Fetches historical data and calculates the live moving average 
        and RSI signals for a specific asset.
        """
        # The Calendar Buffer Fix
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=(long_ma * 2) + 365)).strftime("%Y-%m-%d")
        
        df = fetch_data(ticker, start_date, end_date)
        
        if df.empty:
            return None
            
        # Calculate the indicators
        df_signal = apply_combo_strategy(df, short_window=short_ma, long_window=long_ma, rsi_window=rsi_period)
        
        # Extract the exact data points the controller needs
        signal_data = {
            'latest_signal': df_signal.iloc[-2]['Signal'],
            'previous_signal': df_signal.iloc[-3]['Signal'],
            'current_price': df_signal.iloc[-2]['Close'],
            'current_rsi': df_signal.iloc[-2]['RSI']
        }
        
        return signal_data