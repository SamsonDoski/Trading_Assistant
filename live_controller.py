import os
import sys
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# Import our local tools
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from utils.profile_manager import load_profiles, is_stale
from utils.data_loader import fetch_data
from strategies.ma_rsi_combo import apply_combo_strategy

# Load environment variables
load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# Initialize Alpaca (paper=True keeps us safe)
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)

# 💰 Risk Management: How much cash to allocate per trade
NOTIONAL_ALLOCATION = 5000.00 

def run_live_pipeline():
    print("🤖 V3.0 Live Controller Initialized...")
    profiles = load_profiles()
    
    # Get current positions from Alpaca so we don't double-buy
    try:
        open_positions = {pos.symbol: pos for pos in trading_client.get_all_positions()}
    except Exception as e:
        print(f"❌ Failed to connect to Alpaca: {e}")
        return

    for ticker, rules in profiles.items():
        print(f"\n--- Processing {ticker} ---")
        
        # 1. State Check
        if is_stale(ticker):
            print(f"⚠️ {ticker} is stale. Skipping until Researcher updates it.")
            continue
            
        short_ma = rules["best_short_window"]
        long_ma = rules["best_long_window"]
        rsi_period = rules.get("rsi_period", 14)
        
        print(f"✅ Active Profile: {short_ma}/{long_ma} MA. Fetching live data...")
        
        # 2. Fetch enough data to calculate the Long MA (plus a 50-day buffer)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=long_ma + 50)).strftime("%Y-%m-%d")
        
        df = fetch_data(ticker, start_date, end_date)
        if df.empty:
            print(f"❌ Failed to fetch data for {ticker}.")
            continue
            
        # 3. Calculate Live Strategy Signals
        df_signal = apply_combo_strategy(
            df, short_window=short_ma, long_window=long_ma, rsi_window=rsi_period
        )
        
        # Look at the absolute last row of data (Today)
        latest_signal = df_signal.iloc[-1]['Signal']
        current_price = df_signal.iloc[-1]['Close']
        print(f"📊 Current Price: ${current_price:.2f} | Latest Signal: {latest_signal}")
        
        # 4. Execution Switchboard
        already_owned = ticker in open_positions
        
        if latest_signal == 1 and not already_owned:
            msg = f"🚀 BUY SIGNAL! Executed ${NOTIONAL_ALLOCATION} buy for **{ticker}** at ${current_price:.2f}"
            print(msg)
            # print(f"🚀 BUY SIGNAL! Executing ${NOTIONAL_ALLOCATION} notional buy for {ticker}...")
            order_data = MarketOrderRequest(
                symbol=ticker,
                notional=NOTIONAL_ALLOCATION,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            )
            trading_client.submit_order(order_data=order_data)
            print("✅ Buy order submitted successfully.")
            send_notification(msg)
            
        elif latest_signal == 0 and already_owned:
            msg = f"🛑 SELL SIGNAL! Liquidating position for **{ticker}**"
            print(msg)
            trading_client.close_position(ticker)
            print("✅ Sell order submitted successfully.")
            send_notification(msg)

        elif latest_signal == 1 and already_owned:
            print("⏳ We already own this stock. Holding position.")
            
        elif latest_signal == 0 and not already_owned:
            print("⏳ Waiting for a buy signal.")
            


def send_notification(message):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_url:
        payload = {"content": f"🤖 **Trading Update:** {message}"}
        requests.post(webhook_url, json=payload)

if __name__ == "__main__":
    run_live_pipeline()

