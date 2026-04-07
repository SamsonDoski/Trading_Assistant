import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

load_dotenv()
trading_client = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)

# Define the Order: Buy 1 Share of NVDA at Market Price
market_order_data = MarketOrderRequest(
    symbol="NVDA",
    notional=5000,  # Buy $5000 worth of NVDA
    side=OrderSide.BUY,
    time_in_force=TimeInForce.DAY
)

# Submit the order
order = trading_client.submit_order(order_data=market_order_data)
print(f"✅ Order Submitted! ID: {order.id}")
print(f"✅ Notional Order Submitted for $5,000 of NVDA.")
print(f"Status: {order.status}")